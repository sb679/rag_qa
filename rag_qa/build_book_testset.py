from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence


DEFAULT_OCR_CACHE = Path(
    "user_data/knowledge_files/metallurgy/8a7f8cc2abe9__冶金安全生产技术_12665867(1).pdf.ocr_cache.json"
)
DEFAULT_OUTPUT_DIR = Path("rag_assesment") / "generated_datasets"

CHAPTER_PATTERN = re.compile(r"^第[一二三四五六七八九十百零〇]+[章节篇].{0,40}$")
SECTION_PATTERN = re.compile(r"^第[一二三四五六七八九十百零〇]+节.{0,40}$")
NUMBERED_PATTERN = re.compile(r"^\d+(?:\.\d+){0,3}\s*[^\n]{2,40}$")
NOISE_PATTERNS = [
    re.compile(r"^\d{4}年\d{1,2}月第\d+版$"),
    re.compile(r"^\d{4}年\d{1,2}月第\d+次印刷$"),
    re.compile(r"^\d{6,}$"),
]


def load_ocr_cache(cache_path: Path) -> Dict:
    with cache_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def normalize_line(line: str) -> str:
    cleaned = re.sub(r"[·•．.]{2,}$", "", line.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def merge_broken_heading_lines(lines: Sequence[str]) -> List[str]:
    merged: List[str] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        if (
            index + 1 < len(lines)
            and re.match(r"^第[一二三四五六七八九十百零〇]+[章节篇].{0,2}$", current)
            and lines[index + 1]
            and len(lines[index + 1]) <= 8
        ):
            merged.append(f"{current}{lines[index + 1]}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def is_heading(line: str) -> bool:
    if not line:
        return False
    if any(pattern.match(line) for pattern in NOISE_PATTERNS):
        return False
    if CHAPTER_PATTERN.match(line) or SECTION_PATTERN.match(line):
        return True
    if NUMBERED_PATTERN.match(line):
        if not re.search(r"[\u4e00-\u9fff]", line):
            return False
        if any(token in line for token in ("，", "。", "；", "：", "?", "？", "!", "！")):
            return False
        digit_ratio = sum(ch.isdigit() for ch in line) / max(len(line), 1)
        return digit_ratio < 0.35 and len(line) <= 24
    return False


def split_into_sections(content: str) -> List[Dict[str, str]]:
    lines = merge_broken_heading_lines([normalize_line(line) for line in content.splitlines()])
    indexed_lines = [(index, line) for index, line in enumerate(lines) if line]

    headings: List[tuple[int, str]] = []
    for index, line in indexed_lines:
        if is_heading(line):
            headings.append((index, line))

    if not headings:
        text = "\n".join(line for _, line in indexed_lines).strip()
        return [{"heading": "全文", "context": text}] if text else []

    sections: List[Dict[str, str]] = []
    for position, (line_index, heading) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        chunk_lines = [line for line in lines[line_index + 1:next_index] if line]
        context = "\n".join(chunk_lines).strip()
        if len(context) < 80:
            continue
        sections.append({"heading": heading, "context": context})
    return sections


def build_question(heading: str) -> str:
    if heading == "全文":
        return "问题:请概述本文档的主要内容。"
    if heading.startswith("第"):
        return f"问题:{heading}的主要内容是什么?"
    return f"问题:请介绍{heading}。"


def truncate_context(text: str, max_chars: int) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact
    truncated = compact[:max_chars].rstrip()
    last_break = max(truncated.rfind("。"), truncated.rfind("\n"))
    if last_break >= max_chars // 2:
        truncated = truncated[: last_break + 1].rstrip()
    return truncated


def build_dataset(sections: Sequence[Dict[str, str]], source: str, max_context_chars: int, max_items: int) -> List[Dict[str, str]]:
    dataset: List[Dict[str, str]] = []
    for index, section in enumerate(sections[:max_items], start=1):
        dataset.append(
            {
                "id": index,
                "question": build_question(section["heading"]),
                "context": truncate_context(section["context"], max_context_chars),
                "source": source,
            }
        )
    return dataset


def save_outputs(dataset: Sequence[Dict[str, str]], output_dir: Path, output_name: str, summary_name: str, metadata: Dict) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name
    summary_path = output_dir / summary_name

    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(list(dataset), file_handle, ensure_ascii=False, indent=2)

    with summary_path.open("w", encoding="utf-8") as file_handle:
        json.dump(metadata, file_handle, ensure_ascii=False, indent=2)

    return {"output_path": str(output_path), "summary_path": str(summary_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从单本 OCR 缓存构建问答测试集")
    parser.add_argument("--ocr-cache", default=str(DEFAULT_OCR_CACHE))
    parser.add_argument("--source", default="metallurgy")
    parser.add_argument("--max-context-chars", type=int, default=500)
    parser.add_argument("--max-items", type=int, default=80)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-name", default="metallurgy_safety_testset.json")
    parser.add_argument("--summary-name", default="metallurgy_safety_testset.summary.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cache_path = Path(args.ocr_cache)
    if not cache_path.exists():
        raise FileNotFoundError(f"OCR 缓存不存在: {cache_path}")

    cache_data = load_ocr_cache(cache_path)
    sections = split_into_sections(cache_data.get("content", ""))
    if not sections:
        raise RuntimeError("未能从 OCR 内容中提取有效章节")

    dataset = build_dataset(
        sections,
        source=args.source,
        max_context_chars=args.max_context_chars,
        max_items=args.max_items,
    )
    if not dataset:
        raise RuntimeError("未生成任何数据集条目")

    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_cache": str(cache_path),
        "source": args.source,
        "section_count": len(sections),
        "item_count": len(dataset),
        "max_context_chars": args.max_context_chars,
    }
    saved = save_outputs(
        dataset,
        output_dir=Path(args.output_dir),
        output_name=args.output_name,
        summary_name=args.summary_name,
        metadata=metadata,
    )

    print(json.dumps({**metadata, **saved}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()