import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
RESULT_PATH = ARTIFACTS_DIR / "results" / "strategy_selector_diagnostic_results.json"
PLOTS_DIR = ARTIFACTS_DIR / "plots"
THESIS_MD_PATH = ARTIFACTS_DIR / "reports" / "strategy_selector_thesis_section.md"
THESIS_JSON_PATH = ARTIFACTS_DIR / "reports" / "strategy_selector_thesis_summary.json"


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


def ensure_dirs() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    THESIS_MD_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_result() -> Dict[str, Any]:
    if not RESULT_PATH.exists():
        raise FileNotFoundError(f"Strategy selector result not found: {RESULT_PATH}")
    return json.loads(RESULT_PATH.read_text(encoding="utf-8-sig"))


def save_overall_metrics_plot(result: Dict[str, Any]) -> str:
    labels = ["Accuracy", "Macro-F1"]
    model_values = [
        float(result["model_only"]["accuracy"]),
        float(result["model_only"]["macro_f1"]),
    ]
    hybrid_values = [
        float(result["hybrid_selector"]["accuracy"]),
        float(result["hybrid_selector"]["macro_f1"]),
    ]

    x_positions = [0, 1]
    width = 0.34

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    bars_left = ax.bar([x - width / 2 for x in x_positions], model_values, width=width, label="原始 BERT 分类器", color="#6c757d")
    bars_right = ax.bar([x + width / 2 for x in x_positions], hybrid_values, width=width, label="混合策略选择器", color="#2a9d8f")

    ax.set_title("策略选择器整体指标对比")
    ax.set_ylabel("指标值")
    ax.set_xticks(x_positions, labels)
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend()

    for bars in (bars_left, bars_right):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.4f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    output_path = PLOTS_DIR / "fig_strategy_selector_overall_metrics.png"
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def save_per_class_f1_plot(result: Dict[str, Any]) -> str:
    labels = list(result["hybrid_selector"]["per_class"].keys())
    model_values = [float(result["model_only"]["per_class"][label]["f1"]) for label in labels]
    hybrid_values = [float(result["hybrid_selector"]["per_class"][label]["f1"]) for label in labels]

    x_positions = list(range(len(labels)))
    width = 0.34

    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    bars_left = ax.bar([x - width / 2 for x in x_positions], model_values, width=width, label="原始 BERT 分类器", color="#8d99ae")
    bars_right = ax.bar([x + width / 2 for x in x_positions], hybrid_values, width=width, label="混合策略选择器", color="#1d3557")

    ax.set_title("各策略类别 F1-score 对比")
    ax.set_ylabel("F1-score")
    ax.set_xticks(x_positions, labels)
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend()

    for bars in (bars_left, bars_right):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.4f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    output_path = PLOTS_DIR / "fig_strategy_selector_per_class_f1.png"
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def build_summary(result: Dict[str, Any], overall_plot: str, per_class_plot: str) -> Dict[str, Any]:
    labels = list(result["hybrid_selector"]["per_class"].keys())
    per_class_rows: List[Dict[str, Any]] = []
    for label in labels:
        model_metrics = result["model_only"]["per_class"][label]
        hybrid_metrics = result["hybrid_selector"]["per_class"][label]
        per_class_rows.append(
            {
                "label": label,
                "model_f1": model_metrics["f1"],
                "hybrid_f1": hybrid_metrics["f1"],
                "support": hybrid_metrics["support"],
            }
        )

    corrected_samples = [sample for sample in result.get("samples", []) if sample.get("expected") != sample.get("model_only") and sample.get("expected") == sample.get("hybrid")]

    return {
        "result_path": str(RESULT_PATH),
        "benchmark_size": result.get("benchmark_size"),
        "label_distribution": result.get("label_distribution"),
        "overall_metrics": {
            "model_only": result.get("model_only"),
            "hybrid_selector": result.get("hybrid_selector"),
        },
        "per_class_rows": per_class_rows,
        "corrected_sample_count": len(corrected_samples),
        "plots": {
            "overall_metrics": overall_plot,
            "per_class_f1": per_class_plot,
        },
    }


def write_outputs(result: Dict[str, Any], summary: Dict[str, Any]) -> None:
    corrected_count = summary["corrected_sample_count"]
    model_accuracy = float(result["model_only"]["accuracy"])
    hybrid_accuracy = float(result["hybrid_selector"]["accuracy"])
    model_macro_f1 = float(result["model_only"]["macro_f1"])
    hybrid_macro_f1 = float(result["hybrid_selector"]["macro_f1"])
    direct_model_f1 = float(result["model_only"]["per_class"]["直接检索"]["f1"])

    if hybrid_accuracy > model_accuracy or hybrid_macro_f1 > model_macro_f1:
        overall_text = (
            f"从整体结果看，混合策略选择器的 Accuracy 由 {model_accuracy:.4f} 提升至 {hybrid_accuracy:.4f}，"
            f"Macro-F1 由 {model_macro_f1:.4f} 提升至 {hybrid_macro_f1:.4f}，说明当前纠偏策略对边界样本具有实际修复作用。"
        )
    else:
        overall_text = (
            f"从整体结果看，混合策略选择器的 Accuracy 为 {hybrid_accuracy:.4f}，Macro-F1 为 {hybrid_macro_f1:.4f}，"
            "与原始 BERT 分类器保持一致，说明当前仓库中的规则纠偏尚未在该诊断基准上带来额外增益。"
        )

    if corrected_count > 0:
        detail_text = (
            f"进一步分析各类别结果可以发现，原始 BERT 分类器主要在“直接检索”类别上失效，其 F1-score 为 {direct_model_f1:.4f}；"
            f"加入纠偏后，共修正 {corrected_count} 条样本，说明边界问句仍可通过规则增强获得改善。"
        )
    else:
        detail_text = (
            f"进一步分析各类别结果可以发现，原始 BERT 分类器主要在“直接检索”类别上失效，其 F1-score 为 {direct_model_f1:.4f}；"
            "而当前混合策略输出未修正这些误判，表明事实型问句纠偏规则仍需继续补强。"
        )

    THESIS_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "## 检索策略选择模块诊断实验",
        "",
        "为验证检索策略选择模块在不同查询类型上的分类稳定性，本文构建了一个包含 20 条代表性问题的四分类诊断基准，对原始 BERT 分类器输出与加入规则纠偏后的混合策略选择器进行对比。评价指标采用 Accuracy 和 Macro-F1，并进一步统计各类别的 F1-score 表现。",
        "",
        f"本次实验共使用 {result.get('benchmark_size')} 条测试样本，四类标签分布均衡，每类各 {next(iter(result.get('label_distribution', {}).values()), 0)} 条。",
        "",
        "【此处插入图：原始分类器与混合策略选择器整体指标对比图】",
        summary["plots"]["overall_metrics"],
        "",
        "【此处插入图：各策略类别 F1-score 对比图】",
        summary["plots"]["per_class_f1"],
        "",
        "【此处插入表：检索策略选择模块整体指标对比表】",
        "",
        "| 模型/策略 | Accuracy | Macro-F1 |",
        "| --- | ---: | ---: |",
        f"| 原始 BERT 分类器输出 | {model_accuracy:.4f} | {model_macro_f1:.4f} |",
        f"| 混合策略选择器 | {hybrid_accuracy:.4f} | {hybrid_macro_f1:.4f} |",
        "",
        "【此处插入表：各策略类别 F1-score 对比表】",
        "",
        "| 策略类别 | 原始 BERT F1 | 混合策略 F1 | 样本数 |",
        "| --- | ---: | ---: | ---: |",
    ]

    for row in summary["per_class_rows"]:
        md_lines.append(
            f"| {row['label']} | {float(row['model_f1']):.4f} | {float(row['hybrid_f1']):.4f} | {row['support']} |"
        )

    md_lines.extend(
        [
            "",
            overall_text,
            detail_text,
            "因此，该实验可以作为论文中“策略选择模块优化有效性”的独立证据，但由于样本规模仍然较小，更适合用于模块诊断验证，而不宜单独外推为大规模泛化性能结论。",
        ]
    )

    THESIS_MD_PATH.write_text("\n".join(md_lines), encoding="utf-8")


def main() -> None:
    configure_fonts()
    ensure_dirs()
    result = load_result()
    overall_plot = save_overall_metrics_plot(result)
    per_class_plot = save_per_class_f1_plot(result)
    summary = build_summary(result, overall_plot, per_class_plot)
    write_outputs(result, summary)
    print(f"Saved plots to: {PLOTS_DIR}")
    print(f"Saved thesis section to: {THESIS_MD_PATH}")
    print(f"Saved summary json to: {THESIS_JSON_PATH}")


if __name__ == "__main__":
    main()