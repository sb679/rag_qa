import json
import math
import os
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support
from torch.utils.data import Dataset
from transformers import BertForSequenceClassification, BertTokenizer, Trainer, TrainingArguments

from demo_experiment_paths import STRATEGY_SELECTOR_EXPERIMENT_DIR


warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parent
EXPERIMENT_DIR = STRATEGY_SELECTOR_EXPERIMENT_DIR / "artifacts"
DATASET_DIR = EXPERIMENT_DIR / "datasets"
RESULTS_DIR = EXPERIMENT_DIR / "training_results_v2"
PLOTS_DIR = RESULTS_DIR / "plots"
REPORTS_DIR = RESULTS_DIR / "reports"
MODEL_DIR = STRATEGY_SELECTOR_EXPERIMENT_DIR / "model_snapshot"
BASE_MODEL_DIR = ROOT / "models" / "bert-base-chinese"

TRAIN_FILE = DATASET_DIR / "strategy_classifier_train_v2.jsonl"
VAL_FILE = DATASET_DIR / "strategy_classifier_val_v2.jsonl"
TEST_FILE = DATASET_DIR / "strategy_classifier_test_v2.jsonl"

LABEL_MAP = {
    "直接检索": 0,
    "查询扩展检索": 1,
    "查询分解检索": 2,
    "问题重写检索": 3,
}
ID_TO_LABEL = {value: key for key, value in LABEL_MAP.items()}
PLOT_LABELS = {
    "直接检索": "Direct",
    "查询扩展检索": "Expansion",
    "查询分解检索": "Decomposition",
    "问题重写检索": "Rewrite",
}
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_LENGTH = 128
NUM_EPOCHS = 3
BATCH_SIZE = 8 if DEVICE == "cpu" else 16
LEARNING_RATE = 2e-5
SEED = 42


plt.style.use("dark_background")
COLOR_BG = "#0b1020"
COLOR_PANEL = "#121a30"
COLOR_GRID = "#31456a"
COLOR_TEXT = "#eaf2ff"
COLOR_ACCENT = "#52d1ff"
COLOR_ACCENT_2 = "#ff6ec7"
COLOR_ACCENT_3 = "#ffd166"
COLOR_ACCENT_4 = "#64f4ac"
CLASS_COLORS = ["#52d1ff", "#ff6ec7", "#ffd166", "#64f4ac"]


class StrategyDataset(Dataset):
    def __init__(self, texts: List[str], labels: List[int], tokenizer: BertTokenizer):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=MAX_LENGTH,
        )
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(value[idx]) for key, value in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)


def read_jsonl(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as file_handle:
        return [json.loads(line) for line in file_handle if line.strip()]


def prepare_split(path: Path):
    rows = read_jsonl(path)
    texts = [row["query"] for row in rows]
    labels = [LABEL_MAP[row["strategy"]] for row in rows]
    return rows, texts, labels


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average="macro", zero_division=0)
    accuracy = accuracy_score(labels, predictions)
    return {
        "accuracy": accuracy,
        "precision_macro": precision,
        "recall_macro": recall,
        "f1_macro": f1,
    }


def _style_axes(axis, title: str):
    axis.set_facecolor(COLOR_PANEL)
    for spine in axis.spines.values():
        spine.set_color(COLOR_GRID)
    axis.tick_params(colors=COLOR_TEXT)
    axis.title.set_color(COLOR_TEXT)
    axis.set_title(title, fontsize=14, color=COLOR_TEXT, pad=14, weight="bold")
    axis.grid(color=COLOR_GRID, alpha=0.25, linestyle="--", linewidth=0.8)


def save_dataset_distribution_plot(train_rows, val_rows, test_rows):
    counts = pd.DataFrame([
        Counter(row["strategy"] for row in train_rows),
        Counter(row["strategy"] for row in val_rows),
        Counter(row["strategy"] for row in test_rows),
    ], index=["Train", "Val", "Test"]).fillna(0)

    fig, axes = plt.subplots(1, 2, figsize=(16, 7), facecolor=COLOR_BG)
    for axis in axes:
        axis.set_facecolor(COLOR_PANEL)

    total_counts = counts.sum(axis=0)
    display_labels = [PLOT_LABELS[label] for label in total_counts.index]
    wedges, _ = axes[0].pie(
        total_counts.values,
        colors=CLASS_COLORS,
        startangle=110,
        wedgeprops={"width": 0.42, "edgecolor": COLOR_BG, "linewidth": 2},
    )
    axes[0].text(0, 0, f"{int(total_counts.sum())}\nSamples", ha="center", va="center", color=COLOR_TEXT, fontsize=18, weight="bold")
    axes[0].legend(wedges, display_labels, loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, labelcolor=COLOR_TEXT)
    axes[0].set_title("Dataset Class Balance", color=COLOR_TEXT, fontsize=15, weight="bold")

    bottoms = np.zeros(len(counts.index))
    for idx, label in enumerate(total_counts.index):
        values = counts[label].values
        axes[1].bar(counts.index, values, bottom=bottoms, color=CLASS_COLORS[idx], label=PLOT_LABELS[label], width=0.58, edgecolor=COLOR_BG)
        bottoms += values
    _style_axes(axes[1], "Train / Val / Test Distribution")
    axes[1].legend(frameon=False, labelcolor=COLOR_TEXT)
    axes[1].set_ylabel("Samples", color=COLOR_TEXT)

    fig.suptitle("Strategy Classifier Dataset Overview", fontsize=20, color=COLOR_TEXT, weight="bold")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "dataset_overview.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_training_curve_plot(log_history: List[Dict]):
    train_steps, train_loss = [], []
    eval_steps, eval_loss, eval_f1 = [], [], []
    for item in log_history:
        if "loss" in item and "eval_loss" not in item:
            train_steps.append(item.get("step", len(train_steps)))
            train_loss.append(item["loss"])
        if "eval_loss" in item:
            eval_steps.append(item.get("step", len(eval_steps)))
            eval_loss.append(item["eval_loss"])
            eval_f1.append(item.get("eval_f1_macro"))

    fig, ax1 = plt.subplots(figsize=(12, 7), facecolor=COLOR_BG)
    _style_axes(ax1, "Training Dynamics")
    ax1.plot(train_steps, train_loss, color=COLOR_ACCENT, linewidth=2.8, label="Train Loss")
    ax1.plot(eval_steps, eval_loss, color=COLOR_ACCENT_2, linewidth=2.8, marker="o", label="Validation Loss")
    ax1.fill_between(train_steps, train_loss, color=COLOR_ACCENT, alpha=0.12)
    ax1.fill_between(eval_steps, eval_loss, color=COLOR_ACCENT_2, alpha=0.14)
    ax1.set_xlabel("Step", color=COLOR_TEXT)
    ax1.set_ylabel("Loss", color=COLOR_TEXT)

    ax2 = ax1.twinx()
    ax2.plot(eval_steps, eval_f1, color=COLOR_ACCENT_4, linewidth=3.0, marker="D", label="Validation Macro-F1")
    ax2.set_ylabel("Macro-F1", color=COLOR_TEXT)
    ax2.tick_params(colors=COLOR_TEXT)

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, frameon=False, labelcolor=COLOR_TEXT, loc="upper right")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "training_dynamics.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_confusion_matrix_plot(matrix: np.ndarray, labels: List[str]):
    display_labels = [PLOT_LABELS[label] for label in labels]
    fig, ax = plt.subplots(figsize=(9, 7), facecolor=COLOR_BG)
    _style_axes(ax, "Neon Confusion Matrix")
    im = ax.imshow(matrix, cmap="magma")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(display_labels, rotation=20, ha="right", color=COLOR_TEXT)
    ax.set_yticklabels(display_labels, color=COLOR_TEXT)

    max_value = matrix.max() if matrix.size else 1
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            color = "white" if value >= max_value * 0.45 else COLOR_TEXT
            ax.text(j, i, str(value), ha="center", va="center", color=color, fontsize=12, weight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.yaxis.set_tick_params(color=COLOR_TEXT)
    plt.setp(cbar.ax.get_yticklabels(), color=COLOR_TEXT)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "confusion_matrix_neon.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_metrics_bar_plot(per_class_report: Dict[str, Dict[str, float]]):
    labels = list(LABEL_MAP.keys())
    display_labels = [PLOT_LABELS[label] for label in labels]
    precision = [per_class_report[label]["precision"] for label in labels]
    recall = [per_class_report[label]["recall"] for label in labels]
    f1 = [per_class_report[label]["f1-score"] for label in labels]
    x = np.arange(len(labels))
    width = 0.24

    fig, ax = plt.subplots(figsize=(13, 7), facecolor=COLOR_BG)
    _style_axes(ax, "Per-Class Metric Comparison")
    ax.bar(x - width, precision, width=width, color=COLOR_ACCENT, label="Precision")
    ax.bar(x, recall, width=width, color=COLOR_ACCENT_2, label="Recall")
    ax.bar(x + width, f1, width=width, color=COLOR_ACCENT_4, label="F1-score")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(x)
    ax.set_xticklabels(display_labels, rotation=15, color=COLOR_TEXT)
    ax.legend(frameon=False, labelcolor=COLOR_TEXT)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "per_class_metrics.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_radar_plot(per_class_report: Dict[str, Dict[str, float]]):
    labels = list(LABEL_MAP.keys())
    display_labels = [PLOT_LABELS[label] for label in labels]
    metrics = {
        "Precision": [per_class_report[label]["precision"] for label in labels],
        "Recall": [per_class_report[label]["recall"] for label in labels],
        "F1-score": [per_class_report[label]["f1-score"] for label in labels],
    }
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
    closed_angles = np.concatenate([angles, [angles[0]]])

    fig = plt.figure(figsize=(10, 10), facecolor=COLOR_BG)
    ax = plt.subplot(111, polar=True)
    ax.set_facecolor(COLOR_PANEL)
    ax.grid(color=COLOR_GRID, alpha=0.25, linestyle="--")
    ax.spines['polar'].set_color(COLOR_GRID)
    ax.set_xticks(angles)
    ax.set_xticklabels(display_labels, color=COLOR_TEXT, fontsize=12)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], color=COLOR_TEXT)
    ax.set_ylim(0, 1.05)
    ax.set_title("Strategy Classifier Radar", color=COLOR_TEXT, fontsize=18, weight="bold", pad=24)

    colors = [COLOR_ACCENT, COLOR_ACCENT_2, COLOR_ACCENT_4]
    for (name, values), color in zip(metrics.items(), colors):
        data = np.array(values, dtype=float)
        closed_data = np.concatenate([data, [data[0]]])
        ax.plot(closed_angles, closed_data, color=color, linewidth=2.8, label=name)
        ax.fill(closed_angles, closed_data, color=color, alpha=0.12)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.08), frameon=False, labelcolor=COLOR_TEXT)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "radar_metrics.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_scoreboard_plot(summary_metrics: Dict[str, float]):
    labels = ["Accuracy", "Macro-F1", "Macro-Precision", "Macro-Recall"]
    values = [summary_metrics["accuracy"], summary_metrics["f1_macro"], summary_metrics["precision_macro"], summary_metrics["recall_macro"]]
    theta = np.linspace(0.0, 2 * np.pi, len(labels), endpoint=False)
    radii = np.array(values)
    width = np.pi / 4.5 * np.ones(len(labels))

    fig = plt.figure(figsize=(9, 8), facecolor=COLOR_BG)
    ax = plt.subplot(111, polar=True)
    ax.set_facecolor(COLOR_PANEL)
    bars = ax.bar(theta, radii, width=width, bottom=0.0, color=[COLOR_ACCENT, COLOR_ACCENT_2, COLOR_ACCENT_3, COLOR_ACCENT_4], alpha=0.9)
    for bar in bars:
        bar.set_edgecolor(COLOR_BG)
        bar.set_linewidth(2)
    ax.set_xticks(theta)
    ax.set_xticklabels(labels, color=COLOR_TEXT, fontsize=12)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], color=COLOR_TEXT)
    ax.set_title("Overall Scoreboard", color=COLOR_TEXT, fontsize=18, weight="bold", pad=22)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "overall_scoreboard.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def save_dashboard(summary_metrics: Dict[str, float], per_class_report: Dict[str, Dict[str, float]], matrix: np.ndarray, train_rows, val_rows, test_rows):
    labels = list(LABEL_MAP.keys())
    display_labels = [PLOT_LABELS[label] for label in labels]
    fig = plt.figure(figsize=(18, 12), facecolor=COLOR_BG)
    gs = fig.add_gridspec(2, 2, hspace=0.28, wspace=0.2)

    ax1 = fig.add_subplot(gs[0, 0])
    _style_axes(ax1, "Overall Metrics")
    metric_names = ["Accuracy", "Macro-F1", "Macro-Precision", "Macro-Recall"]
    metric_values = [summary_metrics["accuracy"], summary_metrics["f1_macro"], summary_metrics["precision_macro"], summary_metrics["recall_macro"]]
    ax1.barh(metric_names, metric_values, color=[COLOR_ACCENT, COLOR_ACCENT_2, COLOR_ACCENT_3, COLOR_ACCENT_4])
    ax1.set_xlim(0, 1.05)
    for idx, value in enumerate(metric_values):
        ax1.text(value + 0.015, idx, f"{value:.3f}", color=COLOR_TEXT, va="center", fontsize=11, weight="bold")

    ax2 = fig.add_subplot(gs[0, 1])
    _style_axes(ax2, "Dataset Class Balance")
    counts = Counter(row["strategy"] for row in train_rows + val_rows + test_rows)
    positions = np.arange(len(display_labels))
    ax2.bar(positions, [counts[label] for label in labels], color=CLASS_COLORS)
    ax2.set_xticks(positions)
    ax2.set_xticklabels(display_labels, rotation=15)
    for idx, label in enumerate(labels):
        ax2.text(idx, counts[label] + 8, str(counts[label]), ha="center", color=COLOR_TEXT, fontsize=10)

    ax3 = fig.add_subplot(gs[1, 0])
    _style_axes(ax3, "Per-Class F1")
    f1_values = [per_class_report[label]["f1-score"] for label in labels]
    ax3.plot(display_labels, f1_values, color=COLOR_ACCENT_4, marker="o", linewidth=3)
    ax3.fill_between(display_labels, f1_values, color=COLOR_ACCENT_4, alpha=0.18)
    ax3.set_ylim(0, 1.05)

    ax4 = fig.add_subplot(gs[1, 1])
    _style_axes(ax4, "Confusion Matrix Snapshot")
    ax4.imshow(matrix, cmap="magma")
    ax4.set_xticks(range(len(labels)))
    ax4.set_yticks(range(len(labels)))
    ax4.set_xticklabels(display_labels, rotation=20, ha="right")
    ax4.set_yticklabels(display_labels)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax4.text(j, i, str(matrix[i, j]), ha="center", va="center", color=COLOR_TEXT, fontsize=10, weight="bold")

    fig.suptitle("Strategy Classifier Training Dashboard", fontsize=24, color=COLOR_TEXT, weight="bold")
    fig.savefig(PLOTS_DIR / "training_dashboard.png", dpi=220, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close(fig)


def build_markdown_report(summary_metrics: Dict[str, float], per_class_report: Dict[str, Dict[str, float]], split_sizes: Dict[str, int], rows_total: int):
    report = [
        "# 四分类检索策略分类器训练报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 训练配置",
        "",
        f"- 基础模型：{BASE_MODEL_DIR.name}",
        f"- 最大序列长度：{MAX_LENGTH}",
        f"- 训练轮次：{NUM_EPOCHS}",
        f"- Batch Size：{BATCH_SIZE}",
        f"- 学习率：{LEARNING_RATE}",
        f"- 训练设备：{DEVICE}",
        f"- 总样本数：{rows_total}",
        f"- 训练/验证/测试：{split_sizes['train']} / {split_sizes['val']} / {split_sizes['test']}",
        "",
        "## 整体效果",
        "",
        f"- Accuracy：{summary_metrics['accuracy']:.4f}",
        f"- Macro Precision：{summary_metrics['precision_macro']:.4f}",
        f"- Macro Recall：{summary_metrics['recall_macro']:.4f}",
        f"- Macro F1：{summary_metrics['f1_macro']:.4f}",
        "",
        "## 分类别指标",
        "",
        "| 类别 | Precision | Recall | F1-score | Support |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label in LABEL_MAP.keys():
        metrics = per_class_report[label]
        report.append(f"| {label} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1-score']:.4f} | {metrics['support']} |")

    report.extend([
        "",
        "## 可视化图表",
        "",
        f"- [dataset_overview.png]({(PLOTS_DIR / 'dataset_overview.png').as_posix()})",
        f"- [training_dynamics.png]({(PLOTS_DIR / 'training_dynamics.png').as_posix()})",
        f"- [confusion_matrix_neon.png]({(PLOTS_DIR / 'confusion_matrix_neon.png').as_posix()})",
        f"- [per_class_metrics.png]({(PLOTS_DIR / 'per_class_metrics.png').as_posix()})",
        f"- [radar_metrics.png]({(PLOTS_DIR / 'radar_metrics.png').as_posix()})",
        f"- [overall_scoreboard.png]({(PLOTS_DIR / 'overall_scoreboard.png').as_posix()})",
        f"- [training_dashboard.png]({(PLOTS_DIR / 'training_dashboard.png').as_posix()})",
        "",
        "## 结论",
        "",
        "当前训练得到的是一个独立于线上旧模型的 `bert_strategy_classifier_v2`。该模型基于重建后的四分类平衡数据集训练，适合作为论文实验模型和后续线上替换候选模型。",
    ])
    return "\n".join(report) + "\n"


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    tokenizer = BertTokenizer.from_pretrained(str(BASE_MODEL_DIR))

    train_rows, train_texts, train_labels = prepare_split(TRAIN_FILE)
    val_rows, val_texts, val_labels = prepare_split(VAL_FILE)
    test_rows, test_texts, test_labels = prepare_split(TEST_FILE)

    train_dataset = StrategyDataset(train_texts, train_labels, tokenizer)
    val_dataset = StrategyDataset(val_texts, val_labels, tokenizer)
    test_dataset = StrategyDataset(test_texts, test_labels, tokenizer)

    model = BertForSequenceClassification.from_pretrained(str(BASE_MODEL_DIR), num_labels=len(LABEL_MAP))
    model.to(DEVICE)

    training_args = TrainingArguments(
        output_dir=str(RESULTS_DIR / "checkpoints"),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE * 2,
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        warmup_steps=20,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="steps",
        logging_steps=20,
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        seed=SEED,
        fp16=(DEVICE == "cuda"),
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    predictions = trainer.predict(test_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=-1)

    report_dict = classification_report(
        test_labels,
        pred_labels,
        target_names=list(LABEL_MAP.keys()),
        digits=4,
        output_dict=True,
        zero_division=0,
    )
    confusion = confusion_matrix(test_labels, pred_labels)
    summary_metrics = {
        "accuracy": accuracy_score(test_labels, pred_labels),
        "precision_macro": report_dict["macro avg"]["precision"],
        "recall_macro": report_dict["macro avg"]["recall"],
        "f1_macro": report_dict["macro avg"]["f1-score"],
    }

    trainer.model.save_pretrained(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))
    (MODEL_DIR / "label_map.json").write_text(json.dumps(LABEL_MAP, ensure_ascii=False, indent=2), encoding="utf-8")

    log_history = trainer.state.log_history
    save_dataset_distribution_plot(train_rows, val_rows, test_rows)
    save_training_curve_plot(log_history)
    save_confusion_matrix_plot(confusion, list(LABEL_MAP.keys()))
    save_metrics_bar_plot(report_dict)
    save_radar_plot(report_dict)
    save_scoreboard_plot(summary_metrics)
    save_dashboard(summary_metrics, report_dict, confusion, train_rows, val_rows, test_rows)

    results_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "device": DEVICE,
        "train_size": len(train_rows),
        "val_size": len(val_rows),
        "test_size": len(test_rows),
        "summary_metrics": summary_metrics,
        "classification_report": report_dict,
        "confusion_matrix": confusion.tolist(),
        "label_map": LABEL_MAP,
        "log_history": log_history,
    }
    (RESULTS_DIR / "strategy_classifier_training_summary.json").write_text(
        json.dumps(results_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_markdown = build_markdown_report(
        summary_metrics,
        report_dict,
        {"train": len(train_rows), "val": len(val_rows), "test": len(test_rows)},
        len(train_rows) + len(val_rows) + len(test_rows),
    )
    (REPORTS_DIR / "strategy_classifier_training_report.md").write_text(report_markdown, encoding="utf-8")

    print(json.dumps({
        "model_dir": str(MODEL_DIR),
        "results_dir": str(RESULTS_DIR),
        "summary_metrics": summary_metrics,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()