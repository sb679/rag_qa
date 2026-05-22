# -*- coding:utf-8 -*-
"""Sync manual image annotations into image index and searchable markdown.

Usage:
  python sync_image_annotations.py --account-id my_wechat_account --article-id a25d005bbdcbb34e
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


BASE_DIR = Path(__file__).resolve().parent / "data" / "wechat_collector" / "wechat_data"


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _to_tags(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _scene_to_text(scene: object, fallback_text: str = "") -> str:
    if isinstance(scene, dict) and scene:
        lines = []
        ordered_keys = ["活动类型", "事件名称", "时间", "地点", "人物", "身份", "组织", "视觉特征", "来源"]
        for key in ordered_keys:
            value = str(scene.get(key, "")).strip()
            if value:
                lines.append(f"{key}:{value}")
        if lines:
            return "\n".join(lines)
    return str(fallback_text or "").strip()


def sync_annotations(account_id: str, article_id: str) -> Dict[str, object]:
    account_dir = BASE_DIR / account_id
    docs_dir = account_dir / "docs"
    meta_dir = account_dir / "meta"

    index_path = meta_dir / f"{article_id}.image_index.json"
    ann_path = docs_dir / f"{article_id}.image_annotations.json"
    output_md_path = docs_dir / f"{article_id}.images.annotations.md"
    selected_json_path = docs_dir / f"{article_id}.selected_images.json"

    index_payload = _load_json(index_path)
    ann_payload = _load_json(ann_path)

    annotations = {}
    for item in ann_payload.get("annotations", []):
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id", "")).strip()
        if not image_id:
            continue
        annotations[image_id] = item

    kept = 0
    dropped = 0
    updated = 0
    selected_images: List[Dict[str, object]] = []
    lines: List[str] = []
    lines.append(f"# Image Manual Annotations - {article_id}")
    lines.append("")
    lines.append(f"- account_id: {account_id}")
    lines.append(f"- source_link: {index_payload.get('source_link', '')}")
    lines.append(f"- synced_at: {datetime.now().isoformat()}")
    lines.append("")

    for image in index_payload.get("images", []):
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id", "")).strip()
        ann = annotations.get(image_id)
        if ann is None:
            continue

        manual_summary = str(ann.get("manual_summary", "")).strip()
        manual_notes = str(ann.get("manual_notes", "")).strip()
        manual_tags = _to_tags(ann.get("manual_tags", []))
        scene_annotation = ann.get("scene_annotation", {}) if isinstance(ann.get("scene_annotation", {}), dict) else {}
        scene_annotation_text = _scene_to_text(scene_annotation, str(ann.get("scene_annotation_text", "")))
        keep_for_index = bool(ann.get("keep_for_index", True))

        image["manual_summary"] = manual_summary
        image["manual_notes"] = manual_notes
        image["manual_tags"] = manual_tags
        image["scene_annotation"] = scene_annotation
        image["scene_annotation_text"] = scene_annotation_text

        if not keep_for_index:
            image["indexable"] = False
            dropped += 1
        else:
            kept += 1
            selected_images.append(
                {
                    "image_id": image_id,
                    "local_path": image.get("local_path", ""),
                    "url": image.get("url", ""),
                    "display_index": image.get("display_index", 0),
                    "manual_summary": manual_summary,
                    "manual_notes": manual_notes,
                    "manual_tags": manual_tags,
                    "scene_annotation": scene_annotation,
                    "scene_annotation_text": scene_annotation_text,
                    "keep_for_index": keep_for_index,
                    "indexable": bool(image.get("indexable", False)),
                    "api_summary": image.get("api_summary", ""),
                }
            )

        updated += 1

        lines.append(f"## image_id: {image_id}")
        lines.append(f"- keep_for_index: {keep_for_index}")
        lines.append(f"- local_path: {image.get('local_path', '')}")
        lines.append(f"- source_url: {image.get('url', '')}")
        lines.append("")
        if scene_annotation_text:
            lines.append("scene_annotation:")
            for row in scene_annotation_text.splitlines():
                lines.append(f"  {row}")
            lines.append("")
        if image.get("api_summary"):
            lines.append(f"api_summary: {image.get('api_summary', '')}")
            lines.append("")

    index_payload["images_indexable"] = sum(
        1 for img in index_payload.get("images", []) if isinstance(img, dict) and bool(img.get("indexable", False))
    )
    index_payload["manual_annotation_synced_at"] = datetime.now().isoformat()

    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    selected_json_path.write_text(
        json.dumps(
            {
                "article_id": article_id,
                "account_id": account_id,
                "generated_at": datetime.now().isoformat(),
                "selected_count": len(selected_images),
                "selected_images": selected_images,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "index_path": str(index_path),
        "annotations_path": str(ann_path),
        "annotation_md_path": str(output_md_path),
        "selected_images_path": str(selected_json_path),
        "images_updated": updated,
        "images_indexable": index_payload["images_indexable"],
        "kept": kept,
        "dropped": dropped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync image annotations into index and searchable markdown")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--article-id", required=True)
    args = parser.parse_args()

    result = sync_annotations(account_id=args.account_id, article_id=args.article_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
