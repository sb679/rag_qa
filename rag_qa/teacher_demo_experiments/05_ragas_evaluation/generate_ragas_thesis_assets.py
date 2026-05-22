from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT_DIR = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT_DIR / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "official_ragas_eval"
VISUALS_DIR = ARTIFACTS_DIR / "thesis_manual_visuals"


def configure_fonts() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def find_latest_result() -> Path:
    candidates = sorted(ARTIFACTS_DIR.glob("ragas_vs_legacy_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No ragas_vs_legacy JSON files found in {ARTIFACTS_DIR}")
    return candidates[-1]


def load_payload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_overall_metrics(payload: Dict[str, Any]) -> List[Tuple[str, float]]:
    metrics = payload["official_ragas_metrics"]
    return [
        ("Faithfulness", float(metrics["faithfulness"])),
        ("Answer Relevancy", float(metrics["response_relevancy"])),
        ("Context Precision", float(metrics["context_precision"])),
        ("Context Recall", float(metrics["context_recall"])),
    ]


def build_question_type_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    breakdown = payload.get("question_type_breakdown", [])
    return sorted(breakdown, key=lambda item: float(item.get("official_faithfulness", 0.0)), reverse=True)


def save_radar_chart(metric_rows: Iterable[Tuple[str, float]], output_path: Path) -> None:
    rows = list(metric_rows)
    labels = [label for label, _ in rows]
    values = [value for _, value in rows]
    values.append(values[0])

    total = len(labels)
    angles = [index / float(total) * 2 * 3.141592653589793 for index in range(total)]
    angles.append(angles[0])

    fig = plt.figure(figsize=(8.6, 7.2), facecolor="#fffdf7")
    ax = plt.subplot(111, polar=True)
    ax.set_facecolor("#fffaf0")
    ax.set_theta_offset(3.141592653589793 / 2)
    ax.set_theta_direction(-1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=12, color="#334155")
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=10, color="#64748b")
    ax.grid(color="#d6d3d1", linestyle=(0, (3, 4)), linewidth=0.9)
    ax.spines["polar"].set_color("#cbd5e1")

    ax.plot(angles, values, color="#c2410c", linewidth=2.8)
    ax.fill(angles, values, color="#fb923c", alpha=0.28)
    ax.scatter(angles[:-1], values[:-1], s=68, color="#9a3412", zorder=3)

    for index, (angle, value) in enumerate(zip(angles[:-1], values[:-1])):
        radial_offset = 0.07 if index != 1 else 0.045
        ax.text(angle, min(0.96, value + radial_offset), f"{value:.4f}", ha="center", va="center", fontsize=10.5, color="#7c2d12")

    fig.suptitle("RAGAS 四项核心指标雷达图", fontsize=17, fontweight="bold", color="#1f2937", y=0.98)
    fig.text(0.5, 0.93, "基于 80 条采矿冶金测试问题的官方评测结果", ha="center", fontsize=11, color="#6b7280")
    fig.tight_layout(rect=[0, 0.02, 1, 0.93])
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def save_question_type_chart(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    data = list(rows)
    labels = [str(row["question_type"]) for row in data]
    faithfulness = [float(row["official_faithfulness"]) for row in data]
    relevancy = [float(row["official_response_relevancy"]) for row in data]
    precision = [float(row["official_context_precision"]) for row in data]
    recall = [float(row["official_context_recall"]) for row in data]

    fig, ax = plt.subplots(figsize=(12.8, 6.8), facecolor="#fffdf7")
    ax.set_facecolor("#fffaf0")

    x_positions = list(range(len(labels)))
    width = 0.18
    ax.bar([x - 1.5 * width for x in x_positions], faithfulness, width=width, color="#c2410c", label="Faithfulness")
    ax.bar([x - 0.5 * width for x in x_positions], relevancy, width=width, color="#2563eb", label="Answer Relevancy")
    ax.bar([x + 0.5 * width for x in x_positions], precision, width=width, color="#0f766e", label="Context Precision")
    ax.bar([x + 1.5 * width for x in x_positions], recall, width=width, color="#7c3aed", label="Context Recall")

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=11, color="#334155")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score", fontsize=11, color="#334155")
    ax.set_title("不同题型下的 RAGAS 指标分布", fontsize=16, fontweight="bold", color="#1f2937", pad=28)
    ax.grid(axis="y", linestyle=(0, (3, 4)), linewidth=0.8, color="#d6d3d1")
    ax.tick_params(axis="y", colors="#64748b")

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.04), fontsize=10.5)
    fig.text(0.5, 0.93, "用于展示系统在六类专业问题上的回答支撑性与相关性差异", ha="center", fontsize=10.5, color="#6b7280")
    fig.tight_layout(rect=[0, 0.02, 1, 0.9])
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def save_summary(payload: Dict[str, Any], source_path: Path, radar_path: Path, breakdown_path: Path) -> Path:
    output_path = VISUALS_DIR / "ragas_thesis_visual_summary.json"
    summary = {
        "source_json": str(source_path),
        "sample_count": payload.get("sample_count"),
        "llm_model": payload.get("llm_model"),
        "official_ragas_metrics": payload.get("official_ragas_metrics", {}),
        "question_type_breakdown": payload.get("question_type_breakdown", []),
        "generated_plots": {
            "radar": str(radar_path),
            "question_type_bar": str(breakdown_path),
        },
    }
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    configure_fonts()
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)

    source_path = find_latest_result()
    payload = load_payload(source_path)

    radar_path = VISUALS_DIR / "fig_5_7_ragas_radar.png"
    breakdown_path = VISUALS_DIR / "fig_5_8_ragas_question_types.png"

    save_radar_chart(build_overall_metrics(payload), radar_path)
    save_question_type_chart(build_question_type_rows(payload), breakdown_path)
    summary_path = save_summary(payload, source_path, radar_path, breakdown_path)

    print(json.dumps({
        "source_json": str(source_path),
        "radar": str(radar_path),
        "question_type_bar": str(breakdown_path),
        "summary": str(summary_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()