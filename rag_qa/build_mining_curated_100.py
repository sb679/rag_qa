# -*- coding: utf-8 -*-
"""Build a curated mining QA set from existing curated eval data and auto-QG candidates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
AUTOQG_FILE = ROOT / "rag_assesment" / "mining_autoqg_150.json"
EVAL_FILE = ROOT / "rag_assesment" / "mining_evaluation_data.json"
OUTPUT_FILE = ROOT / "rag_assesment" / "mining_curated_100.json"
SUMMARY_FILE = ROOT / "rag_assesment" / "mining_curated_100.summary.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_question(question: str) -> str:
    question = re.sub(r"^问题[:：]\s*", "", question or "").strip()
    question = re.sub(r"\s+", "", question)
    return question


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def question_is_plausible(question: str) -> bool:
    if not question:
        return False
    if len(question) < 4 or len(question) > 30:
        return False
    if question.count("？") > 1 or question.count("?") > 1:
        return False
    if re.search(r"[\u4e00-\u9fff]{2,}", question) is None:
        return False
    if "����" in question:
        return False
    return True


def score_autoqg_item(item: Dict[str, Any]) -> float:
    question = normalize_question(item.get("question", ""))
    answer = normalize_text(item.get("answer", ""))
    context = normalize_text((item.get("context") or [""])[0])

    score = 0.0

    if 6 <= len(question) <= 28:
        score += 2.0
    if re.search(r"[\u4e00-\u9fff]{2,}", question):
        score += 2.0
    if question.endswith("？") or question.endswith("?"):
        score += 1.0
    if len(set(question)) >= 5:
        score += 1.0

    if 2 <= len(answer) <= 24:
        score += 1.0
    if re.search(r"[\u4e00-\u9fff]", answer):
        score += 2.0
    if not re.fullmatch(r"[\d.\-]+", answer):
        score += 1.0
    if any(token in answer for token in ["、", "，", "。"]):
        score += 0.5

    if len(context) >= 120:
        score += 1.0
    if re.search(r"[\u4e00-\u9fff]{20,}", context):
        score += 1.0

    if question.startswith("谁主编了现代采矿手册"):
        score -= 4.0
    if re.fullmatch(r"[\d.]+", answer):
        score -= 2.0
    if len(answer) <= 4 and re.search(r"^\d", answer):
        score -= 1.0
    if any(token in question for token in ["ISBN", "页码"]):
        score -= 2.0
    if any(token in answer for token in ["ISBN", "页码"]):
        score -= 2.0
    if "����" in answer or "����" in question:
        score -= 4.0

    return score


def make_record(
    question: str,
    answer: str,
    context: List[str],
    source: str,
    quality_score: float,
    ground_truth: str | None = None,
) -> Dict[str, Any]:
    record = {
        "question": question,
        "answer": answer,
        "context": context,
        "source": source,
        "quality_score": round(float(quality_score), 2),
        "quality_tier": "high" if quality_score >= 7.5 else "medium" if quality_score >= 5.0 else "low",
    }
    if ground_truth is not None:
        record["ground_truth"] = ground_truth
    return record


def build_curated_dataset() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    manual_items = load_json(EVAL_FILE)
    autoqg_items = load_json(AUTOQG_FILE)

    selected: List[Dict[str, Any]] = []
    seen_questions = set()

    for item in manual_items:
        question = item["question"].strip()
        key = normalize_question(question)
        if key in seen_questions:
            continue
        seen_questions.add(key)
        selected.append(
            make_record(
                question=question,
                answer=item["answer"].strip(),
                context=list(item.get("context", [])),
                source="mining_evaluation_data.json",
                quality_score=10.0,
                ground_truth=item.get("ground_truth"),
            )
        )

    scored_autoqg: List[Tuple[float, Dict[str, Any]]] = []
    for item in autoqg_items:
        question = item.get("question", "")
        normalized_question = normalize_question(question)
        if normalized_question in seen_questions:
            continue
        if not question_is_plausible(normalized_question):
            continue
        score = score_autoqg_item(item)
        scored_autoqg.append((score, item))

    scored_autoqg.sort(key=lambda pair: (-pair[0], normalize_question(pair[1].get("question", ""))))

    for score, item in scored_autoqg:
        if len(selected) >= 100:
            break
        question = normalize_question(item.get("question", ""))
        if question in seen_questions:
            continue
        seen_questions.add(question)
        selected.append(
            make_record(
                question=question,
                answer=str(item.get("answer", "")).strip(),
                context=list(item.get("context", [])),
                source="mining_autoqg_150.json",
                quality_score=score,
            )
        )

    summary = {
        "total_selected": len(selected),
        "manual_eval_count": sum(1 for item in selected if item["source"] == "mining_evaluation_data.json"),
        "autoqg_count": sum(1 for item in selected if item["source"] == "mining_autoqg_150.json"),
        "high_tier_count": sum(1 for item in selected if item["quality_tier"] == "high"),
        "medium_tier_count": sum(1 for item in selected if item["quality_tier"] == "medium"),
        "low_tier_count": sum(1 for item in selected if item["quality_tier"] == "low"),
        "autoqg_scored_candidates": len(scored_autoqg),
        "autoqg_high_tier_candidates": sum(1 for score, _ in scored_autoqg if score >= 7.5),
        "note": "The source pool does not contain 100 truly high-confidence auto-generated items; this file is a curated 100-item working set with quality tiers.",
    }
    return selected, summary


def main() -> None:
    curated, summary = build_curated_dataset()
    save_json(OUTPUT_FILE, curated)
    save_json(SUMMARY_FILE, summary)
    print(f"Saved {len(curated)} items to {OUTPUT_FILE}")
    print(f"Summary saved to {SUMMARY_FILE}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()