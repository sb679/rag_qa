import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts" / "chunk_config_internal"
REPORT_PATH = ARTIFACTS_DIR / "chunk_config_internal_report.json"
SUMMARY_MD_PATH = ARTIFACTS_DIR / "chunk_config_internal_summary.md"
SUMMARY_JSON_PATH = ARTIFACTS_DIR / "chunk_config_internal_summary.json"


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


def ensure_dirs(artifacts_dir: Path) -> Path:
    plots_dir = artifacts_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return plots_dir


def load_report(report_path: Path) -> Dict[str, Any]:
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _labels(configs: List[Dict[str, Any]]) -> List[str]:
    return [str(item["label"]) for item in configs]


def save_quality_plot(configs: List[Dict[str, Any]], plots_dir: Path, output_tag: str = "") -> str:
    labels = _labels(configs)
    precision_values = [float(item.get("context_precision_proxy_mean") or 0.0) for item in configs]
    recall_values = [float(item.get("context_recall_proxy_mean") or 0.0) for item in configs]
    f1_values = [float(item.get("retrieval_f1_proxy_mean") or 0.0) for item in configs]

    x = list(range(len(labels)))
    width = 0.24

    fig, ax = plt.subplots(figsize=(10.8, 5.1))
    bars_1 = ax.bar([v - width for v in x], precision_values, width=width, color="#457b9d", label="上下文精确率代理")
    bars_2 = ax.bar(x, recall_values, width=width, color="#2a9d8f", label="上下文召回率代理")
    bars_3 = ax.bar([v + width for v in x], f1_values, width=width, color="#1d3557", label="检索F1代理")

    ax.set_title("不同分块策略的离线检索代理指标对比")
    ax.set_ylabel("指标值")
    ax.set_ylim(0, 1.05)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(loc="upper left")

    for bars in (bars_1, bars_2, bars_3):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.015, f"{value:.3f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    output_path = _tagged_path(plots_dir / "fig_chunk_quality_internal.png", output_tag)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def save_score_latency_plot(configs: List[Dict[str, Any]], plots_dir: Path, output_tag: str = "") -> str:
    labels = _labels(configs)
    scores = [float(item.get("normalized_adaptation_index") or 0.0) for item in configs]
    latencies = [float(item.get("latency_mean_sec") or 0.0) for item in configs]

    fig, ax1 = plt.subplots(figsize=(10.2, 5.0))
    bars = ax1.bar(labels, scores, color="#e9c46a", label="归一化综合指数")
    ax1.set_ylabel("归一化综合指数")
    ax1.set_ylim(0, 1.0)
    ax1.grid(axis="y", linestyle="--", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(labels, latencies, color="#e76f51", marker="o", linewidth=2, label="平均时延")
    ax2.set_ylabel("平均时延 / s")
    ax2.set_ylim(0, max(latencies) * 1.25 if latencies else 1)

    for bar, score in zip(bars, scores):
        ax1.text(bar.get_x() + bar.get_width() / 2, score + 0.02, f"{score:.3f}", ha="center", va="bottom", fontsize=8)
    for x_pos, latency in zip(labels, latencies):
        ax2.text(x_pos, latency + 0.2, f"{latency:.2f}s", color="#e76f51", ha="center", va="bottom", fontsize=8)

    ax1.set_title("不同分块策略的归一化综合指数与时延对比")
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left")

    fig.tight_layout()
    output_path = _tagged_path(plots_dir / "fig_chunk_score_latency_internal.png", output_tag)
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def _best_config(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return max(configs, key=lambda item: float(item.get("production_composite_score") or 0.0))


def write_summary(
    report: Dict[str, Any],
    report_path: Path,
    quality_plot: str,
    score_latency_plot: str,
    summary_md_path: Path,
    summary_json_path: Path,
) -> None:
    configs = report["configs"]
    best = _best_config(configs)
    summary = {
        "report_path": str(report_path),
        "samples": report.get("samples"),
        "recommended_config": best.get("label"),
        "score_formula": report.get("score_formula"),
        "plots": {
            "quality": quality_plot,
            "score_latency": score_latency_plot,
        },
        "notes": [
            "该报告用于同一语料、同一测试集、同一检索参数下的分块策略内部比较，不应用于与其他实验直接比较绝对数值。",
            "图1采用分组柱状图展示三项离线检索代理指标，便于比较不同分块策略的聚焦性、覆盖性和综合检索平衡。",
            "图2采用柱线组合图，将归一化综合指数与平均时延并排展示，便于做效果/成本权衡。",
            "归一化综合指数仅用于内部排序展示，最优配置被线性映射到 0.92，不表示绝对检索准确率。",
        ],
    }
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "## 分块策略内部对比实验总结",
        "",
        "本实验采用内部对比原则：在同一冶金语料、同一测试集和同一检索参数下，仅比较不同父子块配置的相对表现。",
        f"本次共评估 {report.get('samples')} 条样本，推荐配置为 {best.get('label')}，其归一化综合指数为 {float(best.get('normalized_adaptation_index') or 0.0):.3f}。",
        "",
        "评分说明：首先保留上下文召回率代理、上下文精确率代理和检索F1代理等原始内部指标；其次引入结构完整性和粒度平衡两个工程指标，计算面向生产配置选择的综合分；最后再将该综合分线性映射为 0.70-0.92 区间内的归一化综合指数，用于排序与结论展示。",
        "",
        "【图1：不同分块策略的离线检索代理指标对比】",
        quality_plot,
        "",
        "【图2：不同分块策略的归一化综合指数与时延对比】",
        score_latency_plot,
        "",
        "| 分块配置 | 精确率代理 | 召回率代理 | 检索F1代理 | 生产综合分 | 平均时延/s | 归一化综合指数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for item in configs:
        lines.append(
            f"| {item['label']} | {float(item.get('context_precision_proxy_mean') or 0.0):.4f} | "
            f"{float(item.get('context_recall_proxy_mean') or 0.0):.4f} | "
            f"{float(item.get('retrieval_f1_proxy_mean') or 0.0):.4f} | "
            f"{float(item.get('production_composite_score') or 0.0):.2f} | "
            f"{float(item.get('latency_mean_sec') or 0.0):.3f} | "
            f"{float(item.get('normalized_adaptation_index') or 0.0):.3f} |"
        )

    lines.extend(
        [
            "",
            f"从内部对比结果看，{best.get('label')} 在当前实验条件下获得最高生产综合分，并被映射为 0.920 的归一化综合指数，因此更适合作为正式实验或论文主配置候选。",
            "若后续需要做正式论文结论，建议仅对生产综合分前 2 名配置继续扩大样本量，而不要重新全量测试全部配置。",
        ]
    )
    summary_md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate plots and summary for internal chunk comparison")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Internal comparison report JSON path")
    parser.add_argument("--output-tag", default="", help="Optional suffix added to generated filenames")
    args = parser.parse_args()

    configure_fonts()
    report_path = Path(args.report).resolve()
    artifacts_dir = report_path.parent
    plots_dir = ensure_dirs(artifacts_dir)
    summary_md_path = _tagged_path(artifacts_dir / SUMMARY_MD_PATH.name, args.output_tag)
    summary_json_path = _tagged_path(artifacts_dir / SUMMARY_JSON_PATH.name, args.output_tag)

    report = load_report(report_path)
    quality_plot = save_quality_plot(report["configs"], plots_dir, args.output_tag)
    score_latency_plot = save_score_latency_plot(report["configs"], plots_dir, args.output_tag)
    write_summary(report, report_path, quality_plot, score_latency_plot, summary_md_path, summary_json_path)
    print(f"Saved plots to: {plots_dir}")
    print(f"Saved summary markdown to: {summary_md_path}")
    print(f"Saved summary json to: {summary_json_path}")


if __name__ == "__main__":
    main()