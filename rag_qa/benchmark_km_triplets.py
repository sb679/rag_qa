# -*- coding:utf-8 -*-
"""Quick benchmark for K/M triplets with bounded runtime.

Compares:
- Baseline: K=5, M=2
- Variant A: K=8, M=3
- Variant B: K=10, M=3

Metrics:
- latency_mean_sec / latency_p95_sec
- hit_quality_mean: overlap proxy between expected context and retrieved context
- hallucination_rate_mean: unsupported sentence ratio in answer against retrieved context

Usage:
    python benchmark_km_triplets.py --max-queries 6 --per-query-timeout 45
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from web.backend import rag_service  # noqa: E402
import core.new_rag_system as new_rag_module  # noqa: E402
import core.vector_store as vector_store_module  # noqa: E402


@dataclass
class SampleResult:
    latency_sec: float
    hit_quality: Optional[float]
    hallucination_rate: Optional[float]
    timed_out: bool
    errored: bool
    rate_limited: bool
    error_message: str = ""


def _is_rate_limited_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return (
        "ratelimit" in text
        or "429" in text
        or "too many requests" in text
        or "wait" in text
        or "限流" in text
    )


def _invoke_once(question: str, source_filter: str, timeout_sec: int):
    def _run_once():
        return rag_service._run_full_rag(  # pylint: disable=protected-access
            query=question,
            source_filter=source_filter,
            query_type="专业咨询",
            history_context="",
            include_source_details=True,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_once)
        return future.result(timeout=timeout_sec)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _char_ngrams(text: str, n: int = 2) -> set:
    text = _normalize_text(text)
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _overlap_ratio(a: str, b: str) -> float:
    a_grams = _char_ngrams(a, n=2)
    b_grams = _char_ngrams(b, n=2)
    if not a_grams:
        return 0.0
    return len(a_grams & b_grams) / len(a_grams)


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？；\n]+", text or "")
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def _build_retrieved_context(retrieval_info: Dict) -> str:
    contexts: List[str] = []
    for src in retrieval_info.get("sources", []) or []:
        contexts.append(src.get("parent_content") or src.get("content") or "")
        for child in src.get("matched_children", []) or []:
            contexts.append(child.get("content") or "")
    return "\n".join(c for c in contexts if c)


def _evaluate_single(question: str, expected_context: str, source_filter: str, timeout_sec: int) -> SampleResult:
    started = time.perf_counter()
    try:
        rag_result = _invoke_once(question=question, source_filter=source_filter, timeout_sec=timeout_sec)
    except FutureTimeout:
        return SampleResult(
            latency_sec=timeout_sec,
            hit_quality=None,
            hallucination_rate=None,
            timed_out=True,
            errored=False,
            rate_limited=False,
            error_message="timeout",
        )
    except Exception as exc:
        return SampleResult(
            latency_sec=max(0.0, time.perf_counter() - started),
            hit_quality=None,
            hallucination_rate=None,
            timed_out=False,
            errored=True,
            rate_limited=_is_rate_limited_error(exc),
            error_message=str(exc),
        )

    latency = max(0.0, time.perf_counter() - started)
    retrieval_info = rag_result.retrieval_info or {}
    answer = rag_result.answer or ""
    retrieved_context = _build_retrieved_context(retrieval_info)

    hit_quality = _overlap_ratio(expected_context, retrieved_context)

    sentences = _split_sentences(answer)
    if not sentences:
        hallucination_rate = 1.0 if answer.strip() else 0.0
    else:
        unsupported = 0
        for sent in sentences:
            support = _overlap_ratio(sent, retrieved_context)
            if support < 0.12:
                unsupported += 1
        hallucination_rate = unsupported / len(sentences)

    return SampleResult(
        latency_sec=latency,
        hit_quality=hit_quality,
        hallucination_rate=hallucination_rate,
        timed_out=False,
        errored=False,
        rate_limited=False,
        error_message="",
    )


def _evaluate_single_with_retry(
    question: str,
    expected_context: str,
    source_filter: str,
    timeout_sec: int,
    retries: int,
    backoff_sec: float,
) -> SampleResult:
    attempt = 0
    while True:
        result = _evaluate_single(question, expected_context, source_filter, timeout_sec)
        if not result.errored or not result.rate_limited or attempt >= retries:
            return result

        sleep_for = backoff_sec * (2 ** attempt)
        print(
            f"rate_limited: question='{question[:30]}' attempt={attempt + 1}/{retries + 1}, "
            f"sleep={sleep_for:.1f}s"
        )
        time.sleep(sleep_for)
        attempt += 1


def _set_km(k_value: int, m_value: int):
    rag_service._config.RETRIEVAL_K = k_value  # pylint: disable=protected-access
    rag_service._config.CANDIDATE_M = m_value  # pylint: disable=protected-access

    if hasattr(new_rag_module, "conf"):
        new_rag_module.conf.RETRIEVAL_K = k_value
        new_rag_module.conf.CANDIDATE_M = m_value
    if hasattr(vector_store_module, "conf"):
        vector_store_module.conf.RETRIEVAL_K = k_value
        vector_store_module.conf.CANDIDATE_M = m_value


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def _load_samples(dataset_path: str, max_queries: int) -> List[Dict[str, str]]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    samples = []
    for record in records:
        q = (record.get("question") or "").strip()
        c = (record.get("context") or "").strip()
        s = (record.get("source") or "mining").strip() or "mining"
        if not q or not c:
            continue
        if q.startswith("问题:"):
            q = q[3:].strip()
        samples.append({"question": q, "context": c, "source": s})
        if len(samples) >= max_queries:
            break
    return samples


def run_benchmark(
    samples: List[Dict[str, str]],
    combos: List[Tuple[int, int]],
    per_query_timeout: int,
    force_strategy: str,
    retries: int,
    retry_backoff_sec: float,
    min_interval_sec: float,
):
    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "samples": len(samples),
        "per_query_timeout_sec": per_query_timeout,
        "configs": [],
    }

    for k_value, m_value in combos:
        _set_km(k_value, m_value)
        time.sleep(0.5)

        original_select_strategy = rag_service._rag_system.strategy_selector.select_strategy  # pylint: disable=protected-access
        if force_strategy:
            rag_service._rag_system.strategy_selector.select_strategy = lambda _q: force_strategy  # pylint: disable=protected-access

        run_results: List[SampleResult] = []
        last_started_at = 0.0
        try:
            for sample in samples:
                now = time.perf_counter()
                if min_interval_sec > 0 and last_started_at > 0:
                    elapsed = now - last_started_at
                    if elapsed < min_interval_sec:
                        time.sleep(min_interval_sec - elapsed)

                last_started_at = time.perf_counter()
                run_results.append(
                    _evaluate_single_with_retry(
                        question=sample["question"],
                        expected_context=sample["context"],
                        source_filter=sample["source"],
                        timeout_sec=per_query_timeout,
                        retries=retries,
                        backoff_sec=retry_backoff_sec,
                    )
                )
        finally:
            rag_service._rag_system.strategy_selector.select_strategy = original_select_strategy  # pylint: disable=protected-access

        latencies = [r.latency_sec for r in run_results]
        success_results = [r for r in run_results if not r.errored and not r.timed_out]
        hit_scores = [r.hit_quality for r in success_results if r.hit_quality is not None]
        halluc_rates = [r.hallucination_rate for r in success_results if r.hallucination_rate is not None]

        item = {
            "k": k_value,
            "m": m_value,
            "latency_mean_sec": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "latency_p95_sec": round(_p95(latencies), 3) if latencies else 0.0,
            "hit_quality_mean": round(sum(hit_scores) / len(hit_scores), 4) if hit_scores else None,
            "hallucination_rate_mean": round(sum(halluc_rates) / len(halluc_rates), 4) if halluc_rates else None,
            "valid_quality_samples": len(hit_scores),
            "timeouts": sum(1 for r in run_results if r.timed_out),
            "errors": sum(1 for r in run_results if r.errored),
            "rate_limited_errors": sum(1 for r in run_results if r.rate_limited),
        }
        report["configs"].append(item)

        print(
            f"K={k_value}, M={m_value} | "
            f"mean={item['latency_mean_sec']}s p95={item['latency_p95_sec']}s | "
            f"hit={item['hit_quality_mean']} halluc={item['hallucination_rate_mean']} | "
            f"valid={item['valid_quality_samples']} "
            f"timeouts={item['timeouts']} errors={item['errors']} rate_limited={item['rate_limited_errors']}"
        )

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def main():
    parser = argparse.ArgumentParser(description="Benchmark K/M triplets with bounded runtime")
    parser.add_argument(
        "--dataset",
        default=os.path.join(current_dir, "rag_assesment", "generated_datasets", "testset_20260417_183026.json"),
        help="Dataset JSON path",
    )
    parser.add_argument("--max-queries", type=int, default=6, help="Number of samples to evaluate")
    parser.add_argument("--per-query-timeout", type=int, default=45, help="Per-query timeout seconds")
    parser.add_argument("--force-strategy", default="直接检索", help="Fixed strategy for stable benchmark; empty to disable")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for rate-limited requests")
    parser.add_argument("--retry-backoff-sec", type=float, default=20.0, help="Base backoff seconds for retries")
    parser.add_argument("--min-interval-sec", type=float, default=2.5, help="Minimum interval between query starts")
    parser.add_argument(
        "--output",
        default=os.path.join(current_dir, "rag_assesment", "generated_datasets", "benchmark_km_report.json"),
        help="Output report JSON path",
    )
    args = parser.parse_args()

    if rag_service._rag_system is None or rag_service._vector_store is None:  # pylint: disable=protected-access
        raise RuntimeError(f"RAG service not ready: {rag_service._init_error}")  # pylint: disable=protected-access

    samples = _load_samples(args.dataset, args.max_queries)
    if not samples:
        raise RuntimeError("No valid samples loaded from dataset")

    combos = [(5, 2), (8, 3), (10, 3)]
    report = run_benchmark(
        samples,
        combos,
        args.per_query_timeout,
        args.force_strategy,
        args.retries,
        args.retry_backoff_sec,
        args.min_interval_sec,
    )

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nReport saved to: {args.output}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
