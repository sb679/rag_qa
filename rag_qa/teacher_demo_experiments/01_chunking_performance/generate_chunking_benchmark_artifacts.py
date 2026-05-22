import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
REPORT_PATH = ARTIFACTS_DIR / "benchmark_km_report.json"
PLOTS_DIR = ARTIFACTS_DIR / "plots"
THESIS_MD_PATH = ARTIFACTS_DIR / "benchmark_km_thesis_section.md"
THESIS_JSON_PATH = ARTIFACTS_DIR / "benchmark_km_thesis_summary.json"


def _tagged_path(path: Path, output_tag: str) -> Path:
    if not output_tag:
        return path
    suffix = output_tag if output_tag.startswith("_") else f"_{output_tag}"
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def configure_fonts() -> None:
    preferred_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in preferred_fonts:
        if font_name in available:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_report(report_path: Path) -> Dict[str, Any]:
    if not report_path.exists():
        raise FileNotFoundError(f"Benchmark report not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def ensure_dirs() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def _labels(configs: List[Dict[str, Any]]) -> List[str]:
    return [f"K={item['k']}, M={item['m']}" for item in configs]


def _metric_value(item: Dict[str, Any], field: str) -> Optional[float]:
    if int(item.get("valid_quality_samples") or 0) <= 0:
        return None
    value = item.get(field)
    if value is None:
        return None
    return float(value)


def _format_metric(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def save_latency_plot(configs: List[Dict[str, Any]], output_tag: str = "") -> str:
    labels = _labels(configs)
    values = [float(item["latency_mean_sec"] or 0.0) for item in configs]
    baseline = values[0] if values and values[0] > 0 else 1.0
    relative_values = [value / baseline for value in values]

    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    bars = ax.bar(labels, relative_values, color=["#457b9d", "#1d3557", "#6c757d"])
    ax.set_title("不同检索参数配置的相对响应时间")
    ax.set_ylabel("相对基线倍数")
    ax.set_ylim(0, max(relative_values) * 1.25)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.axhline(1.0, color="#6c757d", linestyle="--", linewidth=1)
    for index, (bar, rel_value, raw_value) in enumerate(zip(bars, relative_values, values)):
        if index == 0:
            label = f"1.00x\n({raw_value:.3f}s)"
        else:
            delta_pct = (rel_value - 1.0) * 100
            label = f"{rel_value:.2f}x\n({delta_pct:+.1f}%)"
        ax.text(bar.get_x() + bar.get_width() / 2, rel_value + 0.03, label, ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    output_path = _tagged_path(PLOTS_DIR / "fig_5_1_latency.png", output_tag)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def save_quality_plot(configs: List[Dict[str, Any]], output_tag: str = "") -> str:
    labels = _labels(configs)
    hit_metrics = [_metric_value(item, "hit_quality_mean") for item in configs]
    hit_values = [value if value is not None else 0.0 for value in hit_metrics]
    timeout_values = [int(item["timeouts"] or 0) for item in configs]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), sharey=True)

    hit_colors = ["#2a9d8f" if value is not None else "#b0b0b0" for value in hit_metrics]
    bars_left = axes[0].bar(labels, hit_values, color=hit_colors)
    axes[0].set_title("命中质量对比")
    axes[0].set_ylabel("指标值")
    axes[0].set_ylim(0, 1.1)
    axes[0].grid(axis="y", linestyle="--", alpha=0.3)
    for bar, metric, value in zip(bars_left, hit_metrics, hit_values):
        if metric is None:
            bar.set_hatch("//")
            axes[0].text(bar.get_x() + bar.get_width() / 2, 0.03, "N/A", ha="center", va="bottom", fontsize=8)
        else:
            axes[0].text(bar.get_x() + bar.get_width() / 2, value + 0.03, f"{value:.4f}", ha="center", va="bottom", fontsize=8)

    bars_right = axes[1].bar(labels, timeout_values, color="#e76f51")
    axes[1].set_title("超时数对比")
    axes[1].set_ylim(0, max(timeout_values + [1]) * 1.2)
    axes[1].grid(axis="y", linestyle="--", alpha=0.3)
    for bar, value in zip(bars_right, timeout_values):
        axes[1].text(bar.get_x() + bar.get_width() / 2, value + 0.1, f"{value}", ha="center", va="bottom", fontsize=8)

    fig.suptitle("不同检索参数配置的质量与稳定性对比", fontsize=12)
    fig.tight_layout()
    output_path = _tagged_path(PLOTS_DIR / "fig_5_2_quality_timeout.png", output_tag)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def save_hallucination_plot(configs: List[Dict[str, Any]], output_tag: str = "") -> str:
    labels = _labels(configs)
    hit_metrics = [_metric_value(item, "hit_quality_mean") for item in configs]
    halluc_metrics = [_metric_value(item, "hallucination_rate_mean") for item in configs]
    hit_values = [value if value is not None else 0.0 for value in hit_metrics]
    halluc_values = [value if value is not None else 0.0 for value in halluc_metrics]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), sharey=True)

    hit_colors = ["#2a9d8f" if value is not None else "#b0b0b0" for value in hit_metrics]
    bars_left = axes[0].bar(labels, hit_values, color=hit_colors)
    axes[0].set_title("命中质量对比")
    axes[0].set_ylabel("指标值")
    axes[0].set_ylim(0, 1.1)
    axes[0].grid(axis="y", linestyle="--", alpha=0.3)
    for bar, metric, value in zip(bars_left, hit_metrics, hit_values):
        if metric is None:
            bar.set_hatch("//")
            axes[0].text(bar.get_x() + bar.get_width() / 2, 0.03, "N/A", ha="center", va="bottom", fontsize=8)
        else:
            axes[0].text(bar.get_x() + bar.get_width() / 2, value + 0.03, f"{value:.4f}", ha="center", va="bottom", fontsize=8)

    halluc_colors = ["#e76f51" if value is not None else "#b0b0b0" for value in halluc_metrics]
    bars_right = axes[1].bar(labels, halluc_values, color=halluc_colors)
    axes[1].set_title("幻觉率对比")
    axes[1].set_ylim(0, 1.1)
    axes[1].grid(axis="y", linestyle="--", alpha=0.3)
    for bar, metric, value in zip(bars_right, halluc_metrics, halluc_values):
        if metric is None:
            bar.set_hatch("//")
            axes[1].text(bar.get_x() + bar.get_width() / 2, 0.03, "N/A", ha="center", va="bottom", fontsize=8)
        else:
            axes[1].text(bar.get_x() + bar.get_width() / 2, value + 0.03, f"{value:.4f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle("不同检索参数配置的质量与幻觉率对比", fontsize=12)
    fig.tight_layout()
    output_path = _tagged_path(PLOTS_DIR / "fig_5_3_quality_hallucination.png", output_tag)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def build_table_rows(configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in configs:
        rows.append(
            {
                "config": f"K={item['k']}, M={item['m']}",
                "latency_mean_sec": item["latency_mean_sec"],
                "latency_p95_sec": item["latency_p95_sec"],
                "hit_quality_mean": _metric_value(item, "hit_quality_mean"),
                "valid_quality_samples": item["valid_quality_samples"],
                "timeouts": item["timeouts"],
            }
        )
    return rows


def best_config_text(configs: List[Dict[str, Any]]) -> str:
    best_item = max(
        configs,
        key=lambda item: (
            float(item["hit_quality_mean"] or 0.0),
            -int(item["timeouts"] or 0),
            -float(item["latency_mean_sec"] or 0.0),
        ),
    )
    return f"K={best_item['k']}, M={best_item['m']}"


def write_summary(
    report: Dict[str, Any],
    plot_1: str,
    plot_2: str,
    report_path: Path,
    thesis_md_path: Path,
    thesis_json_path: Path,
) -> None:
    configs = report["configs"]
    rows = build_table_rows(configs)
    best_config = best_config_text(configs)

    summary = {
        "report_path": str(report_path),
        "samples": report.get("samples"),
        "per_query_timeout_sec": report.get("per_query_timeout_sec"),
        "hallucination_support_threshold": configs[0].get("hallucination_support_threshold") if configs else None,
        "table_rows": rows,
        "recommended_config": best_config,
        "plots": {
            "latency": plot_1,
            "quality_timeout": plot_2,
        },
        "notes": [
            "该实验属于参数对比实验，建议在论文中同时报告样本数、超时次数和有效质量样本数。",
            "若 valid_quality_samples 明显小于总样本数，应在正文中说明该配置存在超时或失败样本。",
            "当前图表采用柱状图和双子图，分别展示质量与稳定性，避免无效指标干扰参数结论。",
        ],
    }
    thesis_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "## 5.1 父子块检索参数对比实验",
        "",
        "为验证不同父子块检索参数配置对系统问答效果的影响，本文对三组参数组合进行对比实验，重点考察平均响应时间、命中质量以及超时情况。",
        "",
        f"本次实验共使用 {report.get('samples')} 条测试样本，单题超时上限为 {report.get('per_query_timeout_sec')} 秒。",
        "",
        "【此处插入图5-1：不同检索参数配置的相对响应时间对比图】",
        plot_1,
        "",
        "【此处插入图5-2：不同检索参数配置的命中质量与超时数对比图】",
        plot_2,
        "",
        "【此处插入表5-1：不同检索参数组合实验结果对比表】",
        "",
        "| 参数组合 | 平均响应时间/s | P95时延/s | 命中质量 | 有效样本数 | 超时数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in rows:
        md_lines.append(
            f"| {row['config']} | {row['latency_mean_sec']:.3f} | {row['latency_p95_sec']:.3f} | "
            f"{_format_metric(row['hit_quality_mean'])} | {row['valid_quality_samples']} | {row['timeouts']} |"
        )

    md_lines.extend(
        [
            "",
            "从实验结果看，不同参数配置在响应效率、命中质量与稳定性之间存在明显权衡。",
            f"在当前结果中，{best_config} 在质量优先的比较中更占优势，但若其超时数或有效样本数不足，也应在论文中同时说明其稳定性代价。",
            "因此，该实验更适合作为参数选择的探索性依据，而不是单独支撑统计性很强的泛化结论。",
        ]
    )

    baseline_latency = float(configs[0]["latency_mean_sec"] or 0.0) if configs else 0.0
    if baseline_latency > 0:
        md_lines.extend(
            [
                "",
                "相对延时以基线配置 K=5, M=2 记为 1.00x，用于减弱不同实验环境下绝对秒数波动对结论表达的干扰。",
            ]
        )

    thesis_md_path.write_text("\n".join(md_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate thesis-ready benchmark plots and summary files")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Benchmark report JSON path")
    parser.add_argument("--output-tag", default="", help="Optional suffix added to generated filenames")
    args = parser.parse_args()

    configure_fonts()
    ensure_dirs()
    report_path = Path(args.report).resolve()
    thesis_md_path = _tagged_path(THESIS_MD_PATH, args.output_tag)
    thesis_json_path = _tagged_path(THESIS_JSON_PATH, args.output_tag)

    report = load_report(report_path)
    plot_1 = save_latency_plot(report["configs"], args.output_tag)
    plot_2 = save_quality_plot(report["configs"], args.output_tag)
    write_summary(report, plot_1, plot_2, report_path, thesis_md_path, thesis_json_path)
    if any("hallucination_rate_mean" in item for item in report.get("configs", [])):
        save_hallucination_plot(report["configs"], args.output_tag)
    print(f"Saved plots to: {PLOTS_DIR}")
    print(f"Saved thesis section to: {thesis_md_path}")
    print(f"Saved summary json to: {thesis_json_path}")


if __name__ == "__main__":
    main()