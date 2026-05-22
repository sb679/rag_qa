#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import Android-captured WeChat article packages into EduRAG artifacts.

This importer reuses the existing WeChat collector output layout so that the
annotation workbench and cleaner can continue to work without structural
changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image

from base import Config, logger
from edu_document_loaders.edu_ocr import get_ocr
from run_wechat_cleaner import WeChatCleaningAgent
from run_wechat_collector import ArticleRecord, WeChatCollectorAgent


def _normalize_account_id(raw: str) -> str:
    text = (raw or "").strip().lower()
    normalized = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            normalized.append(ch)
        else:
            normalized.append("_")
    result = "".join(normalized).strip("_")
    while "__" in result:
        result = result.replace("__", "_")
    return result[:64]


def _safe_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe_lines(lines: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for raw in lines:
        line = " ".join(str(raw or "").split()).strip()
        if len(line) < 2:
            continue
        if line in seen:
            continue
        seen.add(line)
        result.append(line)
    return result


def _resolve_package_dir(package_path: Path) -> Tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    if package_path.is_dir():
        return package_path, None

    if package_path.suffix.lower() != ".zip":
        raise ValueError("package must be a directory or .zip file")

    temp_dir = tempfile.TemporaryDirectory(prefix="edurag_wechat_mobile_")
    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(temp_dir.name)

    root = Path(temp_dir.name)
    manifest_candidates = sorted(root.glob("**/manifest.json"))
    if not manifest_candidates:
        temp_dir.cleanup()
        raise FileNotFoundError("manifest.json not found inside zip package")
    return manifest_candidates[0].parent, temp_dir


@dataclass
class ImportSummary:
    account_id: str
    article_id: str
    title: str
    source_url: str
    body_length: int
    screenshots: int
    images: int


class MobilePackageImporter:
    def __init__(self, conf: Config):
        self.conf = conf
        self.collector = WeChatCollectorAgent(conf=conf, source_file=conf.WECHAT_SOURCE_FILE)
        self.rapid_ocr = None
        self.paddle_ocr = None

    def _load_manifest(self, package_dir: Path) -> Dict[str, object]:
        manifest_path = package_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
        return _safe_json(manifest_path)

    def _resolve_article_id(self, source_url: str, title: str, captured_at: str) -> str:
        normalized_url = self.collector._normalize_article_url(source_url)
        if normalized_url:
            return self.collector._build_article_id(normalized_url)

        basis = f"{source_url}|{title}|{captured_at}".encode("utf-8")
        return hashlib.md5(basis).hexdigest()[:16]

    def _ocr_image(self, image_path: Path) -> str:
        text = ""
        if self.conf.WECHAT_ENABLE_OCR and self.conf.WECHAT_PADDLE_OCR_ENABLE:
            if self.paddle_ocr is None:
                self.paddle_ocr = self.collector._get_paddle_ocr()
            if self.paddle_ocr is not None:
                text = self.collector._ocr_with_paddle(self.paddle_ocr, image_path)
                if text:
                    return text

        if self.conf.WECHAT_ENABLE_OCR:
            if self.rapid_ocr is None:
                try:
                    self.rapid_ocr = get_ocr()
                except Exception as exc:
                    logger.warning("RapidOCR init failed for mobile import: %s", exc)
                    self.rapid_ocr = False
            if self.rapid_ocr:
                try:
                    result, _ = self.rapid_ocr(str(image_path))
                    if result:
                        text = "\n".join(str(item[1]).strip() for item in result if len(item) > 1).strip()
                except Exception as exc:
                    logger.warning("RapidOCR failed for mobile import path=%s err=%s", image_path, exc)
        return text

    def _merge_body_text(self, package_dir: Path, manifest: Dict[str, object]) -> Tuple[str, List[Dict[str, object]]]:
        screenshots = manifest.get("screenshots", []) if isinstance(manifest.get("screenshots", []), list) else []
        screenshot_items: List[Dict[str, object]] = []
        merged_lines: List[str] = []

        explicit_body = str(manifest.get("body_text", "") or "").strip()
        if explicit_body:
            merged_lines.extend(explicit_body.splitlines())

        for item in screenshots:
            if not isinstance(item, dict):
                continue
            rel_path = str(item.get("path", "")).strip()
            if not rel_path:
                continue
            image_path = (package_dir / rel_path).resolve()
            if not image_path.exists():
                continue

            ui_text = str(item.get("ui_text", "") or "").strip()
            ocr_text = self._ocr_image(image_path)
            screenshot_items.append(
                {
                    "path": image_path,
                    "ui_text": ui_text,
                    "ocr_text": ocr_text,
                    "step": int(item.get("step", 0) or 0),
                }
            )

            if ui_text:
                merged_lines.extend(ui_text.splitlines())
            if ocr_text:
                merged_lines.extend(ocr_text.splitlines())

        return "\n".join(_dedupe_lines(merged_lines)), screenshot_items

    def _build_image_items(
        self,
        package_dir: Path,
        manifest: Dict[str, object],
        article_id: str,
        target_image_dir: Path,
        dry_run: bool,
    ) -> List[Dict[str, object]]:
        image_entries = manifest.get("images", []) if isinstance(manifest.get("images", []), list) else []
        items: List[Dict[str, object]] = []
        target_image_dir.mkdir(parents=True, exist_ok=True)

        for index, raw_item in enumerate(image_entries, start=1):
            if not isinstance(raw_item, dict):
                continue
            rel_path = str(raw_item.get("path", "")).strip()
            if not rel_path:
                continue

            source_path = (package_dir / rel_path).resolve()
            if not source_path.exists():
                continue

            ext = source_path.suffix.lower() or ".png"
            dest_path = target_image_dir / f"{index:03d}{ext}"
            if not dry_run:
                shutil.copy2(source_path, dest_path)

            width = 0
            height = 0
            entropy = 0.0
            size = int(source_path.stat().st_size)
            try:
                with Image.open(source_path) as image_obj:
                    width, height = image_obj.size
                    entropy = float(image_obj.convert("L").entropy() or 0.0)
            except Exception:
                width = 0
                height = 0
                entropy = 0.0

            ocr_text = self._ocr_image(source_path)
            ocr_char_count = len("".join((ocr_text or "").split()))
            image_id = hashlib.md5(f"{article_id}:{index}:{dest_path.name}".encode("utf-8")).hexdigest()[:12]
            items.append(
                {
                    "image_id": image_id,
                    "url": str(raw_item.get("source_url", "") or "").strip(),
                    "local_path": str(dest_path if not dry_run else source_path),
                    "ocr_text": ocr_text,
                    "ocr_char_count": ocr_char_count,
                    "width": width,
                    "height": height,
                    "image_size_bytes": size,
                    "image_entropy": round(entropy, 4),
                    "heuristic_score": 0,
                    "api_priority": 0,
                    "index_reasons": ["mobile_import"],
                    "indexable": bool(raw_item.get("indexable", False)),
                    "decorative_candidate": not bool(raw_item.get("indexable", False)),
                    "api_summary": str(raw_item.get("api_summary", "") or "").strip(),
                    "api_informative": bool(raw_item.get("api_informative", False)),
                }
            )
        return items

    def _write_supporting_capture_files(
        self,
        docs_dir: Path,
        article_id: str,
        manifest: Dict[str, object],
        screenshot_items: List[Dict[str, object]],
    ) -> None:
        sidecar_json_path = docs_dir / f"{article_id}.mobile_capture.json"
        sidecar_md_path = docs_dir / f"{article_id}.mobile_capture.md"

        payload = {
            "manifest": manifest,
            "screenshots": [
                {
                    "path": str(item.get("path", "")),
                    "step": int(item.get("step", 0) or 0),
                    "ui_text": str(item.get("ui_text", "")),
                    "ocr_text": str(item.get("ocr_text", "")),
                }
                for item in screenshot_items
            ],
        }
        sidecar_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        lines: List[str] = []
        lines.append(f"# Mobile Capture - {article_id}")
        lines.append("")
        lines.append(f"- capture_type: {manifest.get('capture_type', '')}")
        lines.append(f"- source_url: {manifest.get('source_url', '')}")
        lines.append(f"- screenshot_count: {len(screenshot_items)}")
        lines.append("")
        for item in screenshot_items:
            lines.append(f"## Step {item.get('step', 0)}")
            lines.append("")
            lines.append(f"- path: {item.get('path', '')}")
            ui_text = str(item.get("ui_text", "")).strip()
            ocr_text = str(item.get("ocr_text", "")).strip()
            if ui_text:
                lines.append("### UI Text")
                lines.append("")
                lines.append(ui_text)
                lines.append("")
            if ocr_text:
                lines.append("### OCR Text")
                lines.append("")
                lines.append(ocr_text)
                lines.append("")
        sidecar_md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def import_package(
        self,
        package: Path,
        account_id_override: str,
        display_name_override: str,
        dry_run: bool,
        clean: bool,
        ingest: bool,
        force: bool,
    ) -> ImportSummary:
        package_dir, temp_dir = _resolve_package_dir(package)
        try:
            manifest = self._load_manifest(package_dir)
            account_id = _normalize_account_id(account_id_override or str(manifest.get("account_id", "") or ""))
            if not account_id:
                raise ValueError("account_id is missing in manifest and not provided via CLI")

            display_name = (display_name_override or str(manifest.get("display_name", "") or account_id)).strip() or account_id
            source_url = str(manifest.get("source_url", "") or "").strip()
            title = str(manifest.get("title", "") or "").strip() or "untitled"
            author = str(manifest.get("author", "") or "").strip() or "unknown"
            published_at = str(manifest.get("published_at", "") or "").strip() or None
            captured_at = str(manifest.get("captured_at", "") or "").strip()
            article_id = self._resolve_article_id(source_url=source_url, title=title, captured_at=captured_at)

            account_dir = Path(self.conf.WECHAT_OUTPUT_DIR).resolve() / account_id
            docs_dir = account_dir / "docs"
            meta_dir = account_dir / "meta"
            image_dir = account_dir / "images"
            article_meta_path = meta_dir / f"{article_id}.json"

            if article_meta_path.exists() and not force:
                raise FileExistsError(f"article already exists: {article_meta_path}")

            docs_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            image_dir.mkdir(parents=True, exist_ok=True)

            body_text, screenshot_items = self._merge_body_text(package_dir, manifest)
            image_items = self._build_image_items(
                package_dir=package_dir,
                manifest=manifest,
                article_id=article_id,
                target_image_dir=image_dir / article_id,
                dry_run=dry_run,
            )

            structured_data = self.collector._build_text_structure(
                title=title,
                author=author,
                published_at=published_at,
                body_text=body_text,
            )
            quality = self.collector._build_quality(body_text=body_text, image_items=image_items)

            record = ArticleRecord(
                article_id=article_id,
                account_id=account_id,
                url=source_url or f"wechat-mobile://{account_id}/{article_id}",
                title=title,
                author=author,
                published_at=published_at,
                body_text=body_text,
                tags=[tag for tag in manifest.get("tags", []) if str(tag).strip()] if isinstance(manifest.get("tags", []), list) else [],
                image_items=image_items,
                video_items=[],
                engagement={
                    "read_num": None,
                    "like_num": None,
                    "share_count": None,
                    "comment_count": None,
                },
                comments={
                    "available": False,
                    "count": None,
                    "items": [],
                    "note": "Imported from Android mobile capture package.",
                },
                quality=quality,
                structured_data={
                    **structured_data,
                    "mobile_capture": {
                        "capture_type": manifest.get("capture_type", ""),
                        "display_name": display_name,
                        "screenshot_count": len(screenshot_items),
                    },
                },
            )

            if not dry_run:
                self.collector._write_article_files(record=record, docs_dir=docs_dir, meta_dir=meta_dir)
                self._write_supporting_capture_files(
                    docs_dir=docs_dir,
                    article_id=article_id,
                    manifest=manifest,
                    screenshot_items=screenshot_items,
                )
                if clean:
                    cleaner = WeChatCleaningAgent(conf=self.conf)
                    cleaner.run(account_id=account_id, ingest=ingest, dry_run=False, batch_size=300)

            return ImportSummary(
                account_id=account_id,
                article_id=article_id,
                title=title,
                source_url=source_url,
                body_length=len(body_text.strip()),
                screenshots=len(screenshot_items),
                images=len(image_items),
            )
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Android WeChat capture packages into EduRAG")
    parser.add_argument("--package", required=True, help="Capture package directory or .zip file")
    parser.add_argument("--account-id", default="", help="Override manifest account_id")
    parser.add_argument("--display-name", default="", help="Override manifest display_name")
    parser.add_argument("--dry-run", action="store_true", help="Preview import result without writing files")
    parser.add_argument("--clean", action="store_true", help="Run wechat cleaner after import")
    parser.add_argument("--ingest", action="store_true", help="Run vector ingestion together with cleaner")
    parser.add_argument("--force", action="store_true", help="Overwrite existing article meta if article_id already exists")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    conf = Config()
    importer = MobilePackageImporter(conf=conf)
    summary = importer.import_package(
        package=Path(args.package).expanduser().resolve(),
        account_id_override=args.account_id,
        display_name_override=args.display_name,
        dry_run=bool(args.dry_run),
        clean=bool(args.clean),
        ingest=bool(args.ingest),
        force=bool(args.force),
    )

    print(json.dumps({
        "account_id": summary.account_id,
        "article_id": summary.article_id,
        "title": summary.title,
        "source_url": summary.source_url,
        "body_length": summary.body_length,
        "screenshots": summary.screenshots,
        "images": summary.images,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
