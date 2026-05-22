from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from base import Config
from build_metallurgy_dataset_experiments import char_f1
from evaluate_official_ragas import (
    _configure_matplotlib_fonts,
    build_metric_column_aliases,
    build_question_type_breakdown,
    build_ragas_dataset,
    compute_legacy_metrics,
    extract_ragas_rows,
    extract_ragas_summary,
    load_ragas_wrappers,
    load_records,
    normalize_question,
    resolve_metric_instances,
    stream_to_text,
)
from build_metallurgy_dataset_experiments import instantiate_rag


DEFAULT_DATASET = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "testset_governance" / "metallurgy_demo20_stable_ragas_dataset.json"
DEFAULT_OUTPUT_DIR = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "generation_mode_comparison_demo20_stable"

OFFICIAL_METRIC_ORDER = [
    "faithfulness",
    "context_precision",
    "context_recall",
    "response_relevancy",
    "factual_correctness",
]

DIRECT_METRIC_ORDER = [
    "response_relevancy",
    "factual_correctness",
]


@dataclass(frozen=True)
class ModeConfig:
    key: str
    label: str
    system_prompt: Optional[str]
    uses_rag: bool = False
    uses_few_shot: bool = False


MODE_CONFIGS: Sequence[ModeConfig] = (
    ModeConfig(
        key="zero_shot",
        label="Zero-shot",
        system_prompt="你是冶金安全领域专家。请仅基于自身知识直接回答问题，不使用任何检索材料。回答尽量简短，只保留与问题直接对应的要点，不要扩展背景，答案尽量控制在120字以内。",
    ),
    ModeConfig(
        key="few_shot",
        label="Few-shot",
        system_prompt="你是冶金安全领域专家。请模仿示例的回答风格：短、准、只回答问题本身，不扩展，答案尽量控制在120字以内。",
        uses_few_shot=True,
    ),
    ModeConfig(
        key="rag",
        label="With RAG",
        system_prompt=None,
        uses_rag=True,
    ),
    ModeConfig(
        key="no_rag",
        label="No RAG",
        system_prompt="你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了，尽量控制在120字以内。",
    ),
)


FEW_SHOT_EXAMPLES: Sequence[Dict[str, str]] = (
    {
        "question": "其他保障措施中需要重点关注哪些危险因素或防控措施？",
        "answer": "应重点落实：热风炉系统及送风、放风主管采取保温措施；走道口设置照明；监控室、配电室和电气室设置操作通道、检修通道和出口；电气室、控制室及疏散通道设置事故照明；检修场所配备防毒面具、防护服、空气呼吸器等应急器具。",
    },
    {
        "question": "围绕信号装置，不同类型或情形下的要求分别是什么？",
        "answer": "信号装置主要有两类作用：一类用于指示电气设备的工作状态，帮助操作人员据此执行正确操作、避免误操作；另一类用于设备异常时发出声光报警，提醒相关人员及时采取处置措施。",
    },
    {
        "question": "围绕滑板系统漏钢及安全措施，不同类型或情形下的要求分别是什么？",
        "answer": "防止盛钢桶滑板系统漏钢，应从四方面控制：提高滑板和水口材质；保证滑板与水口、滑板间的装配质量；按不同钢种和滑板材质制定合理连用次数，防止超标使用；烧氧引流时谨慎操作，避免烧坏水口或滑板。",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare zero-shot / few-shot / RAG / no-RAG under official RAGAS")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Evaluation dataset JSON path")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to save comparison outputs")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=[config.key for config in MODE_CONFIGS],
        default=[config.key for config in MODE_CONFIGS],
        help="Subset of modes to run or combine",
    )
    parser.add_argument("--max-samples", type=int, default=20, help="Limit sample count")
    parser.add_argument("--slice-start", type=int, default=0, help="Start index after loading/subsampling records")
    parser.add_argument("--slice-count", type=int, default=None, help="Take only this many records after --slice-start")
    parser.add_argument(
        "--sample-mode",
        choices=("sequential", "balanced-question-type"),
        default="balanced-question-type",
        help="How to subsample when --max-samples is smaller than the dataset size",
    )
    parser.add_argument("--default-source-filter", default="metallurgy", help="Fallback source filter when dataset rows do not provide source")
    parser.add_argument("--llm-model", default=None, help="Override EDURAG_LLM_MODEL for generation and judge")
    parser.add_argument("--raise-ragas-errors", action="store_true", help="Raise if a RAGAS metric row fails instead of returning NaN")
    parser.add_argument("--reuse-cached", action="store_true", help="Reuse per-mode JSON caches from output-dir when available")
    return parser.parse_args()


def _non_empty_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_score(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return float(value)


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    numeric = [float(item) for item in values if item is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 4)


def _build_macro_scores(summary: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    official_macro = _mean([summary.get(name) for name in OFFICIAL_METRIC_ORDER])
    direct_macro = _mean([summary.get(name) for name in DIRECT_METRIC_ORDER])
    return {
        "official_macro": official_macro,
        "direct_macro": direct_macro,
    }


def _trim_response(text: str, max_chars: int = 160) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    candidate = compact[:max_chars].rstrip(" ，,;；、")
    for token in ("。", "；", ";", "，", ","):
        boundary = candidate.rfind(token)
        if boundary >= max_chars // 2:
            return candidate[: boundary + 1].strip()
    return candidate.strip()


def _build_messages(mode: ModeConfig, question: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if mode.system_prompt:
        messages.append({"role": "system", "content": mode.system_prompt})
    if mode.uses_few_shot:
        for example in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": example["question"]})
            messages.append({"role": "assistant", "content": example["answer"]})
    messages.append({"role": "user", "content": question})
    return messages


def _call_direct_llm(client: OpenAI, model_name: str, mode: ModeConfig, question: str) -> str:
    completion = client.chat.completions.create(
        model=model_name,
        messages=_build_messages(mode, question),
        temperature=0,
        max_tokens=256,
        timeout=120,
        stream=False,
    )
    message = completion.choices[0].message.content if completion.choices else ""
    return _trim_response(_non_empty_text(message))


def build_runtime_samples_for_mode(
    records: Sequence[Dict[str, Any]],
    mode: ModeConfig,
    conf: Config,
    default_source_filter: str,
    rag_system: Any,
    client: OpenAI,
) -> List[Dict[str, Any]]:
    runtime_samples: List[Dict[str, Any]] = []
    for row in records:
        question = normalize_question(row["question"])
        source_filter = _non_empty_text(row.get("source") or default_source_filter) or None
        retrieved_contexts: List[str] = []

        if mode.uses_rag:
            if rag_system is None:
                raise RuntimeError("rag_system is required when mode.uses_rag is True")
            retrieved_docs = rag_system.retrieve_and_merge(question, source_filter=source_filter)
            retrieved_contexts = [getattr(doc, "page_content", "") for doc in retrieved_docs if getattr(doc, "page_content", "")]
            response = stream_to_text(rag_system.generate_answer(question, source_filter=source_filter, use_history=False))
        else:
            response = _call_direct_llm(client, conf.LLM_MODEL, mode, question)

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


def _rank_modes(mode_payloads: Dict[str, Dict[str, Any]], metric_name: str) -> List[str]:
    return sorted(
        mode_payloads.keys(),
        key=lambda key: _coerce_score(mode_payloads[key]["official_ragas_metrics"].get(metric_name)),
        reverse=True,
    )


def _generate_explanations(mode_payloads: Dict[str, Dict[str, Any]]) -> List[str]:
    rag_key = "rag"
    no_rag_key = "no_rag"
    zero_key = "zero_shot"
    few_key = "few_shot"

    required_keys = {rag_key, no_rag_key, zero_key, few_key}
    if not required_keys.issubset(mode_payloads.keys()):
        return ["当前输出只包含部分模式，因此本报告仅给出该模式结果，不生成四方案现象对比结论。"]

    rag_summary = mode_payloads[rag_key]["official_ragas_metrics"]
    no_rag_summary = mode_payloads[no_rag_key]["official_ragas_metrics"]
    zero_summary = mode_payloads[zero_key]["official_ragas_metrics"]
    few_summary = mode_payloads[few_key]["official_ragas_metrics"]

    notes: List[str] = []
    notes.append(
        "走 RAG 模式通常会显著抬高 context_precision、context_recall 与 faithfulness，因为回答显式绑定到检索证据；不走 RAG 的三种直答模式在这些指标上天然吃亏。"
    )
    if _coerce_score(few_summary.get("factual_correctness")) >= _coerce_score(zero_summary.get("factual_correctness")):
        notes.append(
            "少样本模式相对零样本若出现 factual_correctness 提升，通常说明示例对答案格式起到了约束作用，模型更愿意输出‘短、准、少扩写’的答案。"
        )
    else:
        notes.append(
            "少样本模式若没有优于零样本，通常说明示例风格与评测题型不完全匹配，示例反而把模型拉向固定模板或错误归纳。"
        )
    if _coerce_score(rag_summary.get("factual_correctness")) > _coerce_score(no_rag_summary.get("factual_correctness")):
        notes.append(
            "走 RAG 的 factual_correctness 高于不走 RAG，说明检索证据不仅减少了幻觉，还帮助模型在阈值、步骤和处置动作上输出更贴近参考答案的内容。"
        )
    else:
        notes.append(
            "如果走 RAG 没有明显拉开 factual_correctness，通常说明瓶颈不在检索，而在回答压缩策略、题目闭合度或 judge 对表述差异的敏感性。"
        )
    return notes


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _mode_cache_path(output_dir: Path, mode_key: str) -> Path:
    return output_dir / f"mode_result_{mode_key}.json"


def _runtime_cache_path(output_dir: Path, mode_key: str) -> Path:
    return output_dir / f"runtime_samples_{mode_key}.json"


def _run_ragas_stable(
    dataset: Any,
    metrics: Sequence[Any],
    metric_names: Sequence[str],
    llm_wrapper: Any,
    embedding_wrapper: Any,
    raise_exceptions: bool,
) -> Dict[str, Any]:
    from ragas import evaluate
    from ragas.run_config import RunConfig

    result = evaluate(
        dataset,
        metrics=list(metrics),
        llm=llm_wrapper,
        embeddings=embedding_wrapper,
        raise_exceptions=raise_exceptions,
        show_progress=True,
        run_config=RunConfig(max_workers=1),
        batch_size=1,
    )
    column_aliases = build_metric_column_aliases(metrics, metric_names)
    summary = extract_ragas_summary(result, metric_names, column_aliases)
    rows = extract_ragas_rows(result, metric_names, column_aliases)
    return {"summary": summary, "rows": rows, "raw_result": result}


def _plot_metric_bars(output_path: Path, mode_payloads: Dict[str, Dict[str, Any]], mode_configs: Sequence[ModeConfig]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    _configure_matplotlib_fonts(plt)

    mode_keys = [config.key for config in mode_configs]
    labels = [config.label for config in mode_configs]
    metric_labels = [
        "Faithfulness",
        "Context Precision",
        "Context Recall",
        "Response Relevancy",
        "Factual Correctness",
    ]
    x = np.arange(len(metric_labels))
    width = 0.18
    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]

    fig, ax = plt.subplots(figsize=(12.6, 6.8))
    ax.set_facecolor("#fbfaf7")

    for index, mode_key in enumerate(mode_keys):
        summary = mode_payloads[mode_key]["official_ragas_metrics"]
        values = [_coerce_score(summary.get(metric_name)) for metric_name in OFFICIAL_METRIC_ORDER]
        ax.bar(x + (index - 1.5) * width, values, width=width, label=labels[index], color=colors[index])

    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, rotation=0)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Score")
    ax.set_title("四种生成方案的官方 RAGAS 指标对比", fontsize=15, fontweight="bold")
    ax.grid(axis="y", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.10))

    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_macro_scores(output_path: Path, mode_payloads: Dict[str, Dict[str, Any]], mode_configs: Sequence[ModeConfig]) -> None:
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts(plt)

    labels = [config.label for config in mode_configs]
    direct_scores = [_coerce_score(mode_payloads[config.key]["macro_scores"].get("direct_macro")) for config in mode_configs]
    official_scores = [_coerce_score(mode_payloads[config.key]["macro_scores"].get("official_macro")) for config in mode_configs]
    x = list(range(len(labels)))

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6))
    for ax in axes:
        ax.set_facecolor("#fbfaf7")
        ax.grid(axis="y", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
        ax.set_ylim(0, 1.0)

    axes[0].bar(x, direct_scores, color="#355070")
    axes[0].set_title("直接作答质量均值\n(response_relevancy + factual_correctness)/2", fontsize=12, fontweight="bold")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)

    axes[1].bar(x, official_scores, color="#c8553d")
    axes[1].set_title("官方五指标均值\n(五项 RAGAS 指标简单平均)", fontsize=12, fontweight="bold")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)

    fig.suptitle("四方案综合得分对比", fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def write_outputs(output_dir: Path, payload: Dict[str, Any], mode_configs: Sequence[ModeConfig]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"generation_mode_comparison_{timestamp}.json"
    markdown_path = output_dir / f"generation_mode_comparison_{timestamp}.md"
    overall_plot_path = output_dir / f"generation_mode_overall_metrics_{timestamp}.png"
    macro_plot_path = output_dir / f"generation_mode_macro_scores_{timestamp}.png"

    _write_json(json_path, payload)
    _plot_metric_bars(overall_plot_path, payload["mode_results"], mode_configs)
    _plot_macro_scores(macro_plot_path, payload["mode_results"], mode_configs)

    lines: List[str] = [
        "# 四种生成方案效果对比",
        "",
        f"- created_at: {payload['created_at']}",
        f"- dataset: {payload['dataset_path']}",
        f"- sample_count: {payload['sample_count']}",
        f"- llm_model: {payload['llm_model']}",
        "",
        "## 方案定义",
        "",
        "- Zero-shot：不给检索上下文，只给领域专家系统提示，直接回答。",
        "- Few-shot：不给检索上下文，但给 3 个领域内示例问答，再回答。",
        "- With RAG：使用当前系统的检索增强生成链路。",
        "- No RAG：不给检索上下文，只让通用助手直接作答。",
        "",
        "## 对比公式",
        "",
        "```tex",
        "S_{official}(m)=\\frac{1}{5}\\sum_{k \\in \\{F,CP,CR,RR,FC\\}} score_k(m)",
        "S_{direct}(m)=\\frac{response\\_relevancy(m)+factual\\_correctness(m)}{2}",
        "Gain(a,b)=\\frac{S(a)-S(b)}{\\max(S(b), 10^{-6})}",
        "F1=\\frac{2PR}{P+R}",
        "```",
        "",
        "其中：",
        "- F 表示 faithfulness",
        "- CP 表示 context_precision",
        "- CR 表示 context_recall",
        "- RR 表示 response_relevancy",
        "- FC 表示 factual_correctness",
        "",
        "## 总体指标表",
        "",
        "| mode | faithfulness | context_precision | context_recall | response_relevancy | factual_correctness | direct_macro | official_macro |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for config in mode_configs:
        result = payload["mode_results"][config.key]
        summary = result["official_ragas_metrics"]
        macro = result["macro_scores"]
        lines.append(
            "| {label} | {faithfulness} | {context_precision} | {context_recall} | {response_relevancy} | {factual_correctness} | {direct_macro} | {official_macro} |".format(
                label=config.label,
                faithfulness=summary.get("faithfulness"),
                context_precision=summary.get("context_precision"),
                context_recall=summary.get("context_recall"),
                response_relevancy=summary.get("response_relevancy"),
                factual_correctness=summary.get("factual_correctness"),
                direct_macro=macro.get("direct_macro"),
                official_macro=macro.get("official_macro"),
            )
        )

    lines.extend([
        "",
        "## 图表路径",
        "",
        f"- overall_metrics_plot: {overall_plot_path}",
        f"- macro_scores_plot: {macro_plot_path}",
        "",
        "## 现象解释",
        "",
    ])

    for item in payload["explanations"]:
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## 结论建议",
        "",
        "- 如果目标是突出检索增强的价值，应优先比较 With RAG 与 No RAG 的 faithfulness、context_precision、context_recall 差异。",
        "- 如果目标是突出提示工程的价值，应优先比较 Zero-shot 与 Few-shot 的 response_relevancy、factual_correctness 差异。",
        "- 对答辩展示而言，可把四方案并排展示，但论文主结论应把 RAG 与非 RAG 的比较作为主线。",
    ])

    with markdown_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(lines).strip() + "\n")

    return {
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "overall_metrics_plot": str(overall_plot_path),
        "macro_scores_plot": str(macro_plot_path),
    }


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()

    conf = Config()
    if args.llm_model:
        conf.LLM_MODEL = args.llm_model

    if not conf.DASHSCOPE_API_KEY or conf.DASHSCOPE_API_KEY.startswith("demo-key"):
        raise RuntimeError("EDURAG_DASHSCOPE_API_KEY is not configured; comparison evaluation requires a working generation and judge model")

    selected_mode_configs = [config for config in MODE_CONFIGS if config.key in args.modes]
    records = load_records(dataset_path, args.max_samples, args.sample_mode)
    if args.slice_start:
        records = records[args.slice_start :]
    if args.slice_count is not None:
        records = records[: args.slice_count]
    mode_results: Dict[str, Dict[str, Any]] = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    uncached_mode_configs = []
    for config in selected_mode_configs:
        cache_path = _mode_cache_path(output_dir, config.key)
        runtime_cache_path = _runtime_cache_path(output_dir, config.key)
        if args.reuse_cached and cache_path.exists():
            mode_results[config.key] = _read_json(cache_path)
            continue
        uncached_mode_configs.append(config)

    rag_system = instantiate_rag(conf) if any(config.uses_rag for config in uncached_mode_configs) else None
    client = OpenAI(api_key=conf.DASHSCOPE_API_KEY, base_url=conf.DASHSCOPE_BASE_URL)
    metrics, metric_names = resolve_metric_instances()
    llm_wrapper, embedding_wrapper = load_ragas_wrappers(conf)

    for config in uncached_mode_configs:
        cache_path = _mode_cache_path(output_dir, config.key)
        runtime_cache_path = _runtime_cache_path(output_dir, config.key)

        runtime_samples = build_runtime_samples_for_mode(
            records,
            config,
            conf,
            args.default_source_filter,
            rag_system,
            client,
        )
        legacy_metrics = compute_legacy_metrics(records, runtime_samples, args.default_source_filter)
        _write_json(runtime_cache_path, runtime_samples)
        ragas_dataset = build_ragas_dataset(runtime_samples)
        ragas_results = _run_ragas_stable(
            ragas_dataset,
            metrics,
            metric_names,
            llm_wrapper,
            embedding_wrapper,
            raise_exceptions=args.raise_ragas_errors,
        )
        question_type_breakdown = build_question_type_breakdown(records, legacy_metrics, ragas_results.get("rows", []))

        mode_results[config.key] = {
            "label": config.label,
            "legacy_metrics": legacy_metrics,
            "official_ragas_metrics": ragas_results["summary"],
            "macro_scores": _build_macro_scores(ragas_results["summary"]),
            "question_type_breakdown": question_type_breakdown,
            "runtime_samples": runtime_samples,
        }
        _write_json(cache_path, mode_results[config.key])

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "sample_count": len(records),
        "llm_model": conf.LLM_MODEL,
        "mode_results": mode_results,
        "mode_rankings": {
            metric_name: _rank_modes(mode_results, metric_name) for metric_name in OFFICIAL_METRIC_ORDER
        },
        "explanations": _generate_explanations(mode_results),
    }
    report_paths = write_outputs(output_dir, payload, selected_mode_configs)
    stdout_payload = {
        "report_paths": report_paths,
        "mode_rankings": payload["mode_rankings"],
        "macro_scores": {key: value["macro_scores"] for key, value in mode_results.items()},
    }
    print(json.dumps(stdout_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()