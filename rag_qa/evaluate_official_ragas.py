from __future__ import annotations

import argparse
import importlib
import inspect
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from base import Config
from build_metallurgy_dataset_experiments import char_f1, duplicate_rate, exact_match, instantiate_rag
from core.vector_store import VectorStore
from demo_experiment_paths import RAGAS_DATASET_EXPERIMENT_DIR, RAGAS_EVALUATION_EXPERIMENT_DIR


DEFAULT_DATASET = RAGAS_DATASET_EXPERIMENT_DIR / "artifacts" / "generated_datasets" / "metallurgy_method_experiments" / "M1_dataset.json"
DEFAULT_OUTPUT_DIR = RAGAS_EVALUATION_EXPERIMENT_DIR / "artifacts" / "official_ragas_eval"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run official RAGAS evaluation and compare with legacy eval metrics")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Evaluation dataset JSON path")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to save reports")
    parser.add_argument("--max-samples", type=int, default=5, help="Limit sample count for a minimal runnable evaluation")
    parser.add_argument(
        "--sample-mode",
        choices=("sequential", "balanced-question-type"),
        default="sequential",
        help="How to subsample when --max-samples is smaller than the dataset size",
    )
    parser.add_argument("--default-source-filter", default="mining", help="Fallback source filter when dataset rows do not provide source")
    parser.add_argument("--llm-model", default=None, help="Override EDURAG_LLM_MODEL for both RAG and RAGAS judge")
    parser.add_argument("--raise-ragas-errors", action="store_true", help="Raise if a RAGAS metric row fails instead of returning NaN")
    return parser.parse_args()


def load_records(path: Path, max_samples: Optional[int], sample_mode: str = "sequential") -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    if not isinstance(payload, list):
        raise ValueError(f"dataset must be a JSON list: {path}")

    records: List[Dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        question = str(row.get("question", "")).strip()
        ground_truth = str(row.get("ground_truth", row.get("answer", ""))).strip()
        contexts = row.get("context", [])
        if isinstance(contexts, str):
            contexts = [contexts]
        contexts = [str(item).strip() for item in contexts if str(item).strip()]
        if not question or not ground_truth:
            continue
        normalized = dict(row)
        normalized["question"] = question
        normalized["ground_truth"] = ground_truth
        normalized["context"] = contexts
        records.append(normalized)

    if max_samples and max_samples > 0 and len(records) > max_samples:
        if sample_mode == "balanced-question-type":
            records = _balanced_sample_records(records, max_samples)
        else:
            records = records[:max_samples]

    if not records:
        raise ValueError(f"no valid evaluation rows loaded from {path}")
    return records


def _balanced_sample_records(records: Sequence[Dict[str, Any]], max_samples: int) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    ordered_keys: List[str] = []
    for row in records:
        question_type_key = str(row.get("question_type_key") or row.get("question_type") or "unknown").strip() or "unknown"
        if question_type_key not in grouped:
            grouped[question_type_key] = []
            ordered_keys.append(question_type_key)
        grouped[question_type_key].append(row)

    sampled: List[Dict[str, Any]] = []
    while len(sampled) < max_samples:
        progressed = False
        for question_type_key in ordered_keys:
            bucket = grouped[question_type_key]
            if not bucket:
                continue
            sampled.append(bucket.pop(0))
            progressed = True
            if len(sampled) >= max_samples:
                break
        if not progressed:
            break
    return sampled


def normalize_question(question: str) -> str:
    text = str(question or "").strip()
    for prefix in ("问题:", "问题："):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def stream_to_text(output: Any) -> str:
    if isinstance(output, str):
        return output.strip()
    parts: List[str] = []
    for item in output:
        if item:
            parts.append(str(item))
    return "".join(parts).strip()


def build_runtime_samples(records: Sequence[Dict[str, Any]], rag_system: Any, default_source_filter: str) -> List[Dict[str, Any]]:
    runtime_samples: List[Dict[str, Any]] = []
    for row in records:
        question = normalize_question(row["question"])
        source_filter = str(row.get("source") or default_source_filter or "").strip() or None
        retrieved_docs = rag_system.retrieve_and_merge(question, source_filter=source_filter)
        retrieved_contexts = [getattr(doc, "page_content", "") for doc in retrieved_docs if getattr(doc, "page_content", "")]
        response = stream_to_text(rag_system.generate_answer(question, source_filter=source_filter, use_history=False))
        runtime_samples.append(
            {
                "question": question,
                "source_filter": source_filter,
                "reference": str(row["ground_truth"]),
                "dataset_answer": str(row.get("answer", row["ground_truth"])),
                "dataset_contexts": [str(item) for item in row.get("context", [])],
                "response": response,
                "retrieved_contexts": retrieved_contexts,
            }
        )
    return runtime_samples


def compute_legacy_metrics(records: Sequence[Dict[str, Any]], runtime_samples: Sequence[Dict[str, Any]], default_source_filter: str) -> Dict[str, Any]:
    vector_store = VectorStore()
    avg_f1_total = 0.0
    em_hits = 0
    evidence_hits = 0
    dataset_hallucinated = 0
    prediction_grounding_proxy_hits = 0
    per_item: List[Dict[str, Any]] = []

    for raw, runtime in zip(records, runtime_samples):
        response = runtime["response"]
        reference = runtime["reference"]
        f1 = char_f1(response, reference)
        em = exact_match(response, reference)
        avg_f1_total += f1
        em_hits += int(em)

        source_filter = str(raw.get("source") or default_source_filter or "").strip() or None
        try:
            hits = vector_store._hybrid_search_raw(runtime["question"], k=3, source_filter=source_filter)
        except Exception:
            hits = []
        combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
        evidence_score = char_f1(reference, combined)
        evidence_located = evidence_score >= 0.35 or _normalize_text(reference) in _normalize_text(combined)
        evidence_hits += int(evidence_located)

        dataset_context_text = " ".join(runtime["dataset_contexts"])
        dataset_answer = runtime["dataset_answer"]
        if char_f1(dataset_answer, dataset_context_text) < 0.35 and _normalize_text(dataset_answer) not in _normalize_text(dataset_context_text):
            dataset_hallucinated += 1

        retrieved_context_text = " ".join(runtime["retrieved_contexts"])
        grounded = char_f1(response, retrieved_context_text) >= 0.35 or _normalize_text(response) in _normalize_text(retrieved_context_text)
        prediction_grounding_proxy_hits += int(grounded)

        per_item.append(
            {
                "id": raw.get("id"),
                "question": runtime["question"],
                "question_type": raw.get("question_type"),
                "question_type_key": raw.get("question_type_key"),
                "prediction": response,
                "reference": reference,
                "avg_f1": round(f1, 4),
                "exact_match": em,
                "legacy_evidence_located": evidence_located,
                "prediction_grounding_proxy": grounded,
            }
        )

    count = len(runtime_samples)
    return {
        "sample_count": count,
        "duplicate_rate": round(duplicate_rate(records), 4),
        "evidence_locatable_rate": round(evidence_hits / count, 4) if count else 0.0,
        "hallucination_rate_dataset_proxy": round(dataset_hallucinated / count, 4) if count else 0.0,
        "avg_f1": round(avg_f1_total / count, 4) if count else 0.0,
        "em_rate": round(em_hits / count, 4) if count else 0.0,
        "prediction_grounding_proxy_rate": round(prediction_grounding_proxy_hits / count, 4) if count else 0.0,
        "per_item": per_item,
    }


def _normalize_text(text: str) -> str:
    cleaned = "".join(str(text or "").split())
    punctuation = "，。！？；：、“”‘’（）()《》【】-—,.!?;:"
    for token in punctuation:
        cleaned = cleaned.replace(token, "")
    return cleaned


def build_ragas_dataset(runtime_samples: Sequence[Dict[str, Any]]) -> Any:
    ragas_module = importlib.import_module("ragas")
    sample_type = getattr(ragas_module, "SingleTurnSample")
    dataset_type = getattr(ragas_module, "EvaluationDataset")

    ragas_samples = []
    for row in runtime_samples:
        ragas_samples.append(
            sample_type(
                user_input=row["question"],
                retrieved_contexts=row["retrieved_contexts"],
                response=row["response"],
                reference=row["reference"],
            )
        )
    return dataset_type(samples=ragas_samples)


def load_ragas_wrappers(conf: Config) -> Tuple[Any, Any]:
    wrapper_llm_cls = _import_first(
        (
            "ragas.llms.LangchainLLMWrapper",
            "ragas.llms.base.LangchainLLMWrapper",
        )
    )
    wrapper_embedding_cls = _import_first(
        (
            "ragas.embeddings.LangchainEmbeddingsWrapper",
            "ragas.embeddings.base.LangchainEmbeddingsWrapper",
        )
    )

    try:
        from langchain_community.chat_models import ChatOpenAI
    except ImportError as exc:
        raise ImportError("langchain_community.chat_models.ChatOpenAI is unavailable") from exc

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError as exc:
        raise ImportError("langchain_community.embeddings.HuggingFaceEmbeddings is unavailable") from exc

    judge_llm = ChatOpenAI(
        model=conf.LLM_MODEL,
        api_key=conf.DASHSCOPE_API_KEY,
        base_url=conf.DASHSCOPE_BASE_URL,
        temperature=0,
    )
    embeddings = HuggingFaceEmbeddings(model_name=conf.SEMANTIC_MODEL_PATH)
    return wrapper_llm_cls(judge_llm), wrapper_embedding_cls(embeddings)


def _import_first(paths: Iterable[str]) -> Any:
    for dotted_path in paths:
        module_name, _, attr_name = dotted_path.rpartition(".")
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, attr_name):
            return getattr(module, attr_name)
    raise ImportError(f"None of the import targets are available: {', '.join(paths)}")


def resolve_metric_instances() -> Tuple[List[Any], List[str]]:
    metrics_module = importlib.import_module("ragas.metrics")
    metric_specs = [
        ("faithfulness", ["faithfulness", "Faithfulness"]),
        ("context_precision", ["context_precision", "ContextPrecision", "llm_context_precision_with_reference", "LLMContextPrecisionWithReference"]),
        ("context_recall", ["context_recall", "ContextRecall", "llm_context_recall", "LLMContextRecall"]),
        ("response_relevancy", ["response_relevancy", "answer_relevancy", "ResponseRelevancy", "AnswerRelevancy"]),
        ("factual_correctness", ["factual_correctness", "FactualCorrectness"]),
        ("exact_match", ["exact_match", "ExactMatch"]),
    ]

    resolved_metrics: List[Any] = []
    resolved_names: List[str] = []
    seen = set()
    for canonical_name, attr_names in metric_specs:
        metric = _resolve_metric(metrics_module, attr_names)
        if metric is None or canonical_name in seen:
            continue
        seen.add(canonical_name)
        resolved_metrics.append(metric)
        resolved_names.append(canonical_name)
    if not resolved_metrics:
        raise ImportError("No supported official RAGAS metrics could be imported")
    return resolved_metrics, resolved_names


def build_metric_column_aliases(metrics: Sequence[Any], metric_names: Sequence[str]) -> Dict[str, List[str]]:
    aliases: Dict[str, List[str]] = {}
    for canonical_name, metric in zip(metric_names, metrics):
        candidates: List[str] = [canonical_name]
        metric_name = getattr(metric, "name", None)
        if isinstance(metric_name, str) and metric_name.strip():
            candidates.append(metric_name.strip())

        if canonical_name == "response_relevancy":
            candidates.extend(["answer_relevancy", "answer_relevance"])
        elif canonical_name == "context_precision":
            candidates.extend(["llm_context_precision_with_reference", "context_precision"])
        elif canonical_name == "context_recall":
            candidates.extend(["llm_context_recall", "context_recall"])
        elif canonical_name == "factual_correctness":
            candidates.extend(["factual_correctness", "factual_correctness(mode=f1)"])

        deduped: List[str] = []
        seen = set()
        for candidate in candidates:
            normalized = str(candidate).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)
        aliases[canonical_name] = deduped
    return aliases


def _resolve_metric(module: Any, attr_names: Sequence[str]) -> Optional[Any]:
    for attr_name in attr_names:
        if not hasattr(module, attr_name):
            continue
        metric = getattr(module, attr_name)
        if inspect.isclass(metric):
            try:
                return metric()
            except TypeError:
                continue
        return metric
    return None


def run_ragas(dataset: Any, metrics: Sequence[Any], metric_names: Sequence[str], llm_wrapper: Any, embedding_wrapper: Any, raise_exceptions: bool) -> Dict[str, Any]:
    evaluate = getattr(importlib.import_module("ragas"), "evaluate")
    result = evaluate(
        dataset,
        metrics=list(metrics),
        llm=llm_wrapper,
        embeddings=embedding_wrapper,
        raise_exceptions=raise_exceptions,
        show_progress=True,
    )
    column_aliases = build_metric_column_aliases(metrics, metric_names)
    summary = extract_ragas_summary(result, metric_names, column_aliases)
    rows = extract_ragas_rows(result, metric_names, column_aliases)
    return {"summary": summary, "rows": rows, "raw_result": result}


def extract_ragas_summary(result: Any, metric_names: Sequence[str], column_aliases: Dict[str, Sequence[str]]) -> Dict[str, Any]:
    if hasattr(result, "to_pandas"):
        dataframe = result.to_pandas()
        summary: Dict[str, Any] = {}
        for metric_name in metric_names:
            column_name = _find_metric_column_name(dataframe.columns, column_aliases.get(metric_name, [metric_name]))
            if column_name is None:
                continue
            values = dataframe[column_name].dropna()
            summary[metric_name] = round(float(values.mean()), 4) if len(values) else None
        return summary

    summary = {}
    for metric_name in metric_names:
        value = None
        for alias in column_aliases.get(metric_name, [metric_name]):
            try:
                value = result[alias]
            except Exception:
                value = getattr(result, alias, None)
            if value is not None:
                break
        if value is not None:
            summary[metric_name] = round(float(value), 4)
    return summary


def extract_ragas_rows(result: Any, metric_names: Sequence[str], column_aliases: Dict[str, Sequence[str]]) -> List[Dict[str, Optional[float]]]:
    if not hasattr(result, "to_pandas"):
        return []

    dataframe = result.to_pandas()
    resolved_column_names = {
        metric_name: _find_metric_column_name(dataframe.columns, column_aliases.get(metric_name, [metric_name]))
        for metric_name in metric_names
    }

    rows: List[Dict[str, Optional[float]]] = []
    for _, series in dataframe.iterrows():
        row: Dict[str, Optional[float]] = {}
        for metric_name in metric_names:
            column_name = resolved_column_names.get(metric_name)
            if column_name is None:
                row[metric_name] = None
                continue
            row[metric_name] = _coerce_optional_float(series.get(column_name))
        rows.append(row)
    return rows


def _find_metric_column_name(columns: Iterable[Any], candidates: Sequence[str]) -> Optional[str]:
    normalized_candidates = [str(candidate).strip().lower() for candidate in candidates if str(candidate).strip()]
    if not normalized_candidates:
        return None

    resolved_columns = [str(column) for column in columns]
    for column in resolved_columns:
        lowered = column.strip().lower()
        if lowered in normalized_candidates:
            return column

    for column in resolved_columns:
        lowered = column.strip().lower()
        for candidate in normalized_candidates:
            if lowered.startswith(candidate + "("):
                return column
    return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return round(numeric, 4)


def build_question_type_breakdown(records: Sequence[Dict[str, Any]], legacy_metrics: Dict[str, Any], ragas_rows: Sequence[Dict[str, Optional[float]]]) -> List[Dict[str, Any]]:
    legacy_per_item = legacy_metrics.get("per_item", [])
    grouped: Dict[str, Dict[str, Any]] = {}

    for index, raw in enumerate(records):
        question_type_key = str(raw.get("question_type_key") or raw.get("question_type") or "unknown").strip() or "unknown"
        question_type = str(raw.get("question_type") or question_type_key).strip() or question_type_key
        bucket = grouped.setdefault(
            question_type_key,
            {
                "question_type_key": question_type_key,
                "question_type": question_type,
                "sample_count": 0,
                "legacy_avg_f1_sum": 0.0,
                "legacy_em_hits": 0,
                "legacy_evidence_hits": 0,
                "legacy_grounding_hits": 0,
                "official_faithfulness_sum": 0.0,
                "official_faithfulness_count": 0,
                "official_context_precision_sum": 0.0,
                "official_context_precision_count": 0,
                "official_context_recall_sum": 0.0,
                "official_context_recall_count": 0,
                "official_response_relevancy_sum": 0.0,
                "official_response_relevancy_count": 0,
                "official_factual_correctness_sum": 0.0,
                "official_factual_correctness_count": 0,
                "official_exact_match_sum": 0.0,
                "official_exact_match_count": 0,
            },
        )
        bucket["sample_count"] += 1

        if index < len(legacy_per_item):
            item = legacy_per_item[index]
            bucket["legacy_avg_f1_sum"] += float(item.get("avg_f1", 0.0) or 0.0)
            bucket["legacy_em_hits"] += int(bool(item.get("exact_match", False)))
            bucket["legacy_evidence_hits"] += int(bool(item.get("legacy_evidence_located", False)))
            bucket["legacy_grounding_hits"] += int(bool(item.get("prediction_grounding_proxy", False)))

        if index < len(ragas_rows):
            ragas_row = ragas_rows[index]
            _accumulate_optional_metric(bucket, ragas_row, "faithfulness")
            _accumulate_optional_metric(bucket, ragas_row, "context_precision")
            _accumulate_optional_metric(bucket, ragas_row, "context_recall")
            _accumulate_optional_metric(bucket, ragas_row, "response_relevancy")
            _accumulate_optional_metric(bucket, ragas_row, "factual_correctness")
            _accumulate_optional_metric(bucket, ragas_row, "exact_match")

    rows: List[Dict[str, Any]] = []
    for question_type_key, bucket in grouped.items():
        count = max(1, int(bucket["sample_count"]))
        rows.append(
            {
                "question_type_key": question_type_key,
                "question_type": bucket["question_type"],
                "sample_count": bucket["sample_count"],
                "legacy_avg_f1": round(bucket["legacy_avg_f1_sum"] / count, 4),
                "legacy_em_rate": round(bucket["legacy_em_hits"] / count, 4),
                "legacy_evidence_locatable_rate": round(bucket["legacy_evidence_hits"] / count, 4),
                "legacy_prediction_grounding_proxy_rate": round(bucket["legacy_grounding_hits"] / count, 4),
                "official_faithfulness": _mean_from_bucket(bucket, "official_faithfulness"),
                "official_context_precision": _mean_from_bucket(bucket, "official_context_precision"),
                "official_context_recall": _mean_from_bucket(bucket, "official_context_recall"),
                "official_response_relevancy": _mean_from_bucket(bucket, "official_response_relevancy"),
                "official_factual_correctness": _mean_from_bucket(bucket, "official_factual_correctness"),
                "official_exact_match": _mean_from_bucket(bucket, "official_exact_match"),
            }
        )

    rows.sort(key=lambda item: str(item["question_type_key"]))
    return rows


def _accumulate_optional_metric(bucket: Dict[str, Any], row: Dict[str, Optional[float]], metric_name: str) -> None:
    value = row.get(metric_name)
    if value is None:
        return
    sum_key = f"official_{metric_name}_sum"
    count_key = f"official_{metric_name}_count"
    bucket[sum_key] += float(value)
    bucket[count_key] += 1


def _mean_from_bucket(bucket: Dict[str, Any], metric_prefix: str) -> Optional[float]:
    sum_key = f"{metric_prefix}_sum"
    count_key = f"{metric_prefix}_count"
    count = int(bucket.get(count_key, 0) or 0)
    if count <= 0:
        return None
    return round(float(bucket.get(sum_key, 0.0) or 0.0) / count, 4)


def _clamp_score(value: Optional[float], default: float = 0.0) -> float:
    if value is None:
        return default
    return max(0.0, min(1.0, float(value)))


def _idealize_score(value: Optional[float], floor: float, ceiling: float, lift: float = 0.58) -> float:
    current = _clamp_score(value, default=floor)
    target = current + (ceiling - current) * lift
    return round(max(floor, min(ceiling, target)), 4)


def _scale_scores_to_band(values: Sequence[float], lower: float, upper: float) -> List[float]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if math.isclose(min_value, max_value):
        midpoint = round((lower + upper) / 2, 4)
        return [midpoint for _ in values]

    scaled: List[float] = []
    for value in values:
        ratio = (value - min_value) / (max_value - min_value)
        scaled.append(round(lower + ratio * (upper - lower), 4))
    return scaled


def _build_overall_metric_rows(comparison: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "label": "上下文精确率",
            "legacy": None,
            "official": comparison["official_ragas"].get("context_precision"),
            "note": "context_precision",
        },
        {
            "label": "上下文召回率",
            "legacy": None,
            "official": comparison["official_ragas"].get("context_recall"),
            "note": "context_recall",
        },
        {
            "label": "答案相关性",
            "legacy": None,
            "official": comparison["official_ragas"].get("response_relevancy"),
            "note": "response_relevancy",
        },
        {
            "label": "忠实度",
            "legacy": None,
            "official": comparison["official_ragas"].get("faithfulness"),
            "note": "faithfulness",
        },
    ]


def _build_illustrative_comparison(comparison: Dict[str, Any]) -> Dict[str, Any]:
    illustrative = {
        "legacy": dict(comparison.get("legacy", {})),
        "official_ragas": dict(comparison.get("official_ragas", {})),
    }
    illustrative["legacy"].update(
        {
            "prediction_grounding_proxy_rate": _idealize_score(comparison["legacy"].get("prediction_grounding_proxy_rate"), 0.48, 0.72),
            "evidence_locatable_rate": _idealize_score(comparison["legacy"].get("evidence_locatable_rate"), 0.46, 0.7),
        }
    )
    illustrative["official_ragas"].update(
        {
            "faithfulness": _idealize_score(comparison["official_ragas"].get("faithfulness"), 0.8, 0.92),
            "context_precision": _idealize_score(comparison["official_ragas"].get("context_precision"), 0.78, 0.9),
            "context_recall": _idealize_score(comparison["official_ragas"].get("context_recall"), 0.74, 0.88),
            "response_relevancy": _idealize_score(comparison["official_ragas"].get("response_relevancy"), 0.86, 0.96),
        }
    )
    return illustrative


def _build_illustrative_overall_metric_rows(actual: Dict[str, Any], illustrative: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "label": "上下文精确率",
            "legacy": actual["official_ragas"].get("context_precision"),
            "official": illustrative["official_ragas"].get("context_precision"),
            "note": "context_precision",
        },
        {
            "label": "上下文召回率",
            "legacy": actual["official_ragas"].get("context_recall"),
            "official": illustrative["official_ragas"].get("context_recall"),
            "note": "context_recall",
        },
        {
            "label": "答案相关性",
            "legacy": actual["official_ragas"].get("response_relevancy"),
            "official": illustrative["official_ragas"].get("response_relevancy"),
            "note": "response_relevancy",
        },
        {
            "label": "忠实度",
            "legacy": actual["official_ragas"].get("faithfulness"),
            "official": illustrative["official_ragas"].get("faithfulness"),
            "note": "faithfulness",
        },
    ]


def _build_question_type_heatmap_rows(question_type_breakdown: Sequence[Dict[str, Any]]) -> Tuple[List[str], List[List[float]]]:
    labels: List[str] = []
    matrix: List[List[float]] = []
    for row in question_type_breakdown:
        question_type = str(row.get("question_type") or row.get("question_type_key") or "unknown")
        sample_count = int(row.get("sample_count") or 0)
        labels.append(f"{question_type}  (n={sample_count})")
        matrix.append(
            [
                _clamp_score(row.get("official_context_precision")),
                _clamp_score(row.get("official_context_recall")),
                _clamp_score(row.get("official_response_relevancy")),
                _clamp_score(row.get("official_faithfulness")),
            ]
        )
    return labels, matrix


def _build_illustrative_question_type_breakdown(question_type_breakdown: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context_precision_values = [_clamp_score(row.get("official_context_precision")) for row in question_type_breakdown]
    context_recall_values = [_clamp_score(row.get("official_context_recall")) for row in question_type_breakdown]
    faithfulness_values = [_clamp_score(row.get("official_faithfulness")) for row in question_type_breakdown]
    relevancy_values = [_clamp_score(row.get("official_response_relevancy")) for row in question_type_breakdown]

    scaled_context_precision = _scale_scores_to_band(context_precision_values, 0.76, 0.89)
    scaled_context_recall = _scale_scores_to_band(context_recall_values, 0.74, 0.88)
    scaled_faithfulness = _scale_scores_to_band(faithfulness_values, 0.8, 0.92)
    scaled_relevancy = _scale_scores_to_band(relevancy_values, 0.86, 0.95)

    illustrative_rows: List[Dict[str, Any]] = []
    for index, row in enumerate(question_type_breakdown):
        illustrative_row = dict(row)
        illustrative_row["official_context_precision"] = scaled_context_precision[index]
        illustrative_row["official_context_recall"] = scaled_context_recall[index]
        illustrative_row["official_faithfulness"] = scaled_faithfulness[index]
        illustrative_row["official_response_relevancy"] = scaled_relevancy[index]
        illustrative_rows.append(illustrative_row)
    return illustrative_rows


def _apply_thesis_axes_style(ax: Any) -> None:
    ax.set_facecolor("#fbfaf7")
    for spine in ax.spines.values():
        spine.set_visible(False)


def _save_overall_profile_plot(
    plot_path: Path,
    metric_rows: Sequence[Dict[str, Any]],
    title: str,
    subtitle: str,
    illustrative_only: bool = False,
    left_legend_label: str = "Legacy proxy",
    right_legend_label: str = "Official RAGAS",
    comparison_caption: Optional[str] = None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    labels = [str(row["label"]) for row in metric_rows]
    y_positions = list(range(len(labels)))
    has_legacy_values = any(row.get("legacy") is not None for row in metric_rows)
    legacy_color = "#355070"
    official_color = "#c8553d"
    connector_color = "#d6d3d1"

    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    _apply_thesis_axes_style(ax)

    for index, row in enumerate(metric_rows):
        legacy_value = row.get("legacy")
        official_value = row.get("official")
        if legacy_value is not None and official_value is not None:
            ax.hlines(index, float(legacy_value), float(official_value), color=connector_color, linewidth=4.0, zorder=1)
        if legacy_value is not None:
            legacy_numeric = _clamp_score(float(legacy_value))
            ax.scatter(legacy_numeric, index, s=90, color=legacy_color, edgecolors="white", linewidths=1.1, zorder=3)
            ax.text(legacy_numeric - 0.025, index - 0.18, f"{legacy_numeric:.2f}", ha="right", va="center", fontsize=9, color=legacy_color)
        if official_value is not None:
            official_numeric = _clamp_score(float(official_value))
            ax.scatter(official_numeric, index, s=120, marker="D", color=official_color, edgecolors="white", linewidths=1.1, zorder=4)
            if has_legacy_values and legacy_value is not None:
                suffix = f"Δ {official_numeric - _clamp_score(legacy_value):+.2f}"
                ax.text(official_numeric + 0.03, index, suffix, ha="left", va="center", fontsize=9.5, color="#44403c")
            ax.text(official_numeric + 0.002, index - 0.18, f"{official_numeric:.2f}", ha="left", va="center", fontsize=9, color=official_color)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Score", fontsize=11, color="#44403c")
    ax.set_title(title, fontsize=15, color="#1f2937", pad=22, fontweight="bold")
    fig.text(0.125, 0.93, subtitle, fontsize=10, color="#6b7280")
    if comparison_caption:
        fig.text(0.125, 0.895, comparison_caption, fontsize=10.5, color="#334155", fontweight="semibold")
    ax.grid(axis="x", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    ax.tick_params(axis="x", colors="#6b7280")
    ax.tick_params(axis="y", length=0, colors="#374151")

    legend_handles = []
    if has_legacy_values:
        legend_handles.append(Line2D([0], [0], marker="o", color="none", markerfacecolor=legacy_color, markeredgecolor="white", markersize=9, label=left_legend_label))
    legend_handles.append(Line2D([0], [0], marker="D", color="none", markerfacecolor=official_color, markeredgecolor="white", markersize=9, label=right_legend_label))
    ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=2, frameon=False, fontsize=10)

    if illustrative_only:
        fig.text(0.965, 0.945, "Illustrative Only | 非实际评测", ha="right", va="center", fontsize=10.5, color="#b91c1c", fontweight="bold")

    fig.tight_layout(rect=[0, 0.02, 1, 0.88])
    fig.savefig(plot_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _save_ragas_only_table_plot(plot_path: Path, ragas_metrics: Dict[str, Any], title: str, subtitle: str) -> None:
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts(plt)

    metric_specs = [
        ("faithfulness", "忠实度"),
        ("context_precision", "上下文精确率"),
        ("context_recall", "上下文召回率"),
    ]
    labels = [label for _, label in metric_specs]
    values = [_clamp_score(ragas_metrics.get(metric_key)) for metric_key, _ in metric_specs]
    colors = ["#355070", "#457b9d", "#2a9d8f"]

    fig, ax_chart = plt.subplots(figsize=(10.8, 5.4))
    _apply_thesis_axes_style(ax_chart)

    y_positions = list(range(len(labels)))
    ax_chart.hlines(y_positions, [0.0] * len(labels), values, color="#d6d3d1", linewidth=3.2, zorder=1)
    ax_chart.scatter(values, y_positions, s=180, color=colors, edgecolors="white", linewidths=1.2, zorder=3)
    ax_chart.set_yticks(y_positions)
    ax_chart.set_yticklabels(labels, fontsize=11, color="#374151")
    ax_chart.set_ylim(len(labels) - 0.5, -0.5)
    ax_chart.invert_yaxis()
    ax_chart.set_xlim(0, 1.0)
    ax_chart.set_xlabel("得分", fontsize=11, color="#44403c")
    ax_chart.set_title(title, fontsize=15, color="#1f2937", pad=20, fontweight="bold")
    fig.text(0.125, 0.93, subtitle, fontsize=10, color="#6b7280")
    ax_chart.grid(axis="x", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    ax_chart.tick_params(axis="x", colors="#6b7280")
    ax_chart.tick_params(axis="y", length=0, colors="#374151")

    for value, y_position in zip(values, y_positions):
        ax_chart.text(
            min(value + 0.03, 0.97),
            y_position,
            f"{value:.4f}",
            ha="left",
            va="center",
            fontsize=10,
            color="#1f2937",
            fontweight="semibold",
        )

    fig.subplots_adjust(left=0.2, right=0.97, top=0.82, bottom=0.14)
    fig.savefig(plot_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _save_question_type_heatmap(plot_path: Path, question_type_breakdown: Sequence[Dict[str, Any]], title: str, subtitle: str, illustrative_only: bool = False) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    if not question_type_breakdown:
        return

    labels, matrix = _build_question_type_heatmap_rows(question_type_breakdown)
    column_labels = ["Context Precision", "Context Recall", "Answer Relevancy", "Faithfulness"]
    cmap = LinearSegmentedColormap.from_list("thesis_heat", ["#fff7ed", "#fdba74", "#67e8f9", "#0f766e"])

    fig_height = max(5.8, 0.88 * len(labels) + 2.3)
    fig, ax = plt.subplots(figsize=(10.8, fig_height))
    _apply_thesis_axes_style(ax)

    image = ax.imshow(matrix, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(list(range(len(column_labels))))
    ax.set_xticklabels(column_labels, fontsize=11, color="#374151")
    ax.set_yticks(list(range(len(labels))))
    ax.set_yticklabels(labels, fontsize=10.5, color="#374151")
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False, length=0)

    for row_index, row_values in enumerate(matrix):
        for column_index, value in enumerate(row_values):
            text_color = "#ffffff" if value >= 0.62 else "#1f2937"
            ax.text(column_index, row_index, f"{value:.2f}", ha="center", va="center", fontsize=10, color=text_color, fontweight="semibold")

    ax.set_title(title, fontsize=15, color="#1f2937", pad=26, fontweight="bold")
    fig.text(0.125, 0.94, subtitle, fontsize=10, color="#6b7280")

    colorbar = fig.colorbar(image, ax=ax, fraction=0.034, pad=0.025)
    colorbar.set_label("Score", color="#374151")
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(colors="#6b7280")

    for row_boundary in range(len(labels) + 1):
        ax.axhline(row_boundary - 0.5, color="#e7e5e4", linewidth=0.8)
    for column_boundary in range(len(column_labels) + 1):
        ax.axvline(column_boundary - 0.5, color="#f5f5f4", linewidth=1.1)

    if illustrative_only:
        fig.text(0.965, 0.955, "Illustrative Only | 非实际评测", ha="right", va="center", fontsize=10.5, color="#b91c1c", fontweight="bold")

    fig.tight_layout(rect=[0, 0.02, 1, 0.93])
    fig.savefig(plot_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def write_plots(output_dir: Path, timestamp: str, comparison: Dict[str, Any], question_type_breakdown: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return {}

    _configure_matplotlib_fonts(plt)

    output_dir.mkdir(parents=True, exist_ok=True)
    illustratice_only_dir = output_dir / "illustratice_only"
    illustratice_only_dir.mkdir(parents=True, exist_ok=True)

    overall_plot_path = output_dir / f"ragas_vs_legacy_overall_{timestamp}.png"
    question_type_plot_path = output_dir / f"ragas_vs_legacy_by_question_type_{timestamp}.png"
    ragas_only_plot_path = output_dir / f"ragas_only_metrics_{timestamp}.png"

    illustratice_overall_plot_path = illustratice_only_dir / f"ragas_vs_legacy_overall_illustrative_{timestamp}.png"
    illustratice_question_type_plot_path = illustratice_only_dir / f"ragas_vs_legacy_by_question_type_illustrative_{timestamp}.png"

    overall_rows = _build_overall_metric_rows(comparison)
    _save_overall_profile_plot(
        overall_plot_path,
        overall_rows,
        title="官方 RAGAS 四指标概览",
        subtitle="与论文评测口径一致：上下文精确率、上下文召回率、答案相关性、忠实度",
        right_legend_label="Official RAGAS",
        comparison_caption="对比方法：官方 RAGAS 评测（四指标直接展示）",
    )

    _save_ragas_only_table_plot(
        ragas_only_plot_path,
        comparison.get("official_ragas", {}),
        title="官方 RAGAS 指标专用图",
        subtitle="仅展示官方 RAGAS 评测结果，并在图内附上对应数据表",
    )

    if question_type_breakdown:
        _save_question_type_heatmap(
            question_type_plot_path,
            question_type_breakdown,
            title="题型-官方评测指标热力图",
            subtitle="按题型汇总的上下文精确率、上下文召回率、答案相关性与忠实度",
        )

    illustrative_comparison = _build_illustrative_comparison(comparison)
    illustrative_breakdown = _build_illustrative_question_type_breakdown(question_type_breakdown)
    illustrative_rows = _build_illustrative_overall_metric_rows(comparison, illustrative_comparison)
    _save_overall_profile_plot(
        illustratice_overall_plot_path,
        illustrative_rows,
        title="理想效果示意图：官方四指标轮廓",
        subtitle="仅用于论文视觉展示的目标效果示意，不代表真实评测结果",
        illustrative_only=True,
        left_legend_label="Current official",
        right_legend_label="Target profile",
        comparison_caption="对比对象：当前官方 RAGAS 结果 vs 理想目标结果",
    )

    if illustrative_breakdown:
        _save_question_type_heatmap(
            illustratice_question_type_plot_path,
            illustrative_breakdown,
            title="理想效果示意图：题型-官方指标热力图",
            subtitle="仅用于论文视觉展示的目标效果示意，不代表真实评测结果",
            illustrative_only=True,
        )

    return {
        "overall_comparison_plot": str(overall_plot_path),
        "question_type_plot": str(question_type_plot_path),
        "ragas_only_plot": str(ragas_only_plot_path),
        "illustratice_only_dir": str(illustratice_only_dir),
        "illustratice_only_overall_plot": str(illustratice_overall_plot_path),
        "illustratice_only_question_type_plot": str(illustratice_question_type_plot_path),
    }


def _configure_matplotlib_fonts(plt: Any) -> None:
    preferred_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["font.sans-serif"] = preferred_fonts
    plt.rcParams["axes.unicode_minus"] = False


def build_comparison(legacy_metrics: Dict[str, Any], ragas_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "metric_mapping": {
            "evidence_locatable_rate": ["context_recall", "context_precision"],
            "hallucination_rate_dataset_proxy": ["faithfulness"],
            "avg_f1": ["factual_correctness", "exact_match"],
            "em_rate": ["exact_match"],
            "prediction_grounding_proxy_rate": ["faithfulness"],
        },
        "legacy": {
            "duplicate_rate": legacy_metrics.get("duplicate_rate"),
            "evidence_locatable_rate": legacy_metrics.get("evidence_locatable_rate"),
            "hallucination_rate_dataset_proxy": legacy_metrics.get("hallucination_rate_dataset_proxy"),
            "avg_f1": legacy_metrics.get("avg_f1"),
            "em_rate": legacy_metrics.get("em_rate"),
            "prediction_grounding_proxy_rate": legacy_metrics.get("prediction_grounding_proxy_rate"),
        },
        "official_ragas": ragas_summary,
        "notes": [
            "legacy hallucination_rate_dataset_proxy is computed from dataset answer vs dataset context, not from live model outputs.",
            "prediction_grounding_proxy_rate is added here to give a closer apples-to-apples proxy against official faithfulness.",
            "context_precision/context_recall are the nearest official replacements for the legacy evidence_locatable_rate proxy.",
        ],
    }


def write_outputs(output_dir: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"ragas_vs_legacy_{timestamp}.json"
    md_path = output_dir / f"ragas_vs_legacy_{timestamp}.md"
    runtime_path = output_dir / f"ragas_runtime_samples_{timestamp}.json"
    plot_paths = write_plots(output_dir, timestamp, payload["comparison"], payload.get("question_type_breakdown", []))

    json_payload = dict(payload)
    runtime_samples = json_payload.pop("runtime_samples", [])
    json_payload.pop("ragas_result_object", None)
    json_payload["plot_paths"] = plot_paths

    with json_path.open("w", encoding="utf-8") as file_handle:
        json.dump(json_payload, file_handle, ensure_ascii=False, indent=2)

    with runtime_path.open("w", encoding="utf-8") as file_handle:
        json.dump(runtime_samples, file_handle, ensure_ascii=False, indent=2)

    comparison = payload["comparison"]
    lines = [
        "# Official RAGAS vs Legacy Evaluation",
        "",
        f"- created_at: {payload['created_at']}",
        f"- dataset: {payload['dataset_path']}",
        f"- sample_count: {payload['sample_count']}",
        f"- llm_model: {payload['llm_model']}",
        "",
        "## Legacy Metrics",
        "",
    ]
    for key, value in comparison["legacy"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Official RAGAS Metrics", ""])
    for key, value in comparison["official_ragas"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Mapping Notes", ""])
    for note in comparison["notes"]:
        lines.append(f"- {note}")

    if payload.get("question_type_breakdown"):
        lines.extend(["", "## By Question Type", ""])
        lines.append("| question_type | sample_count | legacy_avg_f1 | official_faithfulness | official_factual_correctness |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in payload["question_type_breakdown"]:
            lines.append(
                "| {question_type} | {sample_count} | {legacy_avg_f1} | {official_faithfulness} | {official_factual_correctness} |".format(
                    question_type=row.get("question_type", "unknown"),
                    sample_count=row.get("sample_count", 0),
                    legacy_avg_f1=row.get("legacy_avg_f1", 0.0),
                    official_faithfulness=row.get("official_faithfulness"),
                    official_factual_correctness=row.get("official_factual_correctness"),
                )
            )

    if plot_paths:
        lines.extend(["", "## Plot Paths", ""])
        lines.append("- illustratice_only_* paths are aspirational visuals for thesis layout only, not measured evaluation results.")
        for key, value in plot_paths.items():
            lines.append(f"- {key}: {value}")

    with md_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(lines).strip() + "\n")

    return {
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "runtime_samples": str(runtime_path),
        **plot_paths,
    }


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    conf = Config()
    if args.llm_model:
        conf.LLM_MODEL = args.llm_model

    if not conf.DASHSCOPE_API_KEY or conf.DASHSCOPE_API_KEY.startswith("demo-key"):
        raise RuntimeError("EDURAG_DASHSCOPE_API_KEY is not configured; official RAGAS metrics require a working judge model")

    records = load_records(dataset_path, args.max_samples, args.sample_mode)
    rag_system = instantiate_rag(conf)
    runtime_samples = build_runtime_samples(records, rag_system, args.default_source_filter)
    legacy_metrics = compute_legacy_metrics(records, runtime_samples, args.default_source_filter)

    ragas_dataset = build_ragas_dataset(runtime_samples)
    metrics, metric_names = resolve_metric_instances()
    llm_wrapper, embedding_wrapper = load_ragas_wrappers(conf)
    ragas_results = run_ragas(
        ragas_dataset,
        metrics,
        metric_names,
        llm_wrapper,
        embedding_wrapper,
        raise_exceptions=args.raise_ragas_errors,
    )
    comparison = build_comparison(legacy_metrics, ragas_results["summary"])
    question_type_breakdown = build_question_type_breakdown(records, legacy_metrics, ragas_results.get("rows", []))

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "sample_count": len(runtime_samples),
        "llm_model": conf.LLM_MODEL,
        "legacy_metrics": legacy_metrics,
        "official_ragas_metrics": ragas_results["summary"],
        "comparison": comparison,
        "question_type_breakdown": question_type_breakdown,
        "runtime_samples": runtime_samples,
        "ragas_result_object": ragas_results["raw_result"],
    }
    report_paths = write_outputs(output_dir, payload)

    stdout_payload = {
        "legacy_metrics": {
            "duplicate_rate": legacy_metrics["duplicate_rate"],
            "evidence_locatable_rate": legacy_metrics["evidence_locatable_rate"],
            "hallucination_rate_dataset_proxy": legacy_metrics["hallucination_rate_dataset_proxy"],
            "avg_f1": legacy_metrics["avg_f1"],
            "em_rate": legacy_metrics["em_rate"],
            "prediction_grounding_proxy_rate": legacy_metrics["prediction_grounding_proxy_rate"],
        },
        "official_ragas_metrics": ragas_results["summary"],
        "report_paths": report_paths,
    }
    print(json.dumps(stdout_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()