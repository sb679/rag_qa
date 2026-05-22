# -*- coding:utf-8 -*-
"""Derive WeChat history-page URL from a public article URL.

Usage:
  python get_wechat_history_url.py --article-url "https://mp.weixin.qq.com/s/..."
"""

from __future__ import annotations

import argparse
import html
import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


def extract_biz_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    biz = (query.get("__biz") or [""])[0]
    return biz.strip()


def extract_biz_from_html(page_text: str) -> str:
    # Common patterns in article page source.
    patterns = [
        r'var\s+biz\s*=\s*"([^"]+)"',
        r'"__biz"\s*:\s*"([^"]+)"',
        r'__biz=([A-Za-z0-9_%+-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    return ""


def extract_name(page_text: str) -> str:
    soup = BeautifulSoup(page_text, "html.parser")
    for selector in ["#js_name", "a.rich_media_meta_nickname", "meta[property='og:site_name']"]:
        node = soup.select_one(selector)
        if node is None:
            continue
        if node.name == "meta":
            content = (node.get("content") or "").strip()
            if content:
                return content
        text = node.get_text(strip=True)
        if text:
            return text
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Get WeChat history page URL from article URL")
    parser.add_argument("--article-url", required=True, help="A WeChat article URL")
    parser.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        help="HTTP User-Agent",
    )
    args = parser.parse_args()

    article_url = args.article_url.strip()
    if not article_url:
        raise ValueError("article_url is empty")

    biz = extract_biz_from_url(article_url)
    page_text = ""

    try:
        resp = requests.get(article_url, headers={"User-Agent": args.user_agent}, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        page_text = html.unescape(resp.text)
    except Exception as exc:
        print(f"warning: fetch article failed: {exc}")

    if not biz and page_text:
        biz = extract_biz_from_html(page_text)

    account_name = extract_name(page_text) if page_text else ""

    if not biz:
        print("failed: cannot derive __biz from this article URL")
        print("hint: open the article in browser and copy the fully expanded URL containing __biz")
        return

    history_url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}#wechat_redirect"

    print("ok")
    print(f"article_url={article_url}")
    if account_name:
        print(f"account_name={account_name}")
    print(f"biz={biz}")
    print(f"history_url={history_url}")


if __name__ == "__main__":
    main()
