# -*- coding: utf-8 -*-
"""Split the curated 55-item mining QA set into train/val/test files."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "rag_assesment" / "mining_curated_55.json"
MERGED_FILE = ROOT / "rag_assesment" / "mining_qa_55.json"
TRAIN_FILE = ROOT / "rag_assesment" / "mining_qa_train.json"
VAL_FILE = ROOT / "rag_assesment" / "mining_qa_val.json"
TEST_FILE = ROOT / "rag_assesment" / "mining_qa_test.json"
SUMMARY_FILE = ROOT / "rag_assesment" / "mining_qa_55.summary.json"

SEED = 42
TRAIN_COUNT = 45
VAL_COUNT = 5
TEST_COUNT = 5


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the original QA schema stable across all split files."""
    question = str(item.get("question", "")).strip()
    answer = str(item.get("answer", "")).strip()
    context = item.get("context") or []
    if not isinstance(context, list):
        context = [str(context)]
    context = [str(text).strip() for text in context if str(text).strip()]

    ground_truth = item.get("ground_truth")
    if ground_truth is None or str(ground_truth).strip() == "":
        ground_truth = answer

    return {
        "question": question,
        "answer": answer,
        "context": context,
        "ground_truth": str(ground_truth).strip(),
    }


def main() -> None:
    source_items = load_json(SOURCE_FILE)
    merged_items = [normalize_item(item) for item in source_items]

    if len(merged_items) != 55:
        raise ValueError(f"Expected 55 items in {SOURCE_FILE}, got {len(merged_items)}")

    rng = random.Random(SEED)
    shuffled_items = merged_items[:]
    rng.shuffle(shuffled_items)

    train_items = shuffled_items[:TRAIN_COUNT]
    val_items = shuffled_items[TRAIN_COUNT:TRAIN_COUNT + VAL_COUNT]
    test_items = shuffled_items[TRAIN_COUNT + VAL_COUNT:TRAIN_COUNT + VAL_COUNT + TEST_COUNT]

    if len(train_items) != TRAIN_COUNT or len(val_items) != VAL_COUNT or len(test_items) != TEST_COUNT:
        raise ValueError("Split sizes do not match the requested counts")

    save_json(MERGED_FILE, merged_items)
    save_json(TRAIN_FILE, train_items)
    save_json(VAL_FILE, val_items)
    save_json(TEST_FILE, test_items)

    summary = {
        "source_file": str(SOURCE_FILE),
        "total_count": len(merged_items),
        "train_count": len(train_items),
        "val_count": len(val_items),
        "test_count": len(test_items),
        "seed": SEED,
        "split_rule": "random shuffle, then 45/5/5 split",
        "schema": ["question", "answer", "context", "ground_truth"],
        "note": "The curated 55-item set already includes the 19 manual evaluation pairs; total unique count remains 55.",
    }
    save_json(SUMMARY_FILE, summary)

    print(f"Saved merged dataset to {MERGED_FILE}")
    print(f"Saved train split to {TRAIN_FILE}")
    print(f"Saved val split to {VAL_FILE}")
    print(f"Saved test split to {TEST_FILE}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()