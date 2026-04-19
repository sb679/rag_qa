# -*- coding: utf-8 -*-
"""Unify and classify document files from corpus/upload/samples.

Default behavior only scans and writes a manifest.
Use --copy-mode hardlink|copy to materialize a unified directory tree.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
    ".txt", ".md",
}

FORMAT_GROUPS = {
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "doc",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".bmp": "image",
    ".gif": "image",
    ".txt": "text",
    ".md": "markdown",
}

UPLOAD_NAME_PATTERN = re.compile(r"^([0-9a-fA-F]{8,})__(.+)$")


@dataclass
class DocumentRecord:
    origin: str
    source: str
    format_group: str
    extension: str
    relative_path: str
    absolute_path: str
    file_name: str
    file_name_original: str
    upload_file_id: str
    has_ocr_cache: bool
    size_bytes: int


def _format_group(ext: str) -> str:
    return FORMAT_GROUPS.get(ext.lower(), "other")


def _safe_name(name: str) -> str:
    return re.sub(r"[<>:\"/\\|?*]", "_", name).strip() or "unnamed"


def _hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _parse_uploaded_name(file_name: str) -> Tuple[str, str]:
    match = UPLOAD_NAME_PATTERN.match(file_name)
    if not match:
        return "", file_name
    return match.group(1), match.group(2)


def _collect_files(root_dir: Path) -> List[Path]:
    if not root_dir.exists():
        return []
    return [
        path for path in root_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def _build_record(path: Path, root_dir: Path, origin: str, source: str) -> DocumentRecord:
    relative_path = str(path.relative_to(root_dir)).replace("\\", "/")
    ext = path.suffix.lower()
    upload_file_id, original_name = ("", path.name)
    if origin == "uploaded":
        upload_file_id, original_name = _parse_uploaded_name(path.name)

    cache_path = path.with_name(path.name + ".ocr_cache.json")
    return DocumentRecord(
        origin=origin,
        source=source,
        format_group=_format_group(ext),
        extension=ext,
        relative_path=relative_path,
        absolute_path=str(path),
        file_name=path.name,
        file_name_original=original_name,
        upload_file_id=upload_file_id,
        has_ocr_cache=cache_path.exists(),
        size_bytes=path.stat().st_size,
    )


def scan_documents(workspace_root: Path) -> List[DocumentRecord]:
    records: List[DocumentRecord] = []

    data_root = workspace_root / "data"
    if data_root.exists():
        for source_dir in [p for p in data_root.iterdir() if p.is_dir()]:
            for file_path in _collect_files(source_dir):
                records.append(_build_record(file_path, workspace_root, "base_corpus", source_dir.name))

    uploaded_root = workspace_root / "user_data" / "knowledge_files"
    if uploaded_root.exists():
        for source_dir in [p for p in uploaded_root.iterdir() if p.is_dir()]:
            for file_path in _collect_files(source_dir):
                records.append(_build_record(file_path, workspace_root, "uploaded", source_dir.name))

    samples_root = workspace_root / "samples"
    if samples_root.exists():
        for file_path in _collect_files(samples_root):
            records.append(_build_record(file_path, workspace_root, "sample_ocr", "samples"))

    return records


def write_manifest(records: List[DocumentRecord], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in records]
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def materialize_unified_tree(records: List[DocumentRecord], output_dir: Path, copy_mode: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        base_name = _safe_name(rec.file_name_original)
        doc_id = rec.upload_file_id or _hash_id(rec.relative_path)
        target_name = f"{doc_id}__{base_name}"
        target_dir = output_dir / rec.origin / rec.source / rec.format_group
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / target_name

        source_path = Path(rec.absolute_path)
        if target_path.exists():
            continue

        if copy_mode == "hardlink":
            os.link(source_path, target_path)
        elif copy_mode == "copy":
            shutil.copy2(source_path, target_path)


def summarize(records: List[DocumentRecord]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {
        "origin": {},
        "format_group": {},
        "source": {},
    }
    for rec in records:
        summary["origin"][rec.origin] = summary["origin"].get(rec.origin, 0) + 1
        summary["format_group"][rec.format_group] = summary["format_group"].get(rec.format_group, 0) + 1
        source_key = f"{rec.origin}:{rec.source}"
        summary["source"][source_key] = summary["source"].get(source_key, 0) + 1
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unify and classify local document corpus")
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parent),
        help="Path to rag_qa workspace root",
    )
    parser.add_argument(
        "--output-dir",
        default="user_data/corpus_unified",
        help="Output directory for unified tree",
    )
    parser.add_argument(
        "--manifest",
        default="user_data/corpus_unified/document_manifest.json",
        help="Manifest JSON output path",
    )
    parser.add_argument(
        "--copy-mode",
        choices=["none", "hardlink", "copy"],
        default="none",
        help="none: only manifest, hardlink/copy: materialize unified tree",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    output_dir = (workspace_root / args.output_dir).resolve()
    manifest_path = (workspace_root / args.manifest).resolve()

    records = scan_documents(workspace_root)
    write_manifest(records, manifest_path)

    if args.copy_mode != "none":
        materialize_unified_tree(records, output_dir, args.copy_mode)

    summary = summarize(records)
    print(f"workspace_root={workspace_root}")
    print(f"records={len(records)}")
    print(f"manifest={manifest_path}")
    print(f"copy_mode={args.copy_mode}")
    print("origin_summary=", summary["origin"])
    print("format_summary=", summary["format_group"])


if __name__ == "__main__":
    main()
