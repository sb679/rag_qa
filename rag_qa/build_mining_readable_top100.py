# -*- coding: utf-8 -*-
"""Build a human-readable top-100 subset from merged mining auto-QG data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "rag_assesment" / "mining_autoqg_merged_dedup.json"
CURATED_FALLBACK_FILE = ROOT / "rag_assesment" / "mining_curated_100.json"
EXTRA_FALLBACK_FILES = [
    ROOT / "rag_assesment" / "mining_autoqg_150.json",
    ROOT / "rag_assesment" / "mining_autoqg_180_v1.json",
    ROOT / "rag_assesment" / "mining_autoqg_180_v2.json",
]
OUTPUT_FILE = ROOT / "rag_assesment" / "mining_autoqg_top100_readable.json"
SUMMARY_FILE = ROOT / "rag_assesment" / "mining_autoqg_top100_readable.summary.json"

TOP_K = 100

MINING_KEYWORDS = [
    "矿", "采", "井", "巷", "露天", "地下", "矿山", "矿床", "岩", "爆破",
    "通风", "充填", "水仓", "选矿", "边坡", "支护", "采空区", "钻孔", "开采",
]

QUESTION_BLACKLIST_REGEX = [
    r"谁主编了现代采矿手册",
    r"现代采矿手册有多少本书",
    r"图书在版编目",
    r"ISBN",
    r"供应商|制造商|分销商|JIT|TOC",
    r"什么是横坐标|什么是纵坐标",
]

GENERIC_SHORT_ANSWERS = {
    "如下", "可得", "管理", "连续性", "流速", "变异", "准时", "饱和", "曲线图",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_question(question: str) -> str:
    question = re.sub(r"^问题[:：]\s*", "", question or "").strip()
    question = question.replace("?", "？")
    question = re.sub(r"\s+", "", question)
    if question and question[-1] not in "？。！!":
        question += "？"
    return question


def chinese_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def is_cover_context(context: str) -> bool:
    return (
        ("ISBN" in context and "定价450.00元" in context)
        or ("图书在版编目" in context and "现代采矿手册" in context)
    )


def is_mining_related(question: str, context: str) -> bool:
    text = f"{question} {context}"
    return any(keyword in text for keyword in MINING_KEYWORDS)


def is_blacklisted_question(question: str) -> bool:
    return any(re.search(pattern, question) for pattern in QUESTION_BLACKLIST_REGEX)


def is_readable_question(question: str) -> bool:
    if len(question) < 8 or len(question) > 40:
        return False
    if chinese_count(question) < 6:
        return False
    if re.search(r"[A-Za-z]{2,}|[=:/\\]", question):
        return False
    if re.search(r"[()（）\[\]{}]", question):
        return False
    if re.search(r"\d{4,}", question):
        return False
    if is_blacklisted_question(question):
        return False
    return question.endswith("？")


def is_readable_answer(question: str, answer: str) -> bool:
    answer = answer.strip()
    if not answer:
        return False
    if re.fullmatch(r"[\d.]+", answer):
        return ("多少" in question or "几" in question) and len(answer) <= 8
    if len(answer) < 4 or len(answer) > 80:
        return False
    if chinese_count(answer) < 2:
        return False
    if answer in GENERIC_SHORT_ANSWERS:
        return False
    return True


def is_curated_fallback_acceptable(question: str, answer: str) -> bool:
    if not question:
        return False
    if is_blacklisted_question(question):
        return False
    if len(question) < 6 or len(question) > 64:
        return False
    if chinese_count(question) < 4:
        return False
    if re.search(r"[A-Za-z]{3,}|[=:/\\]{2,}", question):
        return False

    answer = answer.strip()
    if not answer:
        return False
    if re.fullmatch(r"[\d.]+", answer):
        return ("多少" in question or "几" in question) and len(answer) <= 10
    if len(answer) < 2 or len(answer) > 220:
        return False
    if chinese_count(answer) < 1:
        return False
    if answer in GENERIC_SHORT_ANSWERS:
        return False
    return True


def is_curated_primary_acceptable(question: str, answer: str) -> bool:
    if not question or len(question) < 6:
        return False
    if is_blacklisted_question(question):
        return False
    if not answer.strip():
        return False
    return True


def score_item(item: Dict[str, Any]) -> float:
    question = normalize_question(item.get("question", ""))
    answer = str(item.get("answer", "")).strip()
    context = (item.get("context") or [""])[0]

    score = 0.0

    # Question quality
    if 6 <= len(question) <= 36:
        score += 2.0
    if chinese_count(question) >= 4:
        score += 2.0
    if question.endswith("？"):
        score += 1.0
    if re.search(r"[A-Za-z]{2,}", question):
        score -= 2.0
    if re.search(r"[=:/\\]", question):
        score -= 2.0
    if re.search(r"\d{4,}", question):
        score -= 1.0

    # Answer quality
    numeric_only = re.fullmatch(r"[\d.]+", answer) is not None
    if 2 <= len(answer) <= 24:
        score += 1.0
    if chinese_count(answer) >= 1:
        score += 2.0
    if numeric_only:
        score -= 3.0
        if ("多少" in question or "几" in question) and len(answer) <= 6:
            score += 1.0

    # Context quality
    if chinese_count(context) >= 40:
        score += 1.0
    if is_cover_context(context):
        score -= 5.0
    if is_mining_related(question, context):
        score += 2.0

    # Strong penalties for known junk patterns
    if is_blacklisted_question(question):
        score -= 4.0

    return score


def canonical_item(item: Dict[str, Any], clean_score: float) -> Dict[str, Any]:
    question = normalize_question(item.get("question", ""))
    answer = str(item.get("answer", "")).strip()
    context = item.get("context") or []
    if not isinstance(context, list):
        context = [str(context)]

    result = {
        "question": question,
        "answer": answer,
        "context": context,
        "source_file": item.get("source_file"),
        "section_title": item.get("section_title"),
        "chunk_index": item.get("chunk_index"),
        "answer_candidate": item.get("answer_candidate"),
        "model_id": item.get("model_id"),
        "batch_file": item.get("batch_file"),
        "clean_score": round(clean_score, 2),
    }
    return result


def pick_best_by_question(
    source_items: List[Dict[str, Any]],
    min_score: float,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, float], int]:
    best_by_question: Dict[str, Dict[str, Any]] = {}
    score_by_question: Dict[str, float] = {}
    dropped_cover = 0

    for item in source_items:
        question = normalize_question(item.get("question", ""))
        if not question or chinese_count(question) < 2:
            continue

        context = (item.get("context") or [""])[0]
        answer = str(item.get("answer", "")).strip()
        if is_cover_context(context):
            dropped_cover += 1
            continue
        if not is_mining_related(question, context):
            continue
        if not is_readable_question(question):
            continue
        if not is_readable_answer(question, answer):
            continue

        score = score_item(item)
        if score < min_score:
            continue

        if question not in best_by_question or score > score_by_question[question]:
            best_by_question[question] = item
            score_by_question[question] = score

    return best_by_question, score_by_question, dropped_cover


def build_top100() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    source_items = load_json(SOURCE_FILE)
    curated_items = load_json(CURATED_FALLBACK_FILE) if CURATED_FALLBACK_FILE.exists() else []

    selected_by_question: Dict[str, Dict[str, Any]] = {}
    selected_score: Dict[str, float] = {}

    # Stage-0: use curated high-quality set first.
    curated_added = 0
    for item in curated_items:
        question = normalize_question(item.get("question", ""))
        answer = str(item.get("answer", "")).strip()
        if question in selected_by_question:
            continue
        if not is_curated_primary_acceptable(question, answer):
            continue

        # Boost curated data so it stays at top in final ranking.
        selected_by_question[question] = item
        # Keep curated samples ranked ahead of merged noisy candidates.
        selected_score[question] = 100.0 + max(0.0, score_item(item))
        curated_added += 1
        if len(selected_by_question) >= TOP_K:
            break

    # Stage-1: strict readable and mining-related candidates.
    strict_best, strict_scores, dropped_cover_strict = pick_best_by_question(source_items, min_score=6.0)
    strict_ranked: List[Tuple[float, Dict[str, Any]]] = [
        (strict_scores[question], item) for question, item in strict_best.items()
    ]
    strict_ranked.sort(key=lambda pair: (-pair[0], normalize_question(pair[1].get("question", ""))))

    for score, item in strict_ranked:
        question = normalize_question(item.get("question", ""))
        if question in selected_by_question:
            continue
        selected_by_question[question] = item
        selected_score[question] = score
        if len(selected_by_question) >= TOP_K:
            break

    # Stage-2: relaxed score threshold to fill from merged pool.
    relaxed_best, relaxed_scores, dropped_cover_relaxed = pick_best_by_question(source_items, min_score=4.0)
    relaxed_ranked: List[Tuple[float, Dict[str, Any]]] = [
        (relaxed_scores[question], item) for question, item in relaxed_best.items()
    ]
    relaxed_ranked.sort(key=lambda pair: (-pair[0], normalize_question(pair[1].get("question", ""))))

    relaxed_added = 0
    for score, item in relaxed_ranked:
        question = normalize_question(item.get("question", ""))
        if question in selected_by_question:
            continue
        selected_by_question[question] = item
        selected_score[question] = score
        relaxed_added += 1
        if len(selected_by_question) >= TOP_K:
            break

    # Stage-3: if still not enough, use curated high-quality fallback.
    fallback_added = 0
    if len(selected_by_question) < TOP_K and CURATED_FALLBACK_FILE.exists():
        curated_items = load_json(CURATED_FALLBACK_FILE)
        for item in curated_items:
            question = normalize_question(item.get("question", ""))
            answer = str(item.get("answer", "")).strip()

            if question in selected_by_question:
                continue
            if not is_curated_fallback_acceptable(question, answer):
                continue

            selected_by_question[question] = item
            selected_score[question] = max(5.5, score_item(item))
            fallback_added += 1
            if len(selected_by_question) >= TOP_K:
                break

    # Stage-4: extra generated pools for the remaining slots.
    extra_fallback_added = 0
    if len(selected_by_question) < TOP_K:
        for extra_file in EXTRA_FALLBACK_FILES:
            if not extra_file.exists():
                continue
            extra_items = load_json(extra_file)
            for item in extra_items:
                question = normalize_question(item.get("question", ""))
                answer = str(item.get("answer", "")).strip()
                context = (item.get("context") or [""])
                context_text = context[0] if context else ""

                if question in selected_by_question:
                    continue
                if not is_mining_related(question, context_text):
                    continue
                if not is_curated_fallback_acceptable(question, answer):
                    continue

                candidate_score = max(4.5, score_item(item))
                selected_by_question[question] = item
                selected_score[question] = candidate_score
                extra_fallback_added += 1
                if len(selected_by_question) >= TOP_K:
                    break
            if len(selected_by_question) >= TOP_K:
                break

    ranked_selected: List[Tuple[float, Dict[str, Any]]] = [
        (selected_score[question], item)
        for question, item in selected_by_question.items()
    ]
    ranked_selected.sort(key=lambda pair: (-pair[0], normalize_question(pair[1].get("question", ""))))
    selected = [canonical_item(item, score) for score, item in ranked_selected[:TOP_K]]

    summary = {
        "source_file": str(SOURCE_FILE),
        "input_total": len(source_items),
        "strict_candidates": len(strict_best),
        "relaxed_candidates": len(relaxed_best),
        "added_from_curated_first": curated_added,
        "topk": TOP_K,
        "output_total": len(selected),
        "strict_min_score": 6.0,
        "relaxed_min_score": 4.0,
        "added_from_relaxed": relaxed_added,
        "added_from_curated_fallback": fallback_added,
        "added_from_extra_fallback": extra_fallback_added,
        "dropped_cover_like_items": dropped_cover_strict + dropped_cover_relaxed,
        "note": "Top-100 readable mining subset via strict pass + relaxed fill + curated fallback.",
    }
    return selected, summary


def main() -> None:
    selected, summary = build_top100()
    save_json(OUTPUT_FILE, selected)
    save_json(SUMMARY_FILE, summary)
    print(f"Saved {len(selected)} items to {OUTPUT_FILE}")
    print(f"Summary saved to {SUMMARY_FILE}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()