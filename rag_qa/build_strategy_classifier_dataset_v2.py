import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from demo_experiment_paths import RAGAS_DATASET_EXPERIMENT_DIR, STRATEGY_SELECTOR_EXPERIMENT_DIR


ROOT = Path(__file__).resolve().parent
RAGAS_DATA_DIR = RAGAS_DATASET_EXPERIMENT_DIR / "artifacts" / "datasets"
EXPERIMENT_DIR = STRATEGY_SELECTOR_EXPERIMENT_DIR / "artifacts"
DATASET_DIR = EXPERIMENT_DIR / "datasets"
REPORT_DIR = EXPERIMENT_DIR / "reports"
CONVERSATION_DIR = ROOT / "conversations"
DIAGNOSTIC_DATASET = DATASET_DIR / "strategy_selector_diagnostic_benchmark.json"

RANDOM_SEED = 42
TARGET_PER_CLASS = 320
LABELS = ["直接检索", "查询扩展检索", "查询分解检索", "问题重写检索"]
QUESTION_TYPE_TO_STRATEGY = {
    "concept": "直接检索",
    "threshold": "直接检索",
    "process": "直接检索",
    "risk": "查询扩展检索",
    "compare": "查询分解检索",
    "scene": "问题重写检索",
}
DOMAIN_PATTERN = re.compile(r"矿|采矿|选矿|冶金|炼铁|炼钢|尾矿|矿井|矿山|通风|爆破|边坡|炉|煤气|支护")


def normalize_query(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^[）)\(（、，。；：:]+", "", text)
    return text


def add_candidate(container: Dict[str, List[Dict]], strategy: str, query: str, source: str, provenance: str) -> None:
    cleaned = normalize_query(query)
    if len(cleaned) < 6:
        return
    if strategy not in container:
        container[strategy] = []
    container[strategy].append({
        "query": cleaned,
        "strategy": strategy,
        "source": source,
        "provenance": provenance,
    })


def build_variants(question: str, question_type_key: str) -> List[str]:
    question = normalize_query(question)
    variants = [question]
    replacements = {
        "涉及的关键条件、数值或范围要求是什么？": [
            "有哪些关键条件、数值或范围要求？",
            "关键数值要求和适用范围是什么？",
        ],
        "的定义、内涵或主要内容是什么？": [
            "的定义和主要内容是什么？",
            "主要内涵是什么？",
        ],
        "的主要流程、步骤或组成是什么？": [
            "的主要步骤有哪些？",
            "包含哪些关键流程？",
        ],
        "需要重点关注哪些危险因素或安全措施？": [
            "有哪些重点危险因素和防控措施？",
            "需要重点防控哪些风险？",
        ],
        "不同类型或情形下的要求分别是什么？": [
            "不同类型之间有哪些差异？",
            "不同情形下分别应满足什么要求？",
        ],
        "现场应如何开展应急处置？": [
            "现场应如何处置？",
            "应急处理步骤是什么？",
        ],
    }
    for old_text, new_texts in replacements.items():
        if old_text in question:
            for new_text in new_texts:
                variants.append(question.replace(old_text, new_text))

    if question_type_key == "risk":
        topic = question.replace("需要重点关注哪些危险因素或安全措施？", "")
        variants.extend([
            f"{topic}有哪些常见风险与防控重点？",
            f"分析{topic}中应重点关注的危险因素。",
        ])
    elif question_type_key == "compare":
        variants.append(f"请比较{question.rstrip('？?')}。")
    elif question_type_key == "scene":
        variants.append(question.replace("现场应如何开展应急处置？", "应采取哪些处置措施？"))

    seen = []
    dedup = set()
    for item in variants:
        normalized = normalize_query(item)
        if normalized and normalized not in dedup:
            dedup.add(normalized)
            seen.append(normalized)
    return seen


def load_metallurgy_candidates(container: Dict[str, List[Dict]]) -> Counter:
    stats = Counter()
    for file_name in ["metallurgy_train.json", "metallurgy_val.json", "metallurgy_test.json"]:
        data = json.loads((RAGAS_DATA_DIR / file_name).read_text(encoding="utf-8"))
        for item in data:
            strategy = QUESTION_TYPE_TO_STRATEGY.get(item.get("question_type_key"))
            if strategy is None:
                continue
            for variant in build_variants(item.get("question", ""), item.get("question_type_key", "")):
                add_candidate(container, strategy, variant, "metallurgy_dataset", file_name)
                stats[strategy] += 1
    return stats


def load_conversation_candidates(container: Dict[str, List[Dict]]) -> Counter:
    stats = Counter()
    if not CONVERSATION_DIR.exists():
        return stats

    for path in CONVERSATION_DIR.glob("session_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in payload.get("history", []):
            metadata = item.get("metadata", {})
            strategy = metadata.get("strategy")
            question = normalize_query(item.get("question", ""))
            if strategy not in LABELS or not question:
                continue
            if not DOMAIN_PATTERN.search(question):
                continue
            add_candidate(container, strategy, question, "conversation_history", path.name)
            stats[strategy] += 1
    return stats


def load_diagnostic_candidates(container: Dict[str, List[Dict]]) -> Counter:
    stats = Counter()
    if not DIAGNOSTIC_DATASET.exists():
        return stats
    payload = json.loads(DIAGNOSTIC_DATASET.read_text(encoding="utf-8"))
    for item in payload.get("samples", []):
        strategy = item["label"]
        add_candidate(container, strategy, item["query"], "diagnostic_benchmark", DIAGNOSTIC_DATASET.name)
        stats[strategy] += 1
    return stats


def generate_template_candidates(container: Dict[str, List[Dict]], target_per_class: int) -> Counter:
    random.seed(RANDOM_SEED)
    stats = Counter()
    direct_templates = [
        "什么是{topic}？",
        "{topic}的定义是什么？",
        "{topic}有哪些主要特点？",
        "{topic}的基本原理是什么？",
        "{topic}包含哪些关键内容？",
    ]
    expansion_templates = [
        "{topic}对安全生产的影响有哪些？",
        "{topic}的作用和意义是什么？",
        "{topic}的发展趋势如何？",
        "为什么{topic}对矿山生产很重要？",
        "{topic}的价值体现在哪些方面？",
    ]
    subquery_templates = [
        "比较{a}与{b}在{aspect}上的差异。",
        "{a}和{b}的区别是什么？请从{aspect}角度说明。",
        "请分析{a}与{b}在{aspect}方面的优缺点。",
        "{a}和{b}分别适用于哪些场景？重点比较{aspect}。",
        "{a}相较于{b}在{aspect}上各自有什么特点？",
        "若要在{scenario}中进行方案选择，{a}与{b}应如何比较？",
    ]
    scene_templates = [
        "某矿井在{condition}条件下出现{issue}，现场应如何处置？",
        "尾矿库出现{issue}，且{constraint}，应采取什么技术方案？",
        "某{facility}运行中出现{issue}，如何排查并优化？",
        "当{condition}导致{issue}时，操作人员应重点采取哪些措施？",
        "在{condition}工况下，{facility}的安全控制方案应如何设计？",
        "{facility}在{condition}环境下发生{issue}，并受到{constraint}约束，应如何制定处置方案？",
        "如果{facility}出现{issue}且现场存在{constraint}，应优先排查哪些环节并采取什么措施？",
    ]

    direct_topics = [
        "充填采矿法", "矿井通风", "尾矿库排洪系统", "爆破作业", "边坡稳定", "选矿流程", "炼铁安全技术", "煤气防护"
    ]
    expansion_topics = [
        "绿色矿山建设", "尾矿资源化利用", "深部开采", "智能化采矿", "安全管理数字化", "矿山生态修复", "风险分级管控"
    ]
    subquery_pairs = [
        ("露天开采", "地下开采"), ("浮选法", "磁选法"), ("中央式通风", "对角式通风"),
        ("充填采矿法", "空场采矿法"), ("汽车运输", "铁路运输"), ("常规爆破", "微差爆破")
    ]
    compare_aspects = ["安全性", "适用条件", "成本", "效率", "设备要求", "维护难度", "环境影响", "回收率"]
    compare_scenarios = ["深部开采", "露天矿运输", "复杂地质条件", "高瓦斯矿井", "选矿厂工艺改造", "边坡控制"]
    scene_conditions = ["高地应力", "高温高湿", "瓦斯涌出量增大", "边坡裂缝扩展", "回收率持续下降"]
    scene_issues = ["设备异常振动", "浸润线抬高3米", "顶板掉矸", "回收率偏低", "尾矿坝体裂缝"]
    scene_constraints = ["工期紧张", "地质条件复杂", "现场空间受限", "安全指标不能下降", "设备不能长时间停机"]
    facilities = ["通风系统", "球磨机", "破碎机", "尾矿库", "提升机", "选矿厂浮选系统"]

    current_sizes = {label: len(container.get(label, [])) for label in LABELS}
    needed = {label: max(0, target_per_class - current_sizes.get(label, 0)) for label in LABELS}

    for _ in range(needed["直接检索"]):
        template = random.choice(direct_templates)
        query = template.format(topic=random.choice(direct_topics))
        add_candidate(container, "直接检索", query, "template_generated", "direct_templates")
        stats["直接检索"] += 1

    for _ in range(needed["查询扩展检索"]):
        template = random.choice(expansion_templates)
        query = template.format(topic=random.choice(expansion_topics))
        add_candidate(container, "查询扩展检索", query, "template_generated", "query_expansion_templates")
        stats["查询扩展检索"] += 1

    subquery_goal = needed["查询分解检索"]
    generated = 0
    attempts = 0
    while generated < subquery_goal and attempts < subquery_goal * 20:
        attempts += 1
        template = random.choice(subquery_templates)
        left, right = random.choice(subquery_pairs)
        query = template.format(
            a=left,
            b=right,
            aspect=random.choice(compare_aspects),
            scenario=random.choice(compare_scenarios),
        )
        before = len(container["查询分解检索"])
        add_candidate(container, "查询分解检索", query, "template_generated", "decomposition_templates")
        if len(container["查询分解检索"]) > before:
            generated += 1
            stats["查询分解检索"] += 1

    scene_goal = needed["问题重写检索"]
    generated = 0
    attempts = 0
    scene_actions = ["处置", "排查", "整改", "优化", "加固", "重构", "设计"]
    while generated < scene_goal and attempts < scene_goal * 30:
        attempts += 1
        template = random.choice(scene_templates)
        query = template.format(
            condition=random.choice(scene_conditions),
            issue=random.choice(scene_issues),
            constraint=random.choice(scene_constraints),
            facility=random.choice(facilities),
            action=random.choice(scene_actions),
        )
        before = len(container["问题重写检索"])
        add_candidate(container, "问题重写检索", query, "template_generated", "rewrite_templates")
        if len(container["问题重写检索"]) > before:
            generated += 1
            stats["问题重写检索"] += 1

    return stats


def deduplicate_and_sample(container: Dict[str, List[Dict]], target_per_class: int) -> Tuple[List[Dict], Dict[str, int]]:
    rng = random.Random(RANDOM_SEED)
    final_rows: List[Dict] = []
    reuse_counts: Dict[str, int] = {}
    for label in LABELS:
        dedup = {}
        for item in container.get(label, []):
            dedup[item["query"]] = item
        rows = list(dedup.values())
        rng.shuffle(rows)
        selected = rows[:target_per_class]
        reuse_counts[label] = len(selected)
        final_rows.extend(selected)
    rng.shuffle(final_rows)
    return final_rows, reuse_counts


def top_up_missing_classes(final_rows: List[Dict], target_per_class: int) -> List[Dict]:
    rng = random.Random(RANDOM_SEED)
    existing_queries = {row["query"] for row in final_rows}
    counts = Counter(row["strategy"] for row in final_rows)

    direct_topics = ["矿井通风", "爆破安全", "尾矿库排洪", "煤气防护", "炼钢安全技术", "充填采矿法"]
    expansion_topics = ["绿色矿山", "矿山生态修复", "深部开采", "智能采矿", "风险分级管控", "尾矿资源化"]
    compare_pairs = [
        ("露天开采", "地下开采"), ("浮选法", "磁选法"), ("中央式通风", "对角式通风"),
        ("充填采矿法", "空场采矿法"), ("汽车运输", "铁路运输"), ("常规爆破", "微差爆破")
    ]
    compare_aspects = ["安全性", "成本", "效率", "适用条件", "设备要求", "维护难度", "环境影响"]
    scene_conditions = ["高地应力", "高温高湿", "瓦斯涌出量增大", "边坡裂缝扩展", "回收率持续下降", "涌水风险上升"]
    scene_issues = ["设备异常振动", "浸润线抬高3米", "顶板掉矸", "回收率偏低", "尾矿坝体裂缝", "通风阻力增大"]
    scene_constraints = ["工期紧张", "地质条件复杂", "现场空间受限", "安全指标不能下降", "设备不能长时间停机", "预算受限"]
    facilities = ["通风系统", "球磨机", "破碎机", "尾矿库", "提升机", "浮选系统", "排水系统"]

    def build_query(label: str) -> str:
        if label == "直接检索":
            topic = rng.choice(direct_topics)
            template = rng.choice([
                "什么是{topic}？",
                "{topic}的定义是什么？",
                "{topic}有哪些主要特点？",
                "{topic}的基本原理是什么？",
            ])
            return template.format(topic=topic)
        if label == "查询扩展检索":
            topic = rng.choice(expansion_topics)
            template = rng.choice([
                "{topic}的发展趋势如何？",
                "{topic}的作用和意义是什么？",
                "为什么{topic}对安全生产很重要？",
                "{topic}的价值体现在哪些方面？",
            ])
            return template.format(topic=topic)
        if label == "查询分解检索":
            left, right = rng.choice(compare_pairs)
            aspect = rng.choice(compare_aspects)
            template = rng.choice([
                "比较{a}与{b}在{aspect}上的差异。",
                "{a}和{b}的区别是什么？请从{aspect}角度说明。",
                "若要在矿山生产中进行方案选择，{a}与{b}在{aspect}上应如何比较？",
                "{a}相较于{b}在{aspect}上各自有什么优缺点？",
            ])
            return template.format(a=left, b=right, aspect=aspect)
        condition = rng.choice(scene_conditions)
        issue = rng.choice(scene_issues)
        constraint = rng.choice(scene_constraints)
        facility = rng.choice(facilities)
        template = rng.choice([
            "某{facility}在{condition}条件下出现{issue}，现场应如何处置？",
            "当{condition}导致{issue}时，{facility}应如何排查并优化？",
            "{facility}出现{issue}，且{constraint}，应采取什么技术方案？",
            "在{condition}工况下，{facility}受到{constraint}约束时应如何设计控制方案？",
        ])
        return template.format(facility=facility, condition=condition, issue=issue, constraint=constraint)

    for label in LABELS:
        attempts = 0
        while counts[label] < target_per_class and attempts < 5000:
            attempts += 1
            query = normalize_query(build_query(label))
            if query in existing_queries:
                continue
            final_rows.append({
                "query": query,
                "strategy": label,
                "source": "template_topup",
                "provenance": "top_up_missing_classes",
            })
            existing_queries.add(query)
            counts[label] += 1

    rng.shuffle(final_rows)
    return final_rows


def stratified_split(rows: List[Dict]) -> Dict[str, List[Dict]]:
    rng = random.Random(RANDOM_SEED)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["strategy"]].append(row)

    splits = {"train": [], "val": [], "test": []}
    for label, items in grouped.items():
        rng.shuffle(items)
        total = len(items)
        train_end = int(total * 0.8)
        val_end = int(total * 0.9)
        splits["train"].extend(items[:train_end])
        splits["val"].extend(items[train_end:val_end])
        splits["test"].extend(items[val_end:])

    for split_rows in splits.values():
        rng.shuffle(split_rows)
    return splits


def save_jsonl(path: Path, rows: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        for row in rows:
            file_handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_dataset_report(final_rows: List[Dict], source_stats: Dict[str, Counter], split_rows: Dict[str, List[Dict]]) -> str:
    label_distribution = Counter(row["strategy"] for row in final_rows)
    source_distribution = Counter(row["source"] for row in final_rows)
    split_distribution = {
        split: Counter(row["strategy"] for row in rows)
        for split, rows in split_rows.items()
    }

    lines = [
        "# 检索策略分类数据集构建说明",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 数据集构建思路",
        "",
        "本次四分类策略数据集不再依赖仓库中缺失的 `strategy_classification_8000.json` 与 `training_dataset_mining_5000.json`，而是重建为“真实问句复用 + 历史样本补充 + 诊断基准锚定 + 模板增强”的组合式数据集。",
        "",
        "1. 复用 `ragas_paper_bundle/datasets` 下的冶金训练/验证/测试集问句，共 440 条基础问句。",
        "2. 按 question_type_key 将已有问句映射到四类检索策略：concept/threshold/process -> 直接检索，risk -> 查询扩展检索，compare -> 查询分解检索，scene -> 问题重写检索。",
        "3. 对冶金问句进行轻量改写，生成同义或结构变体，以增强分类器对不同问法的鲁棒性。",
        "4. 复用 conversations 目录下的历史带策略样本，但只保留采矿冶金相关问题，避免将烂尾项目中的非领域问题混入训练集。",
        "5. 将诊断基准中的 20 条人工核验样本纳入数据集，作为边界样本锚点。",
        "6. 对缺口较大的类别使用模板增强补齐，最终得到平衡的四分类训练集。",
        "",
        "## 来源统计",
        "",
        f"- 冶金评测集衍生样本：{sum(source_stats['metallurgy'].values())}",
        f"- 历史会话复用样本：{sum(source_stats['conversation'].values())}",
        f"- 诊断基准复用样本：{sum(source_stats['diagnostic'].values())}",
        f"- 模板增强样本：{sum(source_stats['template'].values())}",
        "",
        "## 最终数据集分布",
        "",
        f"- 总样本数：{len(final_rows)}",
        f"- 类别分布：{json.dumps(label_distribution, ensure_ascii=False)}",
        f"- 来源分布：{json.dumps(source_distribution, ensure_ascii=False)}",
        "",
        "## 训练/验证/测试划分",
        "",
        f"- 训练集：{len(split_rows['train'])}，分布：{json.dumps(split_distribution['train'], ensure_ascii=False)}",
        f"- 验证集：{len(split_rows['val'])}，分布：{json.dumps(split_distribution['val'], ensure_ascii=False)}",
        f"- 测试集：{len(split_rows['test'])}，分布：{json.dumps(split_distribution['test'], ensure_ascii=False)}",
        "",
        "## 样本示例",
        "",
    ]
    for row in final_rows[:12]:
        lines.append(f"- [{row['strategy']}] {row['query']} ({row['source']})")
    return "\n".join(lines) + "\n"


def main() -> None:
    random.seed(RANDOM_SEED)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    candidate_pool: Dict[str, List[Dict]] = {label: [] for label in LABELS}
    source_stats = {
        "metallurgy": load_metallurgy_candidates(candidate_pool),
        "conversation": load_conversation_candidates(candidate_pool),
        "diagnostic": load_diagnostic_candidates(candidate_pool),
    }
    source_stats["template"] = generate_template_candidates(candidate_pool, TARGET_PER_CLASS)

    final_rows, selected_counts = deduplicate_and_sample(candidate_pool, TARGET_PER_CLASS)
    final_rows = top_up_missing_classes(final_rows, TARGET_PER_CLASS)
    selected_counts = dict(Counter(row["strategy"] for row in final_rows))
    split_rows = stratified_split(final_rows)

    dataset_path = DATASET_DIR / "strategy_classifier_dataset_v2.jsonl"
    train_path = DATASET_DIR / "strategy_classifier_train_v2.jsonl"
    val_path = DATASET_DIR / "strategy_classifier_val_v2.jsonl"
    test_path = DATASET_DIR / "strategy_classifier_test_v2.jsonl"
    summary_path = DATASET_DIR / "strategy_classifier_dataset_v2.summary.json"
    report_path = REPORT_DIR / "strategy_classifier_dataset_report.md"

    save_jsonl(dataset_path, final_rows)
    save_jsonl(train_path, split_rows["train"])
    save_jsonl(val_path, split_rows["val"])
    save_jsonl(test_path, split_rows["test"])

    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_per_class": TARGET_PER_CLASS,
        "selected_counts": selected_counts,
        "source_stats": {key: dict(value) for key, value in source_stats.items()},
        "split_sizes": {key: len(value) for key, value in split_rows.items()},
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_dataset_report(final_rows, source_stats, split_rows), encoding="utf-8")

    print(json.dumps({
        "dataset_path": str(dataset_path),
        "train_path": str(train_path),
        "val_path": str(val_path),
        "test_path": str(test_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "selected_counts": selected_counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()