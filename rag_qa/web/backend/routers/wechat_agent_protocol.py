from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

MULTI_AGENT_PROTOCOL_VERSION = "v1"
KNOWLEDGE_ORCHESTRATOR_NAME = "knowledge_orchestrator"
KNOWLEDGE_ACQUISITION_AGENT = "knowledge_acquisition_agent"
KNOWLEDGE_GOVERNANCE_AGENT = "knowledge_governance_agent"
EVALUATION_OPTIMIZATION_AGENT = "evaluation_optimization_agent"

AGENT_PROTOCOL_SPEC: Dict[str, Any] = {
    "version": MULTI_AGENT_PROTOCOL_VERSION,
    "orchestrator": KNOWLEDGE_ORCHESTRATOR_NAME,
    "agents": [
        {
            "agent_id": KNOWLEDGE_ACQUISITION_AGENT,
            "title": "知识采集 Agent",
            "kicker": "Agent 01",
            "default_summary": "负责账号观察、入口决策、抓取与清洗触发。",
            "summary_templates": {
                "idle": "尚未接收到新的公众号指令。",
                "preparing": "正在做入口判断，当前意图 {parsed_intent}。",
                "failed": "采集阶段执行失败。",
                "completed": "已处理 {processed} 条链接，新增 {created} 篇文章。",
                "no_new": "当前轮次已执行采集，但没有新增文章进入后续阶段。",
                "decision_ready": "当前意图 {parsed_intent}，等待进入执行阶段。",
                "clean_skipped_detail": "这一轮没有形成新的清洗目标。",
            },
            "metric_templates": {
                "source": "解析源：{value}",
                "decision": "决策：{value}",
                "processed": "处理 {value} 条",
                "duplicate": "重复 {value} 条",
                "intent": "意图：{value}",
            },
        },
        {
            "agent_id": KNOWLEDGE_GOVERNANCE_AGENT,
            "title": "知识治理 Agent",
            "kicker": "Agent 02",
            "default_summary": "负责对已形成的知识资产做重复、元数据与内容质量治理。",
            "summary_templates": {
                "idle": "只有在采集阶段形成新的知识资产后，才会继续进入治理。",
                "failed": "治理阶段执行失败。",
                "completed": "治理阶段已完成。",
                "no_input": "采集阶段没有形成新的清洗目标，所以治理没有拿到输入。",
                "waiting": "当前轮次还没有进入治理阶段。",
            },
            "metric_templates": {
                "risk_level": "风险：{value}",
            },
        },
        {
            "agent_id": EVALUATION_OPTIMIZATION_AGENT,
            "title": "评测优化 Agent",
            "kicker": "Agent 03",
            "default_summary": "负责汇总质量、覆盖率与 RAGAS 指标，并给出优化建议。",
            "summary_templates": {
                "idle": "评测 Agent 会在治理或编排确认后再汇总质量指标。",
                "failed": "评测阶段执行失败。",
                "completed": "评测阶段已完成。",
                "upstream_blocked": "清洗或治理阶段没有稳定完成，评测阶段因此没有继续。",
                "waiting": "当前轮次还没有进入评测阶段。",
            },
            "metric_templates": {
                "ragas_average": "RAGAS {value}",
                "sample_count": "样本 {value}",
                "readiness": "就绪度：{value}",
                "snapshot": "快照：{value}",
            },
        },
    ],
    "handoff_templates": [
        {
            "handoff_id": "collect-to-governance",
            "from_agent": KNOWLEDGE_ACQUISITION_AGENT,
            "to_agent": KNOWLEDGE_GOVERNANCE_AGENT,
            "title": "采集 Agent -> 治理 Agent",
            "handoff_reason": "new_knowledge_created",
            "required_inputs": ["created_articles", "clean_result", "shared_context"],
            "input_rules": [
                {
                    "input": "created_articles",
                    "artifact_types_any": ["article_record", "cleaning_result"],
                },
                {
                    "input": "clean_result",
                    "artifact_types_any": ["article_record", "cleaning_result"],
                },
                {
                    "input": "shared_context",
                    "always": True,
                },
            ],
            "blocking": True,
            "deadline_sec": 600,
            "fallback_summary": "只有采集阶段形成新文章记录或清洗结果后，这一跳才应该被创建。",
        },
        {
            "handoff_id": "governance-to-evaluation",
            "from_agent": KNOWLEDGE_GOVERNANCE_AGENT,
            "to_agent": EVALUATION_OPTIMIZATION_AGENT,
            "title": "治理 Agent -> 评测 Agent",
            "handoff_reason": "governance_report_ready",
            "required_inputs": ["governance_report", "shared_context"],
            "input_rules": [
                {
                    "input": "governance_report",
                    "artifact_types_any": ["governance_report"],
                },
                {
                    "input": "shared_context",
                    "always": True,
                },
            ],
            "blocking": True,
            "deadline_sec": 900,
            "fallback_summary": "只有治理阶段产出治理报告后，评测 Agent 才应该被触发。",
        },
    ],
}


def clone_agent_protocol_spec() -> Dict[str, Any]:
    return deepcopy(AGENT_PROTOCOL_SPEC)


def get_protocol_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    normalized = str(agent_id or "").strip()
    for item in AGENT_PROTOCOL_SPEC["agents"]:
        if str(item.get("agent_id") or "").strip() == normalized:
            return deepcopy(item)
    return None


def get_protocol_handoff_template(from_agent: str, to_agent: str) -> Optional[Dict[str, Any]]:
    normalized_from = str(from_agent or "").strip()
    normalized_to = str(to_agent or "").strip()
    for item in AGENT_PROTOCOL_SPEC["handoff_templates"]:
        if str(item.get("from_agent") or "").strip() == normalized_from and str(item.get("to_agent") or "").strip() == normalized_to:
            return deepcopy(item)
    return None


def build_protocol_handoff(from_agent: str, to_agent: str, **overrides: Any) -> Dict[str, Any]:
    template = get_protocol_handoff_template(from_agent, to_agent) or {
        "handoff_id": f"{from_agent}-to-{to_agent}",
        "from_agent": str(from_agent or "").strip(),
        "to_agent": str(to_agent or "").strip(),
        "title": f"{from_agent} -> {to_agent}",
        "handoff_reason": "",
        "required_inputs": [],
        "blocking": True,
        "deadline_sec": 0,
        "fallback_summary": "",
    }
    payload = deepcopy(template)
    payload.update(overrides)
    return payload