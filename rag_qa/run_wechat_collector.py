# -*- coding:utf-8 -*-
"""Collect WeChat public-account articles into local markdown documents.

This script is designed for self-owned accounts and local execution.
It supports per-account crawl frequency, OCR for images, and optional vector ingestion.
"""

from __future__ import annotations

from contextlib import contextmanager
import argparse
import hashlib
import html
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http.cookiejar import LWPCookieJar
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None

from base import Config, logger
from edu_document_loaders.edu_ocr import get_ocr


@dataclass
class AccountConfig:
    account_id: str
    display_name: str
    enabled: bool = True
    frequency_days: int = 30
    window_days: int = 365
    tags: List[str] = field(default_factory=list)
    article_urls: List[str] = field(default_factory=list)
    history_urls: List[str] = field(default_factory=list)
    max_links_from_history: int = 300


@dataclass
class ArticleRecord:
    article_id: str
    account_id: str
    url: str
    title: str
    author: str
    published_at: Optional[str]
    body_text: str
    tags: List[str]
    image_items: List[Dict[str, object]]
    video_items: List[Dict[str, object]]
    engagement: Dict[str, Optional[int]]
    comments: Dict[str, object]
    quality: Dict[str, object]
    structured_data: Dict[str, object] = field(default_factory=dict)


class WeChatCollectorAgent:
    CANONICAL_ARTICLE_QUERY_KEYS = (
        "__biz",
        "mid",
        "idx",
        "sn",
        "chksm",
        "album_id",
    )

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    ]
    PAGE_BLOCK_KEYWORDS = [
        "参数错误",
        "访问过于频繁",
        "环境异常",
        "系统繁忙",
        "操作频繁",
        "请求错误",
        "请在微信客户端打开链接",
    ]
    DECORATIVE_SUMMARY_KEYWORDS = [
        "装饰",
        "图案",
        "贴纸",
        "表情",
        "边框",
        "背景",
        "无具体文字信息",
        "卡通",
        "星星",
    ]
    INFORMATIVE_SUMMARY_KEYWORDS = [
        "活动",
        "会议",
        "表演",
        "比赛",
        "合影",
        "现场",
        "横幅",
        "展演",
        "训练",
        "授课",
    ]

    def __init__(self, conf: Config, source_file: Optional[str] = None):
        self.conf = conf
        self.source_file = Path(source_file or conf.WECHAT_SOURCE_FILE).resolve()
        self.output_dir = Path(conf.WECHAT_OUTPUT_DIR).resolve()
        self.state_file = Path(conf.WECHAT_STATE_FILE).resolve()
        self.timeout = max(5, int(conf.WECHAT_REQUEST_TIMEOUT_SEC))
        self.session = requests.Session()
        self._setup_session()
        self._paddle_ocr = None
        self._proxy_index = 0
        self._proxy_list = self._parse_proxy_pool()
        self._cookie_jar = None
        self._cookie_path = self.output_dir.parent / "cookies.jar"
        self._load_cookie_jar()

    def _load_cookie_jar(self) -> bool:
        self._cookie_jar = LWPCookieJar(str(self._cookie_path))
        self.session.cookies = self._cookie_jar
        if not self._cookie_path.exists():
            return False

        try:
            self._cookie_jar.load(ignore_discard=True, ignore_expires=True)
            return True
        except Exception:
            self._cookie_jar = None
            return False

    def _require_cookie_jar(self) -> None:
        if self._cookie_jar is not None:
            return

        raise FileNotFoundError(
            f"missing reusable cookie session: {self._cookie_path}. "
            "Export cookies from a logged-in browser session and save them as cookies.jar before crawling history pages."
        )

    def _setup_session(self) -> None:
        """Initialize session with default headers and rotate User-Agent if enabled."""
        ua = self.conf.WECHAT_USER_AGENT
        if self.conf.ANTI_CRAWL_USER_AGENT_ROTATION:
            ua = random.choice(self.USER_AGENTS)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://mp.weixin.qq.com/",
        })

    def _parse_proxy_pool(self) -> List[str]:
        """Parse proxy pool from config."""
        pool_str = (self.conf.ANTI_CRAWL_PROXY_POOL or "").strip()
        if not pool_str:
            return []
        return [p.strip() for p in pool_str.split(",") if p.strip()]

    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy from pool (round-robin)."""
        if not self._proxy_list:
            return None
        proxy = self._proxy_list[self._proxy_index]
        self._proxy_index = (self._proxy_index + 1) % len(self._proxy_list)
        return proxy

    def _apply_random_delay(self) -> None:
        """Apply random delay between requests (anti-crawl)."""
        if self.conf.ANTI_CRAWL_MODE in {"low_cost", "medium_cost"}:
            delay = random.uniform(self.conf.ANTI_CRAWL_REQUEST_DELAY_MIN, self.conf.ANTI_CRAWL_REQUEST_DELAY_MAX)
            time.sleep(delay)

    def run(
        self,
        dry_run: bool = False,
        ingest: bool = False,
        write_report: bool = True,
        report_dir: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, object]:
        accounts = self._load_accounts()
        if not accounts:
            raise ValueError(f"No enabled account found in source file: {self.source_file}")

        if any(self._is_history_page_url(url) for account in accounts for url in account.history_urls):
            self._require_cookie_jar()

        state = self._load_state()
        now = datetime.now()

        result = {
            "started_at": now.isoformat(),
            "source_file": str(self.source_file),
            "processed_accounts": 0,
            "processed_articles": 0,
            "new_articles": 0,
            "skipped_accounts": [],
            "failed_articles": [],
            "account_summaries": [],
        }

        for account in accounts:
            if not force and not self._should_run_account(account, state, now):
                result["skipped_accounts"].append(account.account_id)
                continue

            try:
                with self._account_lock(account.account_id):
                    result["processed_accounts"] += 1
                    logger.info("Processing account=%s articles=%s", account.account_id, len(account.article_urls))

                    processed, new_count, failed, account_summary = self._collect_account(account, dry_run=dry_run)
                    result["processed_articles"] += processed
                    result["new_articles"] += new_count
                    result["failed_articles"].extend(failed)
                    result["account_summaries"].append(account_summary)

                    state.setdefault("accounts", {})[account.account_id] = {
                        "last_run_at": now.isoformat(),
                        "last_processed_articles": processed,
                        "last_new_articles": new_count,
                    }
            except TimeoutError:
                result["skipped_accounts"].append(f"{account.account_id} (locked)")
                logger.warning("Skip account=%s because another collector is already running", account.account_id)

        if not dry_run:
            self._write_state(state)

        if ingest and result["new_articles"] > 0 and not dry_run:
            inserted = self._ingest_to_vector_store()
            result["ingested_chunks"] = inserted

        result["finished_at"] = datetime.now().isoformat()

        if write_report:
            report_paths = self._write_run_report(result=result, report_dir=report_dir, dry_run=dry_run)
            result.update(report_paths)

        return result

    def _collect_account(
        self,
        account: AccountConfig,
        dry_run: bool = False,
    ) -> Tuple[int, int, List[Dict[str, str]], Dict[str, object]]:
        account_dir = self.output_dir / account.account_id
        docs_dir = account_dir / "docs"
        meta_dir = account_dir / "meta"
        image_dir = account_dir / "images"

        if not dry_run:
            docs_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            image_dir.mkdir(parents=True, exist_ok=True)

        processed = 0
        new_count = 0
        skipped_time_window = 0
        failed: List[Dict[str, str]] = []
        sample_records: List[Dict[str, object]] = []
        total_image_count = 0
        total_image_ocr_count = 0
        body_pass_count = 0
        ocr_pass_count = 0

        article_urls = self._resolve_account_article_urls(account)
        article_urls = article_urls[: self.conf.WECHAT_MAX_ARTICLES_PER_ACCOUNT]
        existing_source_links = self._load_existing_source_links(account_dir)

        if not article_urls:
            logger.warning("No article urls resolved for account=%s", account.account_id)
            return processed, new_count, failed, {
                "account_id": account.account_id,
                "display_name": account.display_name,
                "resolved_urls": 0,
                "processed_articles": 0,
                "new_articles": 0,
                "skipped_time_window": 0,
                "failed_articles": 0,
                "body_pass_rate": 0.0,
                "ocr_pass_rate": 0.0,
                "image_ocr_coverage": 0.0,
                "samples": [],
            }

        for article_url in article_urls:
            try:
                normalized_url = self._normalize_article_url(article_url)
                if normalized_url and normalized_url in existing_source_links:
                    processed += 1
                    skipped_time_window += 1
                    continue

                article_key = self._build_article_id(normalized_url or article_url)
                if not dry_run and self._article_outputs_exist_for(account_dir, article_key):
                    processed += 1
                    skipped_time_window += 1
                    continue

                record = self._collect_single_article(account, normalized_url or article_url, image_dir)
                processed += 1
                if record is None:
                    skipped_time_window += 1
                    continue

                new_count += 1
                total_image_count += int(record.quality.get("images_total", 0))
                total_image_ocr_count += int(record.quality.get("images_with_ocr", 0))
                body_pass_count += 1 if bool(record.quality.get("body_pass", False)) else 0
                ocr_pass_count += 1 if bool(record.quality.get("ocr_pass", False)) else 0

                if len(sample_records) < 5:
                    sample_records.append(
                        {
                            "title": record.title,
                            "url": record.url,
                            "published_at": record.published_at,
                            "body_length": len((record.body_text or "").strip()),
                            "image_count": len(record.image_items),
                            "video_count": len(record.video_items),
                            "ocr_score": record.quality.get("ocr_score", 0.0),
                        }
                    )

                if not dry_run:
                    self._write_article_files(record, docs_dir, meta_dir)
                    if record.url:
                        existing_source_links.add(self._normalize_article_url(record.url))
            except Exception as exc:
                logger.error("Collect article failed account=%s url=%s err=%s", account.account_id, article_url, exc)
                failed.append({"account_id": account.account_id, "url": article_url, "error": str(exc)})

        denominator = max(new_count, 1)
        summary = {
            "account_id": account.account_id,
            "display_name": account.display_name,
            "resolved_urls": len(article_urls),
            "processed_articles": processed,
            "new_articles": new_count,
            "skipped_time_window": skipped_time_window,
            "failed_articles": len(failed),
            "body_pass_rate": round(body_pass_count / denominator, 4) if new_count > 0 else 0.0,
            "ocr_pass_rate": round(ocr_pass_count / denominator, 4) if new_count > 0 else 0.0,
            "image_ocr_coverage": round(total_image_ocr_count / max(total_image_count, 1), 4) if total_image_count > 0 else 1.0,
            "samples": sample_records,
        }

        return processed, new_count, failed, summary

    @contextmanager
    def _account_lock(self, account_id: str):
        lock_dir = self.output_dir.parent / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"wechat_{account_id}.lock"
        handle = open(lock_path, "a+b")
        try:
            if msvcrt is not None:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    handle.close()
                    raise TimeoutError(f"account_locked:{account_id}")
            yield handle
        finally:
            if msvcrt is not None:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            handle.close()

    @staticmethod
    def _article_outputs_exist_for(account_dir: Path, article_id: str) -> bool:
        docs_dir = account_dir / "docs"
        meta_dir = account_dir / "meta"
        return (
            (meta_dir / f"{article_id}.json").exists()
            and (docs_dir / f"{article_id}.md").exists()
            and (meta_dir / f"{article_id}.image_index.json").exists()
        )

    def _load_existing_source_links(self, account_dir: Path) -> set[str]:
        meta_dir = account_dir / "meta"
        if not meta_dir.exists():
            return set()

        existing: set[str] = set()
        for meta_path in meta_dir.glob("*.json"):
            if meta_path.name.endswith(".image_index.json"):
                continue
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            source_link = str(payload.get("source_link", "") or payload.get("url", "")).strip()
            normalized = self._normalize_article_url(source_link)
            if normalized:
                existing.add(normalized)
        return existing

    def _collect_single_article(
        self,
        account: AccountConfig,
        article_url: str,
        image_dir: Path,
    ) -> Optional[ArticleRecord]:
        parsed: Dict[str, object] = {}
        html = ""
        max_refetch = max(0, int(self.conf.WECHAT_PAGE_GUARD_MAX_REFETCH))
        for attempt in range(max_refetch + 1):
            html = self._fetch_html(article_url)
            parsed = self._parse_article_html(html, article_url)

            blocked, reason = self._is_probably_blocked_page(parsed, html)
            if not blocked:
                break

            # Do not let a blocked page overwrite the last good result.
            if attempt >= max_refetch:
                raise RuntimeError(f"page_quality_guard_blocked: {reason}")

            if self.conf.ANTI_CRAWL_USER_AGENT_ROTATION:
                self.session.headers["User-Agent"] = random.choice(self.USER_AGENTS)

            wait_s = random.uniform(
                max(0.0, self.conf.WECHAT_PAGE_GUARD_RETRY_MIN_WAIT_SEC),
                max(
                    self.conf.WECHAT_PAGE_GUARD_RETRY_MIN_WAIT_SEC,
                    self.conf.WECHAT_PAGE_GUARD_RETRY_MAX_WAIT_SEC,
                ),
            )
            logger.warning(
                "Page quality guard triggered account=%s url=%s attempt=%s/%s reason=%s wait=%.2fs",
                account.account_id,
                article_url,
                attempt + 1,
                max_refetch + 1,
                reason,
                wait_s,
            )
            time.sleep(wait_s)

        if parsed["published_at"] is not None and not self._in_time_window(parsed["published_at"], account.window_days):
            return None

        article_key = self._build_article_id(article_url)
        image_items = self._collect_image_ocr(
            image_urls=parsed["image_urls"],
            account_id=account.account_id,
            article_id=article_key,
            image_dir=image_dir,
            article_title=parsed["title"],
        )

        structured_data = self._build_text_structure(
            title=parsed["title"],
            author=parsed["author"],
            published_at=parsed["published_at"],
            body_text=parsed["body_text"],
        )

        quality = self._build_quality(
            body_text=parsed["body_text"],
            image_items=image_items,
        )

        return ArticleRecord(
            article_id=article_key,
            account_id=account.account_id,
            url=article_url,
            title=parsed["title"],
            author=parsed["author"],
            published_at=parsed["published_at"],
            body_text=parsed["body_text"],
            tags=list(dict.fromkeys(account.tags + parsed["tags"])),
            image_items=image_items,
            video_items=parsed["video_items"],
            engagement=parsed["engagement"],
            comments=parsed["comments"],
            quality=quality,
            structured_data=structured_data,
        )

    def _is_probably_blocked_page(self, parsed: Dict[str, object], html_text: str) -> Tuple[bool, str]:
        if not self.conf.WECHAT_PAGE_QUALITY_GUARD_ENABLE:
            return False, "guard_disabled"

        title = str(parsed.get("title") or "").strip().lower()
        body_text = str(parsed.get("body_text") or "")
        body_len = len(body_text.strip())
        image_count = len(parsed.get("image_urls") or [])

        if title in {"", "untitled"} and body_len < self.conf.WECHAT_PAGE_GUARD_MIN_BODY_CHARS and image_count == 0:
            return True, "untitled_short_body_no_images"

        lowered = f"{body_text}\n{html_text}".lower()
        for keyword in self.PAGE_BLOCK_KEYWORDS:
            if keyword and keyword.lower() in lowered and body_len < (self.conf.WECHAT_PAGE_GUARD_MIN_BODY_CHARS * 2):
                return True, f"blocked_keyword:{keyword}"

        return False, "ok"

    def _fetch_html(self, url: str) -> str:
        """Fetch HTML with anti-crawl features: retry, proxy rotation, random delays."""
        max_retries = self.conf.ANTI_CRAWL_MAX_RETRIES
        backoff_base = self.conf.ANTI_CRAWL_RETRY_BACKOFF_BASE
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                self._apply_random_delay()
                if self.conf.ANTI_CRAWL_USER_AGENT_ROTATION and attempt > 0:
                    ua = random.choice(self.USER_AGENTS)
                    self.session.headers["User-Agent"] = ua

                proxies = None
                if self.conf.ANTI_CRAWL_MODE == "medium_cost":
                    proxy = self._get_next_proxy()
                    if proxy:
                        proxies = {"http": proxy, "https": proxy}

                response = self.session.get(url, timeout=self.timeout, proxies=proxies)
                response.raise_for_status()
                raw_bytes = response.content

                preferred_encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk"]
                for encoding in preferred_encodings:
                    try:
                        return raw_bytes.decode(encoding)
                    except UnicodeDecodeError:
                        continue

                response.encoding = response.apparent_encoding or response.encoding or "utf-8"
                result = response.text
                
                if self._cookie_jar is not None:
                    try:
                        self._cookie_jar.save(ignore_discard=True, ignore_expires=True)
                    except Exception:
                        pass
                
                return result

            except Exception as exc:
                last_exception = exc
                if attempt < max_retries:
                    wait_time = (backoff_base ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Fetch retry attempt=%d/%d url=%s wait_time=%.2fs err=%s",
                        attempt + 1,
                        max_retries + 1,
                        url,
                        wait_time,
                        exc,
                    )
                    time.sleep(wait_time)
                continue

        raise last_exception if last_exception else Exception(f"Failed to fetch {url} after {max_retries + 1} retries")

    def _parse_article_html(self, html: str, article_url: str) -> Dict[str, object]:
        soup = BeautifulSoup(html, "html.parser")

        title = self._first_text(
            soup,
            selectors=["#activity-name", "h1.rich_media_title", "title"],
            default="untitled",
        )
        author = self._first_text(
            soup,
            selectors=["#js_name", "a.rich_media_meta_nickname", "meta[name=author]"],
            default="unknown",
        )
        published_at = self._extract_publish_time(soup, html)

        content_root = soup.select_one("#js_content") or soup.select_one("article") or soup
        for bad in content_root.select("script, style, noscript"):
            bad.extract()

        body_lines = [line.strip() for line in content_root.get_text("\n").splitlines() if line.strip()]
        body_text = "\n".join(body_lines)

        image_urls = self._extract_image_urls(content_root)
        video_items = self._extract_video_items(content_root)
        tags = self._extract_tags(soup, title)

        engagement = self._extract_engagement_metrics(html)
        comments = {
            "available": False,
            "count": engagement.get("comment_count"),
            "items": [],
            "note": "Public page usually does not expose comment details; this field is reserved for authorized data source.",
        }

        return {
            "title": title,
            "author": author,
            "published_at": published_at,
            "body_text": body_text,
            "image_urls": image_urls,
            "video_items": video_items,
            "tags": tags,
            "engagement": engagement,
            "comments": comments,
            "source_link": article_url,
        }

    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: Iterable[str], default: str) -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if node is None:
                continue
            if node.name == "meta":
                content = node.get("content", "").strip()
                if content:
                    return content
            text = node.get_text(strip=True)
            if text:
                return text
        return default

    @staticmethod
    def _extract_publish_time(soup: BeautifulSoup, html: str) -> Optional[str]:
        meta_time = soup.select_one('meta[property="article:published_time"]')
        if meta_time and meta_time.get("content"):
            return meta_time.get("content").strip()

        unix_patterns = [
            r"var\s+ct\s*=\s*\"?(\d{10})\"?",
            r"\"publish_time\"\s*:\s*\"?(\d{10})\"?",
        ]
        for pattern in unix_patterns:
            match = re.search(pattern, html)
            if not match:
                continue
            try:
                ts = int(match.group(1))
                return datetime.fromtimestamp(ts).isoformat()
            except ValueError:
                continue

        text_patterns = [
            r"publish_time\s*=\s*\"([^\"]+)\"",
            r"\"publish_time\"\s*:\s*\"([^\"]+)\"",
        ]
        for pattern in text_patterns:
            match = re.search(pattern, html)
            if match and match.group(1).strip():
                return match.group(1).strip()

        return None

    @staticmethod
    def _extract_image_urls(content_root: BeautifulSoup) -> List[str]:
        urls: List[str] = []
        for image in content_root.select("img"):
            candidate = (image.get("data-src") or image.get("src") or "").strip()
            if not candidate:
                continue
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            if candidate.startswith("/"):
                continue
            urls.append(candidate)

        unique_urls = list(dict.fromkeys(urls))
        return unique_urls

    @staticmethod
    def _extract_video_items(content_root: BeautifulSoup) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []

        for node in content_root.select("video, iframe, mp-common-videos"):
            item = {
                "tag": node.name,
                "src": (node.get("src") or node.get("data-src") or "").strip(),
                "vid": (node.get("vid") or node.get("data-mpvid") or node.get("data-vid") or "").strip(),
            }
            if item["src"].startswith("//"):
                item["src"] = f"https:{item['src']}"
            if item["src"] or item["vid"]:
                items.append(item)

        return items

    def _build_text_structure(
        self,
        title: str,
        author: str,
        published_at: Optional[str],
        body_text: str,
    ) -> Dict[str, object]:
        preview_chars = body_text[: self.conf.WECHAT_TEXT_STRUCT_MAX_CHARS]
        result: Dict[str, object] = {
            "source": "rule",
            "title": title,
            "author": author,
            "published_at": published_at,
            "summary": preview_chars[:220],
            "keywords": [],
            "entities": [],
            "events": [],
        }

        if not self.conf.WECHAT_TEXT_STRUCT_ENABLE:
            return result

        if not self._api_available():
            return result

        prompt = (
            "请将下面公众号文章内容结构化为 JSON，字段包括："
            "summary(一句话)、keywords(数组)、entities(数组，元素含name/type)、events(数组，元素含event/time)。"
            "只输出 JSON，不要输出解释。"
        )
        user_content = (
            f"标题: {title}\n"
            f"作者: {author}\n"
            f"发布时间: {published_at or 'unknown'}\n"
            f"正文:\n{preview_chars}"
        )

        api_resp = self._call_chat_api(
            model=self.conf.WECHAT_TEXT_STRUCT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=700,
            temperature=0.1,
        )
        parsed = self._extract_json_from_text(api_resp or "")
        if parsed:
            parsed["source"] = "api"
            return parsed

        return result

    @staticmethod
    def _extract_tags(soup: BeautifulSoup, title: str) -> List[str]:
        tags: List[str] = []

        for node in soup.select('meta[name="keywords"], meta[property="article:tag"]'):
            content = (node.get("content") or "").strip()
            if not content:
                continue
            for item in re.split(r"[,，;；]", content):
                item = item.strip()
                if item:
                    tags.append(item)

        for token in re.findall(r"#([^#\s]{2,30})", title):
            tags.append(token.strip())

        return list(dict.fromkeys(tags))

    @staticmethod
    def _extract_engagement_metrics(html: str) -> Dict[str, Optional[int]]:
        patterns = {
            "read_num": [r"\"read_num\"\s*:\s*(\d+)", r"var\s+read_num\s*=\s*(\d+)"],
            "like_num": [r"\"like_num\"\s*:\s*(\d+)", r"var\s+like_num\s*=\s*(\d+)"],
            "old_like_num": [r"\"old_like_num\"\s*:\s*(\d+)", r"var\s+old_like_num\s*=\s*(\d+)"],
            "comment_count": [r"\"comment_count\"\s*:\s*(\d+)", r"var\s+comment_count\s*=\s*(\d+)"],
            "share_count": [r"\"share_count\"\s*:\s*(\d+)", r"var\s+share_count\s*=\s*(\d+)"],
        }

        result: Dict[str, Optional[int]] = {}
        for key, key_patterns in patterns.items():
            value: Optional[int] = None
            for pattern in key_patterns:
                match = re.search(pattern, html)
                if match:
                    try:
                        value = int(match.group(1))
                        break
                    except ValueError:
                        continue
            result[key] = value

        return result

    def _collect_image_ocr(
        self,
        image_urls: List[str],
        account_id: str,
        article_id: str,
        image_dir: Path,
        article_title: str,
    ) -> List[Dict[str, object]]:
        if not image_urls:
            return []

        ocr_engine = None
        paddle_ocr = None
        ocr_mode = (self.conf.WECHAT_OCR_ENGINE or "auto").strip().lower()
        if self.conf.WECHAT_ENABLE_OCR:
            if ocr_mode in {"auto", "paddle"} and self.conf.WECHAT_PADDLE_OCR_ENABLE:
                paddle_ocr = self._get_paddle_ocr()
            if paddle_ocr is None and ocr_mode in {"auto", "rapid"}:
                try:
                    ocr_engine = get_ocr()
                except Exception as exc:
                    logger.warning("RapidOCR init failed: %s", exc)

        items: List[Dict[str, object]] = []
        article_image_dir = image_dir / article_id
        article_image_dir.mkdir(parents=True, exist_ok=True)
        image_api_calls = 0

        for index, image_url in enumerate(image_urls, start=1):
            ext = self._guess_extension(image_url)
            filename = f"{index:03d}{ext}"
            local_path = article_image_dir / filename
            ocr_text = ""
            width = 0
            height = 0
            image_size_bytes = 0
            image_entropy = 0.0

            if not local_path.exists():
                try:
                    if self.conf.ANTI_CRAWL_MODE in {"low_cost", "medium_cost"}:
                        time.sleep(random.uniform(0.06, 0.20))
                    image_resp = self.session.get(image_url, timeout=self.timeout)
                    image_resp.raise_for_status()
                    local_path.write_bytes(image_resp.content)
                except Exception as exc:
                    logger.warning("Download image failed url=%s err=%s", image_url, exc)

            if local_path.exists():
                if paddle_ocr is not None:
                    ocr_text = self._ocr_with_paddle(paddle_ocr, local_path)

                if not ocr_text and ocr_engine is not None:
                    try:
                        result, _ = ocr_engine(str(local_path))
                        if result:
                            ocr_text = "\n".join(str(line[1]).strip() for line in result if len(line) > 1).strip()
                    except Exception as exc:
                        logger.warning("RapidOCR failed path=%s err=%s", local_path, exc)

            if local_path.exists():
                try:
                    image_size_bytes = int(local_path.stat().st_size)
                except Exception:
                    image_size_bytes = 0

                try:
                    with Image.open(local_path) as image_obj:
                        width, height = image_obj.size
                        image_entropy = float(image_obj.convert("L").entropy() or 0.0)
                        fmt = (image_obj.format or "").strip().upper()
                    ext_by_format = {
                        "JPEG": ".jpg",
                        "JPG": ".jpg",
                        "PNG": ".png",
                        "WEBP": ".webp",
                        "BMP": ".bmp",
                        "GIF": ".gif",
                    }.get(fmt, "")
                    if ext_by_format and local_path.suffix.lower() != ext_by_format:
                        normalized_path = local_path.with_suffix(ext_by_format)
                        if not normalized_path.exists():
                            local_path.rename(normalized_path)
                        local_path = normalized_path
                except Exception:
                    width, height = 0, 0
                    image_entropy = 0.0

            ocr_char_count = len(re.sub(r"\s+", "", ocr_text or ""))
            pixels = int(width * height) if width and height else 0
            min_side = min(width, height) if width and height else 0
            max_side = max(width, height) if width and height else 0
            aspect = (width / max(height, 1)) if width and height else 0.0

            index_reasons: List[str] = []
            heuristic_score = 0
            if ocr_char_count >= self.conf.WECHAT_OCR_MIN_CHARS_FOR_INDEX:
                heuristic_score += 5
                index_reasons.append("ocr_text_rich")
            if pixels >= 240_000:
                heuristic_score += 2
                index_reasons.append("large_resolution")
            if image_size_bytes >= 60 * 1024:
                heuristic_score += 1
                index_reasons.append("large_file_size")
            if 0.55 <= aspect <= 1.9:
                heuristic_score += 1
                index_reasons.append("balanced_aspect")
            if image_entropy >= 4.0:
                heuristic_score += 1
                index_reasons.append("high_visual_complexity")

            decorative_candidate = (
                ocr_char_count == 0
                and (
                    (width > 0 and height > 0 and max_side <= 220)
                    or (0 < image_size_bytes <= 14 * 1024)
                    or (0 < pixels <= 95_000 and image_entropy <= 2.2)
                )
            )
            if decorative_candidate:
                heuristic_score -= 4
                index_reasons.append("decorative_candidate")

            indexable = (
                ocr_char_count >= self.conf.WECHAT_OCR_MIN_CHARS_FOR_INDEX
                or (ocr_char_count > 0 and min_side >= self.conf.WECHAT_IMAGE_MIN_SIDE_FOR_INDEX)
                or (heuristic_score >= self.conf.WECHAT_IMAGE_INDEX_HEURISTIC_THRESHOLD and not decorative_candidate)
            )
            if indexable and heuristic_score >= self.conf.WECHAT_IMAGE_INDEX_HEURISTIC_THRESHOLD and "heuristic_high_confidence" not in index_reasons:
                index_reasons.append("heuristic_high_confidence")

            if (
                self.conf.WECHAT_IMAGE_HIGH_RECALL_ENABLE
                and not decorative_candidate
                and pixels >= 180_000
                and image_entropy >= 2.6
            ):
                indexable = True
                if "high_recall_photo_candidate" not in index_reasons:
                    index_reasons.append("high_recall_photo_candidate")

            image_id = hashlib.md5(f"{article_id}:{index}:{image_url}".encode("utf-8")).hexdigest()[:12]

            api_summary = ""
            api_informative = False
            api_priority = (heuristic_score * 1000) + pixels + int(image_size_bytes / 10)
            need_api_fallback = (
                self.conf.WECHAT_ENABLE_IMAGE_API_FALLBACK
                and self._api_available()
                and ocr_char_count < self.conf.WECHAT_IMAGE_API_MIN_OCR_CHARS
                and not decorative_candidate
                and heuristic_score >= 1
            )
            need_api_enrich = (
                self.conf.WECHAT_ENABLE_IMAGE_API_FALLBACK
                and self._api_available()
                and self.conf.WECHAT_IMAGE_ENRICH_INDEXABLE_SUMMARY
                and indexable
                and not decorative_candidate
            )

            items.append(
                {
                    "image_id": image_id,
                    "url": image_url,
                    "local_path": str(local_path),
                    "ocr_text": ocr_text,
                    "ocr_char_count": ocr_char_count,
                    "width": width,
                    "height": height,
                    "image_size_bytes": image_size_bytes,
                    "image_entropy": round(image_entropy, 4),
                    "heuristic_score": heuristic_score,
                    "api_priority": api_priority,
                    "need_api_fallback": need_api_fallback,
                    "need_api_enrich": need_api_enrich,
                    "index_reasons": list(dict.fromkeys(index_reasons)),
                    "indexable": indexable,
                    "decorative_candidate": decorative_candidate,
                    "api_summary": api_summary,
                    "api_informative": api_informative,
                }
            )

        # Priority-based API fallback avoids wasting quota on obvious decorative images.
        if self.conf.WECHAT_ENABLE_IMAGE_API_FALLBACK and self._api_available():
            fallback_candidates = [
                item
                for item in items
                if item.get("need_api_fallback", False)
            ]
            enrich_candidates = [
                item
                for item in items
                if item.get("need_api_enrich", False) and not item.get("need_api_fallback", False)
            ]
            fallback_candidates.sort(key=lambda item: int(item.get("api_priority", 0)), reverse=True)
            enrich_candidates.sort(key=lambda item: int(item.get("api_priority", 0)), reverse=True)
            for item in fallback_candidates + enrich_candidates:
                if image_api_calls >= self.conf.WECHAT_IMAGE_API_MAX_CALLS_PER_ARTICLE:
                    break
                api_summary, api_informative = self._image_api_fallback(
                    image_url=str(item.get("url", "")),
                    title=article_title,
                    ocr_text=str(item.get("ocr_text", "")),
                )
                item["api_summary"] = api_summary
                item["api_informative"] = api_informative
                image_api_calls += 1
                if self.conf.WECHAT_IMAGE_API_CALL_INTERVAL_SEC > 0:
                    time.sleep(self.conf.WECHAT_IMAGE_API_CALL_INTERVAL_SEC)

                if self._looks_decorative_from_summary(api_summary) and not item.get("ocr_char_count", 0):
                    item["decorative_candidate"] = True
                    item["indexable"] = False
                    reasons = list(item.get("index_reasons", []))
                    reasons.append("api_decorative")
                    item["index_reasons"] = list(dict.fromkeys(reasons))
                    continue

                if api_informative:
                    item["indexable"] = True
                    reasons = list(item.get("index_reasons", []))
                    reasons.append("api_informative")
                    item["index_reasons"] = list(dict.fromkeys(reasons))
                    continue

                if self._looks_informative_from_summary(api_summary):
                    item["indexable"] = True
                    reasons = list(item.get("index_reasons", []))
                    reasons.append("api_context_signal")
                    item["index_reasons"] = list(dict.fromkeys(reasons))

        return items

    def _looks_decorative_from_summary(self, summary: str) -> bool:
        text = (summary or "").strip().lower()
        if not text:
            return False
        return any(keyword in text for keyword in self.DECORATIVE_SUMMARY_KEYWORDS)

    def _looks_informative_from_summary(self, summary: str) -> bool:
        text = (summary or "").strip().lower()
        if not text:
            return False
        return any(keyword in text for keyword in self.INFORMATIVE_SUMMARY_KEYWORDS)

    def _get_paddle_ocr(self):
        if self._paddle_ocr is not None:
            return self._paddle_ocr

        try:
            from paddleocr import PaddleOCR  # type: ignore

            # Try new API first, then fallback to legacy signature.
            try:
                self._paddle_ocr = PaddleOCR(
                    lang="ch",
                    use_textline_orientation=True,
                )
            except TypeError:
                self._paddle_ocr = PaddleOCR(
                    lang="ch",
                    use_angle_cls=True,
                    show_log=False,
                )
            logger.info("PaddleOCR initialized successfully")
            return self._paddle_ocr
        except Exception as exc:
            logger.warning("PaddleOCR unavailable, fallback to RapidOCR: %s", exc)
            return None

    @staticmethod
    def _ocr_with_paddle(paddle_ocr, image_path: Path) -> str:
        try:
            result = paddle_ocr.ocr(str(image_path), cls=True)
            if not result:
                return ""
            lines: List[str] = []
            for page in result:
                if not page:
                    continue
                for item in page:
                    if len(item) < 2:
                        continue
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and text_info:
                        text_val = str(text_info[0]).strip()
                    else:
                        text_val = str(text_info).strip()
                    if text_val:
                        lines.append(text_val)
            return "\n".join(lines).strip()
        except Exception:
            return ""

    def _image_api_fallback(self, image_url: str, title: str, ocr_text: str) -> Tuple[str, bool]:
        prompt = (
            "请判断这张图片是否包含对检索有价值的信息。"
            "输出 JSON：{summary:字符串,is_informative:布尔}。"
            "如果是表情包/装饰图，is_informative=false。"
        )
        api_resp = self._call_chat_api(
            model=self.conf.WECHAT_IMAGE_API_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"文章标题: {title}\nOCR文本: {ocr_text or '(empty)'}"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            max_tokens=220,
            temperature=0.1,
        )
        parsed = self._extract_json_from_text(api_resp or "")
        if not parsed:
            return "", False

        summary = str(parsed.get("summary", "")).strip()
        informative = bool(parsed.get("is_informative", False))
        return summary, informative

    def _api_available(self) -> bool:
        key = (self.conf.DASHSCOPE_API_KEY or "").strip()
        if not key or key.startswith("demo-key"):
            return False
        return True

    def _call_chat_api(
        self,
        model: str,
        messages: List[Dict[str, object]],
        max_tokens: int,
        temperature: float,
    ) -> Optional[str]:
        if not self._api_available():
            return None

        endpoint = f"{self.conf.DASHSCOPE_BASE_URL.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.conf.DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        }

        attempts = max(1, int(self.conf.ANTI_CRAWL_MAX_RETRIES))
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.post(endpoint, headers=headers, json=payload, timeout=self.conf.WECHAT_API_TIMEOUT_SEC)
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                    wait_s = (self.conf.ANTI_CRAWL_RETRY_BACKOFF_BASE ** (attempt - 1)) + random.uniform(0.0, 0.6)
                    logger.warning(
                        "Chat API transient error status=%s model=%s attempt=%s/%s wait=%.2fs",
                        resp.status_code,
                        model,
                        attempt,
                        attempts,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    continue

                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    return None
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    text_parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
                    return "\n".join(part for part in text_parts if part).strip()
                return str(content)
            except Exception as exc:
                if attempt < attempts:
                    wait_s = (self.conf.ANTI_CRAWL_RETRY_BACKOFF_BASE ** (attempt - 1)) + random.uniform(0.0, 0.6)
                    logger.warning(
                        "Chat API call failed model=%s attempt=%s/%s wait=%.2fs err=%s",
                        model,
                        attempt,
                        attempts,
                        wait_s,
                        exc,
                    )
                    time.sleep(wait_s)
                    continue
                logger.warning("Chat API call failed model=%s err=%s", model, exc)
                return None

        return None

    @staticmethod
    def _extract_json_from_text(text: str) -> Dict[str, object]:
        if not text:
            return {}

        text = text.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        block = match.group(0)
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}

        return {}

    def _build_quality(self, body_text: str, image_items: List[Dict[str, str]]) -> Dict[str, object]:
        body_length = len((body_text or "").strip())
        body_score = min(body_length / 200.0, 1.0)
        body_pass = body_score >= self.conf.WECHAT_BODY_PASS_THRESHOLD

        total_images = len(image_items)
        images_with_ocr = sum(1 for item in image_items if item.get("ocr_text", "").strip())
        ocr_score = 1.0 if total_images == 0 else images_with_ocr / max(total_images, 1)
        ocr_pass = ocr_score >= self.conf.WECHAT_OCR_PASS_THRESHOLD

        return {
            "body_length": body_length,
            "body_score": round(body_score, 4),
            "body_pass": body_pass,
            "ocr_score": round(ocr_score, 4),
            "ocr_pass": ocr_pass,
            "images_total": total_images,
            "images_with_ocr": images_with_ocr,
        }

    def _write_article_files(self, record: ArticleRecord, docs_dir: Path, meta_dir: Path) -> None:
        article_meta_path = meta_dir / f"{record.article_id}.json"
        article_doc_path = docs_dir / f"{record.article_id}.md"
        article_html_path = docs_dir / f"{record.article_id}.html"
        article_image_index_path = meta_dir / f"{record.article_id}.image_index.json"
        article_images_doc_path = docs_dir / f"{record.article_id}.images.md"
        article_image_annotations_path = docs_dir / f"{record.article_id}.image_annotations.json"
        article_image_review_path = docs_dir / f"{record.article_id}.image_review.html"

        payload = {
            "article_id": record.article_id,
            "account_id": record.account_id,
            "url": record.url,
            "title": record.title,
            "author": record.author,
            "published_at": record.published_at,
            "body_text": record.body_text,
            "tags": record.tags,
            "images": record.image_items,
            "videos": record.video_items,
            "engagement": record.engagement,
            "comments": record.comments,
            "quality": record.quality,
            "structured_data": record.structured_data,
            "collected_at": datetime.now().isoformat(),
        }
        article_meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = [
            f"# {record.title}",
            "",
            f"- article_id: {record.article_id}",
            f"- account_id: {record.account_id}",
            f"- source_link: {record.url}",
            f"- published_at: {record.published_at or 'unknown'}",
            f"- author: {record.author}",
            f"- tags: {', '.join(record.tags) if record.tags else 'none'}",
            f"- read_num: {self._safe_int(record.engagement.get('read_num'))}",
            f"- like_num: {self._safe_int(record.engagement.get('like_num'))}",
            f"- share_count: {self._safe_int(record.engagement.get('share_count'))}",
            f"- comment_count: {self._safe_int(record.engagement.get('comment_count'))}",
            "",
            "## Body",
            "",
            record.body_text or "",
            "",
            "## Image OCR",
            "",
        ]

        if not record.image_items:
            md_lines.append("No image found.")
        else:
            for idx, image_item in enumerate(record.image_items, start=1):
                md_lines.append(f"### Image {idx}")
                md_lines.append(f"- url: {image_item.get('url', '')}")
                md_lines.append(f"- local_path: {image_item.get('local_path', '')}")
                md_lines.append("")
                md_lines.append(image_item.get("ocr_text", "") or "(empty)")
                md_lines.append("")

        md_lines.append("## Video Metadata")
        md_lines.append("")
        if not record.video_items:
            md_lines.append("No video found.")
        else:
            for idx, video_item in enumerate(record.video_items, start=1):
                md_lines.append(f"- video_{idx}: tag={video_item.get('tag', '')}, vid={video_item.get('vid', '')}, src={video_item.get('src', '')}")

        md_lines.append("")
        md_lines.append("## Comments")
        md_lines.append("")
        md_lines.append(record.comments.get("note", "No comment data."))

        md_lines.append("")
        md_lines.append("## Structured Data")
        md_lines.append("")
        md_lines.append(json.dumps(record.structured_data, ensure_ascii=False, indent=2))

        article_doc_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

        article_html_path.write_text(self._render_article_preview_html(record, payload), encoding="utf-8")

        existing_annotations = self._load_image_annotations(article_image_annotations_path)
        image_payload_items: List[Dict[str, object]] = []
        for image in record.image_items:
            image_id = str(image.get("image_id", ""))
            ann = existing_annotations.get(image_id, {})
            image_payload_items.append(
                {
                    "image_id": image_id,
                    "indexable": bool(image.get("indexable", False)),
                    "decorative_candidate": bool(image.get("decorative_candidate", False)),
                    "ocr_char_count": int(image.get("ocr_char_count", 0)),
                    "heuristic_score": int(image.get("heuristic_score", 0)),
                    "image_entropy": float(image.get("image_entropy", 0.0)),
                    "index_reasons": image.get("index_reasons", []),
                    "url": image.get("url", ""),
                    "local_path": image.get("local_path", ""),
                    "ocr_text": image.get("ocr_text", ""),
                    "api_summary": image.get("api_summary", ""),
                    "api_informative": bool(image.get("api_informative", False)),
                    "manual_summary": str(ann.get("manual_summary", "")).strip(),
                    "manual_tags": ann.get("manual_tags", []),
                    "manual_notes": str(ann.get("manual_notes", "")).strip(),
                }
            )

        image_index_payload = {
            "article_id": record.article_id,
            "source_link": record.url,
            "generated_at": datetime.now().isoformat(),
            "images_total": len(record.image_items),
            "images_indexable": sum(1 for image in record.image_items if image.get("indexable", False)),
            "images": image_payload_items,
        }
        article_image_index_path.write_text(json.dumps(image_index_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self._write_image_annotation_template(article_image_annotations_path, image_index_payload)
        article_image_review_path.write_text(
            self._render_image_review_html(record.title, image_index_payload, article_image_annotations_path),
            encoding="utf-8",
        )

        image_doc_lines: List[str] = []
        image_doc_lines.append(f"# Images Index - {record.title}")
        image_doc_lines.append("")
        image_doc_lines.append(f"- article_id: {record.article_id}")
        image_doc_lines.append(f"- source_link: {record.url}")
        image_doc_lines.append(f"- indexable_images: {image_index_payload['images_indexable']}/{image_index_payload['images_total']}")
        image_doc_lines.append("")
        image_doc_lines.append("## Indexable Images")
        image_doc_lines.append("")

        indexable_count = 0
        for image in record.image_items:
            if not image.get("indexable", False):
                continue
            indexable_count += 1
            ann = existing_annotations.get(str(image.get("image_id", "")), {})
            image_doc_lines.append(f"### image_id: {image.get('image_id', '')}")
            image_doc_lines.append(f"- url: {image.get('url', '')}")
            image_doc_lines.append(f"- local_path: {image.get('local_path', '')}")
            image_doc_lines.append(f"- api_informative: {image.get('api_informative', False)}")
            image_doc_lines.append(f"- heuristic_score: {image.get('heuristic_score', 0)}")
            image_doc_lines.append(f"- image_entropy: {image.get('image_entropy', 0.0)}")
            image_doc_lines.append(f"- index_reasons: {', '.join(image.get('index_reasons', []))}")
            if ann.get("manual_summary"):
                image_doc_lines.append(f"- manual_summary: {ann.get('manual_summary', '')}")
            manual_tags = ann.get("manual_tags", [])
            if isinstance(manual_tags, list) and manual_tags:
                image_doc_lines.append(f"- manual_tags: {', '.join(str(tag) for tag in manual_tags if str(tag).strip())}")
            if ann.get("manual_notes"):
                image_doc_lines.append(f"- manual_notes: {ann.get('manual_notes', '')}")
            image_doc_lines.append("")
            image_doc_lines.append(image.get("ocr_text", "") or "(empty)")
            if image.get("api_summary"):
                image_doc_lines.append("")
                image_doc_lines.append(f"API summary: {image.get('api_summary')}")
            image_doc_lines.append("")

        if indexable_count == 0:
            image_doc_lines.append("No indexable image found by current OCR/index rules.")

        article_images_doc_path.write_text("\n".join(image_doc_lines).strip() + "\n", encoding="utf-8")

        video_annotation_template_path = docs_dir / f"{record.article_id}.video_notes.md"
        if self.conf.WECHAT_VIDEO_MANUAL_TEMPLATE_ENABLE:
            video_lines: List[str] = []
            video_lines.append(f"# Video Manual Notes - {record.title}")
            video_lines.append("")
            video_lines.append("请为每个视频补充一句话摘要和关键词，便于后续索引。")
            video_lines.append("")
            if not record.video_items:
                video_lines.append("- 无视频，可忽略。")
            else:
                for idx, video in enumerate(record.video_items, start=1):
                    video_lines.append(f"## Video {idx}")
                    video_lines.append(f"- vid: {video.get('vid', '')}")
                    video_lines.append(f"- src: {video.get('src', '')}")
                    video_lines.append("- one_line_summary: ")
                    video_lines.append("- keywords: ")
                    video_lines.append("- people_or_org: ")
                    video_lines.append("- event_time: ")
                    video_lines.append("")
            video_annotation_template_path.write_text("\n".join(video_lines).strip() + "\n", encoding="utf-8")

    @staticmethod
    def _safe_int(value: Optional[int]) -> str:
        return str(value) if value is not None else "unknown"

    @staticmethod
    def _load_image_annotations(annotation_path: Path) -> Dict[str, Dict[str, object]]:
        if not annotation_path.exists():
            return {}
        try:
            payload = json.loads(annotation_path.read_text(encoding="utf-8"))
            items = payload.get("annotations", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                return {}
            result: Dict[str, Dict[str, object]] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                image_id = str(item.get("image_id", "")).strip()
                if not image_id:
                    continue
                result[image_id] = item
            return result
        except Exception:
            return {}

    def _write_image_annotation_template(self, annotation_path: Path, image_index_payload: Dict[str, object]) -> None:
        existing = self._load_image_annotations(annotation_path)
        annotations: List[Dict[str, object]] = []
        for image in image_index_payload.get("images", []):
            if not isinstance(image, dict):
                continue
            if not bool(image.get("indexable", False)):
                continue
            image_id = str(image.get("image_id", "")).strip()
            old = existing.get(image_id, {})
            tags = old.get("manual_tags", [])
            if not isinstance(tags, list):
                tags = []
            annotations.append(
                {
                    "image_id": image_id,
                    "local_path": image.get("local_path", ""),
                    "manual_summary": str(old.get("manual_summary", "")).strip(),
                    "manual_tags": [str(tag).strip() for tag in tags if str(tag).strip()],
                    "manual_notes": str(old.get("manual_notes", "")).strip(),
                    "keep_for_index": bool(old.get("keep_for_index", True)),
                }
            )

        payload = {
            "article_id": image_index_payload.get("article_id", ""),
            "source_link": image_index_payload.get("source_link", ""),
            "updated_at": datetime.now().isoformat(),
            "annotations": annotations,
            "instructions": "编辑 manual_summary/manual_tags/manual_notes。若某图确认为无效图，将 keep_for_index 设为 false。",
        }
        annotation_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _render_image_review_html(title: str, image_index_payload: Dict[str, object], annotation_path: Path) -> str:
        def esc(value: object) -> str:
            return html.escape("" if value is None else str(value))

        cards: List[str] = []
        for image in image_index_payload.get("images", []):
            if not isinstance(image, dict) or not bool(image.get("indexable", False)):
                continue
            reason_list = image.get("index_reasons", [])
            if not isinstance(reason_list, list):
                reason_list = []
            cards.append(
                f"""
                <section class=\"card\">
                    <div class=\"head\">image_id: {esc(image.get('image_id', ''))}</div>
                    <img src=\"{esc(image.get('url', ''))}\" alt=\"{esc(image.get('image_id', ''))}\" loading=\"lazy\" />
                    <div class=\"meta\">local_path: {esc(image.get('local_path', ''))}</div>
                    <div class=\"meta\">heuristic_score: {esc(image.get('heuristic_score', 0))} | entropy: {esc(image.get('image_entropy', 0.0))}</div>
                    <div class=\"meta\">api_informative: {esc(image.get('api_informative', False))}</div>
                    <div class=\"meta\">index_reasons: {esc(', '.join(str(i) for i in reason_list))}</div>
                    <div class=\"meta\">api_summary: {esc(image.get('api_summary', ''))}</div>
                </section>
                """
            )

        return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{esc(title)} - Image Review</title>
    <style>
        body {{ font-family: Arial, Microsoft YaHei, sans-serif; margin: 0; background: #f4f6fb; color: #111827; }}
        .page {{ max-width: 1280px; margin: 0 auto; padding: 18px; }}
        .tip {{ background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 12px; padding: 14px; margin-bottom: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
        .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px; }}
        .head {{ font-weight: 700; margin-bottom: 8px; }}
        img {{ width: 100%; height: auto; border-radius: 10px; border: 1px solid #e5e7eb; }}
        .meta {{ margin-top: 6px; font-size: 13px; color: #374151; word-break: break-all; }}
    </style>
</head>
<body>
    <div class=\"page\">
        <div class=\"tip\">
            <div><strong>独立标注页</strong></div>
            <div>这是一份不依赖 RAG 的本地图片审阅页。你可以先在这里判断“保留/剔除/摘要/标签/备注”，再把自然语言指令交给 <code>annotate_images_nl.py</code>。</div>
            <div><strong>标注文件：</strong>{esc(str(annotation_path))}</div>
        </div>
        <div class=\"grid\">{''.join(cards)}</div>
    </div>
</body>
</html>
"""

    def _load_accounts(self) -> List[AccountConfig]:
        if not self.source_file.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_file}")

        content = json.loads(self.source_file.read_text(encoding="utf-8"))
        raw_accounts = content.get("accounts", [])
        if not isinstance(raw_accounts, list):
            raise ValueError("Invalid source file: 'accounts' must be a list")

        accounts: List[AccountConfig] = []
        for raw in raw_accounts:
            if not isinstance(raw, dict):
                continue
            account = AccountConfig(
                account_id=str(raw.get("account_id", "")).strip(),
                display_name=str(raw.get("display_name", "")).strip() or str(raw.get("account_id", "")).strip(),
                enabled=bool(raw.get("enabled", True)),
                frequency_days=max(1, int(raw.get("frequency_days", self.conf.WECHAT_DEFAULT_FREQUENCY_DAYS))),
                window_days=max(1, int(raw.get("window_days", 365))),
                tags=[str(item).strip() for item in raw.get("tags", []) if str(item).strip()],
                article_urls=[str(item).strip() for item in raw.get("article_urls", []) if str(item).strip()],
                history_urls=[str(item).strip() for item in raw.get("history_urls", []) if str(item).strip()],
                max_links_from_history=max(1, int(raw.get("max_links_from_history", 300))),
            )
            if account.enabled and account.account_id and (account.article_urls or account.history_urls):
                accounts.append(account)

        return accounts

    def _should_run_account(self, account: AccountConfig, state: Dict[str, object], now: datetime) -> bool:
        account_state = state.get("accounts", {}).get(account.account_id, {})
        if not account_state:
            return True

        last_run_at = account_state.get("last_run_at")
        if not last_run_at:
            return True

        try:
            last_run = datetime.fromisoformat(last_run_at)
        except ValueError:
            return True

        return now - last_run >= timedelta(days=account.frequency_days)

    @staticmethod
    def _build_article_id(url: str) -> str:
        parsed = urlparse(url)
        key = f"{parsed.path}?{parsed.query}".strip("?") or url
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _guess_extension(url: str) -> str:
        clean = url.split("?", 1)[0].lower()
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            if clean.endswith(suffix):
                return suffix
        return ".jpg"

    @staticmethod
    def _in_time_window(published_at: str, window_days: int) -> bool:
        candidates = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
        ]

        dt_obj: Optional[datetime] = None
        for fmt in candidates:
            try:
                dt_obj = datetime.strptime(published_at[:19], fmt)
                break
            except ValueError:
                continue

        if dt_obj is None:
            try:
                dt_obj = datetime.fromisoformat(published_at)
            except ValueError:
                return True

        return datetime.now() - dt_obj <= timedelta(days=window_days)

    def _resolve_account_article_urls(self, account: AccountConfig) -> List[str]:
        resolved: List[str] = []

        for url in account.article_urls:
            resolved.extend(self._resolve_wechat_seed_url(url, account.max_links_from_history))

        for history_url in account.history_urls:
            resolved.extend(self._resolve_wechat_seed_url(history_url, account.max_links_from_history))

        deduped = list(dict.fromkeys(resolved))
        logger.info(
            "Resolved article urls account=%s total=%s manual=%s history_pages=%s",
            account.account_id,
            len(deduped),
            len(account.article_urls),
            len(account.history_urls),
        )
        return deduped

    def _resolve_wechat_seed_url(self, url: str, max_links: int) -> List[str]:
        normalized = self._normalize_article_url(url)
        if normalized:
            return [normalized]

        if self._is_history_page_url(url):
            return self._extract_article_urls_from_history_page(history_url=url, max_links=max_links)

        return []

    def _extract_article_urls_from_history_page(self, history_url: str, max_links: int) -> List[str]:
        html_text = self._fetch_html(history_url)
        if self._is_wechat_verification_page(html_text):
            raise RuntimeError(
                "wechat_history_page_verification_required: history page returned a verification page; "
                "open the link in WeChat client or use an authenticated session/cookie"
            )
        unescaped = html.unescape(html_text.replace(r"\/", "/"))

        patterns = [
            r"https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+",
            r"https?://mp\.weixin\.qq\.com/s\?[^\"'<>\s]+",
            r"(?<=\")/s\?__biz=[^\"'<>\s]+",
        ]

        found: List[str] = []
        for pattern in patterns:
            found.extend(re.findall(pattern, unescaped))

        normalized: List[str] = []
        for item in found:
            candidate = item
            if candidate.startswith("/s?"):
                candidate = f"https://mp.weixin.qq.com{candidate}"
            normalized_url = self._normalize_article_url(candidate)
            if normalized_url:
                normalized.append(normalized_url)

        deduped = list(dict.fromkeys(normalized))
        if len(deduped) > max_links:
            deduped = deduped[:max_links]

        logger.info("Extracted %s article urls from history page=%s", len(deduped), history_url)
        return deduped

    @staticmethod
    def _normalize_article_url(url: str) -> str:
        text = (url or "").strip()
        if not text:
            return ""
        if text.startswith("//"):
            text = f"https:{text}"

        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"}:
            return ""
        if parsed.netloc not in {"mp.weixin.qq.com", "weixin.qq.com"}:
            return ""
        if parsed.path not in {"/s", "/s/"} and not parsed.path.startswith("/s/"):
            return ""

        canonical_scheme = "https"
        canonical_netloc = "mp.weixin.qq.com"
        canonical_path = "/s"
        if parsed.path.startswith("/s/"):
            canonical_path = parsed.path.rstrip("/")

        if canonical_path != "/s":
            return urlunparse((canonical_scheme, canonical_netloc, canonical_path, "", "", ""))

        query_items = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=False):
            if key in WeChatCollectorAgent.CANONICAL_ARTICLE_QUERY_KEYS and value:
                query_items.append((key, value))
        query_items.sort()
        canonical_query = urlencode(query_items)
        return urlunparse((canonical_scheme, canonical_netloc, canonical_path, "", canonical_query, ""))

    @staticmethod
    def _is_history_page_url(url: str) -> bool:
        text = (url or "").strip()
        if not text:
            return False
        if text.startswith("//"):
            text = f"https:{text}"

        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc not in {"mp.weixin.qq.com", "weixin.qq.com"}:
            return False

        query = parsed.query.lower()
        path = parsed.path.lower()
        return path.startswith("/mp/profile_ext") or "action=home" in query or "action=list" in query

    @staticmethod
    def _is_wechat_verification_page(html_text: str) -> bool:
        lowered = (html_text or "").lower()
        return "请在微信客户端打开链接" in lowered or "验证" in lowered and "暂无权限查看此页面内容" in lowered

    def _load_state(self) -> Dict[str, object]:
        if not self.state_file.exists():
            return {"accounts": {}}

        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"accounts": {}}

    def _write_state(self, state: Dict[str, object]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_run_report(self, result: Dict[str, object], report_dir: Optional[str], dry_run: bool) -> Dict[str, str]:
        base_dir = Path(report_dir).resolve() if report_dir else (self.output_dir.parent / "reports")
        base_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = base_dir / f"wechat_collect_report_{timestamp}.json"
        md_path = base_dir / f"wechat_collect_report_{timestamp}.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        account_summaries = result.get("account_summaries", [])
        total_samples = sum(len(item.get("samples", [])) for item in account_summaries)

        lines: List[str] = []
        lines.append("# WeChat Collector Report")
        lines.append("")
        lines.append(f"- started_at: {result.get('started_at')}")
        lines.append(f"- finished_at: {result.get('finished_at')}")
        lines.append(f"- source_file: {result.get('source_file')}")
        lines.append(f"- dry_run: {str(dry_run).lower()}")
        lines.append(f"- processed_accounts: {result.get('processed_accounts', 0)}")
        lines.append(f"- processed_articles: {result.get('processed_articles', 0)}")
        lines.append(f"- new_articles: {result.get('new_articles', 0)}")
        lines.append(f"- failed_articles: {len(result.get('failed_articles', []))}")
        lines.append(f"- sampled_articles_in_report: {total_samples}")
        lines.append("")

        lines.append("## Account Summary")
        lines.append("")
        if not account_summaries:
            lines.append("No account processed.")
        else:
            for item in account_summaries:
                lines.append(f"### {item.get('display_name') or item.get('account_id')}")
                lines.append(f"- account_id: {item.get('account_id')}")
                lines.append(f"- resolved_urls: {item.get('resolved_urls', 0)}")
                lines.append(f"- processed_articles: {item.get('processed_articles', 0)}")
                lines.append(f"- new_articles: {item.get('new_articles', 0)}")
                lines.append(f"- skipped_time_window: {item.get('skipped_time_window', 0)}")
                lines.append(f"- failed_articles: {item.get('failed_articles', 0)}")
                lines.append(f"- body_pass_rate: {item.get('body_pass_rate', 0.0)}")
                lines.append(f"- ocr_pass_rate: {item.get('ocr_pass_rate', 0.0)}")
                lines.append(f"- image_ocr_coverage: {item.get('image_ocr_coverage', 0.0)}")
                lines.append("")

                samples = item.get("samples", [])
                if not samples:
                    lines.append("No sampled articles.")
                    lines.append("")
                else:
                    lines.append("Sampled articles:")
                    for sample in samples:
                        lines.append(
                            "- "
                            f"title={sample.get('title', '')}; "
                            f"published_at={sample.get('published_at', 'unknown')}; "
                            f"body_length={sample.get('body_length', 0)}; "
                            f"image_count={sample.get('image_count', 0)}; "
                            f"video_count={sample.get('video_count', 0)}; "
                            f"ocr_score={sample.get('ocr_score', 0.0)}; "
                            f"url={sample.get('url', '')}"
                        )
                    lines.append("")

        failed_articles = result.get("failed_articles", [])
        lines.append("## Failures")
        lines.append("")
        if not failed_articles:
            lines.append("No failed article.")
        else:
            for fail in failed_articles[:100]:
                lines.append(
                    "- "
                    f"account_id={fail.get('account_id', '')}; "
                    f"url={fail.get('url', '')}; "
                    f"error={fail.get('error', '')}"
                )

        md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return {
            "report_json": str(json_path),
            "report_md": str(md_path),
        }

    def _render_article_preview_html(self, record: ArticleRecord, payload: Dict[str, object]) -> str:
                def esc(value: object) -> str:
                        return html.escape("" if value is None else str(value))

                image_blocks: List[str] = []
                for idx, image_item in enumerate(record.image_items, start=1):
                        image_blocks.append(
                                f"""
                                <section class=\"image-card\">
                                    <div class=\"image-title\">Image {idx}</div>
                                    <div class=\"image-url\">image_id: {esc(image_item.get('image_id', ''))}</div>
                                    <div class=\"image-url\">indexable: {esc(image_item.get('indexable', False))} | decorative_candidate: {esc(image_item.get('decorative_candidate', False))}</div>
                                    <div class=\"image-url\">{esc(image_item.get('url', ''))}</div>
                                    <img src=\"{esc(image_item.get('url', ''))}\" alt=\"image {idx}\" loading=\"lazy\" />
                                    <div class=\"ocr-title\">OCR Text</div>
                                    <pre>{esc(image_item.get('ocr_text', '') or '(empty)')}</pre>
                                </section>
                                """
                        )

                if not image_blocks:
                        image_blocks.append("<p class=\"empty\">No image found.</p>")

                body_html = "<br/>".join(esc(line) for line in (record.body_text or "").splitlines())
                tags_html = ", ".join(esc(tag) for tag in record.tags) if record.tags else "none"

                return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{esc(record.title)} - WeChat Preview</title>
    <style>
        body {{ font-family: Arial, Microsoft YaHei, sans-serif; margin: 0; background: #f6f7fb; color: #1f2937; }}
        .page {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
        .hero {{ background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%); color: white; border-radius: 18px; padding: 24px; box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18); }}
        .hero h1 {{ margin: 0 0 12px; font-size: 28px; line-height: 1.3; }}
        .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; }}
        .meta div {{ background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 12px; padding: 12px; }}
        .section {{ margin-top: 20px; background: white; border-radius: 18px; padding: 20px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06); }}
        .section h2 {{ margin-top: 0; font-size: 20px; }}
        .body {{ line-height: 1.9; white-space: normal; font-size: 16px; }}
        .image-card {{ margin: 18px 0; border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px; background: #fff; }}
        .image-card img {{ max-width: 100%; border-radius: 12px; border: 1px solid #e5e7eb; display: block; margin: 10px 0; }}
        .image-title, .ocr-title {{ font-weight: 700; margin-bottom: 8px; }}
        .image-url {{ font-size: 12px; color: #6b7280; word-break: break-all; }}
        pre {{ white-space: pre-wrap; word-break: break-word; background: #f8fafc; border: 1px solid #e5e7eb; padding: 12px; border-radius: 12px; margin: 8px 0 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
        .stat {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px; }}
        .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: .06em; }}
        .value {{ margin-top: 6px; font-size: 16px; font-weight: 700; word-break: break-word; }}
        .empty {{ color: #6b7280; }}
        a {{ color: #2563eb; word-break: break-all; }}
    </style>
</head>
<body>
    <div class=\"page\">
        <header class=\"hero\">
            <h1>{esc(record.title)}</h1>
            <div>{esc(record.author)} · {esc(record.published_at or 'unknown')}</div>
            <div style=\"margin-top:10px;\"><a href=\"{esc(record.url)}\" target=\"_blank\" rel=\"noreferrer\">{esc(record.url)}</a></div>
            <div class=\"meta\">
                <div><div class=\"label\">Article ID</div><div class=\"value\">{esc(record.article_id)}</div></div>
                <div><div class=\"label\">Body Pass</div><div class=\"value\">{esc(payload['quality']['body_pass'])}</div></div>
                <div><div class=\"label\">OCR Pass</div><div class=\"value\">{esc(payload['quality']['ocr_pass'])}</div></div>
                <div><div class=\"label\">Image OCR Coverage</div><div class=\"value\">{esc(payload['quality']['images_with_ocr'])}/{esc(payload['quality']['images_total'])}</div></div>
            </div>
        </header>

        <section class=\"section\">
            <h2>Metadata</h2>
            <div class=\"grid\">
                <div class=\"stat\"><div class=\"label\">Account</div><div class=\"value\">{esc(record.account_id)}</div></div>
                <div class=\"stat\"><div class=\"label\">Tags</div><div class=\"value\">{tags_html}</div></div>
                <div class=\"stat\"><div class=\"label\">Body Length</div><div class=\"value\">{len(record.body_text or '')}</div></div>
                <div class=\"stat\"><div class=\"label\">Images</div><div class=\"value\">{len(record.image_items)}</div></div>
                <div class=\"stat\"><div class=\"label\">Videos</div><div class=\"value\">{len(record.video_items)}</div></div>
            </div>
        </section>

        <section class=\"section\">
            <h2>Body Preview</h2>
            <div class=\"body\">{body_html}</div>
        </section>

        <section class=\"section\">
            <h2>Images and OCR</h2>
            {''.join(image_blocks)}
        </section>

        <section class=\"section\">
            <h2>Videos</h2>
            <pre>{esc(json.dumps(record.video_items, ensure_ascii=False, indent=2))}</pre>
        </section>

        <section class=\"section\">
            <h2>Comments</h2>
            <pre>{esc(json.dumps(record.comments, ensure_ascii=False, indent=2))}</pre>
        </section>
    </div>
</body>
</html>
"""

    def _ingest_to_vector_store(self) -> int:
        from core.document_processor import process_documents
        from core.vector_store import VectorStore

        chunks = process_documents(str(self.output_dir))
        if not chunks:
            logger.warning("No chunk generated, skip vector ingestion.")
            return 0

        vector_store = VectorStore()
        vector_store.add_documents(chunks)
        logger.info("Vector ingestion finished. chunks=%s", len(chunks))
        return len(chunks)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat collector agent (local)")
    parser.add_argument("--source-file", type=str, default=None, help="Path to account source json")
    parser.add_argument("--dry-run", action="store_true", help="Validate and collect in memory without writing files")
    parser.add_argument("--ingest", action="store_true", help="Ingest generated markdown to vector store")
    parser.add_argument("--no-report", action="store_true", help="Disable writing run report files")
    parser.add_argument("--report-dir", type=str, default=None, help="Custom directory for report files")
    parser.add_argument("--force", action="store_true", help="Ignore previous run state and crawl immediately")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    conf = Config()
    agent = WeChatCollectorAgent(conf=conf, source_file=args.source_file)
    report = agent.run(
        dry_run=args.dry_run,
        ingest=args.ingest,
        write_report=not args.no_report,
        report_dir=args.report_dir,
        force=args.force,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
