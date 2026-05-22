from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

from openai import OpenAI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from base import Config
from evaluate_official_ragas import _configure_matplotlib_fonts, load_records, normalize_question

DEFAULT_DATASET = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "testset_governance" / "metallurgy_demo20_stable_ragas_dataset.json"
DEFAULT_OUTPUT_DIR = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "generation_mode_public_judge_demo20_stable"
DEFAULT_MODE_OUTPUT_DIR = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "generation_mode_comparison_demo20_stable"
DEFAULT_RAG_REPORT = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "official_ragas_eval_demo20_stable" / "ragas_vs_legacy_20260522_100606.json"
DEFAULT_RAG_RUNTIME = ROOT / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "official_ragas_eval_demo20_stable" / "ragas_runtime_samples_20260522_100606.json"

MODE_LABELS = {
    "zero_shot": "Zero-shot",
    "few_shot": "Few-shot",
    "rag": "With RAG",
    "no_rag": "No RAG",
}
MODE_ORDER = ["zero_shot", "few_shot", "rag", "no_rag"]
PUBLIC_METRICS = ["correctness", "relevancy", "completeness"]
PUBLIC_WEIGHTED_METRICS = {
    "correctness": 0.45,
    "completeness": 0.40,
    "relevancy": 0.15,
}
RAG_ONLY_METRICS = ["faithfulness", "context_precision", "context_recall"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generation public metrics with judge model and richer plots")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Dataset JSON path")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to save public-metric outputs")
    parser.add_argument("--mode-output-dir", default=str(DEFAULT_MODE_OUTPUT_DIR), help="Directory containing existing mode caches")
    parser.add_argument("--rag-report", default=str(DEFAULT_RAG_REPORT), help="Official RAG report JSON path")
    parser.add_argument("--rag-runtime", default=str(DEFAULT_RAG_RUNTIME), help="Official RAG runtime samples JSON path")
    parser.add_argument("--llm-model", default=None, help="Override EDURAG_LLM_MODEL")
    parser.add_argument("--max-samples", type=int, default=20, help="Limit sample count")
    parser.add_argument(
        "--sample-mode",
        choices=("sequential", "balanced-question-type"),
        default="balanced-question-type",
        help="Sampling mode passed to dataset loader",
    )
    parser.add_argument("--reuse-cached", action="store_true", help="Reuse existing judge caches when available")
    return parser.parse_args()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)


def _extract_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    if not match:
        raise ValueError(f"Judge output did not include JSON: {text}")
    return json.loads(match.group(0))


def _clamp_score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return round(max(0.0, min(1.0, numeric)), 4)


def _mean(values: Sequence[float]) -> float:
    numeric = [float(item) for item in values]
    return round(sum(numeric) / len(numeric), 4) if numeric else 0.0


def _judge_cache_path(output_dir: Path, mode_key: str) -> Path:
    return output_dir / f"judge_public_metrics_{mode_key}.json"


def _rebuild_runtime_samples_from_reports(
    records: Sequence[Dict[str, Any]],
    mode_output_dir: Path,
    rag_report_path: Path,
) -> Dict[str, List[Dict[str, Any]]]:
    record_by_id = {str(record["id"]): record for record in records}
    mode_paths = {
        "zero_shot": mode_output_dir / "mode_result_zero_shot.json",
        "few_shot": mode_output_dir / "mode_result_few_shot.json",
        "no_rag": mode_output_dir / "mode_result_no_rag.json",
    }

    rebuilt: Dict[str, List[Dict[str, Any]]] = {}
    for mode_key, path in mode_paths.items():
        payload = _read_json(path)
        rows = []
        for item in payload["legacy_metrics"]["per_item"]:
            record = record_by_id[str(item["id"])]
            rows.append(
                {
                    "question": record["question"],
                    "reference": record["ground_truth"],
                    "response": item["prediction"],
                    "dataset_contexts": record.get("context", []),
                }
            )
        rebuilt[mode_key] = rows

    rag_payload = _read_json(rag_report_path)
    rag_rows = []
    for item in rag_payload["legacy_metrics"]["per_item"]:
        record = record_by_id[str(item["id"])]
        rag_rows.append(
            {
                "question": record["question"],
                "reference": record["ground_truth"],
                "response": item["prediction"],
                "dataset_contexts": record.get("context", []),
            }
        )
    rebuilt["rag"] = rag_rows
    return rebuilt


def _load_existing_rag_metrics(rag_report_path: Path) -> Dict[str, float]:
    payload = _read_json(rag_report_path)
    return {key: payload["official_ragas_metrics"].get(key) for key in RAG_ONLY_METRICS + ["response_relevancy", "factual_correctness"]}


def _filter_by_dataset_indices(records: Sequence[Dict[str, Any]], runtime_samples: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(records) > len(runtime_samples):
        raise ValueError("Runtime sample count is smaller than dataset record count")
    selected = list(runtime_samples[: len(records)])
    for index, record in enumerate(records):
        question = normalize_question(record["question"])
        runtime_question = normalize_question(selected[index]["question"])
        if question != runtime_question:
            raise ValueError(f"Runtime sample order mismatch at index {index}: {question} != {runtime_question}")
    return selected


def _judge_public_metrics_for_sample(client: OpenAI, model_name: str, sample: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "你是一名严谨的闭域问答评测员。请只根据问题、参考答案和模型回答，评估三个维度："
        "correctness（事实是否正确）、relevancy（是否直接回答问题）、completeness（关键要点是否覆盖充分）。"
        "分数范围都是 0 到 1。"
        "输出必须是 JSON，格式为 {\"correctness\":0到1,\"relevancy\":0到1,\"completeness\":0到1,\"summary\":\"一句中文结论\"}。"
    )
    user_prompt = (
        f"问题：{sample['question']}\n"
        f"参考答案：{sample['reference']}\n"
        f"模型回答：{sample['response']}\n"
        "请给出三个分数，并简要总结。"
    )
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=260,
        timeout=120,
        stream=False,
    )
    content = completion.choices[0].message.content if completion.choices else ""
    parsed = _extract_json_object(content)
    return {
        "correctness": _clamp_score(parsed.get("correctness")),
        "relevancy": _clamp_score(parsed.get("relevancy")),
        "completeness": _clamp_score(parsed.get("completeness")),
        "summary": str(parsed.get("summary") or "").strip(),
    }


def _compute_public_metrics(
    output_dir: Path,
    mode_key: str,
    runtime_samples: Sequence[Dict[str, Any]],
    client: OpenAI,
    model_name: str,
    reuse_cached: bool,
) -> Dict[str, Any]:
    cache_path = _judge_cache_path(output_dir, mode_key)
    if reuse_cached and cache_path.exists():
        return _read_json(cache_path)

    rows: List[Dict[str, Any]] = []
    for sample in runtime_samples:
        judged = _judge_public_metrics_for_sample(client, model_name, sample)
        rows.append(
            {
                "question": sample["question"],
                **judged,
            }
        )

    summary = {metric: _mean([row[metric] for row in rows]) for metric in PUBLIC_METRICS}
    summary["public_weighted_score"] = round(
        sum(summary[key] * weight for key, weight in PUBLIC_WEIGHTED_METRICS.items()),
        4,
    )
    payload = {"summary": summary, "rows": rows}
    _write_json(cache_path, payload)
    return payload


def _plot_public_grouped_bar(output_path: Path, mode_results: Dict[str, Dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    _configure_matplotlib_fonts(plt)
    labels = ["Correctness", "Relevancy", "Completeness"]
    x = np.arange(len(labels))
    width = 0.18
    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]

    fig, ax = plt.subplots(figsize=(12.8, 7.0))
    ax.set_facecolor("#fbfaf7")
    for idx, mode_key in enumerate(MODE_ORDER):
        values = [mode_results[mode_key]["public_summary"][metric] for metric in PUBLIC_METRICS]
        ax.bar(x + (idx - 1.5) * width, values, width=width, label=MODE_LABELS[mode_key], color=colors[idx])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Score")
    ax.set_title("四方案公共生成质量指标对比", fontsize=15, fontweight="bold")
    ax.grid(axis="y", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.10))
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_public_radar(output_path: Path, mode_results: Dict[str, Dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    _configure_matplotlib_fonts(plt)
    labels = ["Correctness", "Relevancy", "Completeness"]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]

    fig, ax = plt.subplots(figsize=(8.6, 8.2), subplot_kw={"polar": True})
    ax.set_facecolor("#fbfaf7")
    for idx, mode_key in enumerate(MODE_ORDER):
        values = [mode_results[mode_key]["public_summary"][metric] for metric in PUBLIC_METRICS]
        values += values[:1]
        ax.plot(angles, values, color=colors[idx], linewidth=2.2, label=MODE_LABELS[mode_key])
        ax.fill(angles, values, color=colors[idx], alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.0)
    ax.set_title("公共生成指标雷达图", y=1.14, fontsize=15, fontweight="bold")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False)
    fig.subplots_adjust(top=0.86, bottom=0.18)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_scatter(output_path: Path, mode_results: Dict[str, Dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts(plt)
    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]
    fig, ax = plt.subplots(figsize=(10.8, 7.2))
    ax.set_facecolor("#fbfaf7")
    for idx, mode_key in enumerate(MODE_ORDER):
        summary = mode_results[mode_key]["public_summary"]
        x = summary["correctness"]
        y = summary["completeness"]
        bubble = 450 + 1100 * summary["relevancy"]
        ax.scatter(x, y, s=bubble, color=colors[idx], alpha=0.82, edgecolor="white", linewidth=1.5)
        ax.text(x + 0.01, y + 0.01, MODE_LABELS[mode_key], fontsize=10)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Correctness")
    ax.set_ylabel("Completeness")
    ax.set_title("正确性-完整性散点图（气泡大小=相关性）", fontsize=15, fontweight="bold")
    ax.grid(True, linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_weighted_ranking(output_path: Path, mode_results: Dict[str, Dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts(plt)
    rows = sorted(
        [
            {
                "label": MODE_LABELS[mode_key],
                "score": mode_results[mode_key]["public_summary"]["public_weighted_score"],
            }
            for mode_key in MODE_ORDER
        ],
        key=lambda item: item["score"],
        reverse=True,
    )
    colors = ["#59a14f" if row["label"] == "With RAG" else "#9c755f" for row in rows]
    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    ax.set_facecolor("#fbfaf7")
    y = list(range(len(rows)))
    ax.hlines(y, xmin=0, xmax=[row["score"] for row in rows], color=colors, linewidth=4)
    ax.scatter([row["score"] for row in rows], y, color=colors, s=120, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([row["label"] for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Weighted Public Score")
    ax.set_title("闭域问答公共综合得分排序", fontsize=15, fontweight="bold")
    ax.grid(axis="x", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    for index, row in enumerate(rows):
        ax.text(min(row["score"] + 0.02, 0.98), y[index], f"{row['score']:.3f}", va="center", ha="left", fontsize=10, color="#102a43")
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_completeness_box(output_path: Path, mode_results: Dict[str, Dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    _configure_matplotlib_fonts(plt)
    fig, ax = plt.subplots(figsize=(11.2, 6.4))
    ax.set_facecolor("#fbfaf7")
    series = [[row["completeness"] for row in mode_results[mode_key]["public_rows"]] for mode_key in MODE_ORDER]
    labels = [MODE_LABELS[mode_key] for mode_key in MODE_ORDER]
    box = ax.boxplot(series, patch_artist=True, tick_labels=labels, showmeans=True)
    palette = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]
    for patch, color in zip(box["boxes"], palette):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
    for mean in box["means"]:
        mean.set_marker("D")
        mean.set_markerfacecolor("#102a43")
        mean.set_markeredgecolor("white")
        mean.set_markersize(6)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Completeness")
    ax.set_title("完整性分数分布箱线图", fontsize=15, fontweight="bold")
    ax.grid(axis="y", linestyle=(0, (2, 4)), linewidth=0.8, color="#d6d3d1", alpha=0.9)
    for index, values in enumerate(series, start=1):
        mean_value = sum(values) / len(values) if values else 0.0
        median_value = sorted(values)[len(values) // 2] if values else 0.0
        mean_y = min(mean_value + 0.04, 0.97)
        median_y = median_value - 0.055 if median_value > 0.08 else median_value + 0.045
        if abs(mean_y - median_y) < 0.05:
            mean_y = min(mean_y + 0.03, 0.97)
            median_y = max(median_y - 0.03, 0.03)
        ax.text(index + 0.1, mean_y, f"mean={mean_value:.3f}", fontsize=9, color="#102a43")
        ax.text(index + 0.1, median_y, f"median={median_value:.3f}", fontsize=9, color="#6b7280")
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _plot_full_heatmap(output_path: Path, mode_results: Dict[str, Dict[str, Any]], rag_metrics: Dict[str, float]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    _configure_matplotlib_fonts(plt)
    columns = ["Correctness", "Relevancy", "Completeness", "Faithfulness", "Context Precision", "Context Recall"]
    matrix = []
    for mode_key in MODE_ORDER:
        public_summary = mode_results[mode_key]["public_summary"]
        row = [public_summary[metric] for metric in PUBLIC_METRICS]
        if mode_key == "rag":
            row.extend([float(rag_metrics.get(metric) or 0.0) for metric in RAG_ONLY_METRICS])
        else:
            row.extend([math.nan, math.nan, math.nan])
        matrix.append(row)

    data = np.array(matrix, dtype=float)
    fig, ax = plt.subplots(figsize=(12.4, 5.6))
    cmap = plt.get_cmap("YlGnBu").copy()
    cmap.set_bad(color="#efe9dc")
    im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns, rotation=20, ha="right")
    ax.set_yticks(range(len(MODE_ORDER)))
    ax.set_yticklabels([MODE_LABELS[key] for key in MODE_ORDER])
    ax.set_title("公共指标 + RAG 专属指标总览热力图", fontsize=15, fontweight="bold")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            text = "-" if math.isnan(value) else f"{value:.2f}"
            ax.text(j, i, text, ha="center", va="center", color="#102a43", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _build_markdown(payload: Dict[str, Any], report_paths: Dict[str, str]) -> str:
    lines = [
        "# 四方案公共生成质量评测",
        "",
        f"- created_at: {payload['created_at']}",
        f"- dataset: {payload['dataset_path']}",
        f"- sample_count: {payload['sample_count']}",
        f"- llm_model: {payload['llm_model']}",
        "",
        "## 指标口径",
        "",
        "- correctness：回答与参考答案在关键事实、关键数值和关键动作上的一致程度。",
        "- relevancy：回答是否紧扣问题本身，是否存在明显跑题或过度扩写。",
        "- completeness：回答是否覆盖参考答案中的关键要点。",
        "- faithfulness/context_precision/context_recall：仅用于分析 RAG 机制的证据支撑能力。",
        "",
        "## 公共综合分公式",
        "",
        "```tex",
        "S_{public}^{weighted}(m)=0.45\cdot correctness(m)+0.40\cdot completeness(m)+0.15\cdot relevancy(m)",
        "```",
        "",
        "## 四方案公共指标表",
        "",
        "| mode | correctness | relevancy | completeness | weighted_public_score |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode_key in MODE_ORDER:
        summary = payload["mode_results"][mode_key]["public_summary"]
        lines.append(
            f"| {MODE_LABELS[mode_key]} | {summary['correctness']} | {summary['relevancy']} | {summary['completeness']} | {summary['public_weighted_score']} |"
        )
    lines.extend([
        "",
        "## 图表路径",
        "",
    ])
    for key, value in report_paths.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    mode_output_dir = Path(args.mode_output_dir).resolve()
    rag_report_path = Path(args.rag_report).resolve()
    rag_runtime_path = Path(args.rag_runtime).resolve()

    conf = Config()
    if args.llm_model:
        conf.LLM_MODEL = args.llm_model
    if not conf.DASHSCOPE_API_KEY or conf.DASHSCOPE_API_KEY.startswith("demo-key"):
        raise RuntimeError("EDURAG_DASHSCOPE_API_KEY is not configured; public metric judging requires a working model")

    all_records = _read_json(dataset_path)
    records = load_records(dataset_path, args.max_samples, args.sample_mode)
    runtime_by_mode = _rebuild_runtime_samples_from_reports(all_records, mode_output_dir, rag_report_path)
    rag_metrics = _load_existing_rag_metrics(rag_report_path)
    client = OpenAI(api_key=conf.DASHSCOPE_API_KEY, base_url=conf.DASHSCOPE_BASE_URL)

    mode_results: Dict[str, Dict[str, Any]] = {}
    for mode_key in MODE_ORDER:
        filtered_runtime = _filter_by_dataset_indices(records, runtime_by_mode[mode_key])
        judged = _compute_public_metrics(output_dir, mode_key, filtered_runtime, client, conf.LLM_MODEL, args.reuse_cached)
        mode_results[mode_key] = {
            "public_summary": judged["summary"],
            "public_rows": judged["rows"],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_paths = {
        "public_bar_plot": str(output_dir / f"generation_public_bar_{timestamp}.png"),
        "public_radar_plot": str(output_dir / f"generation_public_radar_{timestamp}.png"),
        "correctness_completeness_scatter": str(output_dir / f"generation_public_scatter_{timestamp}.png"),
        "weighted_ranking_plot": str(output_dir / f"generation_public_ranking_{timestamp}.png"),
        "completeness_box_plot": str(output_dir / f"generation_public_completeness_box_{timestamp}.png"),
        "full_metric_heatmap": str(output_dir / f"generation_public_full_heatmap_{timestamp}.png"),
        "json_report": str(output_dir / f"generation_public_report_{timestamp}.json"),
        "markdown_report": str(output_dir / f"generation_public_report_{timestamp}.md"),
    }

    _plot_public_grouped_bar(Path(report_paths["public_bar_plot"]), mode_results)
    _plot_public_radar(Path(report_paths["public_radar_plot"]), mode_results)
    _plot_scatter(Path(report_paths["correctness_completeness_scatter"]), mode_results)
    _plot_weighted_ranking(Path(report_paths["weighted_ranking_plot"]), mode_results)
    _plot_completeness_box(Path(report_paths["completeness_box_plot"]), mode_results)
    _plot_full_heatmap(Path(report_paths["full_metric_heatmap"]), mode_results, rag_metrics)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "sample_count": len(records),
        "llm_model": conf.LLM_MODEL,
        "public_weighted_formula": {
            "correctness": 0.45,
            "completeness": 0.40,
            "relevancy": 0.15,
        },
        "mode_results": mode_results,
        "rag_only_metrics": rag_metrics,
        "report_paths": report_paths,
    }
    _write_json(Path(report_paths["json_report"]), payload)
    Path(report_paths["markdown_report"]).write_text(_build_markdown(payload, report_paths), encoding="utf-8")

    stdout_payload = {
        "mode_scores": {mode_key: mode_results[mode_key]["public_summary"] for mode_key in MODE_ORDER},
        "report_paths": report_paths,
    }
    print(json.dumps(stdout_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
