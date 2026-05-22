"""构建通用知识/专业咨询二分类训练数据集（v2）。"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from demo_experiment_paths import QUERY_CLASSIFIER_EXPERIMENT_DIR, STRATEGY_SELECTOR_EXPERIMENT_DIR
from general_query_seed_bank import CURATED_BOUNDARY_NEGATIVE_BANK, CURATED_GENERAL_QUERY_BANK
from generate_new_training_data import generic_knowledge as LEGACY_GENERAL_KNOWLEDGE_V2
from generate_training_data import generate_general_knowledge_queries


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = QUERY_CLASSIFIER_EXPERIMENT_DIR / "artifacts"
STRATEGY_DATASET = (
    STRATEGY_SELECTOR_EXPERIMENT_DIR
    / "artifacts"
    / "datasets"
    / "strategy_classifier_dataset_v2.jsonl"
)
TARGET_PER_CLASS = 500
RANDOM_SEED = 42
LABELS = ("通用知识", "专业咨询")


GENERAL_ANCHORS: Sequence[Dict[str, str]] = (
    {"query": "什么是人工智能？", "difficulty": "easy", "theme": "technology", "source": "general_anchor", "provenance": "manual"},
    {"query": "Python 中列表和元组有什么区别？", "difficulty": "easy", "theme": "programming", "source": "general_anchor", "provenance": "manual"},
    {"query": "如何准备一场结构化面试？", "difficulty": "medium", "theme": "career", "source": "general_anchor", "provenance": "manual"},
    {"query": "为什么火灾逃生时要弯腰前进？", "difficulty": "hard", "theme": "safety", "source": "general_anchor", "provenance": "manual"},
    {"query": "感冒发烧时应该先休息还是立刻运动出汗？", "difficulty": "medium", "theme": "health", "source": "general_anchor", "provenance": "manual"},
    {"query": "如何写一篇实习总结？", "difficulty": "medium", "theme": "writing", "source": "general_anchor", "provenance": "manual"},
    {"query": "采矿工程专业就业前景怎么样？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
    {"query": "如何写一篇采矿工程实习报告？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
    {"query": "采矿工程学生需要学好高等数学吗？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
    {"query": "矿山企业的校招面试一般会问什么？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
    {"query": "什么是安全生产？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
    {"query": "触电后应该先切断电源还是先救人？", "difficulty": "hard", "theme": "boundary_negative", "source": "general_anchor", "provenance": "manual"},
)


PROFESSIONAL_ANCHORS: Sequence[Dict[str, str]] = (
    {"query": "矿井通风阻力应如何测定？", "difficulty": "easy", "theme": "ventilation", "source": "professional_anchor", "provenance": "manual"},
    {"query": "露天矿边坡角如何根据岩性与台阶高度确定？", "difficulty": "medium", "theme": "open_pit", "source": "professional_anchor", "provenance": "manual"},
    {"query": "尾矿库在线安全监测通常包括哪些关键指标？", "difficulty": "medium", "theme": "tailings", "source": "professional_anchor", "provenance": "manual"},
    {"query": "浮选药剂制度优化时应优先关注哪些工艺参数？", "difficulty": "medium", "theme": "beneficiation", "source": "professional_anchor", "provenance": "manual"},
    {"query": "矿井发生触电事故时现场处置流程是什么？", "difficulty": "hard", "theme": "boundary_positive", "source": "professional_anchor", "provenance": "manual"},
    {"query": "矿山安全生产责任制应如何落实到班组与岗位？", "difficulty": "hard", "theme": "boundary_positive", "source": "professional_anchor", "provenance": "manual"},
    {"query": "井下火灾逃生路线应如何结合回风系统进行规划？", "difficulty": "hard", "theme": "boundary_positive", "source": "professional_anchor", "provenance": "manual"},
    {"query": "绿色矿山建设评价中资源综合利用指标如何核算？", "difficulty": "hard", "theme": "boundary_positive", "source": "professional_anchor", "provenance": "manual"},
    {"query": "深部开采条件下冲击地压风险应如何预警？", "difficulty": "medium", "theme": "geostress", "source": "professional_anchor", "provenance": "manual"},
    {"query": "井下巷道支护参数通常如何确定？", "difficulty": "medium", "theme": "support", "source": "professional_anchor", "provenance": "manual"},
)


GENERAL_TOPICS: Dict[str, Sequence[str]] = {
    "programming": ("Python 调试", "SQL 查询", "前端性能优化", "Git 分支管理", "API 设计"),
    "math": ("概率统计", "线性代数", "微积分", "数值分析", "离散数学"),
    "science": ("量子计算", "DNA 双螺旋", "气候变化", "太阳系行星", "电磁感应"),
    "career": ("简历优化", "校招面试", "职业转型", "项目复盘", "时间管理"),
    "writing": ("论文摘要", "演讲稿", "工作周报", "技术方案", "培训讲义"),
    "health": ("睡眠管理", "膝盖扭伤处理", "饮食控糖", "有氧训练", "压力缓解"),
    "daily": ("租房避坑", "旅行规划", "家用路由器设置", "厨房安全", "汽车保养"),
}


GENERAL_PATTERNS: Sequence[Tuple[str, str]] = (
    ("easy", "{topic} 的基本概念是什么？"),
    ("medium", "如果我是零基础，应该怎样系统学习 {topic}？"),
    ("medium", "{topic} 常见的误区有哪些？"),
    ("medium", "请给出一份关于 {topic} 的分步骤入门建议。"),
    ("hard", "在预算有限且时间紧张的前提下，如何平衡 {topic} 的效果与成本？"),
    ("medium", "学习 {topic} 时，初学者最容易踩的坑是什么？"),
    ("medium", "如果要向完全不了解的人解释 {topic}，应该怎样组织表达？"),
    ("medium", "{topic} 与相近概念相比，核心差异在哪里？"),
    ("hard", "如果只能用一周时间准备 {topic}，应如何安排每天的重点？"),
    ("hard", "从实践角度看，{topic} 失败最常见的原因有哪些？"),
    ("medium", "请帮我设计一个用于训练 {topic} 基础能力的练习清单。"),
    ("hard", "如果需要在团队内推广 {topic}，应如何兼顾理解成本与执行难度？"),
    ("medium", "围绕 {topic}，有哪些值得优先掌握的工具、方法或框架？"),
    ("hard", "面对时间碎片化的情况，如何持续提升 {topic} 而不半途而废？"),
)


BOUNDARY_NEGATIVE_PATTERNS: Sequence[str] = (
    "采矿工程专业学生准备 {topic} 时，应该先学哪些通用基础？",
    "在矿山企业工作的人如果想提升 {topic}，有哪些通用方法？",
    "围绕 {topic}，请帮我给采矿专业本科生写一份学习计划。",
    "如果要做一场关于 {topic} 的校园分享，采矿背景的同学应如何组织内容？",
)


BOUNDARY_NEGATIVE_TOPICS: Sequence[str] = (
    "英语口语", "求职简历", "演讲表达", "时间管理", "数据分析", "论文写作", "职业规划", "沟通技巧"
)


PROFESSIONAL_TOPICS: Dict[str, Sequence[str]] = {
    "ventilation": ("矿井通风", "局部通风机", "回风系统", "需风量计算", "反风演习"),
    "open_pit": ("露天开采", "边坡稳定", "台阶参数", "穿孔爆破", "采剥计划"),
    "underground": ("地下开采", "采准工程", "矿房矿柱", "分段崩落法", "充填采矿法"),
    "beneficiation": ("浮选分离", "磨矿分级", "重选流程", "磁选机", "药剂制度"),
    "safety": ("瓦斯治理", "顶板管理", "探放水", "粉尘防控", "尾矿库安全"),
    "equipment": ("提升机", "液压支架", "掘进机", "压滤机", "球磨机"),
    "geology": ("矿体圈定", "储量估算", "资源评价", "钻探取芯", "品位控制"),
}


PROFESSIONAL_PATTERNS: Sequence[Tuple[str, str]] = (
    ("easy", "{topic} 的关键技术要点有哪些？"),
    ("medium", "{topic} 的主要工艺参数应如何确定？"),
    ("medium", "{topic} 施工或运行中的常见失效模式有哪些？"),
    ("hard", "在埋深较大、围岩条件复杂的前提下，{topic} 应如何优化？"),
    ("hard", "如果现场同时受到工期、成本和安全约束，{topic} 的方案应怎样权衡？"),
)


def normalize_query(query: str) -> str:
    normalized = re.sub(r"\s+", "", query.strip().lower())
    normalized = normalized.replace("？", "?").replace("，", ",")
    return normalized


def save_jsonl(path: Path, rows: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        for row in rows:
            file_handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_strategy_professional_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query).strip()
    cleaned = cleaned.replace("～", "~")
    cleaned = cleaned.replace("请比较围绕", "请比较")
    cleaned = cleaned.replace("请分析围绕", "请分析")

    if cleaned.startswith("围绕") and "，" in cleaned:
        subject, detail = cleaned[2:].split("，", 1)
        detail = detail.strip("。？")
        replacements = (
            ("有哪些常见风险与防控重点", f"{subject}有哪些常见风险与防控重点？"),
            ("需要重点防控哪些风险", f"{subject}需要重点防控哪些风险？"),
            ("不同类型或情形下的要求分别是什么", f"{subject}在不同类型或情形下的要求分别是什么？"),
            ("不同类型之间有哪些差异", f"{subject}不同类型之间有哪些差异？"),
        )
        for marker, rewritten in replacements:
            if marker in detail:
                cleaned = rewritten
                break

    cleaned = re.sub(r"[。？]+$", "", cleaned) + "？"
    return cleaned


def is_bad_strategy_professional_query(query: str) -> bool:
    if "中应重点关注" in query or "中需要重点关注" in query:
        return True
    if query.startswith("围绕）") or query.startswith("围绕（"):
        return True
    if ("（" in query) ^ ("）" in query):
        return True
    if query.count("围绕") > 1:
        return True
    if "？？" in query or "。。" in query:
        return True
    return False


def load_strategy_professional_candidates() -> List[Dict]:
    rows: List[Dict] = []
    if not STRATEGY_DATASET.exists():
        return rows

    with STRATEGY_DATASET.open("r", encoding="utf-8-sig") as file_handle:
        for line in file_handle:
            if not line.strip():
                continue
            item = json.loads(line)
            query = clean_strategy_professional_query(item["query"].strip())
            if is_bad_strategy_professional_query(query):
                continue
            rows.append(
                {
                    "query": query,
                    "label": "专业咨询",
                    "source": "strategy_professional_reuse",
                    "provenance": item.get("provenance", "strategy_classifier_dataset_v2.jsonl"),
                    "difficulty": "medium",
                    "theme": item.get("strategy", "strategy_dataset"),
                }
            )
    return rows


def build_general_candidates() -> List[Dict]:
    rows: List[Dict] = []
    for item in GENERAL_ANCHORS:
        rows.append({**item, "label": "通用知识"})

    for theme, queries in CURATED_GENERAL_QUERY_BANK.items():
        for query in queries:
            rows.append(
                {
                    "query": query,
                    "label": "通用知识",
                    "source": "general_seed_curated",
                    "provenance": "general_query_seed_bank.py",
                    "difficulty": "medium",
                    "theme": theme,
                }
            )

    for query in generate_general_knowledge_queries():
        rows.append(
            {
                "query": query,
                "label": "通用知识",
                "source": "legacy_general_reuse_v1",
                "provenance": "generate_training_data.py",
                "difficulty": "easy",
                "theme": "legacy_general",
            }
        )

    for query in LEGACY_GENERAL_KNOWLEDGE_V2:
        rows.append(
            {
                "query": query,
                "label": "通用知识",
                "source": "legacy_general_reuse_v2",
                "provenance": "generate_new_training_data.py",
                "difficulty": "medium",
                "theme": "legacy_general",
            }
        )

    for theme, queries in CURATED_BOUNDARY_NEGATIVE_BANK.items():
        for query in queries:
            rows.append(
                {
                    "query": query,
                    "label": "通用知识",
                    "source": "boundary_negative_curated",
                    "provenance": "general_query_seed_bank.py",
                    "difficulty": "hard",
                    "theme": "boundary_negative",
                }
            )

    for theme, topics in GENERAL_TOPICS.items():
        for topic in topics:
            for difficulty, pattern in GENERAL_PATTERNS:
                rows.append(
                    {
                        "query": pattern.format(topic=topic),
                        "label": "通用知识",
                        "source": "general_template_generated",
                        "provenance": f"{theme}:{pattern}",
                        "difficulty": difficulty,
                        "theme": theme,
                    }
                )

    for topic in BOUNDARY_NEGATIVE_TOPICS:
        for pattern in BOUNDARY_NEGATIVE_PATTERNS:
            rows.append(
                {
                    "query": pattern.format(topic=topic),
                    "label": "通用知识",
                    "source": "boundary_negative_generated",
                    "provenance": pattern,
                    "difficulty": "hard",
                    "theme": "boundary_negative",
                }
            )
    return rows


def build_professional_candidates() -> List[Dict]:
    rows = load_strategy_professional_candidates()
    for item in PROFESSIONAL_ANCHORS:
        rows.append({**item, "label": "专业咨询"})

    for theme, topics in PROFESSIONAL_TOPICS.items():
        for topic in topics:
            for difficulty, pattern in PROFESSIONAL_PATTERNS:
                rows.append(
                    {
                        "query": pattern.format(topic=topic),
                        "label": "专业咨询",
                        "source": "professional_template_generated",
                        "provenance": f"{theme}:{pattern}",
                        "difficulty": difficulty,
                        "theme": theme,
                    }
                )
    return rows


def deduplicate_and_sample(rows: Sequence[Dict], label: str, target_size: int) -> Tuple[List[Dict], Counter]:
    seen = set()
    deduped: List[Dict] = []
    source_stats: Counter = Counter()
    for row in rows:
        normalized = normalize_query(row["query"])
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(row)
        source_stats[row["source"]] += 1

    if len(deduped) < target_size:
        raise ValueError(f"{label} 候选样本不足：{len(deduped)} < {target_size}")

    rng = random.Random(RANDOM_SEED)
    anchors = [row for row in deduped if row["source"].endswith("anchor")]
    boundary = [row for row in deduped if "boundary" in row["theme"] and row not in anchors]
    remainder = [row for row in deduped if row not in anchors and row not in boundary]
    rng.shuffle(boundary)
    rng.shuffle(remainder)

    selected: List[Dict] = []
    for row in anchors + boundary + remainder:
        if len(selected) >= target_size:
            break
        selected.append(row)

    selected_stats = Counter(row["source"] for row in selected)
    return selected, selected_stats


def stratified_split(rows: Sequence[Dict]) -> Dict[str, List[Dict]]:
    rng = random.Random(RANDOM_SEED)
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        grouped[row["label"]].append(dict(row))

    splits = {"train": [], "val": [], "test": []}
    for label, items in grouped.items():
        rng.shuffle(items)
        total = len(items)
        train_end = int(total * 0.8)
        val_end = int(total * 0.9)
        split_map = {
            "train": items[:train_end],
            "val": items[train_end:val_end],
            "test": items[val_end:],
        }
        for split_name, split_rows in split_map.items():
            for row in split_rows:
                row["split"] = split_name
            splits[split_name].extend(split_rows)

    for split_rows in splits.values():
        rng.shuffle(split_rows)
    return splits


def build_report(final_rows: Sequence[Dict], split_rows: Dict[str, List[Dict]], source_stats: Dict[str, Dict[str, int]]) -> str:
    label_distribution = Counter(row["label"] for row in final_rows)
    source_distribution = Counter(row["source"] for row in final_rows)
    difficulty_distribution = Counter(row["difficulty"] for row in final_rows)
    split_distribution = {split: Counter(row["label"] for row in rows) for split, rows in split_rows.items()}
    lines = [
        "# 通用知识/专业咨询二分类数据集构建说明",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 设计原则",
        "",
        "本数据集吸收四种检索策略分类器 v2 的构建经验，不再通过少量模板重复采样凑数量，而是采用‘真实专业问句复用 + 人工边界锚点 + 多主题模板增强 + 分层切分’的方式，一次性构建 1000 条可训练样本。",
        "",
        "1. 从 strategy_classifier_dataset_v2.jsonl 中复用真实采矿冶金问句，作为专业咨询类的真实语料来源。",
        "2. 单独加入容易混淆的人工锚点样本，覆盖‘带采矿词但应判通用’与‘带安全常识词但应判专业’两类边界。",
        "3. 为通用知识引入编程、数学、科学、求职、写作、健康、日常生活等多主题问句，避免通用类只剩小学常识问答。",
        "4. 输出完整数据集与 train/val/test 分层切分文件，保留 source/provenance/difficulty/theme 字段，便于后续诊断误判。",
        "",
        "## 数据分布",
        "",
        f"- 总样本数：{len(final_rows)}",
        f"- 标签分布：{json.dumps(label_distribution, ensure_ascii=False)}",
        f"- 来源分布：{json.dumps(source_distribution, ensure_ascii=False)}",
        f"- 难度分布：{json.dumps(difficulty_distribution, ensure_ascii=False)}",
        "",
        "## 切分情况",
        "",
        f"- 训练集：{len(split_rows['train'])}，分布：{json.dumps(split_distribution['train'], ensure_ascii=False)}",
        f"- 验证集：{len(split_rows['val'])}，分布：{json.dumps(split_distribution['val'], ensure_ascii=False)}",
        f"- 测试集：{len(split_rows['test'])}，分布：{json.dumps(split_distribution['test'], ensure_ascii=False)}",
        "",
        "## 类别来源统计",
        "",
        f"- 通用知识：{json.dumps(source_stats['通用知识'], ensure_ascii=False)}",
        f"- 专业咨询：{json.dumps(source_stats['专业咨询'], ensure_ascii=False)}",
        "",
        "## 样本示例",
        "",
    ]
    for row in list(final_rows)[:12]:
        lines.append(f"- [{row['label']}] {row['query']} ({row['source']})")
    return "\n".join(lines) + "\n"


def main() -> None:
    random.seed(RANDOM_SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    general_rows, general_stats = deduplicate_and_sample(build_general_candidates(), "通用知识", TARGET_PER_CLASS)
    professional_rows, professional_stats = deduplicate_and_sample(build_professional_candidates(), "专业咨询", TARGET_PER_CLASS)
    final_rows = general_rows + professional_rows
    random.Random(RANDOM_SEED).shuffle(final_rows)
    split_rows = stratified_split(final_rows)

    dataset_path = OUTPUT_DIR / "query_classifier_dataset_v2.jsonl"
    train_path = OUTPUT_DIR / "query_classifier_train_v2.jsonl"
    val_path = OUTPUT_DIR / "query_classifier_val_v2.jsonl"
    test_path = OUTPUT_DIR / "query_classifier_test_v2.jsonl"
    summary_path = OUTPUT_DIR / "query_classifier_dataset_v2.summary.json"
    report_path = OUTPUT_DIR / "query_classifier_dataset_v2.report.md"

    save_jsonl(dataset_path, final_rows)
    save_jsonl(train_path, split_rows["train"])
    save_jsonl(val_path, split_rows["val"])
    save_jsonl(test_path, split_rows["test"])

    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_per_class": TARGET_PER_CLASS,
        "label_counts": dict(Counter(row["label"] for row in final_rows)),
        "source_stats": {"通用知识": dict(general_stats), "专业咨询": dict(professional_stats)},
        "split_sizes": {key: len(value) for key, value in split_rows.items()},
        "strategy_dataset_reused": STRATEGY_DATASET.exists(),
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_report(final_rows, split_rows, summary_payload["source_stats"]), encoding="utf-8")

    print(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "train_path": str(train_path),
                "val_path": str(val_path),
                "test_path": str(test_path),
                "summary_path": str(summary_path),
                "report_path": str(report_path),
                "label_counts": summary_payload["label_counts"],
                "split_sizes": summary_payload["split_sizes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()