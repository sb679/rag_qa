"""Generate mining-domain question-answer pairs with a Chinese QG checkpoint.

The script reads the OCR caches for the three mining manuals, selects section
chunks, extracts answer spans with lightweight heuristics, and generates
questions with a deterministic Transformers question-generation model.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import jieba.posseg as pseg
import torch
from transformers import AutoTokenizer, BartForConditionalGeneration


DEFAULT_MODEL_ID = "IDEA-CCNL/Randeng-BART-139M-QG-Chinese"
DEFAULT_OUTPUT_FILE = Path("rag_assesment") / "mining_autoqg_150.json"
DEFAULT_SUMMARY_FILE = Path("rag_assesment") / "mining_autoqg_150.summary.json"
DEFAULT_TARGET_COUNT = 150
DEFAULT_LONG_SHARE = 0.2
DEFAULT_LONG_CONTEXT_THRESHOLD = 420
DEFAULT_MAX_CHUNKS_PER_SECTION = 5
DEFAULT_CHUNK_SIZE = 300
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_MAX_SOURCE_LENGTH = 512
DEFAULT_MAX_NEW_TOKENS = 32
DEFAULT_NUM_BEAMS = 3
DEFAULT_BATCH_SIZE_CPU = 8
DEFAULT_BATCH_SIZE_CUDA = 16

STOP_PHRASES = {
    "方法",
    "技术",
    "步骤",
    "条件",
    "要求",
    "标准",
    "流程",
    "特点",
    "内容",
    "范围",
    "依据",
    "定义",
    "原理",
    "意义",
    "作用",
    "问题",
    "措施",
    "现状",
    "现象",
    "影响",
    "过程",
    "方案",
    "结果",
    "原因",
}

ANCHOR_PATTERNS = [
    re.compile(r"(?:包括|分为|主要是|主要有|适用于|适合于|属于|由|依据|根据|表现为|意味着|称为|是指)([^。；\n，,]{2,20})"),
    re.compile(r"([^。；\n，,]{2,16})(?:是|为|属于|包括|分为|称为)([^。；\n，,]{2,20})"),
    re.compile(r"(\d+(?:\.\d+)?(?:[%％]|种|个|条|项|米|m|吨|年|月|日|天|小时|人|元|km|公里|平方公里|左右|以上|以下)?)"),
    re.compile(r"([\u4e00-\u9fff]{2,12}(?:、[\u4e00-\u9fff]{2,12}){1,5})"),
]


@dataclass
class GenerationConfig:
    model_id: str = DEFAULT_MODEL_ID
    target_count: int = DEFAULT_TARGET_COUNT
    long_share: float = DEFAULT_LONG_SHARE
    long_context_threshold: int = DEFAULT_LONG_CONTEXT_THRESHOLD
    max_chunks_per_section: int = DEFAULT_MAX_CHUNKS_PER_SECTION
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    max_source_length: int = DEFAULT_MAX_SOURCE_LENGTH
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS
    num_beams: int = DEFAULT_NUM_BEAMS
    batch_size_cpu: int = DEFAULT_BATCH_SIZE_CPU
    batch_size_cuda: int = DEFAULT_BATCH_SIZE_CUDA
    source_dir: str = "data/mining"
    output_file: str = str(DEFAULT_OUTPUT_FILE)
    summary_file: str = str(DEFAULT_SUMMARY_FILE)


def discover_ocr_files(source_dir: Path) -> List[Path]:
    return sorted(source_dir.glob("*.ocr_cache.json"))


def is_heading_line(line: str) -> bool:
    if not re.match(r"^\d+(?:\.\d+){1,3}\s+\S+", line):
        return False
    if not re.search(r"[\u4e00-\u9fff]", line):
        return False
    if len(line) > 80:
        return False
    digit_ratio = sum(ch.isdigit() for ch in line) / max(len(line), 1)
    return digit_ratio < 0.45


def split_into_sections(content: str) -> List[Dict[str, str]]:
    lines = content.splitlines()
    heading_positions: List[tuple[int, str]] = []
    offset = 0
    for line in lines:
        stripped = line.strip()
        if stripped and is_heading_line(stripped):
            heading_positions.append((offset, stripped))
        offset += len(line) + 1

    if not heading_positions:
        return [{"title": "全文", "text": content.strip()}]

    sections: List[Dict[str, str]] = []
    for index, (start, title) in enumerate(heading_positions):
        end = heading_positions[index + 1][0] if index + 1 < len(heading_positions) else len(content)
        section_text = content[start:end].strip()
        if len(section_text) >= 40:
            sections.append({"title": title, "text": section_text})

    return sections or [{"title": "全文", "text": content.strip()}]


def evenly_pick(items: Sequence[Dict], target_count: int) -> List[Dict]:
    if target_count <= 0 or not items:
        return []
    if target_count >= len(items):
        return list(items)
    if target_count == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (target_count - 1)
    picked = []
    seen = set()
    for index in range(target_count):
        candidate_index = round(index * step)
        if candidate_index not in seen:
            seen.add(candidate_index)
            picked.append(items[candidate_index])
    for candidate_index in range(len(items)):
        if len(picked) >= target_count:
            break
        if candidate_index not in seen:
            seen.add(candidate_index)
            picked.append(items[candidate_index])
    return picked[:target_count]


def split_section_into_chunks(section_text: str, chunk_size: int, chunk_overlap: int, max_chunks: int) -> List[str]:
    if not section_text.strip():
        return []

    step = max(1, chunk_size - chunk_overlap)
    raw_chunks: List[str] = []
    start = 0
    text_length = len(section_text)
    while start < text_length:
        end = min(text_length, start + chunk_size)
        chunk = section_text[start:end].strip()
        if chunk:
            raw_chunks.append(chunk)
        if end >= text_length:
            break
        start += step
    if not raw_chunks:
        return []
    if max_chunks <= 0:
        return raw_chunks
    if len(raw_chunks) <= max_chunks:
        return raw_chunks
    indexed = [{"chunk": chunk} for chunk in raw_chunks]
    return [item["chunk"] for item in evenly_pick(indexed, max_chunks)]


def clean_candidate(text: str) -> str:
    text = text.strip().strip("。；，,：:、")
    text = re.sub(r"\s+", "", text)
    return text


def extract_answer_candidates(text: str, limit: int = 8) -> List[str]:
    candidates: List[str] = []
    seen = set()

    def add_candidate(value: str) -> None:
        cleaned = clean_candidate(value)
        if not cleaned:
            return
        if len(cleaned) < 2 or len(cleaned) > 18:
            return
        if cleaned in seen:
            return
        if cleaned in STOP_PHRASES:
            return
        if cleaned.endswith("的") or cleaned.startswith("的"):
            return
        seen.add(cleaned)
        candidates.append(cleaned)

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[。！？!?；;])\s*", text) if sentence.strip()]
    if not sentences:
        sentences = [text]

    for sentence in sentences:
        for pattern in ANCHOR_PATTERNS:
            for match in pattern.finditer(sentence):
                if match.lastindex is None:
                    add_candidate(match.group(1))
                    continue
                for group_index in range(1, match.lastindex + 1):
                    if match.group(group_index):
                        add_candidate(match.group(group_index))

        for word, flag in pseg.cut(sentence):
            if len(word) < 2 or len(word) > 12:
                continue
            if flag.startswith(("n", "v", "a", "t", "m", "s", "f")):
                add_candidate(word)

        for part in re.split(r"[、，,；;\s]+", sentence):
            part = clean_candidate(part)
            if 2 <= len(part) <= 12:
                add_candidate(part)

    numeric_candidates = [c for c in candidates if re.fullmatch(r"\d+(?:\.\d+)?(?:[%％]|种|个|条|项|米|m|吨|年|月|日|天|小时|人|元|km|公里|平方公里|左右|以上|以下)?", c)]
    list_candidates = [c for c in candidates if "、" in c]
    text_candidates = [c for c in candidates if c not in numeric_candidates and c not in list_candidates]

    ordered = numeric_candidates + list_candidates + text_candidates
    return ordered[:limit]


def build_prompt(chunk_text: str, answer: str) -> str:
    masked_text = chunk_text.replace(answer, "<ans>", 1)
    if masked_text == chunk_text:
        return ""
    return f"知识：{masked_text}\n回答：{answer}"


def normalize_question(question: str) -> str:
    question = question.strip()
    question = question.replace("?", "？")
    question = re.sub(r"\s+", "", question)
    if question and question[-1] not in "？。！!":
        question += "？"
    return question


def is_valid_question(question: str, answer: str, chunk_text: str) -> bool:
    if not question or len(question) < 4:
        return False
    if len(question) > 80:
        return False
    if "<ans>" in question:
        return False
    if len(set(question)) <= 2:
        return False
    return True


def prepare_prompt_jobs(chunks: List[Dict], questions_per_chunk: int) -> List[Dict]:
    jobs: List[Dict] = []
    for chunk_index, chunk in enumerate(chunks):
        answers = extract_answer_candidates(chunk["text"], limit=max(questions_per_chunk * 2, 12))
        if not answers:
            continue
        used = 0
        for answer in answers:
            prompt = build_prompt(chunk["text"], answer)
            if not prompt:
                continue
            jobs.append({
                "chunk_index": chunk_index,
                "section_title": chunk["section_title"],
                "source_file": chunk["source_file"],
                "chunk_text": chunk["text"],
                "answer": answer,
                "prompt": prompt,
                "chunk_length": len(chunk["text"]),
                "window_chunk_count": chunk["window_chunk_count"],
                "window_type": chunk["window_type"],
            })
            used += 1
            if used >= questions_per_chunk:
                break
    return jobs


def batch_iter(items: Sequence[Dict], batch_size: int) -> Iterable[List[Dict]]:
    for start in range(0, len(items), batch_size):
        yield list(items[start:start + batch_size])


def generate_questions(jobs: List[Dict], model_id: str, batch_size: int, max_source_length: int,
                       max_new_tokens: int, num_beams: int) -> List[Dict]:
    tokenizer = AutoTokenizer.from_pretrained(model_id, additional_special_tokens=["<ans>"])
    model = BartForConditionalGeneration.from_pretrained(model_id, use_safetensors=False)
    model.resize_token_embeddings(len(tokenizer))
    model.eval()

    if torch.cuda.is_available():
        model = model.to("cuda")
    else:
        model = model.to("cpu")

    model_device = next(model.parameters()).device

    results: List[Dict] = []
    total_batches = math.ceil(len(jobs) / batch_size)
    for batch_index, batch_jobs in enumerate(batch_iter(jobs, batch_size), start=1):
        print(f"Generating batch {batch_index}/{total_batches} ({len(results)}/{len(jobs)} outputs collected)")
        encodings = tokenizer(
            [job["prompt"] for job in batch_jobs],
            return_tensors="pt",
            truncation=True,
            max_length=max_source_length,
            padding=True,
        )
        encodings = {key: value.to(model_device) for key, value in encodings.items()}

        with torch.no_grad():
            outputs = model.generate(
                **encodings,
                do_sample=False,
                num_beams=num_beams,
                max_new_tokens=max_new_tokens,
                no_repeat_ngram_size=4,
                length_penalty=1.0,
                early_stopping=True,
            )

        decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        for job, question in zip(batch_jobs, decoded):
            normalized_question = normalize_question(question)
            if not is_valid_question(normalized_question, job["answer"], job["chunk_text"]):
                continue
            results.append({
                "question": normalized_question,
                "answer": job["answer"],
                "context": [job["chunk_text"]],
                "source_file": job["source_file"],
                "section_title": job["section_title"],
                "chunk_index": job["chunk_index"],
                "answer_candidate": job["answer"],
                "model_id": model_id,
            })
    return results


def build_chunk_pool(source_dir: Path, chunk_size: int, chunk_overlap: int, max_chunks_per_section: int) -> List[Dict]:
    chunk_pool: List[Dict] = []
    for ocr_file in discover_ocr_files(source_dir):
        with ocr_file.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        content = data.get("content", "")
        sections = split_into_sections(content)
        for section_index, section in enumerate(sections):
            chunks = split_section_into_chunks(section["text"], chunk_size, chunk_overlap, max_chunks_per_section)
            for chunk_index, chunk_text in enumerate(chunks):
                chunk_pool.append({
                    "source_file": ocr_file.name,
                    "section_title": section["title"],
                    "section_index": section_index,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "char_length": len(chunk_text),
                })
    return chunk_pool


def build_window_pool(chunks: List[Dict], max_window_chunks: int, long_share: float) -> List[Dict]:
    if not chunks:
        return []

    chunks_by_file: Dict[str, List[Dict]] = {}
    for chunk in chunks:
        chunks_by_file.setdefault(chunk["source_file"], []).append(chunk)

    for file_chunks in chunks_by_file.values():
        file_chunks.sort(key=lambda item: item["chunk_index"])

    windows: List[Dict] = []
    for source_file, file_chunks in chunks_by_file.items():
        file_count = len(file_chunks)
        long_anchor = file_count // 2
        for anchor_index, anchor_chunk in enumerate(file_chunks):
            if anchor_index == long_anchor:
                start = max(0, anchor_index - 2)
                end = min(file_count, start + max_window_chunks)
                start = max(0, end - max_window_chunks)
                window_chunks = file_chunks[start:end]
                window_type = "long"
            elif anchor_index % 2 == 0:
                start = anchor_index
                end = min(file_count, anchor_index + 2)
                window_chunks = file_chunks[start:end]
                window_type = "short"
            else:
                window_chunks = [anchor_chunk]
                window_type = "short"

            window_text = "\n\n".join(chunk["text"] for chunk in window_chunks)
            windows.append({
                "source_file": source_file,
                "section_title": anchor_chunk["section_title"],
                "anchor_chunk_index": anchor_index,
                "window_type": window_type,
                "window_chunk_count": len(window_chunks),
                "text": window_text,
                "char_length": len(window_text),
                "window_chunk_indices": [chunk["chunk_index"] for chunk in window_chunks],
            })

    long_windows = [window for window in windows if window["window_type"] == "long"]
    short_windows = [window for window in windows if window["window_type"] == "short"]
    long_target = max(1, round(len(windows) * long_share))
    selected: List[Dict] = []
    selected.extend(evenly_pick(long_windows, min(long_target, len(long_windows))))
    selected.extend(short_windows)
    selected.sort(key=lambda item: (item["source_file"], item["anchor_chunk_index"]))
    return selected


def create_dataset(config: GenerationConfig) -> Dict:
    source_dir = Path(config.source_dir)
    chunk_pool = build_chunk_pool(source_dir, config.chunk_size, config.chunk_overlap, 0)
    if not chunk_pool:
        raise RuntimeError(f"No OCR chunks found under {source_dir}")

    selected_windows = build_window_pool(
        chunk_pool,
        max_window_chunks=config.max_chunks_per_section,
        long_share=config.long_share,
    )
    if len(selected_windows) > 15:
        selected_windows = evenly_pick(selected_windows, 15)

    jobs = prepare_prompt_jobs(selected_windows, questions_per_chunk=12)
    if not jobs:
        raise RuntimeError("No answer candidates were extracted from the selected chunks")

    batch_size = config.batch_size_cuda if torch.cuda.is_available() else config.batch_size_cpu
    generated = generate_questions(
        jobs,
        model_id=config.model_id,
        batch_size=batch_size,
        max_source_length=config.max_source_length,
        max_new_tokens=config.max_new_tokens,
        num_beams=config.num_beams,
    )

    if len(generated) < config.target_count:
        raise RuntimeError(
            f"Only generated {len(generated)} questions, target was {config.target_count}. "
            f"Try lowering filters or raising the source pool size."
        )

    deduped = generated[:config.target_count]

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": asdict(config),
        "chunk_pool_size": len(chunk_pool),
        "selected_window_count": len(selected_windows),
        "raw_generated_count": len(generated),
        "final_count": len(deduped),
        "source_files": sorted({item["source_file"] for item in deduped}),
        "model_id": config.model_id,
        "generation_mode": "deterministic",
    }
    return {"items": deduped, "summary": summary}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate mining Q&A pairs with a Chinese QG model.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--target-count", type=int, default=DEFAULT_TARGET_COUNT)
    parser.add_argument("--long-share", type=float, default=DEFAULT_LONG_SHARE)
    parser.add_argument("--long-context-threshold", type=int, default=DEFAULT_LONG_CONTEXT_THRESHOLD)
    parser.add_argument("--max-chunks-per-section", type=int, default=DEFAULT_MAX_CHUNKS_PER_SECTION)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--max-source-length", type=int, default=DEFAULT_MAX_SOURCE_LENGTH)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--num-beams", type=int, default=DEFAULT_NUM_BEAMS)
    parser.add_argument("--batch-size-cpu", type=int, default=DEFAULT_BATCH_SIZE_CPU)
    parser.add_argument("--batch-size-cuda", type=int, default=DEFAULT_BATCH_SIZE_CUDA)
    parser.add_argument("--source-dir", default="data/mining")
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--summary-file", default=str(DEFAULT_SUMMARY_FILE))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = GenerationConfig(
        model_id=args.model_id,
        target_count=args.target_count,
        long_share=args.long_share,
        long_context_threshold=args.long_context_threshold,
        max_chunks_per_section=args.max_chunks_per_section,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        max_source_length=args.max_source_length,
        max_new_tokens=args.max_new_tokens,
        num_beams=args.num_beams,
        batch_size_cpu=args.batch_size_cpu,
        batch_size_cuda=args.batch_size_cuda,
        source_dir=args.source_dir,
        output_file=args.output_file,
        summary_file=args.summary_file,
    )

    os.makedirs(Path(config.output_file).parent, exist_ok=True)
    result = create_dataset(config)

    with Path(config.output_file).open("w", encoding="utf-8") as file_handle:
        json.dump(result["items"], file_handle, ensure_ascii=False, indent=2)

    with Path(config.summary_file).open("w", encoding="utf-8") as file_handle:
        json.dump(result["summary"], file_handle, ensure_ascii=False, indent=2)

    print(f"Saved {len(result['items'])} question-answer pairs to {config.output_file}")
    print(f"Summary written to {config.summary_file}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()