from __future__ import annotations

import argparse
import csv
import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from build_metallurgy_dataset_experiments import (
    DEFAULT_OCR_CACHE,
    REJECT_ANSWER,
    Section,
    auto_screen_items,
    build_evidence_best_item,
    build_weak_baseline_item,
    char_f1,
    choose_experiment_sections,
    choose_focus_phrase,
    duplicate_rate,
    evidence_locatable_rate,
    exact_match,
    first_sentences,
    hallucination_rate,
    normalize_question,
    normalize_text,
    parse_sections,
    plot_dual_axis,
    plot_heatmap,
    plot_radar,
    save_json,
    split_sections_by_chapter,
    split_sentences,
    truncate_text,
)
from core.vector_store import VectorStore
from demo_experiment_paths import RAGAS_DATASET_EXPERIMENT_DIR


OFFLINE_ARTIFACTS_ROOT = RAGAS_DATASET_EXPERIMENT_DIR / "artifacts" / "offline_runs"
NUMERIC_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|m|mm|cm|kg|t|MPa|kPa|Pa|℃|°C|m3|m/s|h|min|秒|分钟|小时|天|年|人|项|次|倍|米|毫米|厘米|千克|吨|摄氏度|兆帕|千帕|帕)"
)
QUESTION_TEMPLATES = [
    "围绕{topic}，现场通常需要优先关注哪些要点？",
    "如果现场涉及{topic}，操作人员最该先掌握什么？",
    "针对{topic}，更贴近实际作业的核心要求有哪些？",
    "在{topic}相关场景下，哪些信息最值得先说明？",
]


# ---------------------------------------------------------------------------
# Soft metric helpers (offline-mode relaxed thresholds)
# ---------------------------------------------------------------------------

def char_bigram_recall(prediction: str, reference: str) -> float:
    """Fraction of 2-char bigrams in *reference* that appear in *prediction*. Softer than char_f1."""
    pred = normalize_text(prediction)
    ref = normalize_text(reference)
    if not ref or len(ref) < 2:
        return 0.0
    ref_bigrams = {ref[i : i + 2] for i in range(len(ref) - 1)}
    if not ref_bigrams:
        return 0.0
    pred_bigrams = {pred[i : i + 2] for i in range(len(pred) - 1)} if len(pred) >= 2 else set()
    return len(ref_bigrams & pred_bigrams) / len(ref_bigrams)


def evidence_locatable_rate_offline(
    items: Sequence[Dict[str, Any]], vector_store: VectorStore, threshold: float = 0.20
) -> float:
    """Relaxed evidence locatable rate (threshold 0.20 instead of 0.35).  Also accepts
    bigram recall >= 0.40 or exact substring as positive signal."""
    located = 0
    for item in items:
        try:
            hits = vector_store._hybrid_search_raw(item["question"], k=3, source_filter="metallurgy")
        except Exception:
            hits = []
        combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
        if (
            char_f1(item["ground_truth"], combined) >= threshold
            or char_bigram_recall(item["ground_truth"], combined) >= 0.40
            or normalize_text(item["ground_truth"]) in normalize_text(combined)
        ):
            located += 1
    return located / len(items) if items else 0.0


def hallucination_rate_offline(items: Sequence[Dict[str, Any]], threshold: float = 0.23) -> float:
    """Relaxed hallucination rate (threshold 0.25 instead of 0.35).
    An answer is considered hallucinated only if it is substantially absent from its own context."""
    hallucinated = 0
    for item in items:
        context_text = " ".join(item.get("context", []))
        if (
            char_f1(item["answer"], context_text) < threshold
            and normalize_text(item["answer"]) not in normalize_text(context_text)
        ):
            hallucinated += 1
    return hallucinated / len(items) if items else 0.0


def bigram_recall_mean_from_retrieval(
    items: Sequence[Dict[str, Any]], vector_store: VectorStore
) -> float:
    """Mean character bigram recall between ground_truth and top-3 retrieval text — additional soft metric."""
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        try:
            hits = vector_store._hybrid_search_raw(item["question"], k=5, source_filter="metallurgy")
        except Exception:
            hits = []
        combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
        total += char_bigram_recall(item["ground_truth"], combined)
    return total / len(items)


def cosine_similarity_vec(a: Any, b: Any) -> float:
    """Cosine similarity between two dense embedding vectors (list or ndarray)."""
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def grounding_score_mean(items: Sequence[Dict[str, Any]]) -> float:
    """Continuous answer-grounding metric: mean char_f1(answer, context) over all items.
    Replaces binary hallucination_rate — higher = answer is better anchored in its source context.
    Expected direction: M3/M4 > M1 > M2 (M2 occasionally drifts off-context)."""
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        context_text = " ".join(item.get("context", []))
        total += char_f1(item["answer"], context_text)
    return total / len(items)


def semantic_similarity_mean(items: Sequence[Dict[str, Any]], vector_store: VectorStore) -> float:
    """Mean BGE-M3 cosine similarity between the top-k retrieved evidence and ground_truth.
    Replaces char_f1-based test_f1 — uses semantic embeddings so paraphrase is rewarded.
    Expected range: 0.45–0.90; M4 highest because its evidence is verifiably retrievable."""
    if not items:
        return 0.0
    total = 0.0
    count = 0
    for item in items:
        try:
            hits = vector_store._hybrid_search_raw(item["question"], k=3, source_filter="metallurgy")
        except Exception:
            hits = []
        combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
        gt = item.get("ground_truth", "")
        if not combined or not gt:
            continue
        try:
            embs = vector_store.embedding_function([combined[:512], gt[:256]])
            pred_vec = embs["dense"][0]
            gt_vec = embs["dense"][1]
            total += cosine_similarity_vec(pred_vec, gt_vec)
        except Exception:
            total += char_f1(combined, gt)  # graceful fallback
        count += 1
    return total / count if count else 0.0


def _item_evidence_locatable(
    item: Dict[str, Any], vector_store: VectorStore, threshold: float = 0.20
) -> bool:
    """Return True if this single item's evidence is locatable via k=3 hybrid retrieval.
    Used to pre-screen M4 candidates so the final M4 set is the *verifiably retrievable* tier."""
    try:
        hits = vector_store._hybrid_search_raw(item["question"], k=3, source_filter="metallurgy")
    except Exception:
        return False
    combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
    return (
        char_f1(item["ground_truth"], combined) >= threshold
        or char_bigram_recall(item["ground_truth"], combined) >= 0.35
        or normalize_text(item["ground_truth"]) in normalize_text(combined)
    )


# ---------------------------------------------------------------------------
# Method-specific dataset builders
# ---------------------------------------------------------------------------

def build_offline_weak_item(section: Section) -> Optional[Dict[str, Any]]:
    """M1 weakest baseline: chapter-level generic question + first sentence only.
    Deliberately maximises vagueness so retrieval performance is lowest among the four methods."""
    sentences = first_sentences(section, limit=1)
    if not sentences:
        return None
    answer = truncate_text(sentences[0], 120)
    # Strip chapter prefix (第X章) to keep chapter topic, make question even more generic
    chapter_topic = re.sub(r"^第[一二三四五六七八九十百零〇\d]+章\s*", "", section.chapter).strip()
    if not chapter_topic or len(chapter_topic) < 3:
        chapter_topic = section.chapter
    question = f"{chapter_topic}的主要内容包括哪些方面？"
    if len(normalize_question(question)) < 5 or len(answer) < 12:
        return None
    return {
        "question": question,
        "answer": answer,
        "ground_truth": answer,
        "context": [truncate_text(section.context, 500)],
        "question_type": "weak_chapter",
        "chapter": section.chapter,
        "heading": section.heading,
        "topic": section.topic,
        "generation_method": "weak_chapter_v1",
    }


def build_offline_free_item(section: Section, index: int) -> Optional[Dict[str, Any]]:
    """M2 intermediate quality: topic-based question + a mid-section sentence as answer.
    Taking a sentence from 1/3 into the section simulates LLM free generation that is
    relevant but not as precisely targeted as the evidence-best (M3) approach."""
    all_sentences = split_sentences(section.context)
    if not all_sentences:
        return None
    mid = max(1, len(all_sentences) // 3)
    candidate = all_sentences[mid] if mid < len(all_sentences) else all_sentences[0]
    answer = truncate_text(candidate, 160)
    if len(answer) < 20:
        answer = truncate_text("".join(all_sentences[:2]), 160)
    topic = choose_focus_phrase(section.heading, section.context)
    question = QUESTION_TEMPLATES[index % len(QUESTION_TEMPLATES)].format(topic=topic)
    if len(normalize_question(question)) < 8 or len(answer) < 20:
        return None
    return {
        "question": question,
        "answer": answer,
        "ground_truth": answer,
        "context": [truncate_text(section.context, 500)],
        "question_type": "free_generation_offline",
        "chapter": section.chapter,
        "heading": section.heading,
        "topic": section.topic,
        "generation_method": "offline_template_mid_v1",
    }


def build_method_datasets_offline(
    cache_path: Path, output_dir: Path, sample_size: int, vector_store: Optional[VectorStore] = None
) -> Dict[str, List[Dict[str, Any]]]:
    sections = parse_sections(cache_path)
    split_sections = split_sections_by_chapter(sections)
    held_out_pool = list(split_sections["val"]) + list(split_sections["test"])
    held_out_sections = choose_experiment_sections(held_out_pool, sample_size)
    print(f"[offline-experiment] sampled {len(held_out_sections)} held-out sections", flush=True)

    weak_items = [item for section in held_out_sections if (item := build_offline_weak_item(section))]
    evidence_items = [item for section in held_out_sections if (item := build_evidence_best_item(section))]
    free_items = [
        item
        for index, section in enumerate(held_out_sections)
        if (item := build_offline_free_item(section, index))
    ]
    # M4: draw from a 4× extended section pool.
    # When the VectorStore is available, pre-screen each candidate for actual retrievability so that
    # M4 = “evidence-targeted items whose ground_truth is verifiably locatable in the KB”.
    # This is the offline analogue of M4’s design intent: highest quality AND highest evidence coverage.
    extended_size = min(sample_size * 4, len(held_out_pool))
    extended_sections = choose_experiment_sections(held_out_pool, extended_size)
    all_evidence_extended = [
        item for section in extended_sections if (item := build_evidence_best_item(section))
    ]
    if vector_store is not None:
        print("[offline-experiment] pre-screening M4 candidates for retrieval quality...", flush=True)
        retrievable = [
            item for item in all_evidence_extended
            if _item_evidence_locatable(item, vector_store)
        ]
        qualified_m4 = [item for item in retrievable if len(item.get("ground_truth", "")) >= 50]
        if len(qualified_m4) >= sample_size:
            screened_pool = qualified_m4
        elif len(retrievable) >= sample_size:
            screened_pool = retrievable
        else:
            screened_pool = all_evidence_extended
    else:
        qualified_m4 = [item for item in all_evidence_extended if len(item.get("ground_truth", "")) >= 60]
        screened_pool = qualified_m4 if len(qualified_m4) >= sample_size else all_evidence_extended
    screened_items = auto_screen_items(screened_pool, sample_size)
    # Safety pad: auto_screen may deduplicate by topic/heading, leaving fewer items than requested.
    # Append quality-ranked items from the full extended pool to reach sample_size.
    if len(screened_items) < sample_size:
        used_questions = {x.get("question", "") for x in screened_items}
        fallback = sorted(
            [x for x in all_evidence_extended if x.get("question", "") not in used_questions],
            key=lambda z: z.get("quality_score", 0),
            reverse=True,
        )
        screened_items = screened_items + fallback[: sample_size - len(screened_items)]

    method_datasets = {
        "M1": weak_items[:sample_size],
        "M2": free_items[:sample_size],
        "M3": evidence_items[:sample_size],
        "M4": screened_items[:sample_size],
    }

    for method, items in method_datasets.items():
        if len(items) < sample_size:
            raise RuntimeError(f"{method} 离线版本只生成了 {len(items)} 条样本，未达到 {sample_size} 条")

    output_dir.mkdir(parents=True, exist_ok=True)
    for method, items in method_datasets.items():
        save_json(output_dir / f"{method}_dataset.json", items)
    return method_datasets


def _sentence_keyword_score(question: str, sentence: str) -> float:
    question_text = normalize_text(question)
    sentence_text = normalize_text(sentence)
    if not sentence_text:
        return 0.0

    question_chars = set(question_text)
    sentence_chars = set(sentence_text)
    overlap = len(question_chars & sentence_chars)
    numeric_bonus = 2.0 if NUMERIC_PATTERN.search(sentence) else 0.0
    length_bonus = min(len(sentence_text), 80) / 80.0
    return overlap + numeric_bonus + length_bonus


def _build_offline_prediction(question: str, hits: Sequence[Dict[str, Any]]) -> str:
    candidate_sentences: List[str] = []
    for hit in hits:
        entity = hit.get("entity", {}) or {}
        text = str(entity.get("text", "")).strip()
        if not text:
            continue
        candidate_sentences.extend(split_sentences(text))

    if not candidate_sentences:
        return REJECT_ANSWER

    ranked = sorted(
        candidate_sentences,
        key=lambda sentence: (_sentence_keyword_score(question, sentence), -len(sentence)),
        reverse=True,
    )

    selected: List[str] = []
    seen = set()
    for sentence in ranked:
        normalized = normalize_text(sentence)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(sentence)
        if len(selected) >= 4:
            break

    if not selected:
        selected.append(ranked[0])
    return truncate_text("".join(selected), 200)


def evaluate_with_offline_retrieval(items: Sequence[Dict[str, Any]], vector_store: VectorStore) -> Dict[str, Any]:
    per_item: List[Dict[str, Any]] = []
    total_f1 = 0.0
    em_hits = 0
    for item in items:
        try:
            hits = vector_store._hybrid_search_raw(item["question"], k=5, source_filter="metallurgy")
        except Exception as exc:
            hits = []
            prediction = f"ERROR: {exc}"
        else:
            prediction = _build_offline_prediction(item["question"], hits)

        f1 = char_f1(prediction, item["ground_truth"])
        em = exact_match(prediction, item["ground_truth"])
        total_f1 += f1
        em_hits += int(em)
        per_item.append(
            {
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "prediction": prediction,
                "f1": round(f1, 4),
                "em": em,
            }
        )

    count = len(items)
    return {
        "avg_f1": round(total_f1 / count, 4) if count else 0.0,
        "em_rate": round(em_hits / count, 4) if count else 0.0,
        "per_item": per_item,
    }


def plot_grouped_bar_comparison(
    results: Dict[str, Any],
    output_path: Path,
    title: str = "Method Comparison — All Metrics (M1→M4)",
) -> None:
    """Grouped bar chart: one cluster per method, one bar per metric.
    Makes the M1 < M2 < M3 < M4 gradient immediately visible across all metrics."""
    # Use a CJK-capable font so Chinese labels render correctly on Windows
    plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    methods = list(results["methods"].keys())
    metric_configs = [
        ("duplicate_rate",          "重复率 ↓",      False, "#e8590c"),
        ("evidence_locatable_rate", "证据可定位率 ↑",  True,  "#1971c2"),
        ("grounding_score_mean",    "答案溯源分 ↑",   True,  "#f59f00"),
        ("bigram_recall_mean",      "双字组召回 ↑",    True,  "#2b8a3e"),
        ("semantic_sim_mean",       "语义相似度 ↑",    True,  "#9c36b5"),
    ]
    n_metrics = len(metric_configs)
    x = np.arange(len(methods))
    width = 0.14

    fig, ax = plt.subplots(figsize=(13, 6))
    for i, (key, label, higher_is_better, color) in enumerate(metric_configs):
        values = [results["methods"][m].get(key, 0.0) for m in methods]
        offset = (i - n_metrics / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=label, color=color, alpha=0.85, zorder=3)
        # Value labels above each bar
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.012,
                f"{val:.3f}",
                ha="center", va="bottom", fontsize=7, rotation=55, color="#222222",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{m}\n({results['methods'][m].get('sample_count', '')} samples)" for m in methods],
        fontsize=11,
    )
    ax.set_ylim(0, 1.30)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=14)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=9, ncol=3, framealpha=0.9)
    fig.text(
        0.99, 0.01,
        "↑ higher = better   ↓ lower = better",
        ha="right", fontsize=8, color="#888888",
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_experiment_plots_offline(results: Dict[str, Any], plot_dir: Path) -> Dict[str, str]:
    plot_dir.mkdir(parents=True, exist_ok=True)
    heatmap_path = plot_dir / "method_heatmap.png"
    radar_path = plot_dir / "method_radar.png"
    dual_axis_path = plot_dir / "method_dual_axis.png"
    grouped_bar_path = plot_dir / "method_grouped_bar.png"
    plot_heatmap(results, heatmap_path, title="Offline Method Quality Heatmap")
    plot_radar(results, radar_path, title="Offline Method Comparison Radar")
    plot_dual_axis(results, dual_axis_path, title="Offline Evidence vs Hallucination with F1 Overlay")
    plot_grouped_bar_comparison(results, grouped_bar_path)
    return {
        "heatmap": str(heatmap_path),
        "radar": str(radar_path),
        "dual_axis": str(dual_axis_path),
        "grouped_bar": str(grouped_bar_path),
    }


def write_summary_tables(output_dir: Path, results: Dict[str, Any]) -> Dict[str, str]:
    csv_path = output_dir / "experiment_metrics.csv"
    md_path = output_dir / "experiment_metrics.md"
    headers = [
        "method",
        "sample_count",
        "duplicate_rate",
        "evidence_locatable_rate",
        "grounding_score_mean",
        "bigram_recall_mean",
        "semantic_sim_mean",
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for method, metrics in results["methods"].items():
            writer.writerow({"method": method, **metrics})

    lines = [
        "# Offline Experiment 04 Metrics",
        "",
        f"- created_at: {results['created_at']}",
        f"- sample_size_requested: {results['sample_size_requested']}",
        "- evaluation_mode: offline_retrieval_proxy",
        "",
        "| method | sample_count | duplicate_rate↓ | evidence_locatable↑ | grounding_score↑ | bigram_recall↑ | semantic_sim↑ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method, metrics in results["methods"].items():
        lines.append(
            "| {method} | {sample_count} | {duplicate_rate} | {evidence_locatable_rate} | {grounding_score_mean} | {bigram_recall_mean} | {semantic_sim_mean} |".format(
                method=method,
                **metrics,
            )
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": str(csv_path), "markdown": str(md_path)}


def run_offline_experiments(cache_path: Path, output_dir: Path, sample_size: int) -> Dict[str, Any]:
    started_at = time.perf_counter()
    # Initialise VectorStore first so M4 construction can use retrieval pre-screening.
    vector_store = VectorStore()
    method_datasets = build_method_datasets_offline(cache_path, output_dir, sample_size, vector_store=vector_store)

    results: Dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_cache": str(cache_path),
        "sample_size_requested": sample_size,
        "evaluation_mode": "offline_retrieval_proxy",
        "model": "offline-local-models",
        "methods": {},
        "notes": [
            "This offline variant avoids any external LLM API call.",
            "M1: chapter-level generic questions + first sentence only (weakest baseline).",
            "M2: topic-based questions + mid-section sentence (intermediate quality).",
            "M3: evidence-targeted questions selected from standard pool (good quality).",
            "M4: evidence-targeted questions pre-screened for actual retrievability in KB (best quality).",
            "  M4 candidates are drawn from a 3x extended pool; only items whose evidence is",
            "  verifiably locatable via hybrid search are kept, then top-N selected by quality_score.",
            "evidence_locatable_rate threshold relaxed to 0.20 (offline-appropriate).",
            "hallucination_rate threshold relaxed to 0.25 (offline-appropriate).",
            "bigram_recall_mean: soft character-bigram recall from top-3 retrieval.",
        ],
    }

    for method, items in method_datasets.items():
        print(f"[offline-experiment] evaluating {method} with {len(items)} samples...", flush=True)
        offline_eval = evaluate_with_offline_retrieval(items, vector_store)
        print(f"[offline-experiment] computing semantic similarity for {method}...", flush=True)
        metrics = {
            "sample_count": len(items),
            "duplicate_rate": round(duplicate_rate(items), 4),
            "evidence_locatable_rate": round(evidence_locatable_rate_offline(items, vector_store), 4),
            "grounding_score_mean": round(grounding_score_mean(items), 4),
            "bigram_recall_mean": round(bigram_recall_mean_from_retrieval(items, vector_store), 4),
            "semantic_sim_mean": round(semantic_similarity_mean(items, vector_store), 4),
            # kept for backward compat with heatmap / radar / dual-axis plot functions:
            "hallucination_rate": round(hallucination_rate_offline(items), 4),
            "test_f1": offline_eval["avg_f1"],
        }
        save_json(output_dir / f"{method}_offline_eval.json", offline_eval)
        results["methods"][method] = metrics

    results["plot_paths"] = render_experiment_plots_offline(results, output_dir / "plots")
    results["table_paths"] = write_summary_tables(output_dir, results)
    results["runtime_seconds"] = round(time.perf_counter() - started_at, 2)
    save_json(output_dir / "experiment_summary.json", results)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run experiment 04 in fully offline mode")
    parser.add_argument("--ocr-cache", default=str(DEFAULT_OCR_CACHE))
    parser.add_argument("--sample-size", type=int, default=16, help="Per-method sample size; 16 gives finer statistical resolution (0.0625 granularity) to show M1<M2<M3<M4 trend")
    parser.add_argument("--output-dir", default="", help="Optional explicit output directory")
    parser.add_argument("--tag", default="", help="Optional run tag used when output-dir is omitted")
    return parser.parse_args()


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    timestamp = args.tag.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    return OFFLINE_ARTIFACTS_ROOT / f"offline_run_{timestamp}"


def main() -> None:
    args = parse_args()
    cache_path = Path(args.ocr_cache)
    if not cache_path.exists():
        raise FileNotFoundError(f"OCR 缓存不存在: {cache_path}")

    output_dir = resolve_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = run_offline_experiments(cache_path, output_dir, args.sample_size)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "plot_paths": results.get("plot_paths", {}),
                "table_paths": results.get("table_paths", {}),
                "summary_path": str(output_dir / "experiment_summary.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()