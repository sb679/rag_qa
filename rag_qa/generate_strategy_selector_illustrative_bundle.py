import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

import train_strategy_classifier_v2 as styled_plots


ROOT = Path(__file__).resolve().parent
ILLUSTRATIVE_DIR = ROOT / "ragas_paper_bundle" / "strategy_selector_experiment" / "illustrative_only"
PLOTS_DIR = ILLUSTRATIVE_DIR / "plots"
RESULTS_DIR = ILLUSTRATIVE_DIR / "results"


METHOD_ORDER = ["M0", "M1", "M2", "M3", "M4"]
COMPARISON_METHOD_ORDER = ["M0", "M1", "M3"]
METHOD_LABELS = {
    "M0": "No Strategy",
    "M1": "Rule-Only",
    "M2": "Legacy BERT",
    "M3": "Hybrid Selector",
    "M4": "BERT-v2",
}
METHOD_COLORS = ["#577590", "#277da1", "#f3722c", "#90be6d", "#9d4edd"]

ZH_METHOD_LABELS = {
    "M0": "无策略",
    "M1": "仅规则",
    "M2": "旧版BERT",
    "M3": "混合检索器",
    "M4": "BERT-v2",
}


RULE_EXPLANATION = {
    "definition": "规则指不依赖分类模型参数学习、仅基于查询表面特征与工程经验进行的显式路由逻辑。",
    "rules": [
        "事实型短问句优先走直接检索，例如包含“是什么、有哪些、定义、范围、条件”等表达，且问题较短、目标单一。",
        "对比型或多要素问题走查询分解检索，例如出现“比较、区别、差异、分别、优缺点”等词，或同一句中包含多个对象。",
        "现场工况、异常处置、方案设计类问题走问题重写检索，例如出现“如何、怎样、方案、优化、异常、故障、处置”等词，或同时带有数字参数、约束条件、多分句描述。",
        "抽象概念、趋势、价值、意义类问题走查询扩展检索，例如包含“意义、作用、趋势、前景、价值、影响”等抽象语义词。",
        "当多条规则同时命中时，优先级按工程风险更高的复杂策略覆盖简单策略，通常是问题重写检索 > 查询分解检索 > 查询扩展检索 > 直接检索。",
    ],
}


def configure_chinese_font() -> None:
    preferred_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Zen Hei",
    ]
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in preferred_fonts:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


def ensure_dirs() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_illustrative_summary() -> Dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "illustrative-only",
        "is_hypothetical": True,
        "label": "Idealized Strategy Selector Figures / Illustrative Only",
        "task": "Strategy ablation and end-to-end retrieval-effect comparison",
        "methods": {
            "M0": {
                "display_name": METHOD_LABELS["M0"],
                "accuracy": 0.54,
                "precision": 0.52,
                "recall": 0.50,
                "f1": 0.51,
                "complex_query_success": 0.46,
                "error_rate": 0.38,
            },
            "M1": {
                "display_name": METHOD_LABELS["M1"],
                "accuracy": 0.63,
                "precision": 0.62,
                "recall": 0.61,
                "f1": 0.61,
                "complex_query_success": 0.58,
                "error_rate": 0.26,
            },
            "M2": {
                "display_name": METHOD_LABELS["M2"],
                "accuracy": 0.72,
                "precision": 0.71,
                "recall": 0.70,
                "f1": 0.70,
                "complex_query_success": 0.68,
                "error_rate": 0.19,
            },
            "M3": {
                "display_name": METHOD_LABELS["M3"],
                "accuracy": 0.84,
                "precision": 0.85,
                "recall": 0.86,
                "f1": 0.85,
                "complex_query_success": 0.83,
                "error_rate": 0.10,
            },
            "M4": {
                "display_name": METHOD_LABELS["M4"],
                "accuracy": 0.89,
                "precision": 0.90,
                "recall": 0.91,
                "f1": 0.90,
                "complex_query_success": 0.89,
                "error_rate": 0.06,
            },
        },
        "ablation": {
            "No Strategy": {
                "answer_f1": 0.54,
                "evidence_hit": 0.50,
                "hallucination_control": 0.47,
                "complex_query_success": 0.41,
            },
            "Adaptive Strategy": {
                "answer_f1": 0.86,
                "evidence_hit": 0.88,
                "hallucination_control": 0.84,
                "complex_query_success": 0.82,
            },
        },
        "query_group_ablation": {
            "simple": {
                "No Strategy": {
                    "answer_f1": 0.76,
                    "evidence_hit": 0.73,
                    "hallucination_control": 0.70,
                    "complex_query_success": 0.68,
                },
                "Adaptive Strategy": {
                    "answer_f1": 0.84,
                    "evidence_hit": 0.82,
                    "hallucination_control": 0.80,
                    "complex_query_success": 0.79,
                },
            },
            "complex": {
                "No Strategy": {
                    "answer_f1": 0.41,
                    "evidence_hit": 0.38,
                    "hallucination_control": 0.36,
                    "complex_query_success": 0.31,
                },
                "Adaptive Strategy": {
                    "answer_f1": 0.84,
                    "evidence_hit": 0.87,
                    "hallucination_control": 0.82,
                    "complex_query_success": 0.80,
                },
            },
        },
        "notes": [
            "This bundle is illustrative only and is intended for slide design, thesis layout, or advisor communication.",
            "The numeric values are deliberately idealized and must not be claimed as measured experimental results.",
            "The gap is intentionally enlarged to make the ablation narrative visually legible in slides and thesis mockups.",
            "Use the real metrics in training_results_v2 and the diagnostic benchmark for factual reporting, and use this folder only for visual mockups.",
        ],
        "rule_only_explanation": RULE_EXPLANATION,
    }


def build_illustrative_training_summary() -> Dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "device": "illustrative-only",
        "train_size": 1024,
        "val_size": 128,
        "test_size": 128,
        "summary_metrics": {
            "accuracy": 0.9320,
            "precision_macro": 0.9315,
            "recall_macro": 0.9320,
            "f1_macro": 0.9312,
        },
        "classification_report": {
            "直接检索": {"precision": 0.885, "recall": 0.938, "f1-score": 0.911, "support": 32.0},
            "查询扩展检索": {"precision": 0.933, "recall": 0.875, "f1-score": 0.903, "support": 32.0},
            "查询分解检索": {"precision": 0.947, "recall": 0.938, "f1-score": 0.942, "support": 32.0},
            "问题重写检索": {"precision": 0.963, "recall": 0.977, "f1-score": 0.970, "support": 32.0},
            "accuracy": 0.9320,
            "macro avg": {"precision": 0.9320, "recall": 0.9320, "f1-score": 0.9315, "support": 128.0},
            "weighted avg": {"precision": 0.9320, "recall": 0.9320, "f1-score": 0.9315, "support": 128.0},
        },
        "confusion_matrix": [
            [30, 2, 0, 0],
            [3, 28, 1, 0],
            [1, 1, 30, 0],
            [0, 0, 1, 31],
        ],
        "label_map": styled_plots.LABEL_MAP,
        "log_history": [
            {"loss": 1.182, "epoch": 0.15, "step": 20},
            {"loss": 0.604, "epoch": 0.31, "step": 40},
            {"loss": 0.251, "epoch": 0.47, "step": 60},
            {"loss": 0.082, "epoch": 0.63, "step": 80},
            {"loss": 0.031, "epoch": 0.79, "step": 100},
            {"loss": 0.012, "epoch": 0.94, "step": 120},
            {"eval_loss": 0.238, "eval_accuracy": 0.881, "eval_precision_macro": 0.878, "eval_recall_macro": 0.881, "eval_f1_macro": 0.879, "epoch": 1.0, "step": 128},
            {"loss": 0.026, "epoch": 1.09, "step": 140},
            {"loss": 0.010, "epoch": 1.25, "step": 160},
            {"loss": 0.007, "epoch": 1.41, "step": 180},
            {"loss": 0.006, "epoch": 1.56, "step": 200},
            {"loss": 0.004, "epoch": 1.72, "step": 220},
            {"loss": 0.003, "epoch": 1.88, "step": 240},
            {"eval_loss": 0.168, "eval_accuracy": 0.914, "eval_precision_macro": 0.913, "eval_recall_macro": 0.914, "eval_f1_macro": 0.912, "epoch": 2.0, "step": 256},
            {"loss": 0.003, "epoch": 2.03, "step": 260},
            {"loss": 0.002, "epoch": 2.19, "step": 280},
            {"loss": 0.002, "epoch": 2.34, "step": 300},
            {"loss": 0.0018, "epoch": 2.50, "step": 320},
            {"loss": 0.0016, "epoch": 2.66, "step": 340},
            {"loss": 0.0015, "epoch": 2.81, "step": 360},
            {"loss": 0.0014, "epoch": 2.97, "step": 380},
            {"eval_loss": 0.129, "eval_accuracy": 0.932, "eval_precision_macro": 0.9315, "eval_recall_macro": 0.9320, "eval_f1_macro": 0.9312, "epoch": 3.0, "step": 384},
            {"train_runtime": 1188.0, "train_loss": 0.118, "epoch": 3.0},
        ],
        "notes": [
            "This file is hypothetical and mirrors the structure of the real training summary.",
            "It exists only to generate presentation-style figures with the same chart types as training_results_v2.",
        ],
    }


def build_mock_split_rows() -> tuple[list[Dict[str, str]], list[Dict[str, str]], list[Dict[str, str]]]:
    def make_rows(split_name: str, per_class_count: int) -> list[Dict[str, str]]:
        rows: list[Dict[str, str]] = []
        for strategy in styled_plots.LABEL_MAP.keys():
            for index in range(per_class_count):
                rows.append({
                    "query": f"{split_name} illustrative sample {index + 1} for {strategy}",
                    "strategy": strategy,
                })
        return rows

    return make_rows("train", 256), make_rows("val", 32), make_rows("test", 32)


def _method_values(summary: Dict[str, Any], field: str) -> List[float]:
    return [summary["methods"][method][field] for method in METHOD_ORDER]


def plot_heatmap(summary: Dict[str, Any], output_path: Path) -> None:
    metric_names = ["准确率", "精确率", "召回率", "F1", "复杂查询成功率"]
    matrix = np.array([
        _method_values(summary, "accuracy"),
        _method_values(summary, "precision"),
        _method_values(summary, "recall"),
        _method_values(summary, "f1"),
        _method_values(summary, "complex_query_success"),
    ]).T

    fig, ax = plt.subplots(figsize=(14, 8), facecolor="white")
    heatmap = ax.imshow(matrix, cmap="YlOrRd", vmin=0.35, vmax=0.95)
    ax.set_xticks(np.arange(len(metric_names)))
    ax.set_xticklabels(metric_names, fontsize=14)
    ax.set_yticks(np.arange(len(METHOD_ORDER)))
    ax.set_yticklabels([ZH_METHOD_LABELS[method] for method in METHOD_ORDER], fontsize=14)
    ax.set_title("理想化策略消融热力图", fontsize=28, weight="bold", pad=16)

    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            ax.text(col_index, row_index, f"{matrix[row_index, col_index]:.3f}", ha="center", va="center", fontsize=17, weight="bold", color="#17202a")

    color_bar = fig.colorbar(heatmap, ax=ax, fraction=0.046, pad=0.04)
    color_bar.set_label("示意分数", fontsize=15)
    color_bar.ax.tick_params(labelsize=14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_radar(summary: Dict[str, Any], output_path: Path, theme: str = "dark") -> None:
    metric_names = ["准确率", "精确率", "召回率", "F1", "复杂查询成功率"]
    angles = np.linspace(0, 2 * np.pi, len(metric_names), endpoint=False)
    closed_angles = np.concatenate([angles, [angles[0]]])

    is_light = theme == "light"
    figure_bg = "#f7f4ea" if is_light else "white"
    panel_bg = "#fbfaf7" if is_light else "#050505"
    title_color = "#243447" if is_light else "white"
    tick_color = "#3d4f63" if is_light else "white"
    grid_color = "#b7c4d3" if is_light else "white"
    label_box_face = "#f2efe6" if is_light else "#111111"
    label_box_edge = "#d1d9e6" if is_light else "none"

    fig = plt.figure(figsize=(12, 12), facecolor=figure_bg)
    ax = plt.subplot(111, polar=True)
    ax.set_facecolor(panel_bg)
    ax.set_title("三种方法标准指标对比雷达图", fontsize=22, weight="bold", pad=28, color=title_color)
    ax.set_xticks(angles)
    ax.set_xticklabels([])
    ax.set_yticks([0.4, 0.55, 0.7, 0.85, 1.0])
    ax.set_yticklabels(["0.40", "0.55", "0.70", "0.85", "1.00"], fontsize=12, color=tick_color)
    ax.set_ylim(0.35, 1.0)
    ax.grid(alpha=0.45 if is_light else 0.35, color=grid_color)
    ax.spines["polar"].set_color("#8da0b3" if is_light else grid_color)

    for angle, label in zip(angles, metric_names):
        ax.text(
            angle,
            1.05,
            label,
            color=title_color,
            fontsize=13,
            fontweight="bold",
            ha="center",
            va="center",
            bbox={"facecolor": label_box_face, "edgecolor": label_box_edge, "alpha": 0.98 if is_light else 0.85, "pad": 3},
            clip_on=False,
        )

    metric_keys = ["accuracy", "precision", "recall", "f1", "complex_query_success"]
    comparison_colors = {
        "M0": "#355070" if is_light else "#577590",
        "M1": "#d66f00" if is_light else "#277da1",
        "M3": "#2b9348" if is_light else "#90be6d",
    }
    for method in COMPARISON_METHOD_ORDER:
        color = comparison_colors[method]
        values = np.array([summary["methods"][method][metric] for metric in metric_keys], dtype=float)
        closed_values = np.concatenate([values, [values[0]]])
        ax.plot(closed_angles, closed_values, color=color, linewidth=3, label=ZH_METHOD_LABELS[method])
        ax.fill(closed_angles, closed_values, color=color, alpha=0.10)

    legend = ax.legend(loc="upper right", bbox_to_anchor=(1.26, 1.10), fontsize=13, frameon=True)
    legend.get_frame().set_facecolor("#fffdf8" if is_light else "#111111")
    legend.get_frame().set_edgecolor("#cbd5e1" if is_light else "#444444")
    for text in legend.get_texts():
        text.set_color("#243447" if is_light else "white")
    fig.subplots_adjust(left=0.06, right=0.84, top=0.88, bottom=0.06)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_dual_axis(summary: Dict[str, Any], output_path: Path) -> None:
    labels = [ZH_METHOD_LABELS[method] for method in METHOD_ORDER]
    accuracy = _method_values(summary, "accuracy")
    f1_scores = _method_values(summary, "f1")
    error_rate = _method_values(summary, "error_rate")
    x = np.arange(len(labels))
    width = 0.34

    fig, ax1 = plt.subplots(figsize=(15, 8), facecolor="white")
    ax1.bar(x - width / 2, accuracy, width, color="#277da1", label="准确率")
    ax1.bar(x + width / 2, f1_scores, width, color="#f3722c", label="F1")
    ax1.set_ylim(0.35, 1.02)
    ax1.set_ylabel("分数", fontsize=18)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=14)
    ax1.tick_params(axis="y", labelsize=14)
    ax1.set_title("策略收益与误路由率对比", fontsize=28, weight="bold", pad=14)
    ax1.grid(axis="y", linestyle="--", alpha=0.25)

    for xpos, value in zip(x - width / 2, accuracy):
        ax1.text(xpos, value + 0.006, f"{value:.3f}", ha="center", fontsize=13, weight="bold")
    for xpos, value in zip(x + width / 2, f1_scores):
        ax1.text(xpos, value + 0.006, f"{value:.3f}", ha="center", fontsize=13, weight="bold")

    ax2 = ax1.twinx()
    ax2.plot(x, error_rate, color="#2b9348", linewidth=3, marker="o", markersize=11, label="误路由率")
    ax2.set_ylim(0.0, 0.45)
    ax2.set_ylabel("误路由率", fontsize=18)
    ax2.tick_params(axis="y", labelsize=14)
    for xpos, value in zip(x, error_rate):
        ax2.text(xpos, value + 0.006, f"{value:.3f}", ha="center", fontsize=13, weight="bold", color="#2b9348")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left", fontsize=14, frameon=True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_bundle(summary: Dict[str, Any]) -> Dict[str, str]:
    ensure_dirs()
    heatmap_path = PLOTS_DIR / "hypothetical_strategy_selector_heatmap.png"
    radar_path = PLOTS_DIR / "hypothetical_strategy_selector_radar.png"
    dual_axis_path = PLOTS_DIR / "hypothetical_strategy_selector_dual_axis.png"
    plot_heatmap(summary, heatmap_path)
    plot_radar(summary, radar_path, theme="dark")
    plot_dual_axis(summary, dual_axis_path)
    return {
        "heatmap": str(heatmap_path),
        "radar": str(radar_path),
        "dual_axis": str(dual_axis_path),
    }


def plot_no_strategy_vs_adaptive(summary: Dict[str, Any], output_path: Path, theme: str = "dark") -> None:
    metric_names = ["准确率", "精确率", "召回率", "F1", "复杂查询成功率"]
    metric_keys = ["accuracy", "precision", "recall", "f1", "complex_query_success"]
    no_strategy = [summary["methods"]["M0"][key] for key in metric_keys]
    rule_only = [summary["methods"]["M1"][key] for key in metric_keys]
    hybrid_selector = [summary["methods"]["M3"][key] for key in metric_keys]
    rule_gain = [rule - baseline for rule, baseline in zip(rule_only, no_strategy)]
    hybrid_gain = [hybrid - baseline for hybrid, baseline in zip(hybrid_selector, no_strategy)]
    x = np.arange(len(metric_names))
    width = 0.22

    is_light = theme == "light"
    figure_bg = "#f7f4ea" if is_light else "white"
    panel_bg = "#fbfaf7" if is_light else "#050505"
    title_color = "#243447" if is_light else "white"
    tick_color = "#3d4f63" if is_light else "white"
    grid_color = "#b7c4d3" if is_light else "white"
    label_box_face = "#f2efe6" if is_light else "#111111"
    label_box_edge = "#d1d9e6" if is_light else "none"
    color_no_strategy = "#355070" if is_light else "#7d8597"
    color_rule_only = "#d66f00" if is_light else "#277da1"
    color_hybrid = "#2b9348" if is_light else "#90be6d"

    fig, ax = plt.subplots(figsize=(15, 8), facecolor=figure_bg)
    ax.set_facecolor(panel_bg)
    bars1 = ax.bar(x - width, no_strategy, width, color=color_no_strategy, label="无策略")
    bars2 = ax.bar(x, rule_only, width, color=color_rule_only, label="仅规则")
    bars3 = ax.bar(x + width, hybrid_selector, width, color=color_hybrid, label="混合检索器")
    ax.set_ylim(0.0, 1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([])
    ax.set_ylabel("分数", fontsize=16, color=title_color)
    ax.set_title("无策略 / 仅规则 / 混合检索器 标准指标对比", fontsize=24, weight="bold", pad=14, color=title_color)
    ax.grid(axis="y", linestyle="--", alpha=0.35 if is_light else 0.22, color=grid_color)
    ax.tick_params(axis="y", colors=tick_color, labelsize=13)
    ax.tick_params(axis="x", colors=tick_color, labelsize=13, pad=10, length=0)
    for spine in ax.spines.values():
        spine.set_color("#cbd5e1" if is_light else "#444444")

    for bar in list(bars1) + list(bars2) + list(bars3):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height + 0.02, f"{height:.2f}", ha="center", va="bottom", fontsize=12, weight="bold", color=title_color)

    for idx, (delta_rule, delta_hybrid) in enumerate(zip(rule_gain, hybrid_gain)):
        top = max(no_strategy[idx], rule_only[idx], hybrid_selector[idx])
        ax.text(idx, top + 0.06, f"规则 +{delta_rule:.2f}", ha="center", va="bottom", fontsize=11, weight="bold", color=color_rule_only)
        ax.text(idx, top + 0.12, f"混合 +{delta_hybrid:.2f}", ha="center", va="bottom", fontsize=12, weight="bold", color="#d62828")

    for idx, label in enumerate(metric_names):
        ax.text(
            idx,
            0.03,
            label,
            ha="center",
            va="bottom",
            fontsize=13,
            color=title_color,
            fontweight="bold",
            bbox={"facecolor": label_box_face, "edgecolor": label_box_edge, "alpha": 0.98 if is_light else 0.85, "pad": 3},
        )

    legend = ax.legend(frameon=True, fontsize=14)
    legend.get_frame().set_facecolor("#fffdf8" if is_light else "#111111")
    legend.get_frame().set_edgecolor("#cbd5e1" if is_light else "#444444")
    for text in legend.get_texts():
        text.set_color("#243447" if is_light else "white")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.90, bottom=0.08)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_simple_vs_complex(summary: Dict[str, Any], output_path: Path) -> None:
    groups = summary["query_group_ablation"]
    metric_names = ["答案F1", "证据命中率", "幻觉抑制", "复杂问题成功率"]
    metric_keys = ["answer_f1", "evidence_hit", "hallucination_control", "complex_query_success"]

    fig, axes = plt.subplots(1, 2, figsize=(18, 8), facecolor="white", sharey=True)
    titles = [("simple", "简单问题"), ("complex", "复杂问题")]

    for axis, (group_key, group_title) in zip(axes, titles):
        baseline = [groups[group_key]["No Strategy"][key] for key in metric_keys]
        adaptive = [groups[group_key]["Adaptive Strategy"][key] for key in metric_keys]
        improvement = [after - before for after, before in zip(adaptive, baseline)]
        x = np.arange(len(metric_names))
        width = 0.34

        axis.bar(x - width / 2, baseline, width, color="#8d99ae", label="无策略")
        axis.bar(x + width / 2, adaptive, width, color="#2a9d8f", label="自适应策略")
        axis.set_title(group_title, fontsize=22, weight="bold")
        axis.set_xticks(x)
        axis.set_xticklabels(metric_names, fontsize=12)
        axis.set_ylim(0.0, 1.0)
        axis.grid(axis="y", linestyle="--", alpha=0.22)

        for idx, delta in enumerate(improvement):
            top = max(baseline[idx], adaptive[idx])
            axis.text(idx, top + 0.06, f"+{delta:.2f}", ha="center", va="bottom", fontsize=13, weight="bold", color="#d62828")

    axes[0].set_ylabel("分数", fontsize=16)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=True, fontsize=13)
    fig.suptitle("简单问题 vs 复杂问题：策略收益对比", fontsize=28, weight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_training_style_bundle(training_summary: Dict[str, Any]) -> Dict[str, str]:
    ensure_dirs()
    previous_plots_dir = styled_plots.PLOTS_DIR
    try:
        styled_plots.PLOTS_DIR = PLOTS_DIR
        train_rows, val_rows, test_rows = build_mock_split_rows()
        labels = list(styled_plots.LABEL_MAP.keys())
        styled_plots.save_dataset_distribution_plot(train_rows, val_rows, test_rows)
        styled_plots.save_training_curve_plot(training_summary["log_history"])
        styled_plots.save_confusion_matrix_plot(np.array(training_summary["confusion_matrix"]), labels)
        styled_plots.save_metrics_bar_plot(training_summary["classification_report"])
        styled_plots.save_radar_plot(training_summary["classification_report"])
        styled_plots.save_scoreboard_plot(training_summary["summary_metrics"])
        styled_plots.save_dashboard(
            training_summary["summary_metrics"],
            training_summary["classification_report"],
            np.array(training_summary["confusion_matrix"]),
            train_rows,
            val_rows,
            test_rows,
        )
    finally:
        styled_plots.PLOTS_DIR = previous_plots_dir

    return {
        "dataset_overview": str(PLOTS_DIR / "dataset_overview.png"),
        "training_dynamics": str(PLOTS_DIR / "training_dynamics.png"),
        "confusion_matrix_neon": str(PLOTS_DIR / "confusion_matrix_neon.png"),
        "per_class_metrics": str(PLOTS_DIR / "per_class_metrics.png"),
        "radar_metrics": str(PLOTS_DIR / "radar_metrics.png"),
        "overall_scoreboard": str(PLOTS_DIR / "overall_scoreboard.png"),
        "training_dashboard": str(PLOTS_DIR / "training_dashboard.png"),
    }


def main() -> None:
    configure_chinese_font()
    summary = build_illustrative_summary()
    training_summary = build_illustrative_training_summary()
    summary["plot_paths"] = render_bundle(summary)
    no_strategy_plot = PLOTS_DIR / "no_strategy_vs_adaptive.png"
    plot_no_strategy_vs_adaptive(summary, no_strategy_plot, theme="dark")
    summary["plot_paths"]["no_strategy_vs_adaptive"] = str(no_strategy_plot)
    radar_light_plot = PLOTS_DIR / "hypothetical_strategy_selector_radar_light.png"
    plot_radar(summary, radar_light_plot, theme="light")
    summary["plot_paths"]["hypothetical_strategy_selector_radar_light"] = str(radar_light_plot)
    no_strategy_light_plot = PLOTS_DIR / "no_strategy_vs_adaptive_light.png"
    plot_no_strategy_vs_adaptive(summary, no_strategy_light_plot, theme="light")
    summary["plot_paths"]["no_strategy_vs_adaptive_light"] = str(no_strategy_light_plot)
    simple_vs_complex_plot = PLOTS_DIR / "simple_vs_complex_ablation.png"
    plot_simple_vs_complex(summary, simple_vs_complex_plot)
    summary["plot_paths"]["simple_vs_complex_ablation"] = str(simple_vs_complex_plot)
    summary["training_style_plot_paths"] = render_training_style_bundle(training_summary)
    save_json(RESULTS_DIR / "hypothetical_strategy_selector_summary.json", summary)
    save_json(RESULTS_DIR / "hypothetical_strategy_selector_training_summary.json", training_summary)
    print(RESULTS_DIR / "hypothetical_strategy_selector_summary.json")


if __name__ == "__main__":
    main()