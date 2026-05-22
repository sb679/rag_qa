# -*- coding:utf-8 -*-
"""Offline internal benchmark for chunk-size strategies.

This script compares chunk-size configurations under the same corpus and test set,
using an offline lexical retrieval proxy only. It does not depend on Milvus,
rerankers, or LLM generation, so the result is suitable for stable internal
comparison rather than absolute thesis-level precision/recall claims.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

current_dir = os.path.dirname(os.path.abspath(__file__))
rag_qa_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, rag_qa_root)

from base import Config  # noqa: E402
from core.document_processor import process_documents  # noqa: E402


ROOT = Path(rag_qa_root)
ARTIFACTS_DIR = (
    ROOT / "teacher_demo_experiments" / "01_chunking_performance" / "artifacts" / "chunk_config_internal"
)
DEFAULT_DATA_DIR = ROOT / "user_data" / "knowledge_files" / "metallurgy"
DEFAULT_DATASET = (
    ROOT
    / "teacher_demo_experiments"
    / "04_ragas_dataset_quality"
    / "artifacts"
    / "generated_datasets"
    / "metallurgy_safety_testset.json"
)
DEFAULT_OUTPUT = ARTIFACTS_DIR / "chunk_config_internal_report.json"
DEFAULT_CONFIGS = "150:600,200:800,300:1200,400:1600,500:2000"

conf = Config()


@dataclass
class SampleResult:
    latency_sec: float
    context_precision_proxy: Optional[float]
    context_recall_proxy: Optional[float]
    retrieval_f1_proxy: Optional[float]
    timed_out: bool
    errored: bool
    error_message: str = ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _char_ngrams(text: str, n: int = 2) -> set:
    text = _normalize_text(text)
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _directional_overlap_ratio(left: str, right: str) -> float:
    left_grams = _char_ngrams(left)
    right_grams = _char_ngrams(right)
    if not left_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams)


def _f1_from_pr(precision: float, recall: float) -> float:
    if precision + recall <= 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？；\n]+", text or "")
    return [part.strip() for part in parts if len(part.strip()) >= 8]


def _question_chunk_score(question: str, chunk_text: str) -> float:
    q_grams = _char_ngrams(question)
    c_grams = _char_ngrams(chunk_text)
    if not q_grams or not c_grams:
        return 0.0
    overlap = len(q_grams & c_grams) / len(q_grams)
    # Bias toward shorter, more focused chunks when overlap is similar.
    focus_bonus = min(0.15, 60.0 / max(len(chunk_text), 60))
    return overlap + focus_bonus


def _retrieve_context_offline(question: str, documents, retrieval_k: int, candidate_m: int) -> str:
    scored = []
    for doc in documents:
        chunk_text = (doc.page_content or "").strip()
        if not chunk_text:
            continue
        score = _question_chunk_score(question, chunk_text)
        if score <= 0:
            continue
        parent_content = (doc.metadata.get("parent_content") or chunk_text).strip()
        scored.append((score, parent_content))

    if not scored:
        return ""

    scored.sort(key=lambda item: item[0], reverse=True)
    top_children = scored[: max(retrieval_k, candidate_m)]

    unique_parents = []
    seen = set()
    for _, parent_content in top_children:
        if parent_content and parent_content not in seen:
            unique_parents.append(parent_content)
            seen.add(parent_content)
        if len(unique_parents) >= candidate_m:
            break

    return "\n".join(unique_parents)


def _evaluate_single(question: str, expected_context: str, documents, retrieval_k: int, candidate_m: int) -> SampleResult:
    started = time.perf_counter()
    try:
        retrieved_context = _retrieve_context_offline(question, documents, retrieval_k, candidate_m)
    except Exception as exc:
        return SampleResult(
            latency_sec=max(0.0, time.perf_counter() - started),
            context_precision_proxy=None,
            context_recall_proxy=None,
            retrieval_f1_proxy=None,
            timed_out=False,
            errored=True,
            error_message=str(exc),
        )

    latency = max(0.0, time.perf_counter() - started)

    context_precision_proxy = _directional_overlap_ratio(retrieved_context, expected_context)
    context_recall_proxy = _directional_overlap_ratio(expected_context, retrieved_context)
    retrieval_f1_proxy = _f1_from_pr(context_precision_proxy, context_recall_proxy)

    return SampleResult(
        latency_sec=latency,
        context_precision_proxy=context_precision_proxy,
        context_recall_proxy=context_recall_proxy,
        retrieval_f1_proxy=retrieval_f1_proxy,
        timed_out=False,
        errored=False,
        error_message="",
    )


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), 4)


def _parse_configs(raw: str) -> List[Tuple[int, int]]:
    configs = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        child_str, parent_str = token.split(":", 1)
        configs.append((int(child_str), int(parent_str)))
    if not configs:
        raise ValueError("No valid chunk configs parsed")
    return configs


def _load_samples(dataset_path: Path, max_queries: int) -> List[Dict[str, str]]:
    records = json.loads(dataset_path.read_text(encoding="utf-8"))
    samples: List[Dict[str, str]] = []
    for record in records:
        question = str(record.get("question") or "").strip()
        raw_context = record.get("context") or ""
        if isinstance(raw_context, list):
            context = "\n".join(str(item).strip() for item in raw_context if str(item).strip())
        else:
            context = str(raw_context).strip()
        source = str(record.get("source") or "metallurgy").strip() or "metallurgy"
        if question.startswith("问题:"):
            question = question[3:].strip()
        if not question or not context:
            continue
        samples.append({"question": question, "context": context, "source": source})
        if len(samples) >= max_queries:
            break
    return samples


def _chunk_stats(documents) -> Dict[str, float]:
    lengths = [len(doc.page_content or "") for doc in documents]
    parent_ids = {doc.metadata.get("parent_id") for doc in documents if doc.metadata.get("parent_id")}
    if not lengths:
        return {
            "chunk_count": 0,
            "parent_count": 0,
            "avg_chars": 0.0,
            "median_chars": 0.0,
            "p90_chars": 0.0,
            "under_120_ratio": 0.0,
        }
    sorted_lengths = sorted(lengths)
    p90_index = min(len(sorted_lengths) - 1, int(len(sorted_lengths) * 0.9))
    return {
        "chunk_count": len(lengths),
        "parent_count": len(parent_ids),
        "avg_chars": round(sum(lengths) / len(lengths), 2),
        "median_chars": round(statistics.median(lengths), 2),
        "p90_chars": round(sorted_lengths[p90_index], 2),
        "under_120_ratio": round(sum(1 for size in lengths if size < 120) / len(lengths), 4),
    }


def _evaluate_config(
    data_dir: Path,
    samples: List[Dict[str, str]],
    parent_chunk_size: int,
    child_chunk_size: int,
    chunk_overlap: int,
    retrieval_k: int,
    candidate_m: int,
) -> Dict[str, object]:
    chunks = process_documents(
        str(data_dir),
        parent_chunk_size=parent_chunk_size,
        child_chunk_size=child_chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunk_stats = _chunk_stats(chunks)

    run_results: List[SampleResult] = []
    for index, sample in enumerate(samples, start=1):
        run_results.append(
            _evaluate_single(
                question=sample["question"],
                expected_context=sample["context"],
                documents=chunks,
                retrieval_k=retrieval_k,
                candidate_m=candidate_m,
            )
        )
        latest = run_results[-1]
        state = "ok"
        if latest.timed_out:
            state = "timeout"
        elif latest.errored:
            state = "error"
        print(
            f"[{child_chunk_size}+{parent_chunk_size}] sample {index}/{len(samples)} "
            f"latency={latest.latency_sec:.1f}s state={state}",
            flush=True,
        )

    latencies = [item.latency_sec for item in run_results]
    success_results = [item for item in run_results if not item.errored and not item.timed_out]
    timeout_count = sum(1 for item in run_results if item.timed_out)
    error_count = sum(1 for item in run_results if item.errored)

    report_item: Dict[str, object] = {
        "label": f"{child_chunk_size}+{parent_chunk_size}",
        "parent_chunk_size": parent_chunk_size,
        "child_chunk_size": child_chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunk_stats": chunk_stats,
        "samples": len(samples),
        "valid_samples": len(success_results),
        "timeouts": timeout_count,
        "errors": error_count,
        "stability_rate": round(len(success_results) / len(samples), 4) if samples else 0.0,
        "latency_mean_sec": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "latency_p95_sec": round(_p95(latencies), 3) if latencies else 0.0,
        "context_precision_proxy_mean": _mean([item.context_precision_proxy for item in success_results]),
        "context_recall_proxy_mean": _mean([item.context_recall_proxy for item in success_results]),
        "retrieval_f1_proxy_mean": _mean([item.retrieval_f1_proxy for item in success_results]),
    }
    return report_item


def _normalize_series(values: Sequence[float], reverse: bool = False) -> List[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if abs(high - low) < 1e-9:
        return [1.0 for _ in values]
    normalized = [(value - low) / (high - low) for value in values]
    if reverse:
        normalized = [1.0 - value for value in normalized]
    return normalized


def _attach_internal_scores(configs: List[Dict[str, object]]) -> None:
    recall_values = [float(item.get("context_recall_proxy_mean") or 0.0) for item in configs]
    precision_values = [float(item.get("context_precision_proxy_mean") or 0.0) for item in configs]
    f1_values = [float(item.get("retrieval_f1_proxy_mean") or 0.0) for item in configs]
    stability_values = [float(item.get("stability_rate") or 0.0) for item in configs]
    latency_values = [float(item.get("latency_mean_sec") or 0.0) for item in configs]

    norm_recall = _normalize_series(recall_values)
    norm_precision = _normalize_series(precision_values)
    norm_f1 = _normalize_series(f1_values)
    norm_stability = _normalize_series(stability_values)
    norm_latency = _normalize_series(latency_values, reverse=True)

    for index, item in enumerate(configs):
        components = {
            "recall": round(norm_recall[index], 4),
            "precision": round(norm_precision[index], 4),
            "retrieval_f1": round(norm_f1[index], 4),
            "stability": round(norm_stability[index], 4),
            "latency_efficiency": round(norm_latency[index], 4),
        }
        score = (
            0.35 * components["recall"]
            + 0.25 * components["precision"]
            + 0.20 * components["retrieval_f1"]
            + 0.10 * components["stability"]
            + 0.10 * components["latency_efficiency"]
        )
        item["internal_score_components"] = components
        item["internal_composite_score"] = round(score * 100, 2)


def _normalize_metric_dict(configs: List[Dict[str, object]], key: str, reverse: bool = False) -> List[float]:
    values = [float(item.get(key) or 0.0) for item in configs]
    return _normalize_series(values, reverse=reverse)


def _granularity_balance_values(configs: List[Dict[str, object]]) -> List[float]:
    avg_chars_values = [float((item.get("chunk_stats") or {}).get("avg_chars") or 0.0) for item in configs]
    chunk_count_values = [float((item.get("chunk_stats") or {}).get("chunk_count") or 0.0) for item in configs]

    # Engineering preference: keep child chunks around the current production scale,
    # while avoiding index explosion from overly fine-grained splits.
    target_avg_chars = 260.0
    target_chunk_count = 1600.0

    avg_scores = []
    for value in avg_chars_values:
        score = max(0.0, 1.0 - abs(value - target_avg_chars) / target_avg_chars)
        avg_scores.append(score)

    count_scores = []
    for value in chunk_count_values:
        score = max(0.0, 1.0 - abs(value - target_chunk_count) / target_chunk_count)
        count_scores.append(score)

    combined = [0.6 * avg_score + 0.4 * count_score for avg_score, count_score in zip(avg_scores, count_scores)]
    return _normalize_series(combined)


def _structure_integrity_values(configs: List[Dict[str, object]]) -> List[float]:
    values = []
    for item in configs:
        under_120_ratio = float((item.get("chunk_stats") or {}).get("under_120_ratio") or 0.0)
        values.append(1.0 - under_120_ratio)
    return _normalize_series(values)


def _attach_production_scores(configs: List[Dict[str, object]]) -> None:
    recall_values = _normalize_metric_dict(configs, "context_recall_proxy_mean")
    latency_values = _normalize_metric_dict(configs, "latency_mean_sec", reverse=True)
    f1_values = _normalize_metric_dict(configs, "retrieval_f1_proxy_mean")
    integrity_values = _structure_integrity_values(configs)
    granularity_values = _granularity_balance_values(configs)

    for index, item in enumerate(configs):
        components = {
            "recall": round(recall_values[index], 4),
            "retrieval_f1": round(f1_values[index], 4),
            "structure_integrity": round(integrity_values[index], 4),
            "granularity_balance": round(granularity_values[index], 4),
            "latency_efficiency": round(latency_values[index], 4),
        }
        score = (
            0.20 * components["recall"]
            + 0.10 * components["retrieval_f1"]
            + 0.25 * components["structure_integrity"]
            + 0.30 * components["granularity_balance"]
            + 0.15 * components["latency_efficiency"]
        )
        item["production_score_components"] = components
        item["production_composite_score"] = round(score * 100, 2)


def _attach_normalized_adaptation_index(configs: List[Dict[str, object]], floor: float = 0.70, ceiling: float = 0.92) -> None:
    scores = [float(item.get("production_composite_score") or 0.0) for item in configs]
    if not scores:
        return

    low = min(scores)
    high = max(scores)
    if abs(high - low) < 1e-9:
        for item in configs:
            item["normalized_adaptation_index"] = round(ceiling, 4)
        return

    for item in configs:
        score = float(item.get("production_composite_score") or 0.0)
        ratio = (score - low) / (high - low)
        normalized = floor + (ceiling - floor) * ratio
        item["normalized_adaptation_index"] = round(normalized, 4)


def _config_feedback(item: Dict[str, object], best_latency: float, best_recall: float, best_score: float) -> List[str]:
    feedback: List[str] = []
    recall = float(item.get("context_recall_proxy_mean") or 0.0)
    precision = float(item.get("context_precision_proxy_mean") or 0.0)
    retrieval_f1 = float(item.get("retrieval_f1_proxy_mean") or 0.0)
    latency = float(item.get("latency_mean_sec") or 0.0)
    score = float(item.get("production_composite_score") or 0.0)
    short_ratio = float((item.get("chunk_stats") or {}).get("under_120_ratio") or 0.0)
    granularity_balance = float((item.get("production_score_components") or {}).get("granularity_balance") or 0.0)

    if abs(score - best_score) < 1e-9:
        feedback.append("当前配置的生产导向综合得分最高，可作为正式实验候选。")
    if abs(recall - best_recall) < 1e-9:
        feedback.append("该配置在上下文覆盖代理指标上表现最佳，适合强调召回完整性。")
    if abs(latency - best_latency) < 1e-9:
        feedback.append("该配置响应速度最快，适合时间预算受限场景。")
    if short_ratio > 0.25:
        feedback.append("短块比例偏高，可能存在语义切分过碎的风险。")
    if precision < recall - 0.08:
        feedback.append("覆盖率高于聚焦性，检索内容可能偏散。")
    if precision > recall + 0.08:
        feedback.append("聚焦性较强，但可能遗漏部分关键上下文。")
    if retrieval_f1 < 0.35:
        feedback.append("检索 F1 代理偏低，说明该配置在覆盖与聚焦之间平衡较弱。")
    if granularity_balance > 0.85:
        feedback.append("该配置在粒度平衡和索引规模控制方面更接近生产默认目标。")
    if not feedback:
        feedback.append("该配置整体均衡，无明显短板，可进入下一轮正式验证。")
    return feedback


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal benchmark for chunk-size strategies")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Corpus directory")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Evaluation dataset path")
    parser.add_argument("--configs", default=DEFAULT_CONFIGS, help="Chunk configs as child:parent pairs")
    parser.add_argument("--max-queries", type=int, default=10, help="Number of samples to evaluate")
    parser.add_argument("--chunk-overlap", type=int, default=50, help="Chunk overlap")
    parser.add_argument("--retrieval-k", type=int, default=5, help="Fixed retrieval k for all configs")
    parser.add_argument("--candidate-m", type=int, default=2, help="Fixed rerank candidate m for all configs")
    parser.add_argument("--run-tag", default="", help="Optional run tag used in collection names")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    dataset_path = Path(args.dataset).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run_tag = args.run_tag.strip() or datetime.now().strftime("%m%d%H%M%S")
    configs = _parse_configs(args.configs)
    samples = _load_samples(dataset_path, args.max_queries)
    if not samples:
        raise RuntimeError("No valid samples loaded from dataset")

    report: Dict[str, object] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "offline_internal_chunk_strategy_comparison",
        "comparison_principle": "relative_only",
        "note": "All metrics are offline lexical proxy metrics for comparing chunk strategies under the same corpus and dataset.",
        "run_tag": run_tag,
        "data_dir": str(data_dir),
        "dataset": str(dataset_path),
        "samples": len(samples),
        "fixed_retrieval_params": {
            "retrieval_k": args.retrieval_k,
            "candidate_m": args.candidate_m,
        },
        "score_formula": {
            "internal_composite_score": {
                "recall": 0.35,
                "precision": 0.25,
                "retrieval_f1": 0.20,
                "stability": 0.10,
                "latency_efficiency": 0.10,
            },
            "production_composite_score": {
                "recall": 0.20,
                "retrieval_f1": 0.10,
                "structure_integrity": 0.25,
                "granularity_balance": 0.30,
                "latency_efficiency": 0.15,
                "description": "Production-oriented score emphasizing balanced chunk granularity, lower fragmentation, and manageable index scale.",
            },
            "normalized_adaptation_index": {
                "description": "Linear remapping of production composite scores for presentation-only ranking.",
                "floor": 0.70,
                "ceiling": 0.92,
                "best_config_maps_to": 0.92,
            },
        },
        "configs": [],
    }

    for child_chunk_size, parent_chunk_size in configs:
        print(
            f"Running chunk config child={child_chunk_size} parent={parent_chunk_size} on {len(samples)} samples...",
            flush=True,
        )
        item = _evaluate_config(
            data_dir=data_dir,
            samples=samples,
            parent_chunk_size=parent_chunk_size,
            child_chunk_size=child_chunk_size,
            chunk_overlap=args.chunk_overlap,
            retrieval_k=args.retrieval_k,
            candidate_m=args.candidate_m,
        )
        report["configs"].append(item)

    configs_payload = report["configs"]
    _attach_internal_scores(configs_payload)
    _attach_production_scores(configs_payload)
    _attach_normalized_adaptation_index(configs_payload)

    best_score = max(float(item.get("production_composite_score") or 0.0) for item in configs_payload)
    best_latency = min(float(item.get("latency_mean_sec") or 0.0) for item in configs_payload)
    best_recall = max(float(item.get("context_recall_proxy_mean") or 0.0) for item in configs_payload)
    for item in configs_payload:
        item["feedback"] = _config_feedback(item, best_latency, best_recall, best_score)

    recommended = max(configs_payload, key=lambda item: float(item.get("production_composite_score") or 0.0))
    report["summary"] = {
        "recommended_config": recommended.get("label"),
        "recommended_reason": "Highest production-oriented composite score under fixed corpus, dataset, and offline retrieval proxy settings.",
        "recommended_normalized_index": recommended.get("normalized_adaptation_index"),
        "fastest_config": min(configs_payload, key=lambda item: float(item.get("latency_mean_sec") or 0.0)).get("label"),
        "highest_recall_config": max(configs_payload, key=lambda item: float(item.get("context_recall_proxy_mean") or 0.0)).get("label"),
    }
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved report to: {output_path}")


if __name__ == "__main__":
    main()