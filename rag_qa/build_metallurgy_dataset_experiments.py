from __future__ import annotations

import os
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT.parent))

from base import Config
from core.vector_store import VectorStore
from demo_experiment_paths import RAGAS_DATASET_EXPERIMENT_DIR


DEFAULT_OCR_CACHE = ROOT / "user_data" / "knowledge_files" / "metallurgy" / "8a7f8cc2abe9__冶金安全生产技术_12665867(1).pdf.ocr_cache.json"
RAGAS_PAPER_BUNDLE_DIR = RAGAS_DATASET_EXPERIMENT_DIR / "artifacts"
DATASET_OUTPUT_DIR = RAGAS_PAPER_BUNDLE_DIR / "generated_datasets" / "metallurgy_dataset_suite"
EXPERIMENT_OUTPUT_DIR = RAGAS_PAPER_BUNDLE_DIR / "generated_datasets" / "metallurgy_method_experiments"
RAGAS_PAPER_DATA_DIR = RAGAS_PAPER_BUNDLE_DIR / "datasets"
RAGAS_PAPER_RESULTS_DIR = RAGAS_PAPER_BUNDLE_DIR / "results"
RAGAS_PAPER_PLOTS_DIR = RAGAS_PAPER_BUNDLE_DIR / "plots"
HYPOTHETICAL_BUNDLE_DIR = RAGAS_PAPER_BUNDLE_DIR / "illustrative_only"
HYPOTHETICAL_RESULTS_DIR = HYPOTHETICAL_BUNDLE_DIR / "results"
HYPOTHETICAL_PLOTS_DIR = HYPOTHETICAL_BUNDLE_DIR / "plots"

RANDOM_SEED = 42

POSITIVE_SPLIT_COUNTS = {
    "train": 300,
    "val": 60,
    "test": 80,
}

TYPE_LABELS = {
    "concept": "概念定义类",
    "threshold": "条件阈值类",
    "process": "流程步骤类",
    "risk": "风险防控类",
    "compare": "对比辨析类",
    "scene": "场景化应用类",
    "reject": "拒答集",
}

TYPE_QUOTAS = {
    "train": {"concept": 45, "threshold": 60, "process": 45, "risk": 60, "compare": 45, "scene": 45},
    "val": {"concept": 9, "threshold": 12, "process": 9, "risk": 12, "compare": 9, "scene": 9},
    "test": {"concept": 12, "threshold": 16, "process": 12, "risk": 16, "compare": 12, "scene": 12},
}

REJECT_COUNTS = {
    "out_of_scope": 10,
    "cross_domain": 10,
    "ambiguous": 10,
    "unsupported_detail": 10,
}

QUESTION_TYPE_ORDER = ["threshold", "compare", "scene", "process", "risk", "concept"]

CHAPTER_PATTERN = re.compile(r"^第[一二三四五六七八九十百零〇]+[章节篇].{0,40}$")
SECTION_PATTERN = re.compile(r"^第[一二三四五六七八九十百零〇]+节.{0,40}$")
NUMBERED_PATTERN = re.compile(r"^\d+(?:\.\d+){0,3}\s*[^\n]{2,40}$")
NOISE_PATTERNS = [
    re.compile(r"^\d{4}年\d{1,2}月第\d+版$"),
    re.compile(r"^\d{4}年\d{1,2}月第\d+次印刷$"),
    re.compile(r"^\d{6,}$"),
]

GENERIC_HEADING_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百零〇]+章概述$"),
    re.compile(r"^概述$"),
    re.compile(r"^总则$"),
]

NUMERIC_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|m|mm|cm|kg|t|MPa|kPa|Pa|℃|°C|m3|m/s|h|min|秒|分钟|小时|天|年|人|项|次|倍|米|毫米|厘米|千克|吨|摄氏度|兆帕|千帕|帕)"
)

REJECT_ANSWER = "信息不足，无法从当前《冶金安全生产技术》知识库中得到可靠答案。"


@dataclass(frozen=True)
class Section:
    section_id: str
    order: int
    chapter: str
    heading: str
    topic: str
    context: str


@dataclass
class Candidate:
    section: Section
    question_type: str
    question: str
    answer: str
    ground_truth: str
    context: List[str]
    quality_score: float


def load_ocr_cache(cache_path: Path) -> Dict[str, Any]:
    with cache_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, ensure_ascii=False, indent=2)


def normalize_line(line: str) -> str:
    cleaned = re.sub(r"[·•．.]{2,}$", "", line.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def merge_broken_heading_lines(lines: Sequence[str]) -> List[str]:
    merged: List[str] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        if (
            index + 1 < len(lines)
            and re.match(r"^第[一二三四五六七八九十百零〇]+[章节篇].{0,2}$", current)
            and lines[index + 1]
            and len(lines[index + 1]) <= 8
        ):
            merged.append(f"{current}{lines[index + 1]}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def is_heading(line: str) -> bool:
    if not line:
        return False
    if any(pattern.match(line) for pattern in NOISE_PATTERNS):
        return False
    if CHAPTER_PATTERN.match(line) or SECTION_PATTERN.match(line):
        return True
    if NUMBERED_PATTERN.match(line):
        if re.search(r"[\u4e00-\u9fff]", line) is None:
            return False
        if any(token in line for token in ("，", "。", "；", "：", "?", "？", "!", "！")):
            return False
        digit_ratio = sum(ch.isdigit() for ch in line) / max(len(line), 1)
        return digit_ratio < 0.35 and len(line) <= 24
    return False


def split_sentences(text: str) -> List[str]:
    normalized = re.sub(r"\n+", "\n", text)
    raw_parts = re.split(r"(?<=[。！？；])|\n", normalized)
    sentences = []
    for part in raw_parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" \t\r\n-—:：")
        if len(cleaned) >= 8 and re.search(r"[\u4e00-\u9fff]", cleaned):
            sentences.append(cleaned)
    return sentences


def truncate_text(text: str, max_chars: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    truncated = compact[:max_chars].rstrip()
    last_break = max(truncated.rfind("。"), truncated.rfind("；"), truncated.rfind("，"))
    if last_break >= max_chars // 2:
        truncated = truncated[: last_break + 1].rstrip()
    return truncated


def normalize_question(question: str) -> str:
    text = re.sub(r"^问题[:：]\s*", "", question or "").strip()
    text = re.sub(r"[\s\u3000]+", "", text)
    return text


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        if text is None:
            text = ""
        elif isinstance(text, (dict, list, tuple)):
            text = json.dumps(text, ensure_ascii=False)
        else:
            text = str(text)
    text = re.sub(r"[\s\u3000]+", "", text or "")
    return re.sub(r"[，。！？；：、“”‘’（）()《》【】\-—,.!?;:]", "", text)


def char_f1(prediction: str, reference: str) -> float:
    pred = normalize_text(prediction)
    ref = normalize_text(reference)
    if not pred or not ref:
        return 0.0
    pred_counter = Counter(pred)
    ref_counter = Counter(ref)
    overlap = sum((pred_counter & ref_counter).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def exact_match(prediction: str, reference: str) -> bool:
    return normalize_text(prediction) == normalize_text(reference)


def choose_focus_phrase(heading: str, context: str) -> str:
    topic = re.sub(r"^第[一二三四五六七八九十百零〇]+[章节篇]\s*", "", heading).strip()
    topic = re.sub(r"^第[一二三四五六七八九十百零〇]+节\s*", "", topic).strip()
    topic = re.sub(r"^\d+(?:\.\d+){0,3}\s*", "", topic).strip("：:、.． ")
    if topic and not any(pattern.match(topic) for pattern in GENERIC_HEADING_PATTERNS) and len(topic) >= 4:
        return topic

    for sentence in split_sentences(context):
        phrase = sentence.split("，")[0].split("。")[0].strip()
        phrase = re.sub(r"^[一二三四五六七八九十]+、", "", phrase).strip()
        if 4 <= len(phrase) <= 20:
            return phrase
    return heading.strip()


def parse_sections(cache_path: Path) -> List[Section]:
    cache_data = load_ocr_cache(cache_path)
    content = cache_data.get("content", "")
    lines = merge_broken_heading_lines([normalize_line(line) for line in content.splitlines()])
    indexed_lines = [(index, line) for index, line in enumerate(lines) if line]

    headings: List[Tuple[int, str, str]] = []
    current_chapter = "未标注章节"
    for index, line in indexed_lines:
        if CHAPTER_PATTERN.match(line):
            current_chapter = line
            headings.append((index, line, current_chapter))
            continue
        if is_heading(line):
            headings.append((index, line, current_chapter))

    sections: List[Section] = []
    for position, (line_index, heading, chapter) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        chunk_lines = [line for line in lines[line_index + 1:next_index] if line]
        context = "\n".join(chunk_lines).strip()
        if len(context) < 80:
            continue
        topic = choose_focus_phrase(heading, context)
        sections.append(
            Section(
                section_id=f"sec_{len(sections) + 1:04d}",
                order=len(sections),
                chapter=chapter,
                heading=heading,
                topic=topic,
                context=context,
            )
        )
    return sections


def split_sections_by_chapter(sections: Sequence[Section]) -> Dict[str, List[Section]]:
    chapters: List[str] = []
    chapter_to_sections: Dict[str, List[Section]] = defaultdict(list)
    for section in sections:
        if section.chapter not in chapter_to_sections:
            chapters.append(section.chapter)
        chapter_to_sections[section.chapter].append(section)

    total_sections = len(sections)
    train_target = int(total_sections * 0.68)
    val_target = int(total_sections * 0.16)

    train_sections: List[Section] = []
    val_sections: List[Section] = []
    test_sections: List[Section] = []

    for chapter in chapters:
        bucket = chapter_to_sections[chapter]
        if len(train_sections) < train_target:
            train_sections.extend(bucket)
        elif len(val_sections) < val_target:
            val_sections.extend(bucket)
        else:
            test_sections.extend(bucket)

    return {"train": train_sections, "val": val_sections, "test": test_sections}


def section_sentences(section: Section) -> List[str]:
    return split_sentences(section.context)


def find_sentences(section: Section, keywords: Iterable[str], limit: int = 2, require_numeric: bool = False) -> List[str]:
    matched: List[str] = []
    for sentence in section_sentences(section):
        if require_numeric and not NUMERIC_PATTERN.search(sentence):
            continue
        if any(keyword in sentence for keyword in keywords):
            matched.append(sentence)
        if len(matched) >= limit:
            break
    return matched


def first_sentences(section: Section, limit: int = 2) -> List[str]:
    return section_sentences(section)[:limit]


def build_concept_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = first_sentences(section, limit=2)
    if not answer_sentences:
        return None
    question = f"{section.topic}的定义、内涵或主要内容是什么？"
    answer = truncate_text("".join(answer_sentences), 180)
    return make_candidate(section, "concept", question, answer, 4.0 + len(answer_sentences) * 0.5)


def build_threshold_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = find_sentences(section, ["温度", "压力", "范围", "安全距离", "限值", "浓度", "时间", "速度", "高度", "厚度", "数量", "不小于", "不应", "不得"], limit=2, require_numeric=True)
    if not answer_sentences:
        answer_sentences = [sentence for sentence in section_sentences(section) if NUMERIC_PATTERN.search(sentence)][:2]
    if not answer_sentences:
        return None
    question = f"{section.topic}涉及的关键条件、数值或范围要求是什么？"
    answer = truncate_text("".join(answer_sentences), 180)
    score = 6.0 + sum(1 for _ in NUMERIC_PATTERN.finditer(answer)) * 0.4
    return make_candidate(section, "threshold", question, answer, score)


def build_process_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = find_sentences(section, ["流程", "步骤", "程序", "工艺", "顺序", "组成", "环节", "包括", "先", "然后"], limit=3)
    if not answer_sentences:
        return None
    question = f"{section.topic}的主要流程、步骤或组成是什么？"
    answer = truncate_text("".join(answer_sentences), 200)
    score = 5.8 + 0.4 * len(answer_sentences)
    return make_candidate(section, "process", question, answer, score)


def build_risk_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = find_sentences(section, ["危险", "危害", "事故", "防范", "预防", "措施", "隐患", "安全", "控制", "防护"], limit=3)
    if not answer_sentences:
        return None
    if any(token in section.topic for token in ["危险", "危害", "事故", "防范", "安全", "防护", "措施"]):
        question = f"{section.topic}中需要重点关注的危险因素或防控措施有哪些？"
    else:
        question = f"围绕{section.topic}，需要重点关注哪些危险因素或安全措施？"
    answer = truncate_text("".join(answer_sentences), 200)
    score = 5.8 + 0.4 * len(answer_sentences)
    return make_candidate(section, "risk", question, answer, score)


def build_compare_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = find_sentences(section, ["分为", "不同", "区别", "相比", "各有", "优点", "缺点", "分别", "分类"], limit=3)
    if not answer_sentences:
        answer_sentences = find_sentences(section, ["包括", "组成", "类型", "主要", "可分", "以及"], limit=2)
    if not answer_sentences:
        sentences = first_sentences(section, limit=2)
        if len(sentences) >= 2:
            answer_sentences = sentences
    if not answer_sentences:
        return None
    answer_text = "".join(answer_sentences)
    if "分为" in answer_text or "可分" in answer_text or "类型" in answer_text:
        question = f"{section.topic}通常分为哪些类型？各类型的主要区别是什么？"
    elif any(token in answer_text for token in ["轻度", "中度", "重度"]):
        question = f"{section.topic}在不同严重程度下的处理要求有什么区别？"
    elif any(token in answer_text for token in ["上岗前", "在岗期间", "离岗时", "离岗后"]):
        question = f"针对{section.topic}，不同阶段的检查或管理要求有什么不同？"
    elif any(token in answer_text for token in ["优点", "缺点"]):
        question = f"{section.topic}与其他做法相比，各自的优缺点是什么？"
    elif any(token in answer_text for token in ["男性", "女性"]):
        question = f"{section.topic}对不同人群的判定标准有什么区别？"
    else:
        question = f"围绕{section.topic}，不同类型或情形下的要求分别是什么？"
    answer = truncate_text("".join(answer_sentences), 200)
    score = 6.6 + 0.4 * len(answer_sentences)
    return make_candidate(section, "compare", question, answer, score)


def build_scene_candidate(section: Section) -> Optional[Candidate]:
    answer_sentences = find_sentences(section, ["作业", "现场", "必须", "应当", "应", "严禁", "处理", "处置", "检查", "操作", "管理"], limit=3)
    if not answer_sentences and any(token in section.topic for token in ["安全", "作业", "管理", "防护", "措施", "事故"]):
        answer_sentences = first_sentences(section, limit=2)
    if not answer_sentences:
        return None
    answer_text = "".join(answer_sentences)
    if any(token in answer_text for token in ["应急", "抢救", "复苏", "送医", "救援"]):
        question = f"发生{section.topic}相关异常后，现场应如何开展应急处置？"
    elif any(token in answer_text for token in ["检查", "体格检查", "实验室", "复查"]):
        question = f"针对{section.topic}，现场或医学检查时应重点关注哪些项目？"
    elif any(token in answer_text for token in ["严禁", "禁止", "不得"]):
        question = f"在{section.topic}相关作业中，有哪些关键禁忌或必须避免的做法？"
    else:
        question = f"在{section.topic}相关作业场景下，操作人员应重点注意哪些措施？"
    answer = truncate_text("".join(answer_sentences), 200)
    score = 6.2 + 0.4 * len(answer_sentences)
    return make_candidate(section, "scene", question, answer, score)


def make_candidate(section: Section, question_type: str, question: str, answer: str, score: float) -> Optional[Candidate]:
    answer = answer.strip()
    question = question.strip()
    if len(normalize_question(question)) < 8 or len(answer) < 24:
        return None
    if "����" in question or "����" in answer:
        return None
    return Candidate(
        section=section,
        question_type=question_type,
        question=question,
        answer=answer,
        ground_truth=answer,
        context=[truncate_text(section.context, 500)],
        quality_score=score,
    )


def build_candidate(section: Section, question_type: str) -> Optional[Candidate]:
    builders = {
        "concept": build_concept_candidate,
        "threshold": build_threshold_candidate,
        "process": build_process_candidate,
        "risk": build_risk_candidate,
        "compare": build_compare_candidate,
        "scene": build_scene_candidate,
    }
    return builders[question_type](section)


def build_candidates_by_type(sections: Sequence[Section]) -> Dict[str, List[Candidate]]:
    candidates: Dict[str, List[Candidate]] = defaultdict(list)
    for section in sections:
        for question_type in QUESTION_TYPE_ORDER:
            candidate = build_candidate(section, question_type)
            if candidate is not None:
                candidates[question_type].append(candidate)
    for question_type in candidates:
        candidates[question_type].sort(key=lambda item: (-item.quality_score, item.section.order, item.question))
    return candidates


def select_split_items(sections: Sequence[Section], quotas: Dict[str, int], split_name: str) -> List[Dict[str, Any]]:
    candidates_by_type = build_candidates_by_type(sections)
    selected: List[Dict[str, Any]] = []
    used_questions = set()
    section_use_count: Counter[str] = Counter()
    max_uses_per_section = 2

    type_order = sorted(QUESTION_TYPE_ORDER, key=lambda name: len(candidates_by_type.get(name, [])))
    for question_type in type_order:
        required = quotas[question_type]
        picked = 0
        for candidate in candidates_by_type.get(question_type, []):
            normalized_question = normalize_question(candidate.question)
            if normalized_question in used_questions:
                continue
            if section_use_count[candidate.section.section_id] >= max_uses_per_section:
                continue
            selected.append(candidate_to_record(candidate, split_name, len(selected) + 1))
            used_questions.add(normalized_question)
            section_use_count[candidate.section.section_id] += 1
            picked += 1
            if picked >= required:
                break
        if picked < required:
            raise RuntimeError(f"{split_name} 的 {question_type} 只选出了 {picked} 条，未达到 {required} 条")

    if len(selected) != sum(quotas.values()):
        raise RuntimeError(f"{split_name} 总样本数异常: {len(selected)} vs {sum(quotas.values())}")
    return selected


def candidate_to_record(candidate: Candidate, split_name: str, index: int) -> Dict[str, Any]:
    return {
        "id": f"{split_name}_{index:04d}",
        "split": split_name,
        "question_type": TYPE_LABELS[candidate.question_type],
        "question_type_key": candidate.question_type,
        "question": candidate.question,
        "answer": candidate.answer,
        "ground_truth": candidate.ground_truth,
        "context": candidate.context,
        "source": "metallurgy",
        "chapter": candidate.section.chapter,
        "heading": candidate.section.heading,
        "topic": candidate.section.topic,
        "quality_score": round(candidate.quality_score, 2),
        "generation_method": "evidence_template_v2",
    }


def select_global_split_items(sections: Sequence[Section]) -> Dict[str, List[Dict[str, Any]]]:
    candidates_by_type = build_candidates_by_type(sections)
    split_records: Dict[str, List[Dict[str, Any]]] = {"train": [], "val": [], "test": []}
    used_questions = set()
    used_sections = set()

    for question_type in sorted(QUESTION_TYPE_ORDER, key=lambda name: len(candidates_by_type.get(name, []))):
        total_required = sum(TYPE_QUOTAS[split_name][question_type] for split_name in ("train", "val", "test"))
        chosen: List[Candidate] = []
        for candidate in candidates_by_type.get(question_type, []):
            normalized_question = normalize_question(candidate.question)
            if normalized_question in used_questions:
                continue
            if candidate.section.section_id in used_sections:
                continue
            chosen.append(candidate)
            used_questions.add(normalized_question)
            used_sections.add(candidate.section.section_id)
            if len(chosen) >= total_required:
                break
        if len(chosen) < total_required:
            raise RuntimeError(f"全局 {question_type} 只选出了 {len(chosen)} 条，未达到 {total_required} 条")

        offset = 0
        for split_name in ("train", "val", "test"):
            count = TYPE_QUOTAS[split_name][question_type]
            subset = chosen[offset:offset + count]
            offset += count
            for candidate in subset:
                split_records[split_name].append(candidate_to_record(candidate, split_name, len(split_records[split_name]) + 1))

    for split_name in ("train", "val", "test"):
        expected = sum(TYPE_QUOTAS[split_name].values())
        if len(split_records[split_name]) != expected:
            raise RuntimeError(f"{split_name} 总样本数异常: {len(split_records[split_name])} vs {expected}")
    return split_records


def build_reject_dataset(counts: Dict[str, int]) -> List[Dict[str, Any]]:
    templates = {
        "out_of_scope": [
            "锂电池热失控后应如何分级处置？",
            "核电站主冷却系统故障时的应急原则是什么？",
            "民航发动机失速时的标准处置流程是什么？",
            "深海钻井平台井喷后的隔离步骤有哪些？",
            "医院手术室麻醉废气排放标准是多少？",
            "数据中心液冷服务器泄漏后如何恢复业务？",
            "城市地铁信号系统失灵时如何组织行车？",
            "食品冷链运输的 HACCP 关键控制点有哪些？",
            "光伏逆变器并网故障的诊断流程是什么？",
            "生物实验室三级防护区的气压标准是多少？",
        ],
        "cross_domain": [
            "如何用 Python 实现快速排序？",
            "MySQL 索引失效的常见原因有哪些？",
            "Vue 3 中 watch 和 computed 有什么区别？",
            "卷积神经网络中残差连接的作用是什么？",
            "Docker 容器启动失败时应先看哪些日志？",
            "操作系统中的死锁预防策略有哪些？",
            "如何评估大模型的上下文窗口利用率？",
            "Transformer 中多头注意力的计算过程是什么？",
            "Redis 持久化机制 AOF 和 RDB 有何差异？",
            "在 Java 中如何实现线程池拒绝策略？",
        ],
        "ambiguous": [
            "这个情况下应该怎么办？",
            "这种风险一般大不大？",
            "平时这样操作可以吗？",
            "如果出了问题要不要停？",
            "这个参数到底高还是低？",
            "遇到异常时先看哪里？",
            "这种做法是不是最安全？",
            "这个流程是不是都一样？",
            "如果现场很复杂该怎么处理？",
            "这个标准是不是必须执行？",
        ],
        "unsupported_detail": [
            "《冶金安全生产技术》这本书的作者写作动机是什么？",
            "教材中没有展开讨论的最新欧盟冶金安全法规是什么？",
            "书中涉及企业的 2025 年事故率同比变化是多少？",
            "某钢厂 3 号高炉去年检修预算具体是多少？",
            "作者为什么在这一章选择了这种图表排版方式？",
            "教材未给出的某设备厂家推荐采购型号是什么？",
            "某章节引用标准在 2026 年修订后的条款编号是什么？",
            "这本书每章的写作团队分工明细是什么？",
            "书中案例对应企业的真实地理坐标在哪里？",
            "教材提到的事故中受伤人数精确到个位是多少？",
        ],
    }

    records: List[Dict[str, Any]] = []
    index = 1
    for reject_type, count in counts.items():
        for question in templates[reject_type][:count]:
            records.append(
                {
                    "id": f"reject_{index:04d}",
                    "split": "reject",
                    "question_type": TYPE_LABELS["reject"],
                    "question_type_key": "reject",
                    "reject_type": reject_type,
                    "question": question,
                    "answer": REJECT_ANSWER,
                    "ground_truth": REJECT_ANSWER,
                    "context": [],
                    "source": "metallurgy",
                    "chapter": "N/A",
                    "heading": "N/A",
                    "topic": reject_type,
                    "quality_score": 10.0,
                    "generation_method": "reject_template_v1",
                }
            )
            index += 1
    return records


def build_dataset_suite(cache_path: Path, output_dir: Path) -> Dict[str, Any]:
    sections = parse_sections(cache_path)
    split_sections = split_sections_by_chapter(sections)

    datasets = select_global_split_items(sections)
    datasets["reject"] = build_reject_dataset(REJECT_COUNTS)

    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, items in datasets.items():
        save_json(output_dir / f"metallurgy_{split_name}.json", items)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_cache": str(cache_path),
        "section_count": len(sections),
        "chapter_split_section_counts": {name: len(value) for name, value in split_sections.items()},
        "selection_strategy": "global-by-type-then-split",
        "dataset_counts": {name: len(items) for name, items in datasets.items()},
        "positive_split_counts": POSITIVE_SPLIT_COUNTS,
        "reject_counts": REJECT_COUNTS,
        "question_type_quotas": TYPE_QUOTAS,
        "schema": [
            "id",
            "split",
            "question_type",
            "question_type_key",
            "question",
            "answer",
            "ground_truth",
            "context",
            "source",
            "chapter",
            "heading",
            "topic",
            "quality_score",
            "generation_method",
        ],
        "note": "train/val/test are built by global type selection with non-overlapping source sections. reject set is intentionally unsupported.",
    }
    save_json(output_dir / "metallurgy_dataset_suite.summary.json", summary)
    export_dataset_suite_to_paper_bundle(datasets, summary)
    return summary


def get_llm_client(conf: Config) -> OpenAI:
    return OpenAI(api_key=conf.DASHSCOPE_API_KEY, base_url=conf.DASHSCOPE_BASE_URL)


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def call_llm_json(client: OpenAI, model: str, prompt: str) -> Dict[str, str]:
    completion = client.chat.completions.create(
        model=model,
        temperature=0.5,
        messages=[
            {"role": "system", "content": "你是构建教材问答数据集的助手，只输出 JSON 对象。"},
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content if completion.choices else "{}"
    payload = strip_code_fence(content)
    return json.loads(payload)


def build_weak_baseline_item(section: Section) -> Optional[Dict[str, Any]]:
    sentences = first_sentences(section, limit=2)
    if not sentences:
        return None
    answer = truncate_text("".join(sentences), 180)
    return {
        "question": f"{section.heading}的主要内容是什么？",
        "answer": answer,
        "ground_truth": answer,
        "context": [truncate_text(section.context, 500)],
        "question_type": "weak_heading",
        "chapter": section.chapter,
        "heading": section.heading,
        "topic": section.topic,
    }


def build_evidence_best_item(section: Section) -> Optional[Dict[str, Any]]:
    candidates = [candidate for question_type in QUESTION_TYPE_ORDER if (candidate := build_candidate(section, question_type))]
    if not candidates:
        return None
    best = sorted(candidates, key=lambda item: (-item.quality_score, item.question_type))[0]
    return {
        "question": best.question,
        "answer": best.answer,
        "ground_truth": best.ground_truth,
        "context": best.context,
        "question_type": best.question_type,
        "chapter": section.chapter,
        "heading": section.heading,
        "topic": section.topic,
        "quality_score": round(best.quality_score, 2),
    }


def llm_generate_free_item(client: OpenAI, model: str, section: Section) -> Optional[Dict[str, Any]]:
    prompt = (
        "请基于下面教材片段，自由生成 1 条自然中文问答对。\n"
        "要求：\n"
        "1. 问题像真实用户提问，不要照抄标题。\n"
        "2. 答案可以概括整理，不要求逐字摘录。\n"
        "3. 输出 JSON，字段为 question 和 answer。\n"
        f"章节标题：{section.heading}\n"
        f"证据片段：{truncate_text(section.context, 420)}"
    )
    try:
        data = call_llm_json(client, model, prompt)
    except Exception:
        return None
    question = str(data.get("question", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if len(normalize_question(question)) < 8 or len(answer) < 18:
        return None
    return {
        "question": question,
        "answer": truncate_text(answer, 180),
        "ground_truth": truncate_text(answer, 180),
        "context": [truncate_text(section.context, 500)],
        "question_type": "free_generation",
        "chapter": section.chapter,
        "heading": section.heading,
        "topic": section.topic,
    }


def auto_screen_items(items: Sequence[Dict[str, Any]], sample_size: int) -> List[Dict[str, Any]]:
    def passes(item: Dict[str, Any], min_overlap: float, strict_question_len: bool) -> bool:
        question = normalize_question(item["question"])
        answer = item["answer"]
        context_text = " ".join(item.get("context", []))
        min_question_len = 10 if strict_question_len else 8
        max_question_len = 28 if strict_question_len else 32
        min_answer_len = 30 if strict_question_len else 20
        max_answer_len = 180 if strict_question_len else 220
        if len(question) < min_question_len or len(question) > max_question_len:
            return False
        if len(answer) < min_answer_len or len(answer) > max_answer_len:
            return False
        if char_f1(answer, context_text) < min_overlap:
            return False
        return True

    filtered: List[Dict[str, Any]] = []
    seen_questions = set()

    for min_overlap, strict_question_len in ((0.45, True), (0.30, False)):
        for item in items:
            question = normalize_question(item["question"])
            if question in seen_questions:
                continue
            if not passes(item, min_overlap=min_overlap, strict_question_len=strict_question_len):
                continue
            seen_questions.add(question)
            filtered.append(item)
            if len(filtered) >= sample_size:
                return filtered

    for item in items:
        question = normalize_question(item["question"])
        if question in seen_questions:
            continue
        seen_questions.add(question)
        filtered.append(item)
        if len(filtered) >= sample_size:
            break
    return filtered


def instantiate_rag(conf: Config):
    from core.new_rag_system import RAGSystem

    client = get_llm_client(conf)

    def call_model(prompt: str):
        completion = client.chat.completions.create(
            model=conf.LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个严谨的冶金安全问答助手。"},
                {"role": "user", "content": prompt},
            ],
        )
        return completion.choices[0].message.content if completion.choices else ""

    vector_store = VectorStore()
    return RAGSystem(vector_store, call_model)


def to_ragas_format(items: Sequence[Dict[str, Any]]) -> Dict[str, List[Any]]:
    return {
        "question": [item.get("question", "") for item in items],
        "answer": [item.get("answer", "") for item in items],
        "contexts": [item.get("context", []) for item in items],
        "ground_truth": [item.get("ground_truth", item.get("answer", "")) for item in items],
    }


def ensure_paper_bundle_dirs() -> None:
    for path in (RAGAS_PAPER_BUNDLE_DIR, RAGAS_PAPER_DATA_DIR, RAGAS_PAPER_RESULTS_DIR, RAGAS_PAPER_PLOTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def ensure_hypothetical_bundle_dirs() -> None:
    for path in (HYPOTHETICAL_BUNDLE_DIR, HYPOTHETICAL_RESULTS_DIR, HYPOTHETICAL_PLOTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def export_dataset_suite_to_paper_bundle(datasets: Dict[str, List[Dict[str, Any]]], summary: Dict[str, Any]) -> None:
    ensure_paper_bundle_dirs()
    for split_name, items in datasets.items():
        save_json(RAGAS_PAPER_DATA_DIR / f"metallurgy_{split_name}.json", items)
        if split_name in {"train", "val", "test"}:
            save_json(RAGAS_PAPER_DATA_DIR / f"metallurgy_{split_name}.ragas.json", to_ragas_format(items))
    save_json(RAGAS_PAPER_DATA_DIR / "metallurgy_dataset_suite.summary.json", summary)


def export_method_datasets_to_paper_bundle(method_datasets: Dict[str, List[Dict[str, Any]]], summary: Dict[str, Any]) -> None:
    ensure_paper_bundle_dirs()
    for method, items in method_datasets.items():
        save_json(RAGAS_PAPER_RESULTS_DIR / f"{method}_dataset.json", items)
        save_json(RAGAS_PAPER_RESULTS_DIR / f"{method}_dataset.ragas.json", to_ragas_format(items))
    save_json(RAGAS_PAPER_RESULTS_DIR / "experiment_summary.json", summary)


def plot_heatmap(results: Dict[str, Any], output_path: Path, title: str = "Method Quality Heatmap") -> None:
    methods = list(results["methods"].keys())
    metric_keys = ["evidence_locatable_rate", "hallucination_rate", "test_f1", "duplicate_rate"]
    metric_labels = ["Evidence", "Low Hallucination", "F1", "Low Duplication"]
    raw = np.array([[results["methods"][m][k] for k in metric_keys] for m in methods], dtype=float)
    display = raw.copy()
    display[:, 1] = 1.0 - display[:, 1]
    display[:, 3] = 1.0 - display[:, 3]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    im = ax.imshow(display, cmap="YlOrRd", aspect="auto", vmin=0.0, vmax=max(0.1, float(display.max())))
    ax.set_xticks(np.arange(len(metric_labels)), labels=metric_labels)
    ax.set_yticks(np.arange(len(methods)), labels=methods)
    ax.set_title(title, fontsize=15, fontweight="bold")
    for i in range(display.shape[0]):
        for j in range(display.shape[1]):
            ax.text(j, i, f"{raw[i, j]:.3f}", ha="center", va="center", color="#1f1f1f", fontsize=10, fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Normalized Score", rotation=90)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_radar(results: Dict[str, Any], output_path: Path, title: str = "Method Comparison Radar") -> None:
    methods = list(results["methods"].keys())
    labels = ["Evidence", "Low Hallucination", "F1", "Low Duplication"]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]

    fig = plt.figure(figsize=(8, 6))
    ax = plt.subplot(111, polar=True)
    palette = ["#0b7285", "#e8590c", "#2b8a3e", "#9c36b5"]
    for color, method in zip(palette, methods):
        metrics = results["methods"][method]
        values = [
            metrics["evidence_locatable_rate"],
            1.0 - metrics["hallucination_rate"],
            metrics["test_f1"],
            1.0 - metrics["duplicate_rate"],
        ]
        values += values[:1]
        ax.plot(angles, values, linewidth=2.2, label=method, color=color)
        ax.fill(angles, values, alpha=0.12, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=18)
    ax.legend(loc="upper right", bbox_to_anchor=(1.22, 1.12))
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_dual_axis(results: Dict[str, Any], output_path: Path, title: str = "Evidence vs Hallucination with F1 Overlay") -> None:
    methods = list(results["methods"].keys())
    evidence = [results["methods"][m]["evidence_locatable_rate"] for m in methods]
    hallucination = [results["methods"][m]["hallucination_rate"] for m in methods]
    f1_scores = [results["methods"][m]["test_f1"] for m in methods]
    x = np.arange(len(methods))
    width = 0.34

    fig, ax1 = plt.subplots(figsize=(9, 5.2))
    ax1.bar(x - width / 2, evidence, width, label="Evidence Rate", color="#1971c2")
    ax1.bar(x + width / 2, hallucination, width, label="Hallucination Rate", color="#f03e3e")
    ax1.set_xticks(x, methods)
    ax1.set_ylim(0, 1)
    ax1.set_ylabel("Rate")
    ax1.set_title(title, fontsize=15, fontweight="bold")

    ax2 = ax1.twinx()
    ax2.plot(x, f1_scores, color="#2b8a3e", marker="o", linewidth=2.5, label="F1")
    ax2.set_ylim(0, max(0.1, max(f1_scores) * 1.4))
    ax2.set_ylabel("F1")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_experiment_plots(results: Dict[str, Any]) -> Dict[str, str]:
    ensure_paper_bundle_dirs()
    heatmap_path = RAGAS_PAPER_PLOTS_DIR / "method_heatmap.png"
    radar_path = RAGAS_PAPER_PLOTS_DIR / "method_radar.png"
    dual_axis_path = RAGAS_PAPER_PLOTS_DIR / "method_dual_axis.png"
    plot_heatmap(results, heatmap_path)
    plot_radar(results, radar_path)
    plot_dual_axis(results, dual_axis_path)
    return {
        "heatmap": str(heatmap_path),
        "radar": str(radar_path),
        "dual_axis": str(dual_axis_path),
    }


def build_hypothetical_experiment_summary(sample_size: int) -> Dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sample_size_requested": sample_size,
        "model": "illustrative-only",
        "is_hypothetical": True,
        "label": "Hypothetical / Expected Outcome / Illustrative Only",
        "methods": {
            "M1": {
                "sample_count": sample_size,
                "duplicate_rate": 0.18,
                "evidence_locatable_rate": 0.42,
                "hallucination_rate": 0.30,
                "test_em_rate": 0.08,
                "test_f1": 0.34,
            },
            "M2": {
                "sample_count": sample_size,
                "duplicate_rate": 0.08,
                "evidence_locatable_rate": 0.58,
                "hallucination_rate": 0.18,
                "test_em_rate": 0.16,
                "test_f1": 0.49,
            },
            "M3": {
                "sample_count": sample_size,
                "duplicate_rate": 0.04,
                "evidence_locatable_rate": 0.76,
                "hallucination_rate": 0.10,
                "test_em_rate": 0.26,
                "test_f1": 0.67,
            },
            "M4": {
                "sample_count": sample_size,
                "duplicate_rate": 0.02,
                "evidence_locatable_rate": 0.83,
                "hallucination_rate": 0.06,
                "test_em_rate": 0.31,
                "test_f1": 0.74,
            },
        },
        "notes": [
            "This file is hypothetical and intended only for presentation, thesis design discussion, or advisor communication.",
            "These values are not measured from a live run and must not be presented as real experimental evidence.",
            "Expected trend: evidence-constrained generation and screened datasets outperform weak or free-generation baselines.",
        ],
    }


def render_hypothetical_plots(results: Dict[str, Any]) -> Dict[str, str]:
    ensure_hypothetical_bundle_dirs()
    heatmap_path = HYPOTHETICAL_PLOTS_DIR / "hypothetical_method_heatmap.png"
    radar_path = HYPOTHETICAL_PLOTS_DIR / "hypothetical_method_radar.png"
    dual_axis_path = HYPOTHETICAL_PLOTS_DIR / "hypothetical_method_dual_axis.png"
    plot_heatmap(results, heatmap_path, title="Hypothetical Method Quality Heatmap")
    plot_radar(results, radar_path, title="Hypothetical Method Comparison Radar")
    plot_dual_axis(results, dual_axis_path, title="Hypothetical Evidence vs Hallucination with F1")
    return {
        "heatmap": str(heatmap_path),
        "radar": str(radar_path),
        "dual_axis": str(dual_axis_path),
    }


def generate_hypothetical_bundle(sample_size: int) -> Dict[str, Any]:
    ensure_hypothetical_bundle_dirs()
    summary = build_hypothetical_experiment_summary(sample_size)
    summary["plot_paths"] = render_hypothetical_plots(summary)
    save_json(HYPOTHETICAL_RESULTS_DIR / "hypothetical_experiment_summary.json", summary)
    return summary


def duplicate_rate(items: Sequence[Dict[str, Any]]) -> float:
    normalized = [normalize_question(item["question"]) for item in items]
    return 0.0 if not normalized else 1.0 - len(set(normalized)) / len(normalized)


def evidence_locatable_rate(items: Sequence[Dict[str, Any]], vector_store: VectorStore) -> float:
    located = 0
    for item in items:
        try:
            hits = vector_store._hybrid_search_raw(item["question"], k=3, source_filter="metallurgy")
        except Exception:
            hits = []
        combined = " ".join((hit.get("entity", {}) or {}).get("text", "") for hit in hits)
        score = char_f1(item["ground_truth"], combined)
        if score >= 0.35 or normalize_text(item["ground_truth"]) in normalize_text(combined):
            located += 1
    return located / len(items) if items else 0.0


def hallucination_rate(items: Sequence[Dict[str, Any]]) -> float:
    hallucinated = 0
    for item in items:
        context_text = " ".join(item.get("context", []))
        if char_f1(item["answer"], context_text) < 0.35 and normalize_text(item["answer"]) not in normalize_text(context_text):
            hallucinated += 1
    return hallucinated / len(items) if items else 0.0


def evaluate_with_rag(items: Sequence[Dict[str, Any]], rag_system: RAGSystem) -> Dict[str, Any]:
    per_item = []
    total_f1 = 0.0
    em_hits = 0
    for item in items:
        try:
            prediction = rag_system.generate_answer(item["question"], source_filter="metallurgy", use_history=False)
        except Exception as exc:
            prediction = f"ERROR: {exc}"
        if not isinstance(prediction, str):
            if isinstance(prediction, (dict, list, tuple)):
                prediction = json.dumps(prediction, ensure_ascii=False)
            elif hasattr(prediction, "__iter__"):
                prediction = "".join(str(part) for part in prediction)
            else:
                prediction = str(prediction)
        f1 = char_f1(prediction, item["ground_truth"])
        em = exact_match(prediction, item["ground_truth"])
        total_f1 += f1
        em_hits += int(em)
        per_item.append(
            {
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "prediction": prediction,
                "f1": round(f1, 4),
                "em": em,
            }
        )
    count = len(items)
    return {
        "avg_f1": round(total_f1 / count, 4) if count else 0.0,
        "em_rate": round(em_hits / count, 4) if count else 0.0,
        "per_item": per_item,
    }


def choose_experiment_sections(sections: Sequence[Section], sample_size: int) -> List[Section]:
    rng = random.Random(RANDOM_SEED)
    ranked_sections = sorted(sections, key=lambda item: item.order)
    if len(ranked_sections) <= sample_size:
        return ranked_sections
    sample_pool_size = min(len(ranked_sections), max(sample_size * 2, sample_size + 10))
    sampled = rng.sample(ranked_sections, sample_pool_size)
    sampled.sort(key=lambda item: item.order)
    return sampled[:sample_pool_size]


def build_method_datasets(cache_path: Path, output_dir: Path, sample_size: int, model: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    conf = Config()
    model_name = model or conf.LLM_MODEL
    sections = parse_sections(cache_path)
    split_sections = split_sections_by_chapter(sections)
    held_out_pool = list(split_sections["val"]) + list(split_sections["test"])
    held_out_sections = choose_experiment_sections(held_out_pool, sample_size)
    print(f"[experiment] sampled {len(held_out_sections)} held-out sections for method datasets", flush=True)

    weak_items = [item for section in held_out_sections if (item := build_weak_baseline_item(section))]
    evidence_items = [item for section in held_out_sections if (item := build_evidence_best_item(section))]
    print(f"[experiment] built weak={len(weak_items)} evidence={len(evidence_items)} candidates", flush=True)

    client = get_llm_client(conf)
    free_items: List[Dict[str, Any]] = []
    for index, section in enumerate(held_out_sections, start=1):
        item = llm_generate_free_item(client, model_name, section)
        if item:
            free_items.append(item)
        if index % 5 == 0 or len(free_items) >= sample_size:
            print(
                f"[experiment] free-generation progress sections={index}/{len(held_out_sections)} valid_items={len(free_items)}",
                flush=True,
            )
        if len(free_items) >= sample_size:
            break
    print(f"[experiment] built free-generation items={len(free_items)}", flush=True)
    screened_items = auto_screen_items(evidence_items, sample_size)
    print(f"[experiment] built screened items={len(screened_items)}", flush=True)

    method_datasets = {
        "M1": weak_items[:sample_size],
        "M2": free_items[:sample_size],
        "M3": evidence_items[:sample_size],
        "M4": screened_items[:sample_size],
    }

    for method, items in method_datasets.items():
        if len(items) < sample_size and method != "M4":
            raise RuntimeError(f"{method} 只生成了 {len(items)} 条实验样本，未达到 {sample_size} 条")
    if len(method_datasets["M4"]) < sample_size:
        raise RuntimeError(f"M4 预筛样本不足，只有 {len(method_datasets['M4'])} 条")

    output_dir.mkdir(parents=True, exist_ok=True)
    for method, items in method_datasets.items():
        save_json(output_dir / f"{method}_dataset.json", items)
    return method_datasets


def run_experiments(cache_path: Path, output_dir: Path, sample_size: int, model: Optional[str] = None) -> Dict[str, Any]:
    conf = Config()
    method_datasets = build_method_datasets(cache_path, output_dir, sample_size, model=model)
    vector_store = VectorStore()
    rag_system = instantiate_rag(conf)

    results: Dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ocr_cache": str(cache_path),
        "sample_size_requested": sample_size,
        "model": model or conf.LLM_MODEL,
        "methods": {},
        "notes": [
            "M4 is an auto-screened proxy set; it is not a substitute for true manual screening.",
            "EM/F1 are computed by running the current RAG system and comparing predictions with each method's reference answer.",
        ],
    }

    for method, items in method_datasets.items():
        print(f"[experiment] evaluating {method} with {len(items)} samples...", flush=True)
        rag_eval = evaluate_with_rag(items, rag_system)
        metrics = {
            "sample_count": len(items),
            "duplicate_rate": round(duplicate_rate(items), 4),
            "evidence_locatable_rate": round(evidence_locatable_rate(items, vector_store), 4),
            "hallucination_rate": round(hallucination_rate(items), 4),
            "test_em_rate": rag_eval["em_rate"],
            "test_f1": rag_eval["avg_f1"],
        }
        save_json(output_dir / f"{method}_rag_eval.json", rag_eval)
        results["methods"][method] = metrics

    save_json(output_dir / "experiment_summary.json", results)
    export_method_datasets_to_paper_bundle(method_datasets, results)
    results["plot_paths"] = render_experiment_plots(results)
    save_json(output_dir / "experiment_summary.json", results)
    save_json(RAGAS_PAPER_RESULTS_DIR / "experiment_summary.json", results)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build metallurgy dataset splits and run comparison experiments")
    parser.add_argument("command", choices=["build-suite", "run-experiments", "generate-hypothetical-plots"])
    parser.add_argument("--ocr-cache", default=str(DEFAULT_OCR_CACHE))
    parser.add_argument("--dataset-output-dir", default=str(DATASET_OUTPUT_DIR))
    parser.add_argument("--experiment-output-dir", default=str(EXPERIMENT_OUTPUT_DIR))
    parser.add_argument("--sample-size", type=int, default=10, help="per-method experiment sample size")
    parser.add_argument("--model", default=None, help="override generation/evaluation model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cache_path = Path(args.ocr_cache)
    if not cache_path.exists():
        raise FileNotFoundError(f"OCR 缓存不存在: {cache_path}")

    if args.command == "build-suite":
        summary = build_dataset_suite(cache_path, Path(args.dataset_output_dir))
    elif args.command == "generate-hypothetical-plots":
        summary = generate_hypothetical_bundle(args.sample_size)
    else:
        summary = run_experiments(cache_path, Path(args.experiment_output_dir), args.sample_size, model=args.model)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()