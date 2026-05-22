# -*- coding: utf-8 -*-
"""Clean and index WeChat crawler artifacts for RAG retrieval.

This agent focuses on post-crawl normalization:
- text cleaning and structured markdown generation
- image/video metadata aggregation for retrieval
- optional ingestion into the existing vector store pipeline

Usage examples:
  python run_wechat_cleaner.py --account-id my_wechat_account
  python run_wechat_cleaner.py --account-id my_wechat_account --ingest
  python run_wechat_cleaner.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from base import Config, logger
from sync_image_annotations import sync_annotations


@dataclass
class CleanResult:
    account_id: str
    article_id: str
    text_doc: Path
    media_doc: Path
    image_count: int
    video_count: int


class WeChatCleaningAgent:
    def __init__(self, conf: Config, source: str = "wechat"):
        self.conf = conf
        self.source = (source or "wechat").strip() or "wechat"
        self.wechat_root = Path(conf.WECHAT_OUTPUT_DIR).resolve()

    @staticmethod
    def _safe_json(path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    @staticmethod
    def _normalize_text(text: str) -> str:
        raw = str(text or "")
        lines = [line.strip() for line in raw.splitlines()]
        noise_patterns = [
            r"^微信扫一扫$",
            r"^关注该公众号$",
            r"^编辑[丨|]",
            r"^图片[丨|]",
            r"^一校[丨|]",
            r"^二校[丨|]",
            r"^终审[丨|]",
        ]

        cleaned: List[str] = []
        for line in lines:
            if not line:
                if cleaned and cleaned[-1] == "":
                    continue
                cleaned.append("")
                continue
            if any(re.search(pattern, line) for pattern in noise_patterns):
                continue
            cleaned.append(line)

        while cleaned and cleaned[0] == "":
            cleaned.pop(0)
        while cleaned and cleaned[-1] == "":
            cleaned.pop()

        return "\n".join(cleaned)

    @staticmethod
    def _merge_image_items(image_index_payload: Dict[str, object], selected_images_payload: Dict[str, object]) -> List[Dict[str, object]]:
        selected = selected_images_payload.get("selected_images", []) if isinstance(selected_images_payload, dict) else []
        if isinstance(selected, list) and selected:
            return [item for item in selected if isinstance(item, dict)]

        images = image_index_payload.get("images", []) if isinstance(image_index_payload, dict) else []
        result: List[Dict[str, object]] = []
        for item in images:
            if not isinstance(item, dict):
                continue
            if bool(item.get("indexable", False)):
                result.append(item)
        return result

    def _build_text_doc(self, meta_payload: Dict[str, object], cleaned_body: str) -> str:
        title = str(meta_payload.get("title", "untitled"))
        tags = meta_payload.get("tags", [])
        tags_text = ", ".join(str(tag) for tag in tags if str(tag).strip()) if isinstance(tags, list) else ""

        lines: List[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"- article_id: {meta_payload.get('article_id', '')}")
        lines.append(f"- account_id: {meta_payload.get('account_id', '')}")
        lines.append(f"- source_link: {meta_payload.get('url', '')}")
        lines.append(f"- published_at: {meta_payload.get('published_at', '')}")
        lines.append(f"- author: {meta_payload.get('author', '')}")
        lines.append(f"- tags: {tags_text or 'none'}")
        lines.append("")
        lines.append("## Cleaned Body")
        lines.append("")
        lines.append(cleaned_body or "(empty)")
        lines.append("")
        return "\n".join(lines)

    def _build_media_doc(
        self,
        meta_payload: Dict[str, object],
        image_items: List[Dict[str, object]],
        video_items: List[Dict[str, object]],
        video_notes_text: str,
    ) -> str:
        lines: List[str] = []
        lines.append(f"# Media Index - {meta_payload.get('title', 'untitled')}")
        lines.append("")
        lines.append(f"- article_id: {meta_payload.get('article_id', '')}")
        lines.append(f"- account_id: {meta_payload.get('account_id', '')}")
        lines.append(f"- source_link: {meta_payload.get('url', '')}")
        lines.append(f"- image_items: {len(image_items)}")
        lines.append(f"- video_items: {len(video_items)}")
        lines.append("")

        lines.append("## Images")
        lines.append("")
        if not image_items:
            lines.append("No indexable image metadata.")
        else:
            for idx, item in enumerate(image_items, start=1):
                scene_annotation_text = str(item.get("scene_annotation_text", "")).strip()
                scene_annotation = item.get("scene_annotation", {}) if isinstance(item.get("scene_annotation", {}), dict) else {}
                if not scene_annotation_text and scene_annotation:
                    ordered_keys = ["活动类型", "事件名称", "时间", "地点", "人物", "身份", "组织", "视觉特征", "来源"]
                    rows = []
                    for key in ordered_keys:
                        value = str(scene_annotation.get(key, "")).strip()
                        if value:
                            rows.append(f"{key}:{value}")
                    scene_annotation_text = "\n".join(rows)

                lines.append(f"### Image {idx}")
                lines.append(f"- image_id: {item.get('image_id', '')}")
                lines.append(f"- local_path: {item.get('local_path', '')}")
                lines.append(f"- source_url: {item.get('url', '')}")
                lines.append(f"- article_source_link: {meta_payload.get('url', '')}")
                lines.append(f"- keep_for_index: {item.get('keep_for_index', item.get('indexable', True))}")
                if scene_annotation_text:
                    lines.append("- annotation_template:")
                    for row in scene_annotation_text.splitlines():
                        lines.append(f"  {row}")
                elif item.get("manual_summary") or item.get("manual_tags") or item.get("manual_notes"):
                    lines.append(f"- manual_summary: {item.get('manual_summary', '')}")
                    tags = item.get("manual_tags", [])
                    tags_text = ", ".join(str(tag) for tag in tags if str(tag).strip()) if isinstance(tags, list) else ""
                    if tags_text:
                        lines.append(f"- manual_tags: {tags_text}")
                    notes = str(item.get("manual_notes", "")).strip()
                    if notes:
                        lines.append(f"- manual_notes: {notes}")
                if item.get("api_summary"):
                    lines.append(f"- api_summary: {item.get('api_summary', '')}")
                lines.append("")

        lines.append("## Videos")
        lines.append("")
        if not video_items:
            lines.append("No video metadata.")
        else:
            for idx, item in enumerate(video_items, start=1):
                lines.append(f"### Video {idx}")
                lines.append(f"- tag: {item.get('tag', '')}")
                lines.append(f"- vid: {item.get('vid', '')}")
                lines.append(f"- src: {item.get('src', '')}")
                lines.append("")

        if video_notes_text.strip():
            lines.append("## Video Notes")
            lines.append("")
            lines.append(video_notes_text.strip())
            lines.append("")

        return "\n".join(lines)

    def _process_article(self, account_id: str, article_meta_path: Path, dry_run: bool = False) -> Optional[CleanResult]:
        article_id = article_meta_path.stem
        account_dir = article_meta_path.parent.parent
        docs_dir = account_dir / "docs"
        meta_dir = account_dir / "meta"

        meta_payload = self._safe_json(article_meta_path, {})
        if not isinstance(meta_payload, dict):
            return None

        image_index_path = meta_dir / f"{article_id}.image_index.json"
        ann_path = docs_dir / f"{article_id}.image_annotations.json"
        selected_images_path = docs_dir / f"{article_id}.selected_images.json"
        video_notes_path = docs_dir / f"{article_id}.video_notes.md"

        if image_index_path.exists() and ann_path.exists():
            try:
                sync_annotations(account_id=account_id, article_id=article_id)
            except Exception as exc:
                logger.warning("sync_annotations failed account=%s article=%s err=%s", account_id, article_id, exc)

        image_index_payload = self._safe_json(image_index_path, {})
        selected_images_payload = self._safe_json(selected_images_path, {})
        video_notes_text = video_notes_path.read_text(encoding="utf-8") if video_notes_path.exists() else ""

        cleaned_body = self._normalize_text(str(meta_payload.get("body_text", "")))
        image_items = self._merge_image_items(image_index_payload, selected_images_payload)
        video_items = meta_payload.get("videos", []) if isinstance(meta_payload.get("videos", []), list) else []

        text_doc_path = docs_dir / f"{article_id}.cleaned.md"
        media_doc_path = docs_dir / f"{article_id}.media_index.md"

        if not dry_run:
            docs_dir.mkdir(parents=True, exist_ok=True)
            text_doc_path.write_text(self._build_text_doc(meta_payload, cleaned_body), encoding="utf-8")
            media_doc_path.write_text(self._build_media_doc(meta_payload, image_items, video_items, video_notes_text), encoding="utf-8")

        return CleanResult(
            account_id=account_id,
            article_id=article_id,
            text_doc=text_doc_path,
            media_doc=media_doc_path,
            image_count=len(image_items),
            video_count=len(video_items),
        )

    def run(
        self,
        account_id: Optional[str] = None,
        article_ids: Optional[List[str]] = None,
        ingest: bool = False,
        dry_run: bool = False,
        batch_size: int = 300,
    ) -> Dict[str, object]:
        if not self.wechat_root.exists():
            raise FileNotFoundError(f"WeChat root not found: {self.wechat_root}")

        account_dirs = [p for p in self.wechat_root.iterdir() if p.is_dir()]
        if account_id:
            account_dirs = [p for p in account_dirs if p.name == account_id]
        account_dirs = sorted(account_dirs, key=lambda p: p.name)

        if not account_dirs:
            raise ValueError("No account directory found to clean")

        target_article_ids = {str(item).strip() for item in (article_ids or []) if str(item).strip()}

        cleaned_results: List[CleanResult] = []
        for acc_dir in account_dirs:
            meta_dir = acc_dir / "meta"
            if not meta_dir.exists():
                continue
            for path in sorted(meta_dir.glob("*.json"), key=lambda p: p.name):
                if path.name.endswith(".image_index.json"):
                    continue
                if target_article_ids and path.stem not in target_article_ids:
                    continue
                result = self._process_article(account_id=acc_dir.name, article_meta_path=path, dry_run=dry_run)
                if result is not None:
                    cleaned_results.append(result)

        ingest_chunks = 0
        ingested_files = 0
        if ingest and not dry_run and cleaned_results:
            from core.document_processor import process_single_file
            from core.vector_store import VectorStore

            vector_store = VectorStore()
            for item in cleaned_results:
                for file_path in (item.text_doc, item.media_doc):
                    chunks = process_single_file(str(file_path), source=self.source)
                    if not chunks:
                        continue
                    vector_store.add_documents(chunks, batch_size=batch_size)
                    ingest_chunks += len(chunks)
                    ingested_files += 1

        report = {
            "started_at": datetime.now().isoformat(),
            "wechat_root": str(self.wechat_root),
            "source": self.source,
            "dry_run": dry_run,
            "target_article_ids": sorted(target_article_ids),
            "cleaned_articles": len(cleaned_results),
            "cleaned_accounts": len({item.account_id for item in cleaned_results}),
            "generated_docs": len(cleaned_results) * 2,
            "ingest_enabled": ingest,
            "ingested_files": ingested_files,
            "ingested_chunks": ingest_chunks,
            "samples": [
                {
                    "account_id": item.account_id,
                    "article_id": item.article_id,
                    "text_doc": str(item.text_doc),
                    "media_doc": str(item.media_doc),
                    "image_count": item.image_count,
                    "video_count": item.video_count,
                }
                for item in cleaned_results[:10]
            ],
            "finished_at": datetime.now().isoformat(),
        }
        return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean WeChat crawler artifacts for RAG indexing")
    parser.add_argument("--account-id", type=str, default=None, help="Only clean one account")
    parser.add_argument("--source", type=str, default="wechat", help="Source tag used when ingesting to vector store")
    parser.add_argument("--ingest", action="store_true", help="Ingest cleaned docs into vector store")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing cleaned docs")
    parser.add_argument("--batch-size", type=int, default=300, help="Batch size for vector ingestion")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    conf = Config()
    agent = WeChatCleaningAgent(conf=conf, source=args.source)
    result = agent.run(
        account_id=args.account_id,
        ingest=bool(args.ingest),
        dry_run=bool(args.dry_run),
        batch_size=max(1, int(args.batch_size)),
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
