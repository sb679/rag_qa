# -*- coding: utf-8 -*-
"""Standalone WeChat image annotation routes.

This router only works with local article artifacts under data/wechat_collector/wechat_data
and does not depend on the RAG vector store.
"""
from __future__ import annotations

import json
import mimetypes
import hashlib
import logging
import os
import subprocess
import sys
import zipfile
import io
import re
import asyncio
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from uuid import uuid4

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
for p in (_rag_qa_path, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
import requests

from annotate_images_nl import apply_nl_annotations
from sync_image_annotations import sync_annotations
from core.auth_manager import get_auth_manager
from web.backend.routers.wechat_agent_protocol import (
    EVALUATION_OPTIMIZATION_AGENT,
    KNOWLEDGE_ACQUISITION_AGENT,
    KNOWLEDGE_GOVERNANCE_AGENT,
    KNOWLEDGE_ORCHESTRATOR_NAME,
    MULTI_AGENT_PROTOCOL_VERSION,
    build_protocol_handoff,
    clone_agent_protocol_spec,
)

router = APIRouter()
WECHAT_ROOT = Path(_rag_qa_path) / "data" / "wechat_collector" / "wechat_data"
DESKTOP_CAPTURE_ROOT = Path(_rag_qa_path) / "data" / "wechat_collector" / "desktop_capture"
DESKTOP_PROFILE_STORE = DESKTOP_CAPTURE_ROOT / "device_profiles.json"
DESKTOP_CAPTURE_SCRIPT = Path(_rag_qa_path) / "capture_wechat_desktop.py"
AGENT_TASK_ROOT = Path(_rag_qa_path) / "data" / "wechat_collector" / "agent_tasks"
EVALUATION_HISTORY_PATH = Path(_rag_qa_path) / "data" / "wechat_collector" / "evaluation_history.json"
AGENT_SESSION_STATE_ROOT = Path(_rag_qa_path) / "data" / "wechat_collector" / "agent_session_state"
logger = logging.getLogger(__name__)
auth_manager = get_auth_manager()
_AGENT_TASK_LOCK = threading.RLock()
_EVALUATION_HISTORY_LOCK = threading.RLock()
_AGENT_SESSION_STATE_LOCK = threading.RLock()
_AGENT_TASK_STATE_LOCK = threading.Lock()
_AGENT_TASK_QUEUE: "queue.Queue[str]" = queue.Queue()
_AGENT_TASK_QUEUED_IDS: Set[str] = set()
_AGENT_TASK_WORKER_THREAD: Optional[threading.Thread] = None

AGENT_BRAIN_SYSTEM_PROMPT = """你是微信公众号采集 Agent 的规划大脑。\n"
"你的职责不是直接执行，而是把用户指令翻译成一个严格受限的结构化计划。\n"
"你只能处理以下能力域：\n"
"1. 匹配/搜索本地公众号账号\n"
"2. 抓取公众号详情页或历史页\n"
"3. 决定是否需要桌面微信辅助采集\n"
"4. 清洗已抓取的公众号文章\n"
"5. 将清洗结果入库用于检索\n"
"6. 进入或继续公众号标注工作流\n"
"如果用户请求超出这些能力，例如闲聊、通用问答、写代码、总结别的任务、系统管理、RAG 问答等，必须明确判定为 unsupported。\n"
"输入里可能带有 session_memory，表示当前浏览器会话中最近一次账号、链接、文章标题、失败原因和决策。\n"
"当用户使用‘继续’、‘刚才那个’、‘上次那个账号’、‘那篇文章’这类省略表达时，你可以参考 session_memory 补全上下文；如果当前指令已经明确给出信息，优先使用当前指令。\n"
"请只返回 JSON，不要输出 Markdown。\n"
"JSON schema: {\n"
"  \"supported\": boolean,\n"
"  \"intent\": string,\n"
"  \"message\": string,\n"
"  \"do_collect\": boolean,\n"
"  \"do_clean\": boolean,\n"
"  \"do_ingest\": boolean,\n"
"  \"wants_login\": boolean,\n"
"  \"allow_desktop_fallback\": boolean,\n"
"  \"search_query\": string,\n"
"  \"article_title\": string,\n"
"  \"plan_steps\": string[],\n"
"  \"execution_plan\": [{\n"
"    \"name\": string,\n"
"    \"title\": string,\n"
"    \"enabled\": boolean,\n"
"    \"action\": string,\n"
"    \"retry_limit\": number,\n"
"    \"success_criteria\": string\n"
"  }]\n"
"}.\n"
"intent 只能取 collect, clean, ingest, collect_and_ingest, clean_and_ingest, search_account, desktop_collect, review, unsupported。\n"
"message 要简短解释你的判断，尤其在 unsupported 时要明确说明当前 agent 只支持公众号采集相关工作。\n"
"execution_plan 只能使用 observe, reason, collect, clean, ingest 五种步骤名。\n"
"如果你不确定结构化计划，可以只返回 plan_steps，执行层会自动补全默认计划。"""

MAX_AGENT_REPLAN_ATTEMPTS = 1
MAX_AGENT_TASK_HISTORY = 8
MAX_AGENT_ACCOUNT_HISTORY = 10
MAX_AGENT_TASK_EVENTS = 20
AGENT_TASK_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
EVALUATION_SNAPSHOT_DIRS = [
    Path(_rag_qa_path) / "teacher_demo_experiments" / "05_ragas_evaluation" / "artifacts" / "official_ragas_eval",
    Path(_rag_qa_path) / "ragas_paper_bundle" / "results",
]
EVALUATION_SNAPSHOT_PATTERNS = ["ragas_vs_legacy_*.json"]
MAX_EVALUATION_HISTORY = 200


def _coerce_ragas_metric(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return round(max(0.0, min(1.0, numeric)), 4)


def _normalize_evaluation_snapshot(payload: Dict[str, Any], source_path: Path) -> Optional[Dict[str, Any]]:
    metrics_payload = payload.get("official_ragas_metrics") if isinstance(payload.get("official_ragas_metrics"), dict) else {}
    metrics = {
        "faithfulness": _coerce_ragas_metric(metrics_payload.get("faithfulness")),
        "context_precision": _coerce_ragas_metric(metrics_payload.get("context_precision")),
        "context_recall": _coerce_ragas_metric(metrics_payload.get("context_recall")),
        "response_relevancy": _coerce_ragas_metric(metrics_payload.get("response_relevancy")),
        "factual_correctness": _coerce_ragas_metric(metrics_payload.get("factual_correctness")),
        "exact_match": _coerce_ragas_metric(metrics_payload.get("exact_match")),
    }
    metrics = {key: value for key, value in metrics.items() if value is not None}
    if not metrics:
        return None
    return {
        "source": "official_ragas_snapshot",
        "path": str(source_path),
        "file_name": source_path.name,
        "evaluated_at": str(payload.get("created_at") or "").strip(),
        "sample_count": max(0, int(payload.get("sample_count") or 0)),
        "dataset_path": str(payload.get("dataset_path") or "").strip(),
        "llm_model": str(payload.get("llm_model") or "").strip(),
        "metrics": metrics,
    }


def _load_evaluation_snapshot_from_path(snapshot_ref: str) -> Optional[Dict[str, Any]]:
    snapshot_path = Path(str(snapshot_ref or "").strip())
    if not snapshot_path.exists() or not snapshot_path.is_file():
        return None
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return _normalize_evaluation_snapshot(payload, snapshot_path)


def _discover_latest_evaluation_snapshot() -> Optional[Dict[str, Any]]:
    candidate_files: List[Path] = []
    for directory in EVALUATION_SNAPSHOT_DIRS:
        if not directory.exists():
            continue
        for pattern in EVALUATION_SNAPSHOT_PATTERNS:
            candidate_files.extend(path for path in directory.glob(pattern) if path.is_file())
    for snapshot_path in sorted(candidate_files, key=lambda item: item.stat().st_mtime, reverse=True):
        snapshot = _load_evaluation_snapshot_from_path(str(snapshot_path))
        if snapshot:
            return snapshot
    return None


def _resolve_evaluation_snapshot(snapshot_ref: str, shared_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    resolved_snapshot_ref = str(snapshot_ref or (shared_context.get("evaluation_snapshot_ref") if isinstance(shared_context, dict) else "") or "").strip()
    if resolved_snapshot_ref:
        return _load_evaluation_snapshot_from_path(resolved_snapshot_ref)
    return _discover_latest_evaluation_snapshot()


def _compute_ragas_average(snapshot: Optional[Dict[str, Any]]) -> Optional[float]:
    metrics = snapshot.get("metrics") if isinstance(snapshot, dict) else {}
    if not isinstance(metrics, dict):
        return None
    preferred_keys = ["faithfulness", "context_precision", "context_recall", "response_relevancy"]
    values = [float(metrics[key]) for key in preferred_keys if isinstance(metrics.get(key), (int, float))]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _require_request_user(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = authorization.replace("Bearer ", "", 1).strip()
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return payload


def _agent_session_state_path(user_id: str) -> Path:
    safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(user_id or "").strip()) or "anonymous"
    AGENT_SESSION_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    return AGENT_SESSION_STATE_ROOT / f"{safe_user_id}.json"


def _load_agent_session_state(user_id: str) -> Dict[str, Any]:
    path = _agent_session_state_path(user_id)
    if not path.exists():
        return {}
    with _AGENT_SESSION_STATE_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return payload if isinstance(payload, dict) else {}


def _write_agent_session_state(user_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(state) if isinstance(state, dict) else {}
    payload["updated_at"] = _agent_now_iso()
    path = _agent_session_state_path(user_id)
    with _AGENT_SESSION_STATE_LOCK:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _delete_agent_session_state(user_id: str) -> None:
    path = _agent_session_state_path(user_id)
    with _AGENT_SESSION_STATE_LOCK:
        if path.exists():
            path.unlink()


def _load_evaluation_history(limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 20), MAX_EVALUATION_HISTORY))
    with _EVALUATION_HISTORY_LOCK:
        if not EVALUATION_HISTORY_PATH.exists() or not EVALUATION_HISTORY_PATH.is_file():
            return []
        try:
            payload = json.loads(EVALUATION_HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    if not isinstance(payload, list):
        return []
    entries = [item for item in payload if isinstance(item, dict)]
    return entries[:safe_limit]


def _write_evaluation_history(entries: List[Dict[str, Any]]) -> None:
    EVALUATION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = [item for item in entries if isinstance(item, dict)][:MAX_EVALUATION_HISTORY]
    with _EVALUATION_HISTORY_LOCK:
        EVALUATION_HISTORY_PATH.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_evaluation_history(result: Dict[str, Any], payload: EvaluationOptimizationPayload) -> None:
    evaluation = result.get("evaluation") if isinstance(result.get("evaluation"), dict) else {}
    scope = result.get("scope") if isinstance(result.get("scope"), dict) else {}
    artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else {}
    metrics = artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
    snapshot_meta = metrics.get("evaluation_snapshot") if isinstance(metrics.get("evaluation_snapshot"), dict) else {}
    shared_context = payload.shared_context if isinstance(payload.shared_context, dict) else {}
    knowledge_scope = shared_context.get("knowledge_scope") if isinstance(shared_context.get("knowledge_scope"), dict) else {}
    article_ids = list(dict.fromkeys(str(item).strip() for item in (scope.get("article_ids") or knowledge_scope.get("article_ids") or payload.article_ids or []) if str(item).strip()))
    account_id = _normalize_account_id(scope.get("account_id") or payload.account_id or knowledge_scope.get("account_id") or "")
    recorded_at = _agent_now_iso()
    snapshot_label = " · ".join(
        item for item in [
            str(snapshot_meta.get("file_name") or "").strip(),
            str(snapshot_meta.get("evaluated_at") or "").strip(),
        ] if item
    )
    entry = {
        "history_id": f"eval_hist_{uuid4().hex[:10]}",
        "recorded_at": recorded_at,
        "account_id": account_id,
        "article_count": max(0, int(scope.get("article_count") or len(article_ids))),
        "article_ids": article_ids[:20],
        "quality_score": int(evaluation.get("quality_score") or 0),
        "coverage_score": int(evaluation.get("coverage_score") or 0),
        "readiness": str(evaluation.get("readiness") or "").strip(),
        "governance_risk_level": str(evaluation.get("governance_risk_level") or "").strip(),
        "ragas_average": _compute_ragas_average({"metrics": metrics.get("ragas_metrics") or {}}),
        "sample_count": max(0, int(snapshot_meta.get("sample_count") or 0)),
        "snapshot_label": snapshot_label,
        "snapshot_source": str(snapshot_meta.get("source") or "").strip(),
        "summary": str(artifact.get("summary") or "").strip(),
        "recommendation_count": max(0, int(metrics.get("recommendation_count") or 0)),
        "trigger_mode": "handoff" if payload.governance_report else "manual",
        "governance_report_metrics": {
            "risk_level": str((payload.governance_report or {}).get("report", {}).get("risk_level") or evaluation.get("governance_risk_level") or "").strip(),
            "duplicate_documents": int((payload.governance_report or {}).get("report", {}).get("duplicate_documents") or 0),
            "missing_metadata": int((payload.governance_report or {}).get("report", {}).get("missing_metadata") or 0),
            "content_quality_issues": int((payload.governance_report or {}).get("report", {}).get("content_quality_issues") or 0),
            "annotation_coverage_issues": int((payload.governance_report or {}).get("report", {}).get("annotation_coverage_issues") or 0),
        },
    }
    current = _load_evaluation_history(limit=MAX_EVALUATION_HISTORY)
    _write_evaluation_history([entry, *current])


def _find_evaluation_history_entry(history_id: str) -> Optional[Dict[str, Any]]:
    normalized = str(history_id or "").strip()
    if not normalized:
        return None
    for item in _load_evaluation_history(limit=MAX_EVALUATION_HISTORY):
        if str(item.get("history_id") or "").strip() == normalized:
            return item
    return None


def _build_evaluation_compare_payload(account_id: str = "") -> Dict[str, Any]:
    target_account_id = _normalize_account_id(account_id)
    entries = _load_evaluation_history(limit=MAX_EVALUATION_HISTORY)
    if target_account_id:
        entries = [item for item in entries if _normalize_account_id(item.get("account_id") or "") == target_account_id]
    latest = entries[0] if len(entries) > 0 else None
    previous = entries[1] if len(entries) > 1 else None
    if not latest:
        return {"latest": None, "previous": None, "delta": None}

    def _metric_delta(key: str) -> Optional[float]:
        if not previous:
            return None
        latest_value = latest.get(key)
        previous_value = previous.get(key)
        if not isinstance(latest_value, (int, float)) or not isinstance(previous_value, (int, float)):
            return None
        return round(float(latest_value) - float(previous_value), 4)

    return {
        "latest": latest,
        "previous": previous,
        "delta": {
            "quality_score": _metric_delta("quality_score"),
            "coverage_score": _metric_delta("coverage_score"),
            "ragas_average": _metric_delta("ragas_average"),
        },
    }


def _rerun_evaluation_from_history_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    governance_metrics = entry.get("governance_report_metrics") if isinstance(entry.get("governance_report_metrics"), dict) else {}
    article_ids = [str(item).strip() for item in (entry.get("article_ids") or []) if str(item).strip()]
    account_id = _normalize_account_id(entry.get("account_id") or "")
    article_count = max(0, int(entry.get("article_count") or len(article_ids)))
    payload = EvaluationOptimizationPayload(
        account_id=account_id,
        article_ids=article_ids,
        governance_report={
            "report": {
                "risk_level": str(governance_metrics.get("risk_level") or "unknown").strip() or "unknown",
                "duplicate_documents": int(governance_metrics.get("duplicate_documents") or 0),
                "missing_metadata": int(governance_metrics.get("missing_metadata") or 0),
                "content_quality_issues": int(governance_metrics.get("content_quality_issues") or 0),
                "annotation_coverage_issues": int(governance_metrics.get("annotation_coverage_issues") or 0),
            },
            "scope": {
                "article_count": article_count,
            },
        },
        shared_context={
            "knowledge_scope": {
                "account_id": account_id,
                "article_ids": article_ids,
            },
        },
    )
    return _run_evaluation_optimization_agent(payload)


def _ensure_agent_task_root() -> Path:
    AGENT_TASK_ROOT.mkdir(parents=True, exist_ok=True)
    return AGENT_TASK_ROOT


def _agent_task_file_path(task_id: str) -> Path:
    safe_task_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(task_id or "").strip())
    return _ensure_agent_task_root() / f"{safe_task_id}.json"


def _write_agent_task(task_payload: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(task_payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    payload = dict(task_payload)
    payload["task_id"] = task_id
    payload["updated_at"] = _agent_now_iso()
    events = payload.get("events") or []
    if isinstance(events, list):
        payload["events"] = events[-MAX_AGENT_TASK_EVENTS:]
    with _AGENT_TASK_LOCK:
        _agent_task_file_path(task_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _update_agent_task(task_id: str, updates: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _AGENT_TASK_LOCK:
        payload = _load_agent_task(task_id)
        if isinstance(updates, dict):
            payload.update(updates)
        if isinstance(event, dict):
            payload = _append_agent_task_event(
                payload,
                str(event.get("type") or "info"),
                str(event.get("message") or "").strip(),
                event.get("detail") if isinstance(event.get("detail"), dict) else None,
            )
        return _write_agent_task(payload)


def _load_agent_task(task_id: str) -> Dict[str, Any]:
    path = _agent_task_file_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="未找到对应的 Agent 任务")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent 任务文件损坏，无法读取") from exc


def _list_agent_tasks(limit: int = 20) -> List[Dict[str, Any]]:
    root = _ensure_agent_task_root()
    items: List[Dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    items.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return items[: max(1, int(limit or 20))]


def _append_agent_task_event(task_payload: Dict[str, Any], event_type: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(task_payload)
    events = list(payload.get("events") or [])
    events.append(
        {
            "type": str(event_type or "info").strip() or "info",
            "message": str(message or "").strip(),
            "detail": detail or {},
            "at": _agent_now_iso(),
        }
    )
    payload["events"] = events[-MAX_AGENT_TASK_EVENTS:]
    return payload


def _create_agent_ingest_task(parsed: Dict[str, Any], account_id: str, article_ids: List[str], clean_result: Dict[str, Any]) -> Dict[str, Any]:
    task_id = f"wechat_ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    payload = {
        "task_id": task_id,
        "task_type": "wechat_ingest_deferred",
        "status": "deferred",
        "created_at": _agent_now_iso(),
        "updated_at": _agent_now_iso(),
        "command": str(parsed.get("command") or "").strip(),
        "goal": "将公众号清洗结果写入检索链路",
        "account_id": str(account_id or "").strip(),
        "article_ids": [str(item).strip() for item in (article_ids or []) if str(item).strip()],
        "source": "wechat",
        "summary": "在线入库已延后，当前仅保留抓取与清洗结果。",
        "last_error": str(clean_result.get("ingest_error") or "").strip(),
        "ingest_exit_code": int(clean_result.get("ingest_exit_code") or 0),
        "result": {
            "cleaned_articles": int(clean_result.get("cleaned_articles") or 0),
            "generated_docs": int(clean_result.get("generated_docs") or 0),
            "ingest_enabled": bool(clean_result.get("ingest_enabled")),
            "ingest_deferred": bool(clean_result.get("ingest_deferred")),
        },
        "events": [],
    }
    payload = _append_agent_task_event(payload, "created", "已创建延后入库任务", {"article_ids": payload["article_ids"]})
    payload = _append_agent_task_event(payload, "deferred", payload["summary"], {"last_error": payload["last_error"], "exit_code": payload["ingest_exit_code"]})
    task = _write_agent_task(payload)
    _enqueue_agent_ingest_task(task.get("task_id") or "", reason="auto_enqueue_after_deferred_ingest")
    return _load_agent_task(task.get("task_id") or "")


def _build_wechat_clean_runner_code() -> str:
    return "\n".join([
        "import json, os, sys",
        "root = sys.argv[1]",
        "payload = json.loads(sys.argv[2])",
        "backend_dir = os.path.join(root, 'web', 'backend')",
        "for path in (root, backend_dir):",
        "    if path not in sys.path:",
        "        sys.path.insert(0, path)",
        "from run_wechat_cleaner import WeChatCleaningAgent",
        "from routers.wechat_annotator import _build_wechat_runtime_config",
        "cleaner = WeChatCleaningAgent(conf=_build_wechat_runtime_config(), source='wechat')",
        "result = cleaner.run(",
        "    account_id=payload.get('account_id') or None,",
        "    article_ids=list(payload.get('article_ids') or []),",
        "    ingest=bool(payload.get('ingest')),",
        "    dry_run=bool(payload.get('dry_run')),",
        "    batch_size=max(1, int(payload.get('batch_size', 300) or 300)),",
        ")",
        "print(json.dumps(result, ensure_ascii=False))",
    ])


def _run_wechat_clean_subprocess(account_id: str, article_ids: Optional[List[str]], ingest_enabled: bool, dry_run: bool, batch_size: int = 300, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    runner_payload = {
        "account_id": str(account_id or "").strip(),
        "article_ids": [str(item).strip() for item in (article_ids or []) if str(item).strip()],
        "dry_run": bool(dry_run),
        "batch_size": max(1, int(batch_size or 300)),
        "ingest": bool(ingest_enabled),
    }
    cmd = [
        sys.executable,
        "-c",
        _build_wechat_clean_runner_code(),
        str(Path(_rag_qa_path)),
        json.dumps(runner_payload, ensure_ascii=False),
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(_rag_qa_path)),
        timeout=timeout,
    )


def _run_agent_ingest_task(task_id: str) -> Dict[str, Any]:
    task = _update_agent_task(
        task_id,
        updates={"status": "running", "started_at": _agent_now_iso(), "summary": "后台正在串行执行延后入库任务。"},
        event={"type": "running", "message": "后台 worker 已接手该任务，开始串行入库。"},
    )
    account_id = str(task.get("account_id") or "").strip()
    article_ids = [str(item).strip() for item in (task.get("article_ids") or []) if str(item).strip()]
    try:
        result = _run_wechat_clean_subprocess(account_id, article_ids, True, False, batch_size=300, timeout=1800)
        stdout = str(result.stdout or "").strip()
        stderr = str(result.stderr or "").strip()
        if result.returncode != 0:
            detail = (stderr or stdout or "公众号后台入库失败")[:1000]
            return _update_agent_task(
                task_id,
                updates={
                    "status": "failed",
                    "finished_at": _agent_now_iso(),
                    "last_error": detail,
                    "ingest_exit_code": int(result.returncode),
                    "summary": "后台延后入库失败，请查看最近错误。",
                },
                event={"type": "failed", "message": "后台串行入库失败。", "detail": {"error": detail, "exit_code": int(result.returncode)}},
            )
        parsed_result = _extract_json_object_from_output(stdout)
        return _update_agent_task(
            task_id,
            updates={
                "status": "completed",
                "finished_at": _agent_now_iso(),
                "last_error": "",
                "summary": f"后台延后入库完成：文件 {int(parsed_result.get('ingested_files') or 0)} 个，切块 {int(parsed_result.get('ingested_chunks') or 0)} 个。",
                "result": {
                    **(task.get("result") or {}),
                    **parsed_result,
                    "ingest_deferred": False,
                },
            },
            event={
                "type": "completed",
                "message": "后台串行入库已完成。",
                "detail": {
                    "ingested_files": int(parsed_result.get("ingested_files") or 0),
                    "ingested_chunks": int(parsed_result.get("ingested_chunks") or 0),
                },
            },
        )
    except subprocess.TimeoutExpired:
        return _update_agent_task(
            task_id,
            updates={"status": "failed", "finished_at": _agent_now_iso(), "last_error": "公众号后台入库超时", "summary": "后台延后入库超时，请稍后重试。"},
            event={"type": "failed", "message": "后台串行入库超时。"},
        )
    except Exception as exc:
        return _update_agent_task(
            task_id,
            updates={"status": "failed", "finished_at": _agent_now_iso(), "last_error": str(exc)[:1000], "summary": "后台延后入库失败，请查看最近错误。"},
            event={"type": "failed", "message": "后台串行入库异常退出。", "detail": {"error": str(exc)[:1000]}},
        )


def _agent_task_worker_loop() -> None:
    while True:
        task_id = _AGENT_TASK_QUEUE.get()
        try:
            if str(task_id or "").strip():
                _run_agent_ingest_task(str(task_id).strip())
        except Exception:
            logger.exception("公众号 Agent 后台入库任务执行失败: %s", task_id)
        finally:
            with _AGENT_TASK_STATE_LOCK:
                _AGENT_TASK_QUEUED_IDS.discard(str(task_id or "").strip())
            _AGENT_TASK_QUEUE.task_done()


def ensure_agent_task_worker_started() -> None:
    global _AGENT_TASK_WORKER_THREAD
    with _AGENT_TASK_STATE_LOCK:
        if _AGENT_TASK_WORKER_THREAD and _AGENT_TASK_WORKER_THREAD.is_alive():
            return
        _AGENT_TASK_WORKER_THREAD = threading.Thread(target=_agent_task_worker_loop, name="wechat-agent-ingest-worker", daemon=True)
        _AGENT_TASK_WORKER_THREAD.start()
    _requeue_pending_agent_tasks()


def _enqueue_agent_ingest_task(task_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None
    ensure_agent_task_worker_started()
    task = _load_agent_task(normalized_task_id)
    if str(task.get("status") or "").strip() in AGENT_TASK_TERMINAL_STATUSES:
        return task
    with _AGENT_TASK_STATE_LOCK:
        if normalized_task_id in _AGENT_TASK_QUEUED_IDS:
            return task
        _AGENT_TASK_QUEUED_IDS.add(normalized_task_id)
    task = _update_agent_task(
        normalized_task_id,
        updates={"status": "queued", "summary": "已进入后台串行入库队列，等待 worker 执行。"},
        event={"type": "queued", "message": "任务已加入后台串行入库队列。", "detail": {"reason": str(reason or "manual_enqueue").strip() or "manual_enqueue"}},
    )
    _AGENT_TASK_QUEUE.put(normalized_task_id)
    return task


def _retry_agent_task(task_id: str) -> Dict[str, Any]:
    task = _load_agent_task(task_id)
    task_type = str(task.get("task_type") or "").strip()
    status = str(task.get("status") or "").strip()
    if task_type != "wechat_ingest_deferred":
        raise HTTPException(status_code=400, detail="当前只支持重试公众号延后入库任务")
    if status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="任务已经在执行或排队中，无需重复重试")
    if status == "completed":
        raise HTTPException(status_code=409, detail="任务已经完成，无需重试")

    retried_count = max(0, int(task.get("retried_count") or 0)) + 1
    retried_task = _update_agent_task(
        task_id,
        updates={
            "status": "deferred",
            "started_at": "",
            "finished_at": "",
            "last_error": "",
            "summary": "任务已手动重试，等待重新入队执行。",
            "retried_at": _agent_now_iso(),
            "retried_count": retried_count,
        },
        event={"type": "retry", "message": "任务已手动重试，准备重新入队。", "detail": {"retried_count": retried_count}},
    )
    enqueued = _enqueue_agent_ingest_task(task_id, reason="manual_retry")
    return enqueued or retried_task


def _requeue_pending_agent_tasks() -> None:
    for item in _list_agent_tasks(limit=200):
        status = str(item.get("status") or "").strip()
        task_type = str(item.get("task_type") or "").strip()
        task_id = str(item.get("task_id") or "").strip()
        if task_type != "wechat_ingest_deferred" or not task_id:
            continue
        if status in AGENT_TASK_TERMINAL_STATUSES:
            continue
        _enqueue_agent_ingest_task(task_id, reason="startup_requeue")


def _maybe_attach_agent_task(result: Dict[str, Any], parsed: Dict[str, Any], account_id: str, article_ids: List[str]) -> Optional[Dict[str, Any]]:
    clean_step = next((step for step in reversed(result.get("steps") or []) if str(step.get("name") or "") == "clean"), None)
    clean_result = (clean_step or {}).get("result") or {}
    if not isinstance(clean_result, dict) or not bool(clean_result.get("ingest_deferred")):
        return None
    task = _create_agent_ingest_task(parsed, account_id, article_ids, clean_result)
    clean_result["task_id"] = task.get("task_id")
    clean_result["task_status"] = task.get("status")
    clean_step["result"] = clean_result
    ingest_step = next((step for step in reversed(result.get("steps") or []) if str(step.get("name") or "") == "ingest"), None)
    if ingest_step and isinstance(ingest_step.get("result"), dict):
        ingest_step["result"]["task_id"] = task.get("task_id")
        ingest_step["result"]["task_status"] = task.get("status")
    result["task"] = task
    return task


def _agent_now_iso() -> str:
    return datetime.now().isoformat()


def _infer_multi_agent_task_type(capability_supported: bool, do_collect: bool, do_clean: bool, do_ingest: bool) -> str:
    if not capability_supported:
        return "capability_explanation"
    if do_collect or do_clean or do_ingest:
        return "acquire_knowledge"
    return "acquire_knowledge"


def _build_multi_agent_route(task_type: str) -> List[str]:
    if task_type == "acquire_knowledge":
        return [
            KNOWLEDGE_ACQUISITION_AGENT,
            KNOWLEDGE_GOVERNANCE_AGENT,
            EVALUATION_OPTIMIZATION_AGENT,
        ]
    return []


def _build_multi_agent_shared_context(parsed: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    session_memory = _normalize_agent_session_memory(parsed.get("session_memory") or {})
    return {
        "user_intent": str(parsed.get("intent_label") or "").strip(),
        "knowledge_scope": {
            "source_type": "wechat",
            "account_id": _normalize_account_id(account_id or parsed.get("account_id") or parsed.get("default_account_id") or ""),
            "article_urls": list(parsed.get("urls") or []),
            "search_query": str(parsed.get("search_query") or "").strip(),
            "article_title": str(parsed.get("article_title") or "").strip(),
        },
        "constraints": {
            "force": bool(parsed.get("force")),
            "auto_clean": bool(parsed.get("do_clean")),
            "auto_ingest": bool(parsed.get("do_ingest")),
            "dry_run": bool(parsed.get("dry_run")),
            "frequency_days": int(parsed.get("frequency_days") or 30),
            "window_days": int(parsed.get("window_days") or 365),
        },
        "memory_summary": {
            "recent_account_id": str(session_memory.get("recent_account_id") or "").strip(),
            "recent_display_name": str(session_memory.get("recent_display_name") or "").strip(),
            "recent_failure_reason": str(session_memory.get("recent_failure_reason") or "").strip(),
            "recent_decision": str(session_memory.get("recent_decision") or "").strip(),
        },
        "tool_availability": {
            "wechat_collector": True,
            "cleaner": True,
            "ingest_pipeline": True,
            "graph_service": True,
            "evaluation_runner": True,
        },
    }


def _get_agent_step_by_name(steps: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for step in steps:
        if str(step.get("name") or "").strip() == name:
            return step
    return None


def _build_multi_agent_artifacts(result: Dict[str, Any], account_id: str) -> List[Dict[str, Any]]:
    steps = result.get("steps") or []
    collect_step = _get_agent_step_by_name(steps, "collect") or _get_agent_step_by_name(steps, "desktop_collect")
    clean_step = _get_agent_step_by_name(steps, "clean")
    collect_result = (collect_step or {}).get("result") or {}
    run_result = collect_result.get("run_result") or {}
    clean_result = (clean_step or {}).get("result") or {}

    artifacts: List[Dict[str, Any]] = []
    seen_article_artifacts: Set[str] = set()
    for item in list(collect_result.get("created_articles") or []) + list(run_result.get("created_articles") or []):
        article_id = str((item or {}).get("article_id") or "").strip()
        if not article_id:
            continue
        artifact_id = f"article::{account_id}::{article_id}"
        if artifact_id in seen_article_artifacts:
            continue
        seen_article_artifacts.add(artifact_id)
        artifacts.append(
            {
                "artifact_type": "article_record",
                "artifact_id": artifact_id,
                "producer": KNOWLEDGE_ACQUISITION_AGENT,
                "summary": str((item or {}).get("title") or article_id).strip(),
                "location": {
                    "source_type": "wechat",
                    "account_id": account_id,
                    "article_id": article_id,
                    "source_link": str((item or {}).get("source_link") or "").strip(),
                },
            }
        )

    cleaned_articles = int(clean_result.get("cleaned_articles") or 0)
    generated_docs = int(clean_result.get("generated_docs") or 0)
    ingested_files = int(clean_result.get("ingested_files") or 0)
    ingested_chunks = int(clean_result.get("ingested_chunks") or 0)
    if cleaned_articles > 0 or generated_docs > 0 or ingested_files > 0 or ingested_chunks > 0:
        artifacts.append(
            {
                "artifact_type": "cleaning_result",
                "artifact_id": f"clean::{account_id}::{str(result.get('parsed', {}).get('trace_id') or uuid4().hex)}",
                "producer": KNOWLEDGE_ACQUISITION_AGENT,
                "summary": f"cleaned_articles={cleaned_articles} generated_docs={generated_docs}",
                "location": {
                    "source_type": "wechat",
                    "account_id": account_id,
                },
                "metrics": {
                    "cleaned_articles": cleaned_articles,
                    "generated_docs": generated_docs,
                    "ingested_files": ingested_files,
                    "ingested_chunks": ingested_chunks,
                },
            }
        )

    task = result.get("task") or {}
    task_id = str(task.get("task_id") or "").strip()
    if task_id:
        artifacts.append(
            {
                "artifact_type": "deferred_task",
                "artifact_id": f"task::{task_id}",
                "producer": KNOWLEDGE_ACQUISITION_AGENT,
                "summary": str(task.get("summary") or "延后入库任务已创建").strip(),
                "location": {
                    "task_id": task_id,
                    "task_type": str(task.get("task_type") or "").strip(),
                },
            }
        )
    return artifacts


def _build_multi_agent_review(result: Dict[str, Any], parsed: Dict[str, Any], artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
    steps = result.get("steps") or []
    failed_step = next((step for step in reversed(steps) if str((step.get("evaluation") or {}).get("status") or step.get("status") or "").strip() == "failed"), None)
    intervention_step = _get_agent_step_by_name(steps, "intervention")
    created_articles = [item for item in artifacts if str(item.get("artifact_type") or "") == "article_record"]
    knowledge_changed = bool(created_articles) or any(str(item.get("artifact_type") or "") == "cleaning_result" for item in artifacts)
    evaluation_result = result.get("evaluation_optimization") or {}
    evaluation_artifact = evaluation_result.get("artifact") if isinstance(evaluation_result, dict) else None

    outcome = "completed"
    failure_reason = ""
    next_actions: List[str] = []
    failed_step_name = str((failed_step or {}).get("name") or "").strip()
    if failed_step:
        failure_reason = str(((failed_step.get("evaluation") or {}).get("failure_reason") or "")).strip()
        if failed_step_name == "governance" and knowledge_changed:
            outcome = "partial_success"
            next_actions.extend(["govern_knowledge", "manual_review"])
        elif failed_step_name == "evaluation_optimization" and knowledge_changed:
            outcome = "partial_success"
            next_actions.extend(["evaluate_system", "manual_review"])
        else:
            outcome = "needs_human" if intervention_step else "failed"
    elif isinstance(evaluation_artifact, dict):
        outcome = "completed"
        next_actions.extend(["apply_optimizations", "monitor_quality"])
    elif knowledge_changed:
        outcome = "completed"
        next_actions.extend(["govern_knowledge", "evaluate_system"])

    if outcome == "needs_human":
        next_actions.append("manual_review")

    summary = (
        (
            f"知识采集已完成，但治理阶段失败：{str((failed_step or {}).get('evaluation', {}).get('summary') or '').strip()}"
            if failed_step_name == "governance" and knowledge_changed
            else f"知识采集与治理已完成，但评测阶段失败：{str((failed_step or {}).get('evaluation', {}).get('summary') or '').strip()}"
            if failed_step_name == "evaluation_optimization" and knowledge_changed
            else str((failed_step or {}).get("evaluation", {}).get("summary") or "").strip()
        )
        if failed_step
        else ("知识采集、治理与评测已完成，可按建议继续优化。" if isinstance(evaluation_artifact, dict) else ("知识采集阶段已完成，建议继续进入治理与评测。" if knowledge_changed else "当前轮次未产生新的知识资产。"))
    )
    return {
        "review_type": "task_review",
        "reviewer": KNOWLEDGE_ACQUISITION_AGENT,
        "outcome": outcome,
        "summary": summary,
        "failure_reason": failure_reason,
        "retryable": bool(((failed_step or {}).get("evaluation") or {}).get("retryable")),
        "recommended_next_actions": list(dict.fromkeys(next_actions)),
    }


def _build_multi_agent_handoffs(parsed: Dict[str, Any], account_id: str, artifacts: List[Dict[str, Any]], review: Dict[str, Any]) -> List[Dict[str, Any]]:
    if str(review.get("outcome") or "") != "completed":
        return []
    has_knowledge_artifact = any(str(item.get("artifact_type") or "") in {"article_record", "cleaning_result"} for item in artifacts)
    if not has_knowledge_artifact:
        return []
    article_ids = [
        str((item.get("location") or {}).get("article_id") or "").strip()
        for item in artifacts
        if str(item.get("artifact_type") or "") == "article_record"
    ]
    article_ids = list(dict.fromkeys(item for item in article_ids if item))
    return [
        build_protocol_handoff(
            KNOWLEDGE_ACQUISITION_AGENT,
            KNOWLEDGE_GOVERNANCE_AGENT,
            scope={
                "account_id": account_id,
                "article_ids": article_ids,
            },
        ),
        build_protocol_handoff(
            KNOWLEDGE_GOVERNANCE_AGENT,
            EVALUATION_OPTIMIZATION_AGENT,
        ),
    ]


def _build_multi_agent_orchestration(result: Dict[str, Any], parsed: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    trace_id = str(parsed.get("trace_id") or uuid4().hex).strip()
    persisted_task = result.get("task") or {}
    persisted_task_id = str(persisted_task.get("task_id") or "").strip()
    artifacts = _build_multi_agent_artifacts(result, account_id)
    review = _build_multi_agent_review(result, parsed, artifacts)
    handoffs = _build_multi_agent_handoffs(parsed, account_id, artifacts, review)
    completed_agents = [KNOWLEDGE_ACQUISITION_AGENT]
    governance_result = result.get("governance") or {}
    governance_artifact = governance_result.get("artifact") if isinstance(governance_result, dict) else None
    evaluation_result = result.get("evaluation_optimization") or {}
    evaluation_artifact = evaluation_result.get("artifact") if isinstance(evaluation_result, dict) else None
    if isinstance(governance_artifact, dict):
        artifacts.append(governance_artifact)
        completed_agents.append(KNOWLEDGE_GOVERNANCE_AGENT)
        if isinstance(evaluation_artifact, dict):
            artifacts.append(evaluation_artifact)
            completed_agents.append(EVALUATION_OPTIMIZATION_AGENT)
            handoffs = []
        elif str(evaluation_result.get("status") or "").strip() == "failed":
            handoffs = []
        else:
            handoffs = [build_protocol_handoff(KNOWLEDGE_GOVERNANCE_AGENT, EVALUATION_OPTIMIZATION_AGENT)]
    completed_agents = list(dict.fromkeys(completed_agents))
    orchestration_status = "waiting_handoff" if handoffs else str(review.get("outcome") or "completed")
    current_agent = KNOWLEDGE_ACQUISITION_AGENT
    if EVALUATION_OPTIMIZATION_AGENT in completed_agents:
        current_agent = EVALUATION_OPTIMIZATION_AGENT
    elif KNOWLEDGE_GOVERNANCE_AGENT in completed_agents:
        current_agent = KNOWLEDGE_GOVERNANCE_AGENT

    return {
        "version": MULTI_AGENT_PROTOCOL_VERSION,
        "orchestrator": KNOWLEDGE_ORCHESTRATOR_NAME,
        "protocol": clone_agent_protocol_spec(),
        "task": {
            "task_id": persisted_task_id or f"runtime_{trace_id[:12]}",
            "persisted": bool(persisted_task_id),
            "trace_id": trace_id,
            "task_type": str(parsed.get("task_type") or "acquire_knowledge"),
            "goal": _build_agent_goal(parsed),
            "status": orchestration_status,
            "current_agent": current_agent,
            "route": list(parsed.get("agent_route") or []),
            "created_at": str(persisted_task.get("created_at") or _agent_now_iso()),
            "updated_at": _agent_now_iso(),
        },
        "shared_context": _build_multi_agent_shared_context(parsed, account_id),
        "artifacts": artifacts,
        "review": review,
        "handoffs": handoffs,
        "completed_agents": completed_agents,
        "next_agent": str((handoffs[0] or {}).get("to_agent") or "") if handoffs else "",
    }


def _governance_focus_enabled(focus: List[str], name: str) -> bool:
    normalized = {str(item).strip().lower() for item in (focus or []) if str(item).strip()}
    return not normalized or name.lower() in normalized


def _build_governance_article_issue(article_payload: Dict[str, Any], focus: List[str]) -> Dict[str, Any]:
    article = article_payload.get("article") or {}
    article_id = str(article_payload.get("article_id") or "").strip()
    title = str(article.get("title") or "").strip()
    author = str(article.get("author") or "").strip()
    published_at = str(article.get("published_at") or "").strip()
    source_link = str(article.get("source_link") or "").strip()
    body_text = str(article.get("body_text") or "")
    images_total = int(article_payload.get("images_total") or 0)
    images_reviewed = int(article_payload.get("images_reviewed") or 0)

    issue_types: List[str] = []
    if _governance_focus_enabled(focus, "metadata") and (not title or not author or author.lower() == "unknown" or not published_at or not source_link):
        issue_types.append("metadata")
    if _governance_focus_enabled(focus, "content_quality") and len(body_text.strip()) < 120:
        issue_types.append("content_quality")
    if _governance_focus_enabled(focus, "annotation_coverage") and images_total > 0 and images_reviewed < images_total:
        issue_types.append("annotation_coverage")

    return {
        "article_id": article_id,
        "title": title or article_id,
        "source_link": source_link,
        "issue_types": issue_types,
        "missing_metadata": {
            "title": not bool(title),
            "author": not bool(author) or author.lower() == "unknown",
            "published_at": not bool(published_at),
            "source_link": not bool(source_link),
        },
        "body_text_length": len(body_text.strip()),
        "images_total": images_total,
        "images_reviewed": images_reviewed,
    }


def _run_knowledge_governance_agent_for_articles(account_id: str, article_payloads: List[Dict[str, Any]], focus: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized_focus = [str(item).strip().lower() for item in (focus or []) if str(item).strip()]
    duplicate_groups: Dict[str, List[str]] = {}
    issues: List[Dict[str, Any]] = []
    missing_metadata = 0
    content_quality_issues = 0
    annotation_coverage_issues = 0

    for payload in article_payloads:
        article = payload.get("article") or {}
        source_link = str(article.get("source_link") or "").strip()
        article_id = str(payload.get("article_id") or "").strip()
        if source_link and _governance_focus_enabled(normalized_focus, "duplicates"):
            duplicate_groups.setdefault(source_link, []).append(article_id)

        issue = _build_governance_article_issue(payload, normalized_focus)
        if issue["issue_types"]:
            issues.append(issue)
        if "metadata" in issue["issue_types"]:
            missing_metadata += 1
        if "content_quality" in issue["issue_types"]:
            content_quality_issues += 1
        if "annotation_coverage" in issue["issue_types"]:
            annotation_coverage_issues += 1

    duplicate_pairs = [
        {"source_link": source_link, "article_ids": article_ids}
        for source_link, article_ids in duplicate_groups.items()
        if len(article_ids) > 1
    ]
    duplicate_documents = sum(max(0, len(item["article_ids"]) - 1) for item in duplicate_pairs)

    risk_score = 0
    if duplicate_documents > 0:
        risk_score += 2
    if missing_metadata > 0:
        risk_score += 2
    if content_quality_issues > 0:
        risk_score += 1
    if annotation_coverage_issues > 0:
        risk_score += 1
    risk_level = "high" if risk_score >= 4 else ("medium" if risk_score >= 2 else "low")

    actions: List[Dict[str, Any]] = []
    if missing_metadata > 0:
        actions.append({"type": "auto_fix", "action": "normalize_metadata"})
    if annotation_coverage_issues > 0:
        actions.append({"type": "manual_review", "action": "review_image_annotations"})
    if duplicate_documents > 0:
        actions.append({"type": "manual_review", "action": "review_duplicate_articles"})
    if content_quality_issues > 0:
        actions.append({"type": "manual_review", "action": "review_short_body_articles"})

    report = {
        "agent": KNOWLEDGE_GOVERNANCE_AGENT,
        "status": "completed",
        "scope": {
            "account_id": account_id,
            "article_count": len(article_payloads),
            "focus": normalized_focus,
        },
        "report": {
            "risk_level": risk_level,
            "duplicate_documents": duplicate_documents,
            "missing_metadata": missing_metadata,
            "content_quality_issues": content_quality_issues,
            "annotation_coverage_issues": annotation_coverage_issues,
        },
        "issues": issues[:50],
        "duplicate_groups": duplicate_pairs[:20],
        "actions": actions,
        "handoff_suggestion": EVALUATION_OPTIMIZATION_AGENT,
    }
    report["artifact"] = {
        "artifact_type": "governance_report",
        "artifact_id": f"governance::{account_id or 'unknown'}::{uuid4().hex[:8]}",
        "producer": KNOWLEDGE_GOVERNANCE_AGENT,
        "summary": f"risk={risk_level} duplicates={duplicate_documents} missing_metadata={missing_metadata}",
        "location": {
            "source_type": "wechat",
            "account_id": account_id,
        },
        "metrics": report["report"],
    }
    return report


def _run_knowledge_governance_agent(payload: KnowledgeGovernancePayload) -> Dict[str, Any]:
    account_id = _normalize_account_id(payload.account_id)
    requested_ids = [str(item).strip() for item in (payload.article_ids or []) if str(item).strip()]
    normalized_focus = [str(item).strip().lower() for item in (payload.focus or []) if str(item).strip()]
    if not account_id and not requested_ids:
        raise HTTPException(status_code=400, detail="治理任务至少需要 account_id 或 article_ids")

    article_entries = list_articles(account_id=account_id or None).get("articles", [])
    if requested_ids:
        requested_set = set(requested_ids)
        article_entries = [item for item in article_entries if str(item.get("article_id") or "").strip() in requested_set]
    article_entries = article_entries[: max(1, int(payload.limit or 20))]
    if not article_entries:
        raise HTTPException(status_code=404, detail="当前范围内没有可治理的文章")

    resolved_account_id = account_id or str((article_entries[0] or {}).get("account_id") or "").strip()
    article_payloads = [
        _load_article_payload(str(item.get("account_id") or resolved_account_id).strip(), str(item.get("article_id") or "").strip())
        for item in article_entries
        if str(item.get("article_id") or "").strip()
    ]
    result = _run_knowledge_governance_agent_for_articles(resolved_account_id, article_payloads, focus=payload.focus)
    result["orchestration"] = {
        "version": MULTI_AGENT_PROTOCOL_VERSION,
        "orchestrator": KNOWLEDGE_ORCHESTRATOR_NAME,
        "protocol": clone_agent_protocol_spec(),
        "task": {
            "task_id": f"governance_{uuid4().hex[:12]}",
            "persisted": False,
            "trace_id": uuid4().hex,
            "task_type": "govern_knowledge",
            "goal": "治理公众号知识资产",
            "status": "waiting_handoff",
            "current_agent": KNOWLEDGE_GOVERNANCE_AGENT,
            "route": [KNOWLEDGE_GOVERNANCE_AGENT, EVALUATION_OPTIMIZATION_AGENT],
            "created_at": _agent_now_iso(),
            "updated_at": _agent_now_iso(),
        },
        "shared_context": {
            "knowledge_scope": {
                "source_type": "wechat",
                "account_id": resolved_account_id,
                "article_ids": [str(item.get("article_id") or "").strip() for item in article_entries],
            },
            "constraints": {
                "focus": normalized_focus,
                "limit": max(1, int(payload.limit or 20)),
            },
        },
        "artifacts": [result["artifact"]],
        "review": {
            "review_type": "task_review",
            "reviewer": KNOWLEDGE_GOVERNANCE_AGENT,
            "outcome": "completed",
            "summary": f"治理报告已生成，风险等级 {result['report']['risk_level']}。",
            "failure_reason": "",
            "retryable": False,
            "recommended_next_actions": ["evaluate_system"],
        },
        "handoffs": [build_protocol_handoff(KNOWLEDGE_GOVERNANCE_AGENT, EVALUATION_OPTIMIZATION_AGENT)],
        "completed_agents": [KNOWLEDGE_GOVERNANCE_AGENT],
        "next_agent": EVALUATION_OPTIMIZATION_AGENT,
    }
    return result


def _run_evaluation_optimization_agent(payload: EvaluationOptimizationPayload) -> Dict[str, Any]:
    account_id = _normalize_account_id(payload.account_id)
    requested_ids = list(dict.fromkeys(str(item).strip() for item in (payload.article_ids or []) if str(item).strip()))
    governance_report = payload.governance_report if isinstance(payload.governance_report, dict) else {}
    shared_context = payload.shared_context if isinstance(payload.shared_context, dict) else {}
    evaluation_snapshot = _resolve_evaluation_snapshot(getattr(payload, "evaluation_snapshot_ref", ""), shared_context)
    ragas_average = _compute_ragas_average(evaluation_snapshot)
    knowledge_scope = shared_context.get("knowledge_scope") if isinstance(shared_context.get("knowledge_scope"), dict) else {}
    context_article_ids = list(dict.fromkeys(str(item).strip() for item in (knowledge_scope.get("article_ids") or []) if str(item).strip()))
    article_ids = requested_ids or context_article_ids
    report_metrics = governance_report.get("report") if isinstance(governance_report.get("report"), dict) else {}
    if not report_metrics:
        artifact = governance_report.get("artifact") if isinstance(governance_report.get("artifact"), dict) else {}
        report_metrics = artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
    article_count = max(
        len(article_ids),
        int((governance_report.get("scope") or {}).get("article_count") or 0) if isinstance(governance_report.get("scope"), dict) else 0,
    )
    if not report_metrics and article_count <= 0:
        raise HTTPException(status_code=400, detail="评测任务至少需要治理报告或文章范围")

    duplicate_documents = max(0, int(report_metrics.get("duplicate_documents") or 0))
    missing_metadata = max(0, int(report_metrics.get("missing_metadata") or 0))
    content_quality_issues = max(0, int(report_metrics.get("content_quality_issues") or 0))
    annotation_coverage_issues = max(0, int(report_metrics.get("annotation_coverage_issues") or 0))
    governance_risk = str(report_metrics.get("risk_level") or "unknown").strip() or "unknown"

    quality_penalty = min(95, duplicate_documents * 8 + missing_metadata * 6 + content_quality_issues * 4 + annotation_coverage_issues * 4)
    quality_score = max(5, 100 - quality_penalty)
    if article_count > 0:
        coverage_score = max(0, min(100, int(round(((article_count - annotation_coverage_issues) / article_count) * 100))))
    else:
        coverage_score = 100

    if governance_risk == "low" and quality_score >= 85 and (ragas_average is None or ragas_average >= 0.8):
        readiness = "ready"
    elif governance_risk == "high" or quality_score < 65 or (ragas_average is not None and ragas_average < 0.55):
        readiness = "needs_attention"
    else:
        readiness = "needs_tuning"

    recommendations: List[Dict[str, Any]] = []
    if duplicate_documents > 0:
        recommendations.append({"priority": "high", "action": "deduplicate_source_articles", "reason": f"发现 {duplicate_documents} 篇重复文档"})
    if missing_metadata > 0:
        recommendations.append({"priority": "high", "action": "normalize_metadata", "reason": f"发现 {missing_metadata} 篇元数据缺失文章"})
    if annotation_coverage_issues > 0:
        recommendations.append({"priority": "medium", "action": "review_image_annotations", "reason": f"发现 {annotation_coverage_issues} 篇图像标注未覆盖文章"})
    if content_quality_issues > 0:
        recommendations.append({"priority": "medium", "action": "review_short_body_articles", "reason": f"发现 {content_quality_issues} 篇正文偏短文章"})
    if not recommendations:
        recommendations.append({"priority": "low", "action": "monitor_quality", "reason": "当前数据质量稳定，可继续观察后续增量"})

    result = {
        "agent": EVALUATION_OPTIMIZATION_AGENT,
        "status": "completed",
        "scope": {
            "account_id": account_id,
            "article_count": article_count,
            "article_ids": article_ids[:50],
        },
        "evaluation": {
            "quality_score": quality_score,
            "coverage_score": coverage_score,
            "readiness": readiness,
            "governance_risk_level": governance_risk,
            "ragas_average": ragas_average,
            "evaluation_snapshot": evaluation_snapshot,
        },
        "recommendations": recommendations,
        "handoff_suggestion": "",
    }
    snapshot_label = ""
    if isinstance(evaluation_snapshot, dict):
        snapshot_label = str(evaluation_snapshot.get("file_name") or evaluation_snapshot.get("evaluated_at") or "").strip()
    result["artifact"] = {
        "artifact_type": "evaluation_report",
        "artifact_id": f"evaluation::{account_id or 'unknown'}::{uuid4().hex[:8]}",
        "producer": EVALUATION_OPTIMIZATION_AGENT,
        "summary": (
            f"quality={quality_score} coverage={coverage_score} readiness={readiness}"
            + (f" ragas={ragas_average}" if ragas_average is not None else "")
            + (f" snapshot={snapshot_label}" if snapshot_label else "")
        ),
        "location": {
            "source_type": "wechat",
            "account_id": account_id,
        },
        "metrics": {
            "quality_score": quality_score,
            "coverage_score": coverage_score,
            "readiness": readiness,
            "governance_risk_level": governance_risk,
            "recommendation_count": len(recommendations),
            "ragas_average": ragas_average,
            "ragas_metrics": dict((evaluation_snapshot or {}).get("metrics") or {}),
            "evaluation_snapshot": {
                "source": str((evaluation_snapshot or {}).get("source") or "").strip(),
                "file_name": str((evaluation_snapshot or {}).get("file_name") or "").strip(),
                "evaluated_at": str((evaluation_snapshot or {}).get("evaluated_at") or "").strip(),
                "sample_count": int((evaluation_snapshot or {}).get("sample_count") or 0),
                "dataset_path": str((evaluation_snapshot or {}).get("dataset_path") or "").strip(),
                "llm_model": str((evaluation_snapshot or {}).get("llm_model") or "").strip(),
            },
        },
    }
    result["orchestration"] = {
        "version": MULTI_AGENT_PROTOCOL_VERSION,
        "orchestrator": KNOWLEDGE_ORCHESTRATOR_NAME,
        "protocol": clone_agent_protocol_spec(),
        "task": {
            "task_id": f"evaluation_{uuid4().hex[:12]}",
            "persisted": False,
            "trace_id": uuid4().hex,
            "task_type": "optimize_evaluation",
            "goal": "评测公众号知识资产质量",
            "status": "completed",
            "current_agent": EVALUATION_OPTIMIZATION_AGENT,
            "route": [EVALUATION_OPTIMIZATION_AGENT],
            "created_at": _agent_now_iso(),
            "updated_at": _agent_now_iso(),
        },
        "shared_context": shared_context,
        "artifacts": [result["artifact"]],
        "review": {
            "review_type": "task_review",
            "reviewer": EVALUATION_OPTIMIZATION_AGENT,
            "outcome": "completed",
            "summary": f"评测报告已生成，就绪度 {readiness}。",
            "confidence": 0.73,
            "checks": [
                {
                    "name": "governance_report_present",
                    "passed": bool(report_metrics),
                    "detail": "治理报告或指标摘要已提供。" if report_metrics else "当前基于文章范围直接估算评测结果。",
                },
                {
                    "name": "evaluation_report_generated",
                    "passed": True,
                    "detail": "已生成最小评测报告与优化建议。",
                },
            ],
        },
        "handoffs": [],
        "completed_agents": [EVALUATION_OPTIMIZATION_AGENT],
        "next_agent": "",
        "evaluation": {
            "status": result["status"],
            "summary": result["artifact"]["summary"],
            "qualityScore": quality_score,
            "coverageScore": coverage_score,
            "readiness": readiness,
            "governanceRiskLevel": governance_risk,
            "ragasAverage": ragas_average,
            "snapshotLabel": snapshot_label,
            "sampleCount": int((evaluation_snapshot or {}).get("sample_count") or 0) if isinstance(evaluation_snapshot, dict) else 0,
        },
    }
    _record_evaluation_history(result, payload)
    return result


def _maybe_run_governance_handoff(result: Dict[str, Any], account_id: str, article_ids: List[str]) -> Optional[Dict[str, Any]]:
    if not article_ids:
        return None
    steps = result.get("steps") or []
    failed_step = next(
        (
            step
            for step in reversed(steps)
            if str(((step.get("evaluation") or {}).get("status") or step.get("status") or "")).strip() == "failed"
        ),
        None,
    )
    if failed_step:
        return None
    payload = KnowledgeGovernancePayload(
        account_id=account_id,
        article_ids=list(dict.fromkeys(str(item).strip() for item in (article_ids or []) if str(item).strip())),
        focus=["duplicates", "metadata", "content_quality", "annotation_coverage"],
        limit=max(1, len(list(dict.fromkeys(str(item).strip() for item in (article_ids or []) if str(item).strip())))),
    )
    try:
        governance_result = _run_knowledge_governance_agent(payload)
    except HTTPException as exc:
        governance_result = {
            "agent": KNOWLEDGE_GOVERNANCE_AGENT,
            "status": "failed",
            "error": str(exc.detail or "知识治理执行失败").strip(),
        }
        result["governance"] = governance_result
        result.setdefault("steps", []).append(
            {
                "name": "governance",
                "status": "failed",
                "result": governance_result,
                "evaluation": {
                    "success": False,
                    "retryable": False,
                    "status": "failed",
                    "summary": str(exc.detail or "知识治理执行失败").strip(),
                    "failure_reason": "governance_handoff_failed",
                },
            }
        )
        return governance_result
    result["governance"] = governance_result
    result.setdefault("steps", []).append(
        {
            "name": "governance",
            "status": str(governance_result.get("status") or "completed"),
            "result": governance_result,
            "evaluation": {
                "success": True,
                "retryable": False,
                "status": "done",
                "summary": str(((governance_result.get("artifact") or {}).get("summary") or "治理报告已生成")).strip(),
                "failure_reason": "",
            },
        }
    )
    return governance_result


def _maybe_run_evaluation_handoff(result: Dict[str, Any], account_id: str, article_ids: List[str]) -> Optional[Dict[str, Any]]:
    governance_result = result.get("governance") or {}
    if not isinstance(governance_result, dict) or str(governance_result.get("status") or "").strip() != "completed":
        return None
    steps = result.get("steps") or []
    failed_step = next(
        (
            step
            for step in reversed(steps)
            if str(((step.get("evaluation") or {}).get("status") or step.get("status") or "")).strip() == "failed"
        ),
        None,
    )
    if failed_step:
        return None
    payload = EvaluationOptimizationPayload(
        account_id=account_id,
        article_ids=list(dict.fromkeys(str(item).strip() for item in (article_ids or []) if str(item).strip())),
        governance_report=governance_result,
        shared_context=_build_multi_agent_shared_context(result.get("parsed") or {}, account_id),
    )
    try:
        evaluation_result = _run_evaluation_optimization_agent(payload)
    except HTTPException as exc:
        evaluation_result = {
            "agent": EVALUATION_OPTIMIZATION_AGENT,
            "status": "failed",
            "error": str(exc.detail or "评测优化执行失败").strip(),
        }
        result["evaluation_optimization"] = evaluation_result
        result.setdefault("steps", []).append(
            {
                "name": "evaluation_optimization",
                "status": "failed",
                "result": evaluation_result,
                "evaluation": {
                    "success": False,
                    "retryable": False,
                    "status": "failed",
                    "summary": str(exc.detail or "评测优化执行失败").strip(),
                    "failure_reason": "evaluation_handoff_failed",
                },
            }
        )
        return evaluation_result
    result["evaluation_optimization"] = evaluation_result
    result.setdefault("steps", []).append(
        {
            "name": "evaluation_optimization",
            "status": str(evaluation_result.get("status") or "completed"),
            "result": evaluation_result,
            "evaluation": {
                "success": True,
                "retryable": False,
                "status": "done",
                "summary": str(((evaluation_result.get("artifact") or {}).get("summary") or "评测优化报告已生成")).strip(),
                "failure_reason": "",
            },
        }
    )
    return evaluation_result


def _is_agent_continuation_command(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    return re.search(r"继续|刚才|上次|那个|这篇|那篇|同一篇|沿用|接着", text, flags=re.IGNORECASE) is not None


def _normalize_agent_task_memory(raw: Any) -> Dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "command": str(payload.get("command") or "").strip(),
        "goal": str(payload.get("goal") or "").strip(),
        "intent": str(payload.get("intent") or "").strip(),
        "status": str(payload.get("status") or "idle").strip() or "idle",
        "last_step": str(payload.get("last_step") or "").strip(),
        "last_failure_reason": str(payload.get("last_failure_reason") or "").strip(),
        "attempt_count": max(0, int(payload.get("attempt_count", 0) or 0)),
        "last_plan_signature": str(payload.get("last_plan_signature") or "").strip(),
        "target_account_id": _normalize_account_id(payload.get("target_account_id") or ""),
        "target_display_name": str(payload.get("target_display_name") or "").strip(),
        "target_article_title": str(payload.get("target_article_title") or "").strip(),
        "target_search_query": str(payload.get("target_search_query") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def _normalize_agent_task_history(raw: Any) -> List[Dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "command": str(item.get("command") or "").strip(),
            "goal": str(item.get("goal") or "").strip(),
            "intent": str(item.get("intent") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "last_step": str(item.get("last_step") or "").strip(),
            "failure_reason": str(item.get("failure_reason") or "").strip(),
            "account_id": _normalize_account_id(item.get("account_id") or ""),
            "finished_at": str(item.get("finished_at") or "").strip(),
        })
    return normalized[:MAX_AGENT_TASK_HISTORY]


def _normalize_agent_account_history(raw: Any) -> List[Dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        account_id = _normalize_account_id(item.get("account_id") or "")
        display_name = str(item.get("display_name") or "").strip()
        if not account_id and not display_name:
            continue
        normalized.append({
            "account_id": account_id,
            "display_name": display_name,
            "history_url": str(item.get("history_url") or "").strip(),
            "article_title": str(item.get("article_title") or "").strip(),
            "search_query": str(item.get("search_query") or "").strip(),
            "last_action": str(item.get("last_action") or "").strip(),
            "last_outcome": str(item.get("last_outcome") or "").strip(),
            "last_failure_reason": str(item.get("last_failure_reason") or "").strip(),
            "last_success_at": str(item.get("last_success_at") or "").strip(),
            "last_attempt_at": str(item.get("last_attempt_at") or "").strip(),
        })
    return normalized[:MAX_AGENT_ACCOUNT_HISTORY]


def _normalize_agent_execution_plan(raw: Any) -> List[Dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    normalized: List[Dict[str, Any]] = []
    allowed_names = {"observe", "reason", "collect", "clean", "ingest"}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name not in allowed_names:
            continue
        normalized.append({
            "name": name,
            "title": str(item.get("title") or name).strip() or name,
            "enabled": bool(item.get("enabled", True)),
            "action": str(item.get("action") or "").strip(),
            "retry_limit": max(0, int(item.get("retry_limit", 0) or 0)),
            "success_criteria": str(item.get("success_criteria") or "").strip(),
        })
    return normalized


def _make_agent_plan_step(name: str, title: str, enabled: bool = True, action: str = "", retry_limit: int = 0, success_criteria: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "enabled": enabled,
        "action": action,
        "retry_limit": max(0, int(retry_limit)),
        "success_criteria": success_criteria,
    }


def _build_default_agent_execution_plan(do_collect: bool, do_clean: bool, do_ingest: bool) -> List[Dict[str, Any]]:
    return [
        _make_agent_plan_step("observe", "观察账号、cookie 与历史页状态", True, "inspect_environment", 0, "生成可用于后续决策的环境快照"),
        _make_agent_plan_step("reason", "选择本轮采集入口", True, "select_collect_action", 0, "输出明确 action，并解释为什么这样走"),
        _make_agent_plan_step("collect", "执行抓取或桌面采集", do_collect, "auto_collect", 1 if do_collect else 0, "至少满足一种：新增文章、处理到候选链接、识别出全部重复/频控跳过"),
        _make_agent_plan_step("clean", "清洗文章正文与媒体元数据", do_clean, "clean_articles", 0, "cleaned_articles 大于 0，或本轮本就没有清洗目标"),
        _make_agent_plan_step("ingest", "把清洗结果写入检索链路", do_ingest, "ingest_cleaned_docs", 0, "启用入库时 ingested_files 或 ingested_chunks 大于 0"),
    ]


def _reconcile_agent_execution_plan(plan: List[Dict[str, Any]], do_collect: bool, do_clean: bool, do_ingest: bool) -> List[Dict[str, Any]]:
    default_plan = _build_default_agent_execution_plan(do_collect, do_clean, do_ingest)
    if not plan:
        return default_plan

    plan_by_name = {
        str(item.get("name") or "").strip(): item
        for item in plan
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    reconciled: List[Dict[str, Any]] = []
    for default_item in default_plan:
        name = str(default_item.get("name") or "").strip()
        item = plan_by_name.get(name)
        if not item:
            reconciled.append(default_item)
            continue

        merged = {**default_item, **item}
        if name == "observe":
            merged["enabled"] = True
        elif name == "reason":
            merged["enabled"] = True
        elif name == "collect":
            merged["enabled"] = bool(do_collect)
            merged["retry_limit"] = max(int(item.get("retry_limit", default_item.get("retry_limit", 0)) or 0), int(default_item.get("retry_limit", 0) or 0)) if do_collect else 0
        elif name == "clean":
            merged["enabled"] = bool(do_clean)
        elif name == "ingest":
            merged["enabled"] = bool(do_ingest)
        reconciled.append(merged)
    return reconciled


def _build_plan_outline_from_execution_plan(plan: List[Dict[str, Any]]) -> List[str]:
    return [str(item.get("title") or item.get("name") or "").strip() for item in plan if bool(item.get("enabled", True)) and str(item.get("title") or item.get("name") or "").strip()][:5]


def _get_agent_plan_step(parsed: Dict[str, Any], name: str) -> Dict[str, Any]:
    for item in parsed.get("execution_plan") or []:
        if str(item.get("name") or "").strip() == name:
            return item
    return {}


def _agent_plan_step_enabled(parsed: Dict[str, Any], name: str) -> bool:
    step = _get_agent_plan_step(parsed, name)
    if step:
        return bool(step.get("enabled", True))
    return False


def _build_agent_goal(parsed: Dict[str, Any]) -> str:
    parts: List[str] = []
    if bool(parsed.get("do_collect")):
        parts.append("采集")
    if bool(parsed.get("do_clean")):
        parts.append("清洗")
    if bool(parsed.get("do_ingest")):
        parts.append("入库")
    if not parts:
        parts.append("解释能力边界")
    return "并".join(parts) + "公众号数据"


def _build_agent_plan_signature(plan: List[Dict[str, Any]]) -> str:
    enabled_names = [str(item.get("name") or "").strip() for item in plan if bool(item.get("enabled", True))]
    return ">".join(enabled_names)


def _evaluate_agent_step(name: str, result: Dict[str, Any], parsed: Optional[Dict[str, Any]] = None, decision: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    parsed = parsed or {}
    decision = decision or {}
    if name == "observe":
        resolved_account = str(result.get("resolved_account_id") or result.get("requested_account_id") or "").strip()
        success = bool(result)
        return {
            "success": success,
            "retryable": False,
            "status": "done" if success else "failed",
            "summary": f"resolved_account={resolved_account or 'unknown'} has_cookie={bool(result.get('has_cookie_session'))}",
            "failure_reason": "" if success else "empty_observation",
        }
    if name == "reason":
        action = str(result.get("action") or "").strip()
        success = bool(action)
        return {
            "success": success,
            "retryable": False,
            "status": "done" if success else "failed",
            "summary": f"action={action or 'unknown'} reason={str(result.get('reason') or '').strip()}",
            "failure_reason": "" if success else "missing_collect_action",
        }
    if name == "collect":
        action = str((decision or {}).get("action") or result.get("action") or "").strip()
        if action == "desktop_capture":
            import_result = result.get("import_result") or {}
            imported_count = int(import_result.get("imported_articles") or import_result.get("imported_count") or 0)
            success = imported_count > 0
            return {
                "success": success,
                "retryable": False,
                "status": "done" if success else "failed",
                "summary": f"desktop_imported={imported_count}",
                "failure_reason": "" if success else "desktop_capture_imported_zero_articles",
            }
        if action == "request_user_intervention":
            return {
                "success": False,
                "retryable": bool(parsed.get("allow_desktop_fallback")) and bool(parsed.get("article_title")) and bool(parsed.get("search_query") or result.get("display_name")),
                "status": "failed",
                "summary": str(result.get("message") or result.get("reason") or "需要人工介入").strip(),
                "failure_reason": str(result.get("reason") or "request_user_intervention").strip(),
            }
        if action == "skip_collect":
            return {
                "success": True,
                "retryable": False,
                "status": "skipped",
                "summary": str(result.get("reason") or "collect skipped").strip(),
                "failure_reason": "",
            }
        run_result = result.get("run_result") or {}
        processed = int(run_result.get("processed_articles") or 0)
        new_articles = int(run_result.get("new_articles") or 0)
        duplicate_count = int(result.get("duplicate_url_count") or run_result.get("duplicate_url_count") or 0)
        blocked_count = len(run_result.get("blocked_articles") or []) if isinstance(run_result.get("blocked_articles"), list) else 0
        failed_count = len(run_result.get("failed_articles") or []) if isinstance(run_result.get("failed_articles"), list) else 0
        skipped_reason = str(run_result.get("skipped_reason") or "").strip()
        success = bool(new_articles > 0 or processed > 0 or duplicate_count > 0 or skipped_reason in {"frequency_control", "all_duplicates", "all_duplicates_or_empty_history"})
        retryable = not success and bool(parsed.get("allow_desktop_fallback")) and bool(parsed.get("article_title"))
        failure_reason = "" if success else (skipped_reason or "collect_finished_without_usable_output")
        return {
            "success": success,
            "retryable": retryable,
            "status": "done" if success else "failed",
            "summary": f"processed={processed} new={new_articles} duplicates={duplicate_count} blocked={blocked_count} failed={failed_count}",
            "failure_reason": failure_reason,
        }
    if name == "clean":
        cleaned_articles = int(result.get("cleaned_articles") or 0)
        skipped_reason = str(result.get("skipped_reason") or "").strip()
        success = bool(cleaned_articles > 0 or result.get("dry_run") or skipped_reason == "no_new_articles_to_clean")
        summary = f"cleaned_articles={cleaned_articles} generated_docs={int(result.get('generated_docs') or 0)}"
        if skipped_reason == "no_new_articles_to_clean":
            summary = "no_new_articles_to_clean"
        return {
            "success": success,
            "retryable": False,
            "status": "done" if success else "failed",
            "summary": summary,
            "failure_reason": "" if success else "cleaned_articles_zero",
        }
    if name == "ingest":
        ingest_enabled = bool(parsed.get("do_ingest"))
        if not ingest_enabled:
            return {"success": True, "retryable": False, "status": "skipped", "summary": "ingest disabled", "failure_reason": ""}
        if bool(result.get("dry_run")):
            return {"success": True, "retryable": False, "status": "skipped", "summary": "dry-run 不执行真实入库", "failure_reason": ""}
        cleaned_articles = int(result.get("cleaned_articles") or 0)
        generated_docs = int(result.get("generated_docs") or 0)
        ingested_files = int(result.get("ingested_files") or 0)
        ingested_chunks = int(result.get("ingested_chunks") or 0)
        ingest_deferred = bool(result.get("ingest_deferred"))
        zero_output_but_completed = bool(
            cleaned_articles > 0
            and generated_docs > 0
            and ingested_files == 0
            and ingested_chunks == 0
            and not ingest_deferred
        )
        success = bool(cleaned_articles == 0 or ingest_deferred or ingested_files > 0 or ingested_chunks > 0 or zero_output_but_completed)
        summary = f"ingested_files={ingested_files} ingested_chunks={ingested_chunks}"
        if ingest_deferred:
            summary = "ingest deferred to background task"
        elif zero_output_but_completed:
            summary = "ingest finished without new chunks"
        return {
            "success": success,
            "retryable": False,
            "status": "done" if success else "failed",
            "summary": summary,
            "failure_reason": "" if success else "ingest_outputs_zero",
        }
    return {"success": True, "retryable": False, "status": "done", "summary": "", "failure_reason": ""}


def _pick_agent_history_candidate(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    history = _normalize_agent_session_memory(parsed.get("session_memory") or {}).get("account_history") or []
    requested_account_id = str(parsed.get("account_id") or "").strip()
    search_query = str(parsed.get("search_query") or "").strip().lower()
    if requested_account_id:
        for entry in history:
            if str(entry.get("account_id") or "").strip() == requested_account_id:
                return entry
    if search_query:
        for entry in history:
            haystack = f"{str(entry.get('display_name') or '').strip()} {str(entry.get('account_id') or '').strip()}".lower()
            if search_query in haystack:
                return entry
    if _is_agent_continuation_command(parsed.get("command") or "") and history:
        successful = [entry for entry in history if str(entry.get("last_outcome") or "").strip() == "success"]
        return successful[0] if successful else history[0]
    return None


def _build_agent_updated_session_memory(base_memory: Dict[str, Any], parsed: Dict[str, Any], steps: List[Dict[str, Any]], current_account_id: str) -> Dict[str, Any]:
    memory = _normalize_agent_session_memory(base_memory)
    finished_at = _agent_now_iso()
    latest_failure = ""
    last_step_name = ""
    final_status = "success"
    for step in steps:
        last_step_name = str(step.get("name") or last_step_name).strip() or last_step_name
        evaluation = step.get("evaluation") or {}
        if str(evaluation.get("status") or "").strip() == "failed":
            latest_failure = str(evaluation.get("failure_reason") or "").strip()
            final_status = "failed"
    if final_status != "failed":
        for step in reversed(steps):
            status = str(step.get("status") or "").strip()
            if status == "failed":
                final_status = "failed"
                break
    observation = next((item.get("result") or {} for item in steps if str(item.get("name") or "") == "observe"), {})
    decision = next((item.get("result") or {} for item in steps if str(item.get("name") or "") == "reason"), {})
    task_memory = _normalize_agent_task_memory(memory.get("task_memory") or {})
    task_memory.update({
        "command": str(parsed.get("command") or "").strip(),
        "goal": _build_agent_goal(parsed),
        "intent": str(parsed.get("intent_label") or "").strip(),
        "status": final_status,
        "last_step": last_step_name,
        "last_failure_reason": latest_failure,
        "attempt_count": max(1, int(parsed.get("_replan_attempts", 0) or 0) + 1),
        "last_plan_signature": _build_agent_plan_signature(parsed.get("execution_plan") or []),
        "target_account_id": _normalize_account_id(current_account_id or observation.get("resolved_account_id") or parsed.get("account_id") or ""),
        "target_display_name": str(observation.get("matched_display_name") or parsed.get("search_query") or "").strip(),
        "target_article_title": str(parsed.get("article_title") or "").strip(),
        "target_search_query": str(parsed.get("search_query") or "").strip(),
        "updated_at": finished_at,
    })
    task_history = _normalize_agent_task_history(memory.get("task_history") or [])
    task_history.insert(0, {
        "command": task_memory["command"],
        "goal": task_memory["goal"],
        "intent": task_memory["intent"],
        "status": task_memory["status"],
        "last_step": task_memory["last_step"],
        "failure_reason": latest_failure,
        "account_id": task_memory["target_account_id"],
        "finished_at": finished_at,
    })
    account_history = _normalize_agent_account_history(memory.get("account_history") or [])
    account_id = task_memory["target_account_id"]
    display_name = str(observation.get("matched_display_name") or task_memory.get("target_display_name") or parsed.get("search_query") or account_id).strip()
    if account_id or display_name:
        updated_entry = {
            "account_id": account_id,
            "display_name": display_name,
            "history_url": str(observation.get("history_url") or memory.get("recent_history_url") or "").strip(),
            "article_title": str(parsed.get("article_title") or memory.get("recent_article_title") or "").strip(),
            "search_query": str(parsed.get("search_query") or display_name or "").strip(),
            "last_action": str(decision.get("action") or parsed.get("intent_label") or "").strip(),
            "last_outcome": final_status,
            "last_failure_reason": latest_failure,
            "last_success_at": finished_at if final_status == "success" else "",
            "last_attempt_at": finished_at,
        }
        merged_history = [updated_entry]
        for entry in account_history:
            if str(entry.get("account_id") or "").strip() == account_id and account_id:
                continue
            if str(entry.get("display_name") or "").strip() == display_name and display_name:
                continue
            merged_history.append(entry)
        account_history = merged_history[:MAX_AGENT_ACCOUNT_HISTORY]
    memory.update({
        "recent_account_id": account_id or memory.get("recent_account_id") or "",
        "recent_display_name": display_name or memory.get("recent_display_name") or "",
        "recent_history_url": str(observation.get("history_url") or memory.get("recent_history_url") or "").strip(),
        "recent_urls": list(parsed.get("urls") or memory.get("recent_urls") or [])[:5],
        "recent_article_title": str(parsed.get("article_title") or memory.get("recent_article_title") or "").strip(),
        "recent_failure_reason": latest_failure,
        "recent_decision": str(decision.get("action") or memory.get("recent_decision") or "").strip(),
        "task_memory": task_memory,
        "task_history": task_history[:MAX_AGENT_TASK_HISTORY],
        "account_history": account_history,
    })
    return memory


def _build_agent_replan(parsed: Dict[str, Any], observation: Dict[str, Any], decision: Dict[str, Any], evaluation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    collect_plan = _get_agent_plan_step(parsed, "collect")
    retry_limit = min(MAX_AGENT_REPLAN_ATTEMPTS, int(collect_plan.get("retry_limit", 0) or 0))
    current_attempts = max(0, int(parsed.get("_replan_attempts", 0) or 0))
    if current_attempts >= retry_limit:
        return None
    if not bool(evaluation.get("retryable")):
        return None
    if str(decision.get("action") or "").strip() == "desktop_capture":
        return None
    search_query = str(parsed.get("search_query") or observation.get("matched_display_name") or "").strip()
    article_title = str(parsed.get("article_title") or observation.get("seed_probe_title") or "").strip()
    if bool(parsed.get("allow_desktop_fallback")) and search_query and article_title:
        return {
            "reason": str(evaluation.get("failure_reason") or "collect_retry_with_desktop_capture").strip(),
            "updates": {
                "force_collect_action": "desktop_capture",
                "allow_desktop_fallback": True,
                "search_query": search_query,
                "article_title": article_title,
            },
        }
    history_candidate = _pick_agent_history_candidate(parsed)
    if history_candidate:
        display_name = str(history_candidate.get("display_name") or history_candidate.get("account_id") or "").strip()
        return {
            "reason": str(evaluation.get("failure_reason") or "collect_retry_with_account_history").strip(),
            "updates": {
                "account_id": str(history_candidate.get("account_id") or parsed.get("account_id") or "").strip(),
                "search_query": str(history_candidate.get("search_query") or display_name or parsed.get("search_query") or "").strip(),
            },
        }
    return None


def _apply_agent_replan(parsed: Dict[str, Any], replan: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(parsed)
    updates = replan.get("updates") or {}
    updated.update(updates)
    updated["_replan_attempts"] = max(0, int(parsed.get("_replan_attempts", 0) or 0)) + 1
    return updated


def _execute_agent_collect_sync(parsed: Dict[str, Any], decision: Dict[str, Any], current_account_id: str) -> Dict[str, Any]:
    action = str(decision.get("action") or "").strip()
    if action in {"crawl_seed_urls", "crawl_history_url"}:
        decided_account_id = str(decision.get("account_id") or current_account_id).strip() or current_account_id
        crawl_payload = CrawlArticleUrlsPayload(
            account_id=decided_account_id,
            display_name=str(decision.get("display_name") or decided_account_id).strip() or decided_account_id,
            article_urls=list(decision.get("seed_urls") or []),
            frequency_days=max(1, int(parsed["frequency_days"])),
            window_days=max(1, int(parsed["window_days"])),
            max_links_from_history=50 if action == "crawl_history_url" else 1,
            dry_run=bool(parsed["dry_run"]),
            force=bool(parsed["force"]),
        )
        crawl_result = crawl_article_urls(crawl_payload)
        return {"step_name": "collect", "result": crawl_result, "account_id": decided_account_id}
    if action == "desktop_capture":
        desktop_result = _run_agent_desktop_collect_step(parsed, decision)
        decided_account_id = str(decision.get("account_id") or current_account_id).strip() or current_account_id
        return {"step_name": "desktop_collect", "result": desktop_result, "account_id": decided_account_id}
    if action == "request_user_intervention":
        return {"step_name": "intervention", "result": decision, "account_id": current_account_id}
    return {"step_name": "collect", "result": decision, "account_id": current_account_id}


def _build_agent_capability_reply(command: str, capability_message: str, supported: bool) -> str:
    if supported:
        return ""

    text = (command or "").strip()
    if not text:
        return "我是公众号采集助手，当前页主要用来处理公众号匹配、抓取、清洗、入库和标注衔接。"

    intro_pattern = r"你是谁|你是干什么的|你会什么|你能做什么|你可以做什么|help|帮助|说明一下|介绍一下"
    if re.search(intro_pattern, text, flags=re.IGNORECASE):
        return (
            "我是当前页面里的公众号采集助手。"
            "我主要负责 5 类事情：匹配本地公众号账号、抓取公众号链接、在直抓不通时回退到桌面微信采集、清洗文章内容并入库，以及把结果衔接到标注工作台。"
            "我不是通用闲聊助手，所以像开放问答、自我发挥式聊天这类请求我不会展开回答。"
            "如果你要我做本页职责范围内的事，直接告诉我目标公众号、链接，或说“清洗并入库当前账号”即可。"
        )

    base_message = capability_message.strip() or (
        "这条请求不在当前页面的处理范围内。"
        "这里主要只做公众号账号匹配、链接抓取、桌面微信采集回退、文章清洗、入库和标注衔接。"
    )

    return (
        f"{base_message}"
        "如果你想继续用当前页面，可以直接改成执行型指令，例如："
        "“匹配本地账号 XXX 并抓取这条公众号链接”、"
        "“继续清洗并入库当前账号”，"
        "或者“进入标注工作台”。"
    )


def _is_agent_intro_or_help_query(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    pattern = r"你是谁|你是干什么的|你会什么|你能做什么|你可以做什么|help|帮助|说明一下|介绍一下|怎么用|如何使用|能做哪些事|可以做哪些事"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None

REASON_TRANSLATION = {
    "large_resolution": "高分辨率",
    "large_file_size": "大文件",
    "high_visual_complexity": "高视觉复杂度",
    "heuristic_high_confidence": "启发式高可信度",
    "text_bearing": "含文字",
    "information_content": "信息图",
    "screenshot": "截图",
    "diagram": "图表",
    "chart": "图表",
    "table": "表格",
    "photograph": "照片",
    "document": "文档",
    "mixed_media": "混合媒体",
}

SCENE_ANNOTATION_KEYS = [
    "活动类型",
    "事件名称",
    "时间",
    "地点",
    "人物",
    "身份",
    "组织",
    "视觉特征",
    "来源",
]

SCENE_ANNOTATION_REFERENCE = {
    "活动类型": "体育活动|足球赛",
    "事件名称": "2022年xx学院篮球联赛",
    "时间": "2022-11-01",
    "地点": "操场",
    "人物": "张三等（人名）",
    "身份": "x学院舞蹈队长[第七届]",
    "组织": "xx学院|xx社团",
    "视觉特征": "篮球|运动服|眼镜男子",
    "来源": "XX公众号_2022年11月11日，“弘扬时代金典，唱响回声嘹亮”（文章内容名字）",
}

SCENE_ANNOTATION_DEFAULTS = {
    "活动类型": "",
    "事件名称": "",
    "时间": "",
    "地点": "",
    "人物": "",
    "身份": "",
    "组织": "",
    "视觉特征": "",
    "来源": "",
}


def _build_scene_annotation_defaults(article: Dict[str, Any], image: Dict[str, Any]) -> Dict[str, str]:
    data = dict(SCENE_ANNOTATION_DEFAULTS)
    title = str((article or {}).get("title", "")).strip()
    published_at = str((article or {}).get("published_at", "")).strip()
    source_link = str((article or {}).get("source_link", "")).strip()
    source_name = str((article or {}).get("author", "")).strip() or str((article or {}).get("account_id", "")).strip() or "XX公众号"
    display_idx = int((image or {}).get("display_index", 0) or 0)

    if title:
        data["事件名称"] = title
    if published_at:
        data["时间"] = published_at[:10]
    if source_name or title:
        data["来源"] = f"{source_name}_{published_at[:10] if published_at else '未知日期'}，{title or '未命名文章'}"
    if source_link:
        data["来源"] = f"{data['来源']} ({source_link})"
    if display_idx:
        data["视觉特征"] = f"图像{display_idx}"
    return {k: str(v).strip() for k, v in data.items()}


def _scene_annotation_to_text(scene: Dict[str, Any]) -> str:
    lines: List[str] = []
    for key in SCENE_ANNOTATION_KEYS:
        value = str((scene or {}).get(key, "")).strip()
        lines.append(f"{key}:{value}")
    return "\n".join(lines)


def _parse_scene_annotation_text(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            key, value = line.split(":", 1)
        elif "：" in line:
            key, value = line.split("：", 1)
        else:
            continue
        k = str(key).strip()
        v = str(value).strip()
        if k in SCENE_ANNOTATION_KEYS and v:
            result[k] = v
    return result


def _build_wechat_runtime_config():
    from base import Config

    conf = Config()
    wechat_root = WECHAT_ROOT
    conf.WECHAT_OUTPUT_DIR = str(wechat_root)
    conf.WECHAT_SOURCE_FILE = str(wechat_root.parent / "source.json")
    conf.WECHAT_STATE_FILE = str(wechat_root.parent / "state.json")

    runtime_defaults = {
        "WECHAT_REQUEST_TIMEOUT_SEC": 20,
        "WECHAT_USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "WECHAT_MAX_ARTICLES_PER_ACCOUNT": 50,
        "WECHAT_PAGE_QUALITY_GUARD_ENABLE": True,
        "WECHAT_PAGE_GUARD_MIN_BODY_CHARS": 120,
        "WECHAT_PAGE_GUARD_MAX_REFETCH": 0,
        "WECHAT_PAGE_GUARD_RETRY_MIN_WAIT_SEC": 0.0,
        "WECHAT_PAGE_GUARD_RETRY_MAX_WAIT_SEC": 0.0,
        "WECHAT_TEXT_STRUCT_MAX_CHARS": 1200,
        "WECHAT_TEXT_STRUCT_ENABLE": False,
        "WECHAT_TEXT_STRUCT_MODEL": "",
        "WECHAT_OCR_ENGINE": "off",
        "WECHAT_ENABLE_OCR": False,
        "WECHAT_PADDLE_OCR_ENABLE": False,
        "WECHAT_OCR_MIN_CHARS_FOR_INDEX": 20,
        "WECHAT_IMAGE_MIN_SIDE_FOR_INDEX": 160,
        "WECHAT_IMAGE_INDEX_HEURISTIC_THRESHOLD": 3,
        "WECHAT_IMAGE_HIGH_RECALL_ENABLE": False,
        "WECHAT_ENABLE_IMAGE_API_FALLBACK": False,
        "WECHAT_IMAGE_API_MIN_OCR_CHARS": 20,
        "WECHAT_IMAGE_ENRICH_INDEXABLE_SUMMARY": False,
        "WECHAT_IMAGE_API_MAX_CALLS_PER_ARTICLE": 0,
        "WECHAT_IMAGE_API_CALL_INTERVAL_SEC": 0.0,
        "WECHAT_IMAGE_API_MODEL": "",
        "WECHAT_API_TIMEOUT_SEC": 20,
        "WECHAT_BODY_PASS_THRESHOLD": 0.0,
        "WECHAT_OCR_PASS_THRESHOLD": 0.0,
        "WECHAT_VIDEO_MANUAL_TEMPLATE_ENABLE": False,
        "WECHAT_DEFAULT_FREQUENCY_DAYS": 30,
        "ANTI_CRAWL_USER_AGENT_ROTATION": False,
        "ANTI_CRAWL_PROXY_POOL": "",
        "ANTI_CRAWL_MODE": "off",
        "ANTI_CRAWL_REQUEST_DELAY_MIN": 0.0,
        "ANTI_CRAWL_REQUEST_DELAY_MAX": 0.0,
        "ANTI_CRAWL_MAX_RETRIES": 0,
        "ANTI_CRAWL_RETRY_BACKOFF_BASE": 1.0,
    }
    for attr_name, default_value in runtime_defaults.items():
        if not hasattr(conf, attr_name):
            setattr(conf, attr_name, default_value)
    return conf


def _translate_reason(reason: str) -> str:
    text = str(reason).strip()
    if not text:
        return text
    translated = REASON_TRANSLATION.get(text.lower(), None)
    return translated if translated else text


class AnnotationSavePayload(BaseModel):
    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    last_instruction: str = ""


class NaturalLanguagePayload(BaseModel):
    instruction: str


class AutoFillPayload(BaseModel):
    overwrite_existing: bool = False


class CrawlArticleUrlsPayload(BaseModel):
    account_id: str
    display_name: str = ""
    article_urls: List[str] = Field(default_factory=list)
    frequency_days: int = 30
    window_days: int = 365
    max_links_from_history: int = 1
    dry_run: bool = False
    force: bool = True


class AgentCommandPayload(BaseModel):
    command: str
    default_account_id: str = "my_wechat_account"
    frequency_days: int = 30
    window_days: int = 365
    force: bool = True
    session_memory: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeGovernancePayload(BaseModel):
    account_id: str = ""
    article_ids: List[str] = Field(default_factory=list)
    focus: List[str] = Field(default_factory=lambda: ["duplicates", "metadata", "content_quality", "annotation_coverage"])
    limit: int = 20


class EvaluationOptimizationPayload(BaseModel):
    account_id: str = ""
    article_ids: List[str] = Field(default_factory=list)
    governance_report: Dict[str, Any] = Field(default_factory=dict)
    shared_context: Dict[str, Any] = Field(default_factory=dict)
    evaluation_snapshot_ref: str = ""


class AgentSessionStatePayload(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict)


class CrawlHistoryAccountPayload(BaseModel):
    account_id: str
    history_url: str = ""
    display_name: str = ""
    frequency_days: int = 30
    window_days: int = 365
    max_links_from_history: int = 20
    dry_run: bool = False
    force: bool = True


class DesktopCapturePayload(BaseModel):
    operator_id: str = ""
    profile_name: str = ""
    account_id: str
    display_name: str = ""
    source_url: str = ""
    title: str = ""
    author: str = ""
    published_at: str = ""
    search_query: str = ""
    article_title: str = ""
    wechat_path: str = ""
    window_title_re: str = ".*微信.*"
    steps: int = 4
    wait_sec: float = 0.0
    settle_delay_sec: float = 1.0
    launch_timeout_sec: float = 20.0
    auto_scroll: bool = True
    skip_history: bool = False
    remember: bool = True
    import_after_capture: bool = False
    clean_after_import: bool = False
    ingest_after_import: bool = False
    force_import: bool = True


def _normalize_operator_id(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return text[:64]


def _load_capture_profile_store(profile_store: Path) -> Dict[str, Any]:
    payload = _safe_json_load(profile_store, {})
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if not isinstance(profiles, dict):
        profiles = {}
    return {
        "profiles": profiles,
        "last_profile": str(payload.get("last_profile", "") or "") if isinstance(payload, dict) else "",
    }


def _save_capture_profile_store(profile_store: Path, payload: Dict[str, Any]) -> None:
    profile_store.parent.mkdir(parents=True, exist_ok=True)
    profile_store.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _filter_capture_profiles(profile_store: Path, operator_id: str = "") -> List[Dict[str, Any]]:
    store = _load_capture_profile_store(profile_store)
    profiles = store.get("profiles", {}) if isinstance(store.get("profiles", {}), dict) else {}
    normalized_operator = _normalize_operator_id(operator_id)
    results: List[Dict[str, Any]] = []
    for name, payload in profiles.items():
        if not isinstance(payload, dict):
            continue
        profile_operator = _normalize_operator_id(payload.get("operator_id", ""))
        if normalized_operator and profile_operator != normalized_operator:
            continue
        results.append({
            "profile_name": str(name),
            **payload,
        })
    results.sort(key=lambda item: (str(item.get("operator_id", "")), str(item.get("account_id", "")), str(item.get("machine_name", item.get("serial", "")))))
    return results


def _delete_capture_profile(profile_store: Path, profile_name: str, operator_id: str = "") -> bool:
    store = _load_capture_profile_store(profile_store)
    profiles = store.get("profiles", {}) if isinstance(store.get("profiles", {}), dict) else {}
    payload = profiles.get(profile_name, {}) if isinstance(profiles.get(profile_name, {}), dict) else {}
    if not payload:
        return False
    if operator_id and _normalize_operator_id(payload.get("operator_id", "")) != _normalize_operator_id(operator_id):
        return False
    profiles.pop(profile_name, None)
    if store.get("last_profile", "") == profile_name:
        store["last_profile"] = ""
    _save_capture_profile_store(profile_store, store)
    return True


def _load_desktop_profile_store() -> Dict[str, Any]:
    return _load_capture_profile_store(DESKTOP_PROFILE_STORE)


def _filter_desktop_profiles(operator_id: str = "") -> List[Dict[str, Any]]:
    return _filter_capture_profiles(DESKTOP_PROFILE_STORE, operator_id=operator_id)


def _delete_desktop_profile(profile_name: str, operator_id: str = "") -> bool:
    return _delete_capture_profile(DESKTOP_PROFILE_STORE, profile_name=profile_name, operator_id=operator_id)


def _import_capture_package(
    capture_result: Dict[str, Any],
    account_id: str,
    display_name: str,
    clean_after_import: bool,
    ingest_after_import: bool,
    force_import: bool,
) -> Dict[str, Any]:
    from import_wechat_mobile_package import MobilePackageImporter
    from base import Config

    importer = MobilePackageImporter(conf=Config())
    summary = importer.import_package(
        package=Path(str(capture_result.get("session_dir", ""))).resolve(),
        account_id_override=_normalize_account_id(account_id),
        display_name_override=str(display_name or ""),
        dry_run=False,
        clean=bool(clean_after_import),
        ingest=bool(ingest_after_import),
        force=bool(force_import),
    )
    return {
        "import_result": summary.__dict__,
        "refreshed": list_articles(account_id=summary.account_id),
    }


def _run_desktop_capture(payload: DesktopCapturePayload) -> Dict[str, Any]:
    if not DESKTOP_CAPTURE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"桌面端采集脚本不存在: {DESKTOP_CAPTURE_SCRIPT}")

    cmd = [
        sys.executable,
        str(DESKTOP_CAPTURE_SCRIPT),
        "--json-output",
        "--account-id", _normalize_account_id(payload.account_id),
        "--operator-id", _normalize_operator_id(payload.operator_id),
        "--steps", str(max(1, int(payload.steps))),
        "--wait-sec", str(max(0.0, float(payload.wait_sec))),
        "--settle-delay-sec", str(max(0.0, float(payload.settle_delay_sec))),
        "--launch-timeout-sec", str(max(1.0, float(payload.launch_timeout_sec))),
        "--window-title-re", str(payload.window_title_re or ".*微信.*"),
    ]
    if payload.profile_name:
        cmd.extend(["--profile", str(payload.profile_name)])
    if payload.display_name:
        cmd.extend(["--display-name", str(payload.display_name)])
    if payload.source_url:
        cmd.extend(["--source-url", str(payload.source_url)])
    if payload.title:
        cmd.extend(["--title", str(payload.title)])
    if payload.author:
        cmd.extend(["--author", str(payload.author)])
    if payload.published_at:
        cmd.extend(["--published-at", str(payload.published_at)])
    if payload.search_query:
        cmd.extend(["--search-query", str(payload.search_query)])
    if payload.article_title:
        cmd.extend(["--article-title", str(payload.article_title)])
    if payload.wechat_path:
        cmd.extend(["--wechat-path", str(payload.wechat_path)])
    if payload.auto_scroll:
        cmd.append("--auto-scroll")
    if payload.skip_history:
        cmd.append("--skip-history")
    if not payload.remember:
        cmd.append("--no-remember")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=max(60, int(payload.steps) * 45))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="无法运行桌面端采集脚本") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="桌面端自动采集超时，请检查 PC 微信是否卡住") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"桌面端自动采集失败: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "桌面端自动采集失败").strip()
        raise HTTPException(status_code=500, detail=detail)

    stdout = (result.stdout or "").strip()
    try:
        capture_result = json.loads(stdout)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法解析桌面端采集结果: {stdout[:300]}") from exc

    response: Dict[str, Any] = {
        "capture": capture_result,
        "profiles": _filter_desktop_profiles(operator_id=payload.operator_id),
    }

    if payload.import_after_capture:
        response.update(
            _import_capture_package(
                capture_result=capture_result,
                account_id=payload.account_id,
                display_name=str(payload.display_name or ""),
                clean_after_import=bool(payload.clean_after_import),
                ingest_after_import=bool(payload.ingest_after_import),
                force_import=bool(payload.force_import),
            )
        )

    return response


def _normalize_wechat_article_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = f"https:{text}"

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc not in {"mp.weixin.qq.com", "weixin.qq.com"}:
        return ""
    if parsed.path not in {"/s", "/s/"} and not parsed.path.startswith("/s/"):
        return ""

    canonical_scheme = "https"
    canonical_netloc = "mp.weixin.qq.com"
    canonical_path = "/s"
    if parsed.path.startswith("/s/"):
        canonical_path = parsed.path.rstrip("/")

    if canonical_path != "/s":
        return urlunparse((canonical_scheme, canonical_netloc, canonical_path, "", "", ""))

    allowed_query_keys = {"__biz", "mid", "idx", "sn", "chksm", "album_id"}
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key in allowed_query_keys and value:
            query_items.append((key, value))
    query_items.sort()
    canonical_query = urlencode(query_items)
    return urlunparse((canonical_scheme, canonical_netloc, canonical_path, "", canonical_query, ""))


def _normalize_wechat_history_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = f"https:{text}"

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc not in {"mp.weixin.qq.com", "weixin.qq.com"}:
        return ""
    if parsed.path not in {"/mp/profile_ext", "/profile_ext"}:
        return ""

    query_map = dict(parse_qsl(parsed.query, keep_blank_values=False))
    biz = (query_map.get("__biz") or "").strip()
    if not biz:
        return ""

    canonical_query_items = [("action", "home"), ("__biz", biz)]
    return urlunparse(("https", "mp.weixin.qq.com", "/mp/profile_ext", "", urlencode(canonical_query_items), ""))


def _normalize_wechat_seed_url(url: str) -> str:
    article_url = _normalize_wechat_article_url(url)
    if article_url:
        return article_url
    return _normalize_wechat_history_url(url)


def _derive_wechat_history_url_from_article(url: str) -> str:
    article_url = _normalize_wechat_article_url(url)
    if not article_url:
        return ""
    parsed = urlparse(article_url)
    query_map = dict(parse_qsl(parsed.query, keep_blank_values=False))
    biz = str(query_map.get("__biz") or "").strip()
    if not biz:
        return ""
    return _normalize_wechat_history_url(f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}")


def _normalize_account_id(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return text[:64]


def _resolve_crawl_payload(payload: CrawlArticleUrlsPayload) -> Dict[str, Any]:
    account_id = _normalize_account_id(payload.account_id)
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id 不能为空，且只能包含字母/数字/_/-")

    normalized_seed_urls = list(
        dict.fromkeys(
            [
                normalized
                for normalized in (_normalize_wechat_seed_url(url) for url in payload.article_urls)
                if normalized
            ]
        )
    )
    existing_urls = _load_existing_article_source_links(account_id)
    deduped_seed_urls = [url for url in normalized_seed_urls if url not in existing_urls]
    if not normalized_seed_urls:
        raise HTTPException(status_code=400, detail="未检测到有效公众号链接，支持文章详情页和历史详情页")

    return {
        "account_id": account_id,
        "display_name": (payload.display_name or account_id).strip() or account_id,
        "normalized_seed_urls": deduped_seed_urls,
        "duplicate_urls": [url for url in normalized_seed_urls if url in existing_urls],
        "input_normalized_seed_urls": normalized_seed_urls,
        "frequency_days": max(1, int(payload.frequency_days)),
        "window_days": max(1, int(payload.window_days)),
        "max_links_from_history": max(1, int(payload.max_links_from_history)),
        "dry_run": bool(payload.dry_run),
        "force": bool(payload.force),
    }


def _list_wechat_source_files() -> List[Path]:
    base_dir = WECHAT_ROOT.parent
    candidates: List[Path] = []
    for pattern in ("*.json", "sources/*.json"):
        candidates.extend(base_dir.glob(pattern))
    results: List[Path] = []
    for path in sorted(set(candidates)):
        if path.name in {"state.json", "collector_state.json"}:
            continue
        if path.parent.name in {"reports", ".locks", "wechat_data", "api_sources"}:
            continue
        if path.is_file():
            results.append(path)
    return results


def _persist_wechat_local_account(
    account_id: str,
    display_name: str = "",
    seed_urls: Optional[List[str]] = None,
    frequency_days: int = 30,
    window_days: int = 365,
    max_links_from_history: int = 200,
) -> Dict[str, Any]:
    normalized_account_id = _normalize_account_id(account_id)
    if not normalized_account_id:
        raise HTTPException(status_code=400, detail="account_id 不能为空，且只能包含字母/数字/_/-")

    source_path = WECHAT_ROOT.parent / "source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {"accounts": []}
    if source_path.exists():
        try:
            loaded = json.loads(source_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {"accounts": []}

    raw_accounts = payload.get("accounts", [])
    if not isinstance(raw_accounts, list):
        raw_accounts = []
        payload["accounts"] = raw_accounts

    normalized_seed_urls = list(
        dict.fromkeys(
            [
                normalized
                for normalized in (_normalize_wechat_seed_url(url) for url in (seed_urls or []))
                if normalized
            ]
        )
    )
    derived_history_urls = [
        history_url
        for history_url in (_derive_wechat_history_url_from_article(url) for url in normalized_seed_urls)
        if history_url
    ]
    incoming_history_urls = [
        url for url in normalized_seed_urls if _normalize_wechat_history_url(url)
    ]
    incoming_article_urls = [
        url for url in normalized_seed_urls if _normalize_wechat_article_url(url)
    ]

    target = None
    for item in raw_accounts:
        if not isinstance(item, dict):
            continue
        if _normalize_account_id(str(item.get("account_id", ""))) == normalized_account_id:
            target = item
            break

    if target is None:
        target = {
            "account_id": normalized_account_id,
            "display_name": display_name.strip() or normalized_account_id,
            "enabled": True,
            "frequency_days": max(1, int(frequency_days or 30)),
            "window_days": max(1, int(window_days or 365)),
            "max_links_from_history": max(1, int(max_links_from_history or 200)),
            "history_urls": [],
            "article_urls": [],
        }
        raw_accounts.append(target)

    current_history_urls = [
        normalized
        for normalized in (_normalize_wechat_history_url(url) for url in target.get("history_urls", []))
        if normalized
    ]
    current_article_urls = [
        normalized
        for normalized in (_normalize_wechat_article_url(url) for url in target.get("article_urls", []))
        if normalized
    ]

    merged_history_urls = list(dict.fromkeys(current_history_urls + incoming_history_urls + derived_history_urls))
    merged_article_urls = list(dict.fromkeys(current_article_urls + incoming_article_urls))

    target["account_id"] = normalized_account_id
    target["display_name"] = display_name.strip() or str(target.get("display_name", "")).strip() or normalized_account_id
    target["enabled"] = bool(target.get("enabled", True))
    target["frequency_days"] = max(1, int(target.get("frequency_days", frequency_days or 30)))
    target["window_days"] = max(1, int(target.get("window_days", window_days or 365)))
    target["max_links_from_history"] = max(1, int(target.get("max_links_from_history", max_links_from_history or 200)))
    target["history_urls"] = merged_history_urls
    target["article_urls"] = merged_article_urls

    payload["accounts"] = raw_accounts
    source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "account_id": normalized_account_id,
        "display_name": target["display_name"],
        "history_urls": merged_history_urls,
        "article_urls": merged_article_urls,
        "source_file": str(source_path),
    }


def _load_wechat_source_accounts() -> List[Dict[str, Any]]:
    accounts: List[Dict[str, Any]] = []
    for path in _list_wechat_source_files():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for raw in payload.get("accounts", []):
            if not isinstance(raw, dict):
                continue
            account_id = _normalize_account_id(str(raw.get("account_id", "")))
            if not account_id:
                continue
            history_urls = [
                str(item).strip()
                for item in raw.get("history_urls", [])
                if str(item).strip()
            ]
            accounts.append(
                {
                    "account_id": account_id,
                    "display_name": str(raw.get("display_name", "")).strip() or account_id,
                    "history_urls": history_urls,
                    "article_urls": [str(item).strip() for item in raw.get("article_urls", []) if str(item).strip()],
                    "source_file": path.name,
                }
            )

    # 兼容仅存在本地抓取结果、但未写入 source.json 的账号，避免搜索公众号时直接返回 not found。
    if WECHAT_ROOT.exists():
        for account_dir in WECHAT_ROOT.iterdir():
            if not account_dir.is_dir():
                continue
            account_id = _normalize_account_id(account_dir.name)
            if not account_id:
                continue
            hints = _collect_account_name_hints(account_id)
            display_name = (hints.get("possible_names") or [account_id])[0]
            accounts.append(
                {
                    "account_id": account_id,
                    "display_name": str(display_name).strip() or account_id,
                    "history_urls": [],
                    "article_urls": [],
                    "source_file": "wechat_data",
                }
            )
    merged: Dict[str, Dict[str, Any]] = {}
    for item in accounts:
        current = merged.setdefault(
            item["account_id"],
            {
                "account_id": item["account_id"],
                "display_name": item["display_name"],
                "history_urls": [],
                "article_urls": [],
                "source_files": [],
            },
        )
        if item["display_name"] and current["display_name"] == current["account_id"]:
            current["display_name"] = item["display_name"]
        current["history_urls"] = list(dict.fromkeys(current["history_urls"] + item["history_urls"]))
        current["article_urls"] = list(dict.fromkeys(current["article_urls"] + item["article_urls"]))
        current["source_files"] = list(dict.fromkeys(current["source_files"] + [item["source_file"]]))
    return list(merged.values())


def _load_wechat_runtime_state() -> Dict[str, Any]:
    state_path = WECHAT_ROOT.parent / "state.json"
    if not state_path.exists():
        return {"accounts": {}}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"accounts": {}}
    except Exception:
        return {"accounts": {}}


def _normalize_search_text(value: str) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'[_\-:/\\|,.，。；;：!?！？()（）\[\]【】<>《》"\']+', '', text)
    return text


def _is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    idx = 0
    for char in haystack:
        if idx < len(needle) and needle[idx] == char:
            idx += 1
            if idx == len(needle):
                return True
    return idx == len(needle)


def _collect_account_name_hints(account_id: str) -> Dict[str, Any]:
    meta_dir = WECHAT_ROOT / account_id / 'meta'
    if not meta_dir.exists():
        return {
            'possible_names': [],
            'sample_titles': [],
            'existing_article_count': 0,
        }

    names: Dict[str, int] = {}
    sample_titles: List[str] = []
    article_count = 0
    for meta_path in sorted(meta_dir.glob('*.json')):
        if meta_path.name.endswith('.image_index.json'):
            continue
        try:
            payload = json.loads(meta_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        article_count += 1
        author = str(payload.get('author', '')).strip()
        title = str(payload.get('title', '')).strip()
        if author and author.lower() not in {'unknown', 'untitled'}:
            names[author] = names.get(author, 0) + 1
        if title and title.lower() != 'untitled' and len(sample_titles) < 3:
            sample_titles.append(title)

    possible_names = [name for name, _ in sorted(names.items(), key=lambda item: (-item[1], len(item[0])))]
    return {
        'possible_names': possible_names[:5],
        'sample_titles': sample_titles,
        'existing_article_count': article_count,
    }


def _score_account_search(item: Dict[str, Any], keyword: str) -> Dict[str, Any]:
    normalized_keyword = _normalize_search_text(keyword)
    if not normalized_keyword:
        return {'score': 0, 'matched_names': [], 'matched_fields': []}

    field_values = {
        'display_name': str(item.get('display_name', '')).strip(),
        'account_id': str(item.get('account_id', '')).strip(),
    }
    matched_names: List[str] = []
    matched_fields: List[str] = []
    score = 0

    for label, value in field_values.items():
        normalized_value = _normalize_search_text(value)
        if not normalized_value:
            continue
        if normalized_keyword == normalized_value:
            score = max(score, 120)
            matched_fields.append(label)
        elif normalized_keyword in normalized_value:
            score = max(score, 100)
            matched_fields.append(label)
        elif _is_subsequence(normalized_keyword, normalized_value):
            score = max(score, 82)
            matched_fields.append(f'{label}_subsequence')

    for alias in item.get('possible_names', []) or []:
        normalized_alias = _normalize_search_text(alias)
        if not normalized_alias:
            continue
        if normalized_keyword == normalized_alias:
            score = max(score, 115)
            matched_names.append(alias)
            matched_fields.append('possible_name_exact')
        elif normalized_keyword in normalized_alias:
            score = max(score, 96)
            matched_names.append(alias)
            matched_fields.append('possible_name_contains')
        elif _is_subsequence(normalized_keyword, normalized_alias):
            score = max(score, 88)
            matched_names.append(alias)
            matched_fields.append('possible_name_subsequence')

    for title in item.get('sample_titles', []) or []:
        normalized_title = _normalize_search_text(title)
        if normalized_keyword and normalized_keyword in normalized_title:
            score = max(score, 72)
            matched_fields.append('sample_title')

    unique_names = list(dict.fromkeys([name for name in matched_names if name]))
    unique_fields = list(dict.fromkeys(matched_fields))
    return {'score': score, 'matched_names': unique_names[:3], 'matched_fields': unique_fields}


def _load_existing_article_source_links(account_id: str) -> set[str]:
    meta_dir = WECHAT_ROOT / account_id / "meta"
    if not meta_dir.exists():
        return set()

    existing: set[str] = set()
    for meta_path in meta_dir.glob("*.json"):
        if meta_path.name.endswith(".image_index.json"):
            continue
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source_link = str(payload.get("source_link", "") or payload.get("url", "")).strip()
        normalized = _normalize_wechat_article_url(source_link)
        if normalized:
            existing.add(normalized)
    return existing


def _resolve_history_account_payload(payload: CrawlHistoryAccountPayload) -> Dict[str, Any]:
    account_id = _normalize_account_id(payload.account_id)
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id 不能为空")

    matched = next((item for item in _load_wechat_source_accounts() if item["account_id"] == account_id), None)
    history_url = str(payload.history_url or "").strip()
    if not history_url and matched:
        history_url = str((matched.get("history_urls") or [""])[0]).strip()
    if not history_url:
        raise HTTPException(status_code=404, detail="未找到该公众号的历史页配置")

    return {
        "account_id": account_id,
        "display_name": str(payload.display_name or (matched or {}).get("display_name") or account_id).strip() or account_id,
        "history_url": history_url,
        "frequency_days": max(1, int(payload.frequency_days)),
        "window_days": max(1, int(payload.window_days)),
        "max_links_from_history": max(1, int(payload.max_links_from_history)),
        "dry_run": bool(payload.dry_run),
        "force": bool(payload.force),
    }


def _extract_wechat_urls_from_text(text: str) -> List[str]:
    candidates = re.findall(
        r"https?://(?:mp\.)?weixin\.qq\.com(?:/s[^\s\"'<>]*|/mp/profile_ext[^\s\"'<>]*)",
        text or "",
        flags=re.IGNORECASE,
    )
    normalized = []
    for item in candidates:
        url = _normalize_wechat_seed_url(item)
        if url:
            normalized.append(url)
    return list(dict.fromkeys(normalized))


def _extract_frequency_days(text: str) -> Optional[int]:
    raw = text or ""
    lowered = raw.lower()

    if re.search(r"每\s*天|daily|每天", raw, flags=re.IGNORECASE):
        return 1
    if re.search(r"每\s*周|weekly|每周", raw, flags=re.IGNORECASE):
        return 7
    if re.search(r"每\s*月|monthly|每月", raw, flags=re.IGNORECASE):
        return 30

    patterns = [
        r"每\s*(\d+)\s*天",
        r"频率\s*[:=：]?\s*(\d+)\s*天",
        r"frequency\s*[:=]\s*(\d+)\s*(?:d|day|days)",
        r"every\s*(\d+)\s*days?",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return max(1, int(match.group(1)))
    return None


def _extract_window_days(text: str) -> Optional[int]:
    raw = text or ""
    lowered = raw.lower()

    fixed_map = [
        (r"近\s*一年|最近\s*一年|过去\s*一年|last\s*year", 365),
        (r"近\s*半年|最近\s*半年|过去\s*半年|last\s*6\s*months", 180),
        (r"近\s*一月|最近\s*一月|过去\s*一月|last\s*month", 30),
    ]
    for pattern, value in fixed_map:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return value

    day_match = re.search(r"(?:近|最近|过去|窗口|window)\s*(\d+)\s*天", lowered, flags=re.IGNORECASE)
    if day_match:
        return max(1, int(day_match.group(1)))

    month_match = re.search(r"(?:近|最近|过去|窗口|window)\s*(\d+)\s*个?月", lowered, flags=re.IGNORECASE)
    if month_match:
        return max(1, int(month_match.group(1)) * 30)

    year_match = re.search(r"(?:近|最近|过去|窗口|window)\s*(\d+)\s*年", lowered, flags=re.IGNORECASE)
    if year_match:
        return max(1, int(year_match.group(1)) * 365)

    english_day_match = re.search(r"(?:last|window)\s*(\d+)\s*days?", lowered, flags=re.IGNORECASE)
    if english_day_match:
        return max(1, int(english_day_match.group(1)))

    return None


def _extract_force_mode(text: str) -> Optional[bool]:
    lowered = (text or "").lower()
    if re.search(r"不\s*强制|不要\s*强制|非\s*强制|遵循\s*频率|respect\s+frequency|no\s*force", lowered, flags=re.IGNORECASE):
        return False

    # "force" should act as positive signal only when it appears as an independent token.
    if re.search(r"(?:^|[\s,，。;；])(?:强制|覆盖|忽略频率|force|override)(?:$|[\s,，。;；])", lowered, flags=re.IGNORECASE):
        return True
    return None


def _extract_agent_search_query(text: str) -> str:
    raw = str(text or "").strip()
    patterns = [
        r"(?:查找|搜索|打开|进入|定位)公众号\s*[:：]?\s*[\"“”']?([^，。,；;\n]+)",
        r"公众号\s*[:：]\s*[\"“”']?([^，。,；;\n]+)",
        r"搜索\s*[\"“”']?([^，。,；;\n]+)\s*公众号",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip(" \t\r\n\"“”'")
            if value:
                return value
    return ""


def _extract_agent_operator_id(text: str) -> str:
    raw = str(text or "")
    match = re.search(r"(?:operator[_\s-]*id|操作人|操作员)\s*[:=：]\s*([a-zA-Z0-9_-]+)", raw, flags=re.IGNORECASE)
    if not match:
        return ""
    return _normalize_operator_id(match.group(1))


def _extract_agent_article_title(text: str) -> str:
    raw = str(text or "")
    patterns = [
        r"(?:文章标题|标题|article[_\s-]*title)\s*[:=：]\s*[\"“”']?([^，。,；;\n]+)",
        r"文章\s*[\"“”']([^\"“”']+)[\"“”']",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip(" \t\r\n\"“”'")
            if value:
                return value
    return ""


def _normalize_agent_session_memory(raw: Any) -> Dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    recent_urls = [
        str(item).strip()
        for item in (payload.get("recent_urls") or [])
        if str(item).strip()
    ][:5]
    return {
        "account_locked": bool(payload.get("account_locked", False)),
        "pinned_account_id": _normalize_account_id(payload.get("pinned_account_id") or ""),
        "pinned_display_name": str(payload.get("pinned_display_name") or "").strip(),
        "recent_account_id": _normalize_account_id(payload.get("recent_account_id") or ""),
        "recent_display_name": str(payload.get("recent_display_name") or "").strip(),
        "recent_history_url": str(payload.get("recent_history_url") or "").strip(),
        "recent_urls": recent_urls,
        "recent_article_title": str(payload.get("recent_article_title") or "").strip(),
        "recent_failure_reason": str(payload.get("recent_failure_reason") or "").strip(),
        "recent_decision": str(payload.get("recent_decision") or "").strip(),
        "task_memory": _normalize_agent_task_memory(payload.get("task_memory") or {}),
        "task_history": _normalize_agent_task_history(payload.get("task_history") or []),
        "account_history": _normalize_agent_account_history(payload.get("account_history") or []),
    }


def _get_agent_brain_client():
    diagnostics = {
        "configured": False,
        "provider_ready": False,
        "model": "",
        "base_url": "",
        "fallback_reason": "llm_unconfigured",
        "error": "",
    }
    try:
        from openai import OpenAI
        from base.config import Config

        conf = Config()
        api_key = str(getattr(conf, "GENERAL_API_KEY", "") or getattr(conf, "DASHSCOPE_API_KEY", "") or "").strip()
        base_url = str(getattr(conf, "GENERAL_BASE_URL", "") or getattr(conf, "DASHSCOPE_BASE_URL", "") or "").strip()
        model = str(getattr(conf, "GENERAL_LLM_MODEL", "") or getattr(conf, "LLM_MODEL", "") or "").strip()
        diagnostics["model"] = model
        diagnostics["base_url"] = base_url
        if not api_key or api_key.startswith("demo-key") or not base_url or not model:
            return None, None, diagnostics
        diagnostics["configured"] = True
        diagnostics["provider_ready"] = True
        diagnostics["fallback_reason"] = ""
        return OpenAI(api_key=api_key, base_url=base_url), model, diagnostics
    except Exception as exc:
        logger.warning("Agent brain client unavailable: %s", exc)
        diagnostics["fallback_reason"] = "llm_client_unavailable"
        diagnostics["error"] = str(exc)[:200]
        return None, None, diagnostics


def _plan_agent_command_with_llm(command: str, extracted: Dict[str, Any], session_memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    client, model, diagnostics = _get_agent_brain_client()
    llm_diagnostics = {
        "configured": bool(diagnostics.get("configured", False)),
        "provider_ready": bool(diagnostics.get("provider_ready", False)),
        "attempted": False,
        "succeeded": False,
        "model": str(diagnostics.get("model") or "").strip(),
        "base_url": str(diagnostics.get("base_url") or "").strip(),
        "fallback_reason": str(diagnostics.get("fallback_reason") or "llm_unconfigured").strip(),
        "error": str(diagnostics.get("error") or "").strip(),
    }
    if client is None or not model:
        return {"plan": None, "diagnostics": llm_diagnostics}

    user_payload = {
        "command": command,
        "extracted_urls": list(extracted.get("urls") or []),
        "extracted_search_query": str(extracted.get("search_query") or "").strip(),
        "extracted_article_title": str(extracted.get("article_title") or "").strip(),
        "default_account_id": str(extracted.get("default_account_id") or "").strip(),
        "session_memory": _normalize_agent_session_memory(session_memory),
    }
    llm_diagnostics["attempted"] = True
    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": AGENT_BRAIN_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        content = str((((completion.choices or [None])[0] or {}).message or {}).content or "").strip()
        if not content:
            llm_diagnostics["fallback_reason"] = "llm_empty_response"
            return {"plan": None, "diagnostics": llm_diagnostics}
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            llm_diagnostics["fallback_reason"] = "llm_invalid_json"
            return {"plan": None, "diagnostics": llm_diagnostics}
        llm_diagnostics["succeeded"] = True
        llm_diagnostics["fallback_reason"] = ""
        return {
            "plan": {
                "supported": bool(parsed.get("supported", True)),
                "intent": str(parsed.get("intent", "")).strip() or "unsupported",
                "message": str(parsed.get("message", "")).strip(),
                "do_collect": bool(parsed.get("do_collect", False)),
                "do_clean": bool(parsed.get("do_clean", False)),
                "do_ingest": bool(parsed.get("do_ingest", False)),
                "wants_login": bool(parsed.get("wants_login", False)),
                "allow_desktop_fallback": bool(parsed.get("allow_desktop_fallback", False)),
                "search_query": str(parsed.get("search_query", "")).strip(),
                "article_title": str(parsed.get("article_title", "")).strip(),
                "plan_steps": [str(item).strip() for item in (parsed.get("plan_steps") or []) if str(item).strip()][:4],
                "execution_plan": _normalize_agent_execution_plan(parsed.get("execution_plan") or []),
            },
            "diagnostics": llm_diagnostics,
        }
    except Exception as exc:
        logger.warning("Agent brain planning failed, fallback to rules: %s", exc)
        llm_diagnostics["fallback_reason"] = "llm_request_failed"
        llm_diagnostics["error"] = str(exc)[:200]
        return {"plan": None, "diagnostics": llm_diagnostics}


def _parse_agent_command(payload: AgentCommandPayload) -> Dict[str, Any]:
    command = (payload.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="command 不能为空")

    lowered = command.lower()
    urls = _extract_wechat_urls_from_text(command)
    default_account_id = _normalize_account_id(payload.default_account_id)
    session_memory = _normalize_agent_session_memory(payload.session_memory)
    pinned_account_id = str(session_memory.get("pinned_account_id") or "").strip()
    pinned_display_name = str(session_memory.get("pinned_display_name") or "").strip()
    account_locked = bool(session_memory.get("account_locked", False)) and bool(pinned_account_id)
    recent_account_id = str(session_memory.get("recent_account_id") or "").strip()
    recent_display_name = str(session_memory.get("recent_display_name") or "").strip()
    recent_article_title = str(session_memory.get("recent_article_title") or "").strip()
    task_memory = _normalize_agent_task_memory(session_memory.get("task_memory") or {})
    continuation_mode = _is_agent_continuation_command(command)

    account_id = ""
    account_explicit = False
    account_patterns = [
        r"account[_\s-]*id\s*[:=：]\s*([a-zA-Z0-9_-]+)",
        r"账号\s*[:=：]\s*([a-zA-Z0-9_-]+)",
    ]
    for pattern in account_patterns:
        match = re.search(pattern, command, flags=re.IGNORECASE)
        if match:
            account_id = _normalize_account_id(match.group(1))
            account_explicit = bool(account_id)
            break
    if not account_id and not urls and account_locked:
        account_id = pinned_account_id
    if not account_id and not urls and recent_account_id:
        account_id = recent_account_id
    if not account_id and not urls and continuation_mode and task_memory.get("target_account_id"):
        account_id = str(task_memory.get("target_account_id") or "").strip()
    if not account_id and not urls:
        account_id = default_account_id

    search_query = _extract_agent_search_query(command)
    operator_id = _extract_agent_operator_id(command)
    article_title = _extract_agent_article_title(command)
    if not search_query and continuation_mode:
        search_query = str(task_memory.get("target_search_query") or recent_display_name or "").strip()
    if not article_title and recent_article_title and continuation_mode:
        article_title = recent_article_title
    if not article_title and continuation_mode:
        article_title = str(task_memory.get("target_article_title") or "").strip()

    collect_keywords = ["抓取", "采集", "收集", "crawl", "collect"]
    clean_keywords = ["清洗", "清理", "处理", "normalize", "clean"]
    ingest_keywords = ["入库", "索引", "向量", "ingest", "index"]
    no_ingest_keywords = ["不入库", "仅清洗", "只清洗", "不索引", "no ingest", "clean only"]
    dry_run_keywords = ["dry-run", "dry run", "试运行", "预览", "仅预览"]
    search_keywords = ["查找公众号", "搜索公众号", "打开公众号", "进入公众号", "补爬", "未爬取", "未抓取"]
    login_keywords = ["登录微信", "登录我的微信", "打开微信", "桌面微信", "pc微信", "wechat"]

    do_collect = bool(urls) or any(k in lowered for k in collect_keywords) or any(k in lowered for k in search_keywords) or bool(search_query)
    do_clean = any(k in lowered for k in clean_keywords)
    do_ingest = any(k in lowered for k in ingest_keywords)
    no_ingest = any(k in lowered for k in no_ingest_keywords)
    dry_run = any(k in lowered for k in dry_run_keywords)
    frequency_days = _extract_frequency_days(command) or max(1, int(payload.frequency_days))
    window_days = _extract_window_days(command) or max(1, int(payload.window_days))
    force = _extract_force_mode(command)
    wants_login = any(k in lowered for k in login_keywords)
    allow_desktop_fallback = wants_login or "桌面" in command or "微信" in command
    llm_plan_result = _plan_agent_command_with_llm(command, {
        "urls": urls,
        "search_query": search_query,
        "article_title": article_title,
        "default_account_id": default_account_id,
    }, session_memory=session_memory)
    llm_plan = llm_plan_result.get("plan") if isinstance(llm_plan_result, dict) else None
    brain_diagnostics = dict(llm_plan_result.get("diagnostics") or {}) if isinstance(llm_plan_result, dict) else {}
    capability_supported = True
    capability_message = ""
    brain_source = "rules"
    intent_label = ""
    plan_outline: List[str] = []
    execution_plan: List[Dict[str, Any]] = []
    assistant_reply = ""
    if llm_plan:
        brain_source = "llm"
        capability_supported = bool(llm_plan.get("supported", True))
        capability_message = str(llm_plan.get("message", "")).strip()
        intent_label = str(llm_plan.get("intent", "")).strip()
        plan_outline = [str(item).strip() for item in (llm_plan.get("plan_steps") or []) if str(item).strip()][:4]
        search_query = str(llm_plan.get("search_query") or search_query).strip()
        article_title = str(llm_plan.get("article_title") or article_title).strip()
        do_collect = bool(llm_plan.get("do_collect", do_collect))
        do_clean = bool(llm_plan.get("do_clean", do_clean))
        do_ingest = bool(llm_plan.get("do_ingest", do_ingest))
        wants_login = bool(llm_plan.get("wants_login", wants_login))
        allow_desktop_fallback = bool(llm_plan.get("allow_desktop_fallback", allow_desktop_fallback or wants_login))
        execution_plan = _normalize_agent_execution_plan(llm_plan.get("execution_plan") or [])
    elif not urls and not search_query and not article_title and _is_agent_intro_or_help_query(command):
        capability_supported = False
        capability_message = "当前这条输入更像是在询问页面能力说明，不属于公众号抓取、清洗或入库指令。"
        intent_label = "unsupported"
        brain_diagnostics["fallback_reason"] = str(brain_diagnostics.get("fallback_reason") or "help_query_short_circuit").strip() or "help_query_short_circuit"

    has_domain_signal = bool(
        urls
        or search_query
        or article_title
        or any(k in lowered for k in collect_keywords + clean_keywords + ingest_keywords + search_keywords + login_keywords)
        or continuation_mode
    )
    if not capability_supported and has_domain_signal:
        capability_supported = True
        capability_message = ""
        brain_diagnostics["fallback_reason"] = "domain_signal_rule_override"
        if intent_label == "unsupported":
            intent_label = "collect_and_ingest" if do_collect and do_ingest else ("clean_and_ingest" if do_clean and do_ingest else ("collect" if do_collect else ("clean" if do_clean else "review")))
    if force is None:
        force = bool(payload.force)

    if not capability_supported:
        do_collect = False
        do_clean = False
        do_ingest = False
    elif do_ingest:
        do_clean = True
    elif do_collect and not no_ingest:
        # 默认让“采集”可直接进入检索链路：采集 -> 清洗 -> 入库
        do_clean = True
        do_ingest = True
    elif do_clean and not no_ingest:
        # For wechat data pipeline, users usually expect cleaned content to be searchable in RAG.
        do_ingest = True
    if capability_supported and not do_collect and not do_clean:
        do_clean = True
        if not no_ingest:
            do_ingest = True

    execution_plan = _reconcile_agent_execution_plan(execution_plan, do_collect, do_clean, do_ingest)

    if not plan_outline:
        if not capability_supported:
            plan_outline = []
        else:
            plan_outline = _build_plan_outline_from_execution_plan(execution_plan)

    assistant_reply = _build_agent_capability_reply(command, capability_message, capability_supported)
    task_type = _infer_multi_agent_task_type(capability_supported, do_collect, do_clean, do_ingest)
    agent_route = _build_multi_agent_route(task_type)
    trace_id = uuid4().hex

    return {
        "command": command,
        "account_id": account_id,
        "account_explicit": account_explicit,
        "default_account_id": default_account_id,
        "urls": urls,
        "do_collect": do_collect,
        "do_clean": do_clean,
        "do_ingest": do_ingest,
        "dry_run": dry_run,
        "frequency_days": frequency_days,
        "window_days": window_days,
        "force": force,
        "search_query": search_query,
        "operator_id": operator_id,
        "article_title": article_title,
        "wants_login": wants_login,
        "allow_desktop_fallback": allow_desktop_fallback,
        "capability_supported": capability_supported,
        "capability_message": capability_message,
        "brain_source": brain_source,
        "brain_diagnostics": {
            "configured": bool(brain_diagnostics.get("configured", False)),
            "provider_ready": bool(brain_diagnostics.get("provider_ready", False)),
            "attempted": bool(brain_diagnostics.get("attempted", False)),
            "succeeded": bool(brain_diagnostics.get("succeeded", False)),
            "model": str(brain_diagnostics.get("model") or "").strip(),
            "base_url": str(brain_diagnostics.get("base_url") or "").strip(),
            "fallback_reason": str(brain_diagnostics.get("fallback_reason") or ("" if brain_source == "llm" else "rule_path")).strip(),
            "error": str(brain_diagnostics.get("error") or "").strip(),
            "domain_signal_detected": has_domain_signal,
            "continuation_mode": continuation_mode,
            "signal_summary": {
                "url_count": len(urls),
                "has_search_query": bool(search_query),
                "has_article_title": bool(article_title),
                "account_locked": account_locked,
                "wants_login": wants_login,
                "do_collect": do_collect,
                "do_clean": do_clean,
                "do_ingest": do_ingest,
            },
        },
        "intent_label": intent_label,
        "plan_outline": plan_outline,
        "execution_plan": execution_plan,
        "assistant_reply": assistant_reply,
        "protocol_version": MULTI_AGENT_PROTOCOL_VERSION,
        "task_type": task_type,
        "agent_route": agent_route,
        "trace_id": trace_id,
        "session_memory": session_memory,
        "account_locked": account_locked,
        "pinned_account_id": pinned_account_id,
        "pinned_display_name": pinned_display_name,
        "_replan_attempts": 0,
    }


def _has_wechat_cookie_session() -> bool:
    return (WECHAT_ROOT.parent / "cookies.jar").exists()


def _pick_agent_account_candidate(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    requested_account_id = str(parsed.get("account_id", "") or "").strip()
    if requested_account_id:
        for item in _load_wechat_source_accounts():
            if str(item.get("account_id", "")).strip() == requested_account_id:
                return item

    history_candidate = _pick_agent_history_candidate(parsed)
    if history_candidate:
        history_url = str(history_candidate.get("history_url") or "").strip()
        account_id = str(history_candidate.get("account_id") or "").strip()
        display_name = str(history_candidate.get("display_name") or account_id).strip() or account_id
        return {
            "account_id": account_id,
            "display_name": display_name,
            "preferred_name": display_name,
            "history_urls": [history_url] if history_url else [],
            "article_urls": [],
            "source_files": ["session_memory.account_history"],
        }

    search_query = str(parsed.get("search_query", "") or "").strip()
    if not search_query:
        return None
    candidates = search_accounts_by_name(search_query).get("accounts", [])
    return candidates[0] if candidates else None


def _infer_account_from_seed_urls(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    seed_urls = [
        str(url).strip()
        for url in (parsed.get("urls") or [])
        if _normalize_wechat_article_url(str(url).strip())
    ]
    if not seed_urls:
        return None

    article_url = seed_urls[0]
    try:
        from run_wechat_collector import WeChatCollectorAgent

        conf = _build_wechat_runtime_config()
        agent = WeChatCollectorAgent(conf=conf, source_file=conf.WECHAT_SOURCE_FILE)
        html = agent._fetch_html(article_url)
        article_meta = agent._parse_article_html(html, article_url)
    except Exception as exc:
        logger.warning("Failed to infer account from seed url=%s reason=%s", article_url, exc)
        return None

    author = str(article_meta.get("author") or "").strip()
    title = str(article_meta.get("title") or "").strip()
    history_url = _derive_wechat_history_url_from_article(article_url)
    matched_account = None

    inferred_account_id = _normalize_account_id(author)
    if not inferred_account_id and author:
        inferred_account_id = f"wechat_{hashlib.sha1(author.encode('utf-8')).hexdigest()[:12]}"

    resolved_account_id = str(inferred_account_id or parsed.get("default_account_id") or "").strip()
    if not resolved_account_id:
        return None

    display_name = str((matched_account or {}).get("preferred_name") or (matched_account or {}).get("display_name") or author or resolved_account_id).strip() or resolved_account_id
    synthetic_account = matched_account or {
        "account_id": resolved_account_id,
        "display_name": display_name,
        "history_urls": [history_url] if history_url else [],
        "article_urls": [article_url],
        "source_files": ["seed_probe"],
    }
    return {
        "account_id": resolved_account_id,
        "display_name": display_name,
        "matched_account": synthetic_account,
        "history_url": history_url,
        "author": author,
        "title": title,
    }


def _build_agent_observation(parsed: Dict[str, Any]) -> Dict[str, Any]:
    candidate = _pick_agent_account_candidate(parsed)
    inferred_seed_account = None
    if not candidate and parsed.get("urls") and not parsed.get("account_explicit"):
        inferred_seed_account = _infer_account_from_seed_urls(parsed)
        candidate = (inferred_seed_account or {}).get("matched_account") or candidate

    observed_account_id = str((candidate or {}).get("account_id") or parsed.get("account_id") or (parsed.get("default_account_id") if not parsed.get("urls") else "") or "").strip()
    history_urls = [str(item).strip() for item in (candidate or {}).get("history_urls", []) if str(item).strip()]
    if inferred_seed_account and inferred_seed_account.get("history_url"):
        history_urls = list(dict.fromkeys(history_urls + [str(inferred_seed_account.get("history_url") or "").strip()]))
    articles_snapshot = list_articles(account_id=observed_account_id) if observed_account_id else {"articles": []}
    desktop_profiles = _filter_desktop_profiles(operator_id=str(parsed.get("operator_id", "") or ""))
    account_desktop_profiles = [
        item for item in desktop_profiles
        if str(item.get("account_id", "")).strip() == observed_account_id
    ] if observed_account_id else desktop_profiles

    return {
        "requested_account_id": str(parsed.get("account_id", "") or "").strip(),
        "resolved_account_id": observed_account_id,
        "search_query": str(parsed.get("search_query", "") or "").strip(),
        "matched_account": candidate,
        "matched_display_name": str(((candidate or {}).get("preferred_name") or (candidate or {}).get("display_name") or (inferred_seed_account or {}).get("display_name") or observed_account_id)).strip() or observed_account_id,
        "has_seed_urls": bool(parsed.get("urls")),
        "seed_urls": list(parsed.get("urls") or []),
        "has_cookie_session": _has_wechat_cookie_session(),
        "has_history_url": bool(history_urls),
        "history_url": history_urls[0] if history_urls else "",
        "existing_article_count": len(articles_snapshot.get("articles", [])),
        "inferred_from_seed_url": bool(inferred_seed_account),
        "seed_probe_author": str((inferred_seed_account or {}).get("author") or "").strip(),
        "seed_probe_title": str((inferred_seed_account or {}).get("title") or "").strip(),
        "desktop_profile_count": len(account_desktop_profiles),
        "desktop_profiles": account_desktop_profiles,
        "allow_desktop_fallback": bool(parsed.get("allow_desktop_fallback")),
        "article_title": str(parsed.get("article_title", "") or "").strip(),
    }


def _decide_agent_collect_action(parsed: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
    if not bool(parsed.get("capability_supported", True)):
        return {
            "action": "request_user_intervention",
            "reason": "unsupported_capability",
            "message": str(parsed.get("capability_message") or "当前 Agent 只支持公众号账号匹配、链接抓取、桌面微信采集、清洗、入库和标注相关工作，暂时不能处理这条请求。"),
        }

    if not parsed.get("do_collect"):
        return {"action": "skip_collect", "reason": "command_without_collect_intent"}

    if str(parsed.get("force_collect_action") or "").strip() == "desktop_capture":
        account_id = str(observation.get("resolved_account_id") or observation.get("requested_account_id") or parsed.get("account_id") or "").strip()
        display_name = str(observation.get("matched_display_name") or account_id).strip() or account_id
        return {
            "action": "desktop_capture",
            "account_id": account_id,
            "display_name": display_name,
            "search_query": str(parsed.get("search_query") or display_name).strip(),
            "article_title": str(parsed.get("article_title") or observation.get("article_title") or "").strip(),
            "operator_id": str(parsed.get("operator_id") or "").strip(),
            "reason": "replanned_force_desktop_capture",
        }

    if observation.get("has_seed_urls"):
        account_id = str(observation.get("resolved_account_id") or parsed.get("default_account_id") or observation.get("requested_account_id") or "").strip()
        display_name = str(observation.get("matched_display_name") or account_id).strip() or account_id
        return {
            "action": "crawl_seed_urls",
            "account_id": account_id,
            "display_name": display_name,
            "seed_urls": observation.get("seed_urls") or [],
            "reason": "input_contains_seed_urls",
        }

    if observation.get("has_history_url") and observation.get("has_cookie_session"):
        account_id = str(observation.get("resolved_account_id") or observation.get("requested_account_id") or "").strip()
        return {
            "action": "crawl_history_url",
            "account_id": account_id,
            "display_name": str(((observation.get("matched_account") or {}).get("display_name") or account_id)).strip() or account_id,
            "seed_urls": [str(observation.get("history_url") or "").strip()],
            "reason": "history_url_available_with_cookie",
        }

    if observation.get("has_history_url") and not observation.get("has_cookie_session"):
        if observation.get("allow_desktop_fallback") and observation.get("article_title"):
            account_id = str(observation.get("resolved_account_id") or observation.get("requested_account_id") or "").strip()
            return {
                "action": "desktop_capture",
                "account_id": account_id,
                "display_name": str(observation.get("matched_display_name") or account_id).strip() or account_id,
                "search_query": str(observation.get("search_query") or observation.get("matched_display_name") or "").strip(),
                "article_title": str(observation.get("article_title") or "").strip(),
                "operator_id": str(parsed.get("operator_id") or "").strip(),
                "reason": "history_url_requires_cookie_but_desktop_capture_available",
            }
        return {
            "action": "request_user_intervention",
            "reason": "history_url_requires_cookie_session",
            "message": "已匹配到公众号历史页，但当前缺少 cookies.jar，无法安全自动补爬。请先导出微信登录 cookie，或改用桌面采集面板。",
        }

    if observation.get("allow_desktop_fallback"):
        if observation.get("article_title") and (observation.get("search_query") or observation.get("matched_display_name")):
            account_id = str(observation.get("resolved_account_id") or observation.get("requested_account_id") or "").strip()
            return {
                "action": "desktop_capture",
                "account_id": account_id,
                "display_name": str(observation.get("matched_display_name") or account_id).strip() or account_id,
                "search_query": str(observation.get("search_query") or observation.get("matched_display_name") or "").strip(),
                "article_title": str(observation.get("article_title") or "").strip(),
                "operator_id": str(parsed.get("operator_id") or "").strip(),
                "reason": "desktop_capture_requested_with_article_hint",
            }
        return {
            "action": "request_user_intervention",
            "reason": "desktop_capture_needs_operator_guidance",
            "message": "当前未找到可直接抓取的历史页配置。建议在桌面采集面板中复用已登录微信，先确认公众号和文章入口，再继续采集。",
        }

    return {
        "action": "request_user_intervention",
        "reason": "no_collectible_source_found",
        "message": "未找到可抓取的公众号入口。请在指令中提供公众号详情页/历史页链接，或补充可匹配的公众号名称。",
    }


def _extract_agent_collect_article_ids(result: Dict[str, Any]) -> List[str]:
    article_ids: List[str] = []
    for item in (result.get("created_articles") or []):
        article_id = str((item or {}).get("article_id") or "").strip()
        if article_id:
            article_ids.append(article_id)
    run_result = result.get("run_result") or {}
    for item in (run_result.get("created_articles") or []):
        article_id = str((item or {}).get("article_id") or "").strip()
        if article_id:
            article_ids.append(article_id)
    import_result = result.get("import_result") or {}
    for item in (import_result.get("created_articles") or []):
        article_id = str((item or {}).get("article_id") or "").strip()
        if article_id:
            article_ids.append(article_id)
    return list(dict.fromkeys(article_ids))


def _run_agent_clean_step(parsed: Dict[str, Any], account_id: str, article_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized_article_ids = [str(item).strip() for item in (article_ids or []) if str(item).strip()]
    if article_ids is not None and not normalized_article_ids:
        now = datetime.now().isoformat()
        return {
            "started_at": now,
            "finished_at": now,
            "wechat_root": str(Path(_rag_qa_path) / "data" / "wechat_collector" / "wechat_data"),
            "source": "wechat",
            "dry_run": bool(parsed.get("dry_run")),
            "target_article_ids": [],
            "cleaned_articles": 0,
            "cleaned_accounts": 0,
            "generated_docs": 0,
            "ingest_enabled": bool(parsed.get("do_ingest")),
            "ingested_files": 0,
            "ingested_chunks": 0,
            "samples": [],
            "skipped_reason": "no_new_articles_to_clean",
        }
    try:
        result = _run_wechat_clean_subprocess(account_id, normalized_article_ids, bool(parsed.get("do_ingest")), bool(parsed.get("dry_run")), batch_size=300, timeout=900)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="无法运行公众号清洗脚本") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="公众号清洗/入库超时") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"公众号清洗/入库失败: {exc}") from exc
    stdout = str(result.stdout or "").strip()
    stderr = str(result.stderr or "").strip()

    if result.returncode != 0 and bool(parsed.get("do_ingest")):
        try:
            fallback = _run_wechat_clean_subprocess(account_id, normalized_article_ids, False, bool(parsed.get("dry_run")), batch_size=300, timeout=900)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="无法运行公众号清洗脚本") from exc
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="公众号清洗/入库超时") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"公众号清洗/入库失败: {exc}") from exc
        fallback_stdout = str(fallback.stdout or "").strip()
        fallback_stderr = str(fallback.stderr or "").strip()
        if fallback.returncode == 0:
            try:
                fallback_result = _extract_json_object_from_output(fallback_stdout)
            except Exception as exc:
                detail = fallback_stdout or fallback_stderr or "公众号清洗脚本未返回 JSON 结果"
                raise HTTPException(status_code=500, detail=f"无法解析公众号清洗结果: {detail[:1000]}") from exc
            fallback_result.update(
                {
                    "ingest_enabled": True,
                    "ingested_files": 0,
                    "ingested_chunks": 0,
                    "ingest_deferred": True,
                    "ingest_error": (stderr or stdout or "公众号在线入库失败")[:1000],
                    "ingest_exit_code": int(result.returncode),
                }
            )
            return fallback_result

    if result.returncode != 0:
        detail = stderr or stdout or "公众号清洗/入库失败"
        raise HTTPException(status_code=500, detail=detail[:1000])

    try:
        return _extract_json_object_from_output(stdout)
    except Exception as exc:
        detail = stdout or stderr or "公众号清洗脚本未返回 JSON 结果"
        raise HTTPException(status_code=500, detail=f"无法解析公众号清洗结果: {detail[:1000]}") from exc


def _extract_json_object_from_output(output: str) -> Dict[str, Any]:
    text = str(output or "").strip()
    if not text:
        raise ValueError("empty subprocess output")

    decoder = json.JSONDecoder()
    candidate_positions = [index for index, char in enumerate(text) if char == "{"]
    for index in reversed(candidate_positions):
        try:
            payload, end = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if text[index + end :].strip():
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("no trailing json object found in subprocess output")


def _run_agent_desktop_collect_step(parsed: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    payload = DesktopCapturePayload(
        operator_id=str(decision.get("operator_id") or parsed.get("operator_id") or "").strip(),
        account_id=str(decision.get("account_id") or parsed.get("account_id") or "").strip() or str(parsed.get("default_account_id", "") or "my_wechat_account"),
        display_name=str(decision.get("display_name") or decision.get("search_query") or "").strip(),
        search_query=str(decision.get("search_query") or "").strip(),
        article_title=str(decision.get("article_title") or parsed.get("article_title") or "").strip(),
        auto_scroll=True,
        import_after_capture=True,
        clean_after_import=False,
        ingest_after_import=False,
        force_import=bool(parsed.get("force")),
    )
    return _run_desktop_capture(payload)


def _safe_json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _article_paths(account_id: str, article_id: str) -> Dict[str, Path]:
    account_dir = WECHAT_ROOT / account_id
    meta_dir = account_dir / "meta"
    docs_dir = account_dir / "docs"
    images_dir = account_dir / "images" / article_id
    return {
        "account_dir": account_dir,
        "meta_dir": meta_dir,
        "docs_dir": docs_dir,
        "index_path": meta_dir / f"{article_id}.image_index.json",
        "meta_path": meta_dir / f"{article_id}.json",
        "ann_path": docs_dir / f"{article_id}.image_annotations.json",
        "review_path": docs_dir / f"{article_id}.image_review.html",
        "images_dir": images_dir,
    }


def _compute_export_version(article_id: str, kept_images: List[Dict[str, Any]]) -> str:
    """Compute a stable version hash for kept-image exports to prevent duplicate downloads."""
    basis: List[Dict[str, Any]] = []
    for image in kept_images:
        local_path = Path(str(image.get("local_path", "")).strip())
        local_size = 0
        local_mtime = 0
        if local_path.exists() and local_path.is_file():
            stat = local_path.stat()
            local_size = int(stat.st_size)
            local_mtime = int(stat.st_mtime)
        basis.append(
            {
                "image_id": str(image.get("image_id", "")),
                "display_index": int(image.get("display_index", 0) or 0),
                "local_path": str(local_path),
                "source_url": str(image.get("source_url", "")),
                "local_size": local_size,
                "local_mtime": local_mtime,
            }
        )
    basis_json = json.dumps({"article_id": article_id, "kept": basis}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(basis_json.encode("utf-8")).hexdigest()


def _load_article_payload(account_id: str, article_id: str) -> Dict[str, Any]:
    paths = _article_paths(account_id, article_id)
    index_payload = _safe_json_load(paths["index_path"], {})
    meta_payload = _safe_json_load(paths["meta_path"], {})
    ann_payload = _safe_json_load(paths["ann_path"], {})

    images = index_payload.get("images", []) if isinstance(index_payload, dict) else []
    annotations = ann_payload.get("annotations", []) if isinstance(ann_payload, dict) else []
    ann_map = {
        str(item.get("image_id", "")): item
        for item in annotations
        if isinstance(item, dict) and str(item.get("image_id", "")).strip()
    }

    merged_images: List[Dict[str, Any]] = []
    for i, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id", "")).strip()
        ann = ann_map.get(image_id, {})
        article_meta = {
            "title": meta_payload.get("title") or index_payload.get("title") or article_id,
            "author": meta_payload.get("author", "unknown"),
            "published_at": meta_payload.get("published_at") or index_payload.get("published_at") or "",
            "source_link": index_payload.get("source_link") or meta_payload.get("url", ""),
            "account_id": account_id,
        }
        scene_annotation = ann.get("scene_annotation", {}) if isinstance(ann.get("scene_annotation", {}), dict) else {}
        scene_defaults = _build_scene_annotation_defaults(article_meta, {"display_index": i})
        if not scene_annotation:
            scene_annotation = dict(scene_defaults)
        else:
            merged_scene = dict(scene_defaults)
            for k in SCENE_ANNOTATION_KEYS:
                value = str(scene_annotation.get(k, "")).strip()
                if value:
                    merged_scene[k] = value
            scene_annotation = merged_scene

        scene_annotation_text = str(ann.get("scene_annotation_text", "")).strip()
        if not scene_annotation_text:
            scene_annotation_text = _scene_annotation_to_text(scene_annotation)

        local_path = str(image.get("local_path", ""))
        image_url = f"/api/wechat-annotator/articles/{account_id}/{article_id}/images/{image_id}" if image_id else ""
        merged_images.append(
            {
                "display_index": i,
                "image_id": image_id,
                "url": image_url,
                "source_url": image.get("url", ""),
                "local_path": local_path,
                "width": int(image.get("width", 0)),
                "height": int(image.get("height", 0)),
                "image_size_bytes": int(image.get("image_size_bytes", 0)),
                "indexable": bool(image.get("indexable", False)),
                "decorative_candidate": bool(image.get("decorative_candidate", False)),
                "ocr_char_count": int(image.get("ocr_char_count", 0)),
                "heuristic_score": int(image.get("heuristic_score", 0)),
                "image_entropy": float(image.get("image_entropy", 0.0)),
                "index_reasons": image.get("index_reasons", []),
                "index_reasons_zh": [_translate_reason(r) for r in (image.get("index_reasons", []) or [])],
                "api_summary": image.get("api_summary", ""),
                "api_informative": bool(image.get("api_informative", False)),
                "scene_annotation": scene_annotation,
                "scene_annotation_text": scene_annotation_text,
                "manual_summary": str(ann.get("manual_summary", "")),
                "manual_tags": ann.get("manual_tags", []) if isinstance(ann.get("manual_tags", []), list) else [],
                "manual_notes": str(ann.get("manual_notes", "")),
                "keep_for_index": bool(ann.get("keep_for_index", True)),
                "is_reviewed": any(
                    [
                        bool(str(ann.get("manual_summary", "")).strip()),
                        bool(ann.get("manual_tags", [])),
                        bool(str(ann.get("manual_notes", "")).strip()),
                        ann.get("keep_for_index") is False,
                    ]
                ),
            }
        )

    kept = sum(1 for img in merged_images if img.get("keep_for_index", True))
    dropped = sum(1 for img in merged_images if not img.get("keep_for_index", True))
    reviewed = sum(1 for img in merged_images if img.get("is_reviewed", False))

    return {
        "account_id": account_id,
        "article_id": article_id,
        "article": {
            "title": meta_payload.get("title") or index_payload.get("title") or article_id,
            "author": meta_payload.get("author", "unknown"),
            "published_at": meta_payload.get("published_at") or index_payload.get("published_at"),
            "source_link": index_payload.get("source_link") or meta_payload.get("url", ""),
            "body_text": meta_payload.get("body_text", ""),
            "body_text_preview": (meta_payload.get("body_text", "")[:500] + "...") if len(meta_payload.get("body_text", "")) > 500 else meta_payload.get("body_text", ""),
        },
        "annotations_path": str(paths["ann_path"]),
        "review_path": str(paths["review_path"]),
        "images_total": len(merged_images),
        "images_indexable": sum(1 for img in merged_images if img.get("indexable", False)),
        "images_kept": kept,
        "images_dropped": dropped,
        "images_reviewed": reviewed,
        "images": merged_images,
        "last_instruction": ann_payload.get("last_instruction", "") if isinstance(ann_payload, dict) else "",
        "last_instruction_at": ann_payload.get("last_instruction_at", "") if isinstance(ann_payload, dict) else "",
    }


def _derive_auto_tags(image: Dict[str, Any], summary: str) -> List[str]:
    tags: List[str] = []
    for reason in (image.get("index_reasons") or []):
        text = str(reason).strip()
        if not text:
            continue
        text = text.replace("_", " ")
        tags.append(text)

    if bool(image.get("api_informative", False)):
        tags.append("信息图")
    if bool(image.get("decorative_candidate", False)):
        tags.append("疑似装饰图")
    if int(image.get("ocr_char_count", 0)) >= 8:
        tags.append("含文字")
    if int(image.get("width", 0)) >= 1200:
        tags.append("大图")

    summary_text = str(summary or "")
    if "logo" in summary_text.lower() or "标志" in summary_text or "会标" in summary_text:
        tags.append("标志")
    if "活动" in summary_text:
        tags.append("活动")
    if "合影" in summary_text:
        tags.append("合影")
    if "海报" in summary_text or "宣传" in summary_text:
        tags.append("宣传")

    result: List[str] = []
    seen = set()
    for tag in tags:
        t = str(tag).strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)
    return result[:10]


def _autofill_annotations(account_id: str, article_id: str, overwrite_existing: bool = False) -> Dict[str, Any]:
    paths = _article_paths(account_id, article_id)
    if not paths["index_path"].exists():
        raise HTTPException(status_code=404, detail="文章不存在")

    payload = _load_article_payload(account_id, article_id)
    existing = _safe_json_load(paths["ann_path"], {}) if paths["ann_path"].exists() else {}
    existing_items = existing.get("annotations", []) if isinstance(existing, dict) else []
    ann_map: Dict[str, Dict[str, Any]] = {}
    for item in existing_items:
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id", "")).strip()
        if image_id:
            ann_map[image_id] = item

    changed = 0
    filled_summary = 0
    filled_tags = 0
    filled_notes = 0
    normalized: List[Dict[str, Any]] = []
    for image in payload.get("images", []):
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id", "")).strip()
        if not image_id:
            continue

        current = ann_map.get(image_id, {})
        summary = str(current.get("manual_summary", "") or "").strip()
        tags = current.get("manual_tags", [])
        tags_list = [str(t).strip() for t in (tags if isinstance(tags, list) else []) if str(t).strip()]
        notes = str(current.get("manual_notes", "") or "").strip()

        scene_defaults = _build_scene_annotation_defaults(payload.get("article", {}), image)
        scene_current = current.get("scene_annotation", {}) if isinstance(current.get("scene_annotation", {}), dict) else {}
        scene_from_text = _parse_scene_annotation_text(str(current.get("scene_annotation_text", "")).strip())
        scene_merged = dict(scene_defaults)
        for key in SCENE_ANNOTATION_KEYS:
            value = str(scene_current.get(key, "")).strip() or str(scene_from_text.get(key, "")).strip()
            if value:
                scene_merged[key] = value

        suggested_summary = str(image.get("api_summary", "") or "").strip()
        if not suggested_summary:
            suggested_summary = f"图片#{int(image.get('display_index', 0) or 0)} 自动预填：建议人工补充语义描述"

        scene_merged["视觉特征"] = str(scene_merged.get("视觉特征", "")).strip() or "未填写"
        if suggested_summary:
            scene_merged["事件名称"] = str(scene_merged.get("事件名称", "")).strip() or suggested_summary

        suggested_tags = [
            str(scene_merged.get("活动类型", "")).strip(),
            str(scene_merged.get("组织", "")).strip(),
            str(scene_merged.get("视觉特征", "")).strip(),
        ]
        suggested_tags = [item for tag in suggested_tags for item in [seg.strip() for seg in tag.split("|")] if item]
        if not suggested_tags:
            suggested_tags = _derive_auto_tags(image, suggested_summary)

        suggested_notes = _scene_annotation_to_text(scene_merged)
        scene_text_current = str(current.get("scene_annotation_text", "")).strip()
        scene_annotation_text = scene_text_current or suggested_notes
        scene_annotation = dict(scene_merged)

        new_summary = summary
        new_tags = tags_list
        new_notes = notes

        if overwrite_existing or not new_summary:
            if new_summary != suggested_summary:
                new_summary = suggested_summary
                filled_summary += 1
                changed += 1
        if overwrite_existing or not new_tags:
            if new_tags != suggested_tags:
                new_tags = suggested_tags
                filled_tags += 1
                changed += 1
        if overwrite_existing or not new_notes:
            if new_notes != suggested_notes:
                new_notes = suggested_notes
                filled_notes += 1
                changed += 1

        if overwrite_existing or not scene_text_current:
            scene_annotation_text = suggested_notes
            changed += 1

        keep_for_index = current.get("keep_for_index")
        if keep_for_index is None:
            keep_for_index = bool(image.get("indexable", True))

        normalized.append(
            {
                "image_id": image_id,
                "local_path": image.get("local_path", ""),
                "manual_summary": new_summary,
                "manual_tags": new_tags,
                "manual_notes": new_notes,
                "scene_annotation": scene_annotation,
                "scene_annotation_text": scene_annotation_text,
                "keep_for_index": bool(keep_for_index),
            }
        )

    paths["docs_dir"].mkdir(parents=True, exist_ok=True)
    ann_payload = {
        "article_id": article_id,
        "account_id": account_id,
        "updated_at": datetime.now().isoformat(),
        "last_instruction": str(existing.get("last_instruction", "")) if isinstance(existing, dict) else "",
        "last_instruction_at": str(existing.get("last_instruction_at", "")) if isinstance(existing, dict) else "",
        "annotations": normalized,
    }
    paths["ann_path"].write_text(json.dumps(ann_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_result = _sync_annotations_safe(account_id, article_id)

    return {
        "ok": True,
        "changed": changed,
        "filled_summary": filled_summary,
        "filled_tags": filled_tags,
        "filled_notes": filled_notes,
        "overwrite_existing": overwrite_existing,
        "annotations_path": str(paths["ann_path"]),
        "sync": sync_result,
        "review_payload": _load_article_payload(account_id, article_id),
    }


def _sync_annotations_safe(account_id: str, article_id: str) -> Dict[str, Any]:
    try:
        result = sync_annotations(account_id=account_id, article_id=article_id)
        return {"ok": True, **result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/articles")
def list_articles(account_id: Optional[str] = None) -> Dict[str, Any]:
    if not WECHAT_ROOT.exists():
        return {"accounts": [], "articles": []}

    accounts_payload: List[Dict[str, Any]] = []
    articles_payload: List[Dict[str, Any]] = []

    for account_dir in sorted([p for p in WECHAT_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name):
        if account_id and account_dir.name != account_id:
            continue
        meta_dir = account_dir / "meta"
        if not meta_dir.exists():
            continue

        account_articles: List[Dict[str, Any]] = []
        article_ids: Set[str] = set()
        for meta_path in meta_dir.glob("*.json"):
            if meta_path.name.endswith(".image_index.json"):
                article_ids.add(meta_path.name.replace(".image_index.json", ""))
            else:
                article_ids.add(meta_path.stem)

        def _article_sort_key(article_key: str) -> float:
            paths = _article_paths(account_dir.name, article_key)
            stat_path = paths["index_path"] if paths["index_path"].exists() else paths["meta_path"]
            try:
                return float(stat_path.stat().st_mtime)
            except Exception:
                return 0.0

        for article_id in sorted(article_ids, key=_article_sort_key, reverse=True):
            payload = _load_article_payload(account_dir.name, article_id)
            paths = _article_paths(account_dir.name, article_id)
            saved_images: List[Dict[str, Any]] = []
            for image in payload.get("images", []):
                if not isinstance(image, dict):
                    continue
                image_id = str(image.get("image_id", "")).strip()
                if not image_id:
                    continue
                image_url = f"/api/wechat-annotator/articles/{quote(account_dir.name)}/{quote(article_id)}/images/{quote(image_id)}"
                image_path = Path(str(image.get("local_path", "")).strip())
                image_size = 0
                try:
                    if image_path.exists() and image_path.is_file():
                        image_size = int(image_path.stat().st_size)
                except Exception:
                    image_size = 0
                saved_images.append(
                    {
                        "image_id": image_id,
                        "url": image_url,
                        "thumbnail_url": image_url,
                        "size": image_size,
                        "display_index": int(image.get("display_index", 0) or 0),
                        "manual_summary": str(image.get("manual_summary", "")).strip(),
                        "keep_for_index": bool(image.get("keep_for_index", True)),
                    }
                )
            first_image = saved_images[0] if saved_images else None
            cover_image_url = ""
            if first_image:
                cover_image_url = first_image.get("url", "")
            stat_path = paths["index_path"] if paths["index_path"].exists() else paths["meta_path"]
            try:
                updated_at = datetime.fromtimestamp(stat_path.stat().st_mtime).isoformat()
            except Exception:
                updated_at = ""
            item = {
                "account_id": account_dir.name,
                "article_id": article_id,
                "title": payload["article"].get("title", article_id),
                "author": payload["article"].get("author", "unknown"),
                "source_link": payload["article"].get("source_link", ""),
                "published_at": payload["article"].get("published_at", ""),
                "cover_image_url": cover_image_url,
                "images_total": payload.get("images_total", 0),
                "images_indexable": payload.get("images_indexable", 0),
                "images_reviewed": payload.get("images_reviewed", 0),
                "saved_image_count": len(saved_images),
                "saved_images": saved_images,
                "has_image_index": paths["index_path"].exists(),
                "annotations_path": payload.get("annotations_path", ""),
                "updated_at": updated_at,
            }
            account_articles.append(item)
            articles_payload.append(item)

        accounts_payload.append(
            {
                "account_id": account_dir.name,
                "article_count": len(account_articles),
                "articles": account_articles,
            }
        )

    return {"accounts": accounts_payload, "articles": articles_payload}


@router.get("/accounts/search")
def search_accounts_by_name(q: str = "") -> Dict[str, Any]:
    keyword = str(q or "").strip().lower()
    candidates = []
    runtime_state = _load_wechat_runtime_state().get("accounts", {})
    for item in _load_wechat_source_accounts():
        hints = _collect_account_name_hints(item['account_id'])
        article_summary = list_articles(account_id=item["account_id"]).get("articles", [])
        state_entry = runtime_state.get(item["account_id"], {}) if isinstance(runtime_state, dict) else {}
        enriched = {
            **item,
            **hints,
            "last_run_at": str(state_entry.get("last_run_at", "") or ""),
            "last_processed_articles": int(state_entry.get("last_processed_articles", 0) or 0),
            "last_new_articles": int(state_entry.get("last_new_articles", 0) or 0),
        }
        valid_author_groups: Dict[str, List[Dict[str, Any]]] = {}
        for article in article_summary:
            author = str((article or {}).get("author", "") or "").strip()
            if not author or author.lower() in {"unknown", "untitled"}:
                continue
            valid_author_groups.setdefault(author, []).append(article)

        if len(valid_author_groups) > 1:
            for author, author_articles in valid_author_groups.items():
                author_articles_sorted = sorted(
                    author_articles,
                    key=lambda article: str(article.get("updated_at", "") or ""),
                    reverse=True,
                )
                author_enriched = {
                    **enriched,
                    "display_name": author,
                    "possible_names": [author],
                    "sample_titles": [
                        str(article.get("title", "")).strip()
                        for article in author_articles_sorted
                        if str(article.get("title", "")).strip() and str(article.get("title", "")).strip().lower() != "untitled"
                    ][:3],
                    "latest_article_updated_at": str((author_articles_sorted[0] or {}).get("updated_at", "") or ""),
                }
                match = _score_account_search(author_enriched, keyword)
                if keyword and match['score'] <= 0:
                    continue
                candidates.append(
                    {
                        **author_enriched,
                        "overview_key": f"{item['account_id']}::{author}",
                        "has_history_url": bool(item.get("history_urls")),
                        "existing_article_count": len(author_articles),
                        "match_score": match['score'],
                        "matched_names": match['matched_names'],
                        "matched_fields": match['matched_fields'],
                        "preferred_name": author,
                    }
                )
            continue

        latest_article_updated_at = ""
        if article_summary:
            latest_article_updated_at = str(article_summary[0].get("updated_at", "") or "")
        enriched["latest_article_updated_at"] = latest_article_updated_at
        match = _score_account_search(enriched, keyword)
        if keyword and match['score'] <= 0:
            continue
        candidates.append(
            {
                **enriched,
                "overview_key": item["account_id"],
                "has_history_url": bool(item.get("history_urls")),
                "existing_article_count": max(int(hints.get('existing_article_count', 0)), len(article_summary)),
                "match_score": match['score'],
                "matched_names": match['matched_names'],
                "matched_fields": match['matched_fields'],
                "preferred_name": (match['matched_names'][0] if match['matched_names'] else (enriched.get('possible_names') or [enriched.get('display_name')])[0]),
            }
        )
    candidates.sort(key=lambda item: (-int(item.get('match_score', 0)), -int(item.get('existing_article_count', 0)), len(str(item.get('account_id', '')))))
    return {"accounts": candidates}


@router.get("/desktop/profiles")
def list_desktop_profiles(operator_id: str = "") -> Dict[str, Any]:
    return {
        "operator_id": _normalize_operator_id(operator_id),
        "profiles": _filter_desktop_profiles(operator_id=operator_id),
        "last_profile": _load_desktop_profile_store().get("last_profile", ""),
    }


@router.delete("/desktop/profiles/{profile_name}")
def delete_desktop_profile(profile_name: str, operator_id: str = "") -> Dict[str, Any]:
    ok = _delete_desktop_profile(profile_name=profile_name, operator_id=operator_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该 profile，或它不属于当前 operator")
    return {
        "ok": True,
        "operator_id": _normalize_operator_id(operator_id),
        "profiles": _filter_desktop_profiles(operator_id=operator_id),
    }


@router.post("/desktop/capture")
async def run_desktop_capture(payload: DesktopCapturePayload) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _run_desktop_capture(payload))


@router.post("/desktop/capture/stream")
async def run_desktop_capture_stream(payload: DesktopCapturePayload, request: Request):
    async def stream():
        cmd = [
            sys.executable,
            str(DESKTOP_CAPTURE_SCRIPT),
            "--json-output",
            "--progress-json",
            "--account-id", _normalize_account_id(payload.account_id),
            "--operator-id", _normalize_operator_id(payload.operator_id),
            "--steps", str(max(1, int(payload.steps))),
            "--wait-sec", str(max(0.0, float(payload.wait_sec))),
            "--settle-delay-sec", str(max(0.0, float(payload.settle_delay_sec))),
            "--launch-timeout-sec", str(max(1.0, float(payload.launch_timeout_sec))),
            "--window-title-re", str(payload.window_title_re or ".*微信.*"),
        ]
        if payload.profile_name:
            cmd.extend(["--profile", str(payload.profile_name)])
        if payload.display_name:
            cmd.extend(["--display-name", str(payload.display_name)])
        if payload.source_url:
            cmd.extend(["--source-url", str(payload.source_url)])
        if payload.title:
            cmd.extend(["--title", str(payload.title)])
        if payload.author:
            cmd.extend(["--author", str(payload.author)])
        if payload.published_at:
            cmd.extend(["--published-at", str(payload.published_at)])
        if payload.search_query:
            cmd.extend(["--search-query", str(payload.search_query)])
        if payload.article_title:
            cmd.extend(["--article-title", str(payload.article_title)])
        if payload.wechat_path:
            cmd.extend(["--wechat-path", str(payload.wechat_path)])
        if payload.auto_scroll:
            cmd.append("--auto-scroll")
        if payload.skip_history:
            cmd.append("--skip-history")
        if not payload.remember:
            cmd.append("--no-remember")

        try:
            yield f"data: {json.dumps({'type': 'loading', 'message': '正在启动桌面端采集脚本…'}, ensure_ascii=False)}\n\n"
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(_rag_qa_path)),
            )
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': f'无法启动桌面端采集脚本: {exc}'}, ensure_ascii=False)}\n\n"
            return

        capture_result: Optional[Dict[str, Any]] = None
        stderr_lines: List[str] = []

        async def _read_stdout():
            nonlocal capture_result
            assert process.stdout is not None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode('utf-8', errors='ignore').strip()
                if not text:
                    continue
                try:
                    payload_json = json.loads(text)
                except Exception:
                    yield f"data: {json.dumps({'type': 'log', 'message': text}, ensure_ascii=False)}\n\n"
                    continue
                event_type = str(payload_json.get('type', '') or '').strip()
                if event_type:
                    yield f"data: {json.dumps(payload_json, ensure_ascii=False)}\n\n"
                elif isinstance(payload_json, dict) and payload_json.get('ok') is True:
                    capture_result = payload_json

        async def _read_stderr():
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                text = line.decode('utf-8', errors='ignore').strip()
                if text:
                    stderr_lines.append(text)

        async for chunk in _read_stdout():
            if await request.is_disconnected():
                process.kill()
                return
            yield chunk

        await _read_stderr()
        return_code = await process.wait()
        if return_code != 0:
            detail = '\n'.join(stderr_lines[-6:]) or '桌面端采集脚本执行失败'
            yield f"data: {json.dumps({'type': 'error', 'data': detail}, ensure_ascii=False)}\n\n"
            return

        if capture_result is None:
            detail = '\n'.join(stderr_lines[-6:]) or '未收到桌面端采集结果'
            yield f"data: {json.dumps({'type': 'error', 'data': detail}, ensure_ascii=False)}\n\n"
            return

        import_result = None
        refreshed = None
        if payload.import_after_capture:
            try:
                yield f"data: {json.dumps({'type': 'import_start', 'message': '采集完成，开始导入到采矿安全智能问答系统…'}, ensure_ascii=False)}\n\n"
                import_bundle = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: _import_capture_package(
                        capture_result=capture_result,
                        account_id=payload.account_id,
                        display_name=str(payload.display_name or ''),
                        clean_after_import=bool(payload.clean_after_import),
                        ingest_after_import=bool(payload.ingest_after_import),
                        force_import=bool(payload.force_import),
                    )
                )
                import_result = import_bundle.get('import_result')
                refreshed = import_bundle.get('refreshed')
                yield f"data: {json.dumps({'type': 'import_done', 'result': import_result}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'data': f'桌面端采集包导入失败: {exc}'}, ensure_ascii=False)}\n\n"
                return

        done_payload = {
            'capture': capture_result,
            'import_result': import_result,
            'profiles': _filter_desktop_profiles(operator_id=payload.operator_id),
            'refreshed': refreshed,
        }
        yield f"data: {json.dumps({'type': 'done', 'data': done_payload}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get("/articles/{account_id}/{article_id}")
def get_article(account_id: str, article_id: str) -> Dict[str, Any]:
    paths = _article_paths(account_id, article_id)
    if not paths["index_path"].exists() and not paths["meta_path"].exists():
        raise HTTPException(status_code=404, detail="文章不存在")
    return _load_article_payload(account_id, article_id)


@router.get("/articles/{account_id}/{article_id}/images/{image_id}")
def get_article_image(account_id: str, article_id: str, image_id: str):
    paths = _article_paths(account_id, article_id)
    is_hires = image_id.endswith("_hires")
    base_image_id = image_id[:-6] if is_hires else image_id
    
    if is_hires:
        paths["images_dir"].mkdir(parents=True, exist_ok=True)
        for candidate in paths["images_dir"].glob(f"{base_image_id}_hires*"):
            if candidate.is_file():
                media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                return FileResponse(candidate, media_type=media_type)
        raise HTTPException(status_code=404, detail="高清版本不存在")
    
    payload = _load_article_payload(account_id, article_id)
    for image in payload.get("images", []):
        if not isinstance(image, dict):
            continue
        if str(image.get("image_id", "")).strip() != image_id:
            continue
        local_path = Path(str(image.get("local_path", "")))
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="图片文件不存在")
        media_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        return FileResponse(local_path, media_type=media_type)
    raise HTTPException(status_code=404, detail="图片不存在")


@router.post("/articles/{account_id}/{article_id}/images/{image_id}/download-hires")
def attempt_hires_image_download(
    account_id: str,
    article_id: str,
    image_id: str,
):
    """Attempt to download a higher-resolution image from source URL and save locally."""
    review_payload = _load_article_payload(account_id, article_id)
    target_image = None
    for image in review_payload.get("images", []):
        if not isinstance(image, dict):
            continue
        if str(image.get("image_id", "")).strip() != image_id:
            continue
        target_image = image
        break

    if not target_image:
        raise HTTPException(status_code=404, detail="图片不存在")

    source_url = str(target_image.get("source_url", "")).strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="源URL不可用")

    hires_attempts = []
    if "/640" in source_url:
        hires_attempts.append(source_url.replace("/640", "/0"))
        hires_attempts.append(source_url.replace("/640", ""))
    hires_attempts.append(source_url + "?imageView2/2/w/1920")
    hires_attempts.append(source_url)

    downloaded = False
    final_path = None
    paths = _article_paths(account_id, article_id)
    paths["images_dir"].mkdir(parents=True, exist_ok=True)
    for attempt_url in hires_attempts:
        try:
            import time
            time.sleep(0.5)
            resp = requests.get(attempt_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and len(resp.content) > 0:
                ext = mimetypes.guess_extension(resp.headers.get("content-type", "image/jpeg")) or ".jpg"
                final_path = paths["images_dir"] / f"{image_id}_hires{ext}"
                final_path.write_bytes(resp.content)
                downloaded = True
                break
        except Exception:
            continue

    if not downloaded:
        return {
            "ok": False,
            "message": "无法下载更高清版本，请使用现有图片",
            "attempts": len(hires_attempts),
        }

    return {
        "ok": True,
        "message": "已下载更高清版本",
        "file_path": str(final_path),
        "file_size_kb": len(final_path.read_bytes()) // 1024,
        "download_image_url": f"/api/wechat-annotator/articles/{account_id}/{article_id}/images/{image_id}_hires",
    }


@router.get("/articles/{account_id}/{article_id}/export-kept-images")
def export_kept_images(account_id: str, article_id: str, metadata_only: bool = False):
    """Export all manually kept images as a ZIP file for browser download."""
    paths = _article_paths(account_id, article_id)
    if not paths["index_path"].exists():
        raise HTTPException(status_code=404, detail="article not found")

    payload = _load_article_payload(account_id, article_id)
    kept_images = [
        image
        for image in payload.get("images", [])
        if isinstance(image, dict) and bool(image.get("keep_for_index", True))
    ]
    if not kept_images:
        raise HTTPException(status_code=400, detail="no kept images found")

    export_version = _compute_export_version(article_id, kept_images)
    if metadata_only:
        return {
            "ok": True,
            "account_id": account_id,
            "article_id": article_id,
            "export_version": export_version,
            "kept_count": len(kept_images),
        }

    zip_buffer = io.BytesIO()
    added_count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for image in kept_images:
            image_id = str(image.get("image_id", "")).strip()
            local_path = Path(str(image.get("local_path", "")).strip())
            display_index = int(image.get("display_index", 0) or 0)

            if local_path.exists() and local_path.is_file():
                arcname = f"{display_index:03d}_{local_path.name}"
                zf.write(local_path, arcname)
                added_count += 1
                logger.info(
                    "export_kept_images article=%s image_id=%s source=local_path path=%s",
                    article_id,
                    image_id,
                    str(local_path),
                )
                continue

            source_url = str(image.get("source_url", "")).strip()
            if source_url.startswith("http://") or source_url.startswith("https://"):
                try:
                    resp = requests.get(source_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200 or not resp.content:
                        continue

                    suffix = mimetypes.guess_extension(resp.headers.get("content-type", "image/jpeg")) or ".jpg"
                    arcname = f"{display_index:03d}_{image_id or 'image'}{suffix}"
                    zf.writestr(arcname, resp.content)
                    added_count += 1
                    logger.info(
                        "export_kept_images article=%s image_id=%s source=source_url url=%s",
                        article_id,
                        image_id,
                        source_url,
                    )
                except Exception:
                    logger.warning(
                        "export_kept_images article=%s image_id=%s source=source_url_failed url=%s",
                        article_id,
                        image_id,
                        source_url,
                    )
                    continue

    if added_count == 0:
        raise HTTPException(status_code=400, detail="no downloadable kept images found")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={article_id}_kept_images.zip",
            "X-Export-Version": export_version,
        },
    )


@router.put("/articles/{account_id}/{article_id}/annotations")
def save_annotations(account_id: str, article_id: str, payload: AnnotationSavePayload):
    paths = _article_paths(account_id, article_id)
    if not paths["ann_path"].exists():
        paths["docs_dir"].mkdir(parents=True, exist_ok=True)

    article_payload = _load_article_payload(account_id, article_id) if paths["index_path"].exists() else {"article": {}, "images": []}
    image_map = {
        str(item.get("image_id", "")).strip(): item
        for item in (article_payload.get("images", []) or [])
        if isinstance(item, dict) and str(item.get("image_id", "")).strip()
    }

    normalized = []
    for item in payload.annotations:
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id", "")).strip()
        if not image_id:
            continue

        image_detail = image_map.get(image_id, {})
        defaults = _build_scene_annotation_defaults(article_payload.get("article", {}), image_detail)
        scene_annotation = item.get("scene_annotation", {}) if isinstance(item.get("scene_annotation", {}), dict) else {}
        scene_from_text = _parse_scene_annotation_text(str(item.get("scene_annotation_text", "")).strip())

        merged_scene = dict(defaults)
        for key in SCENE_ANNOTATION_KEYS:
            value = str(scene_annotation.get(key, "")).strip() or str(scene_from_text.get(key, "")).strip()
            if value:
                merged_scene[key] = value

        manual_summary = str(item.get("manual_summary", "")).strip()
        manual_tags = [str(tag).strip() for tag in (item.get("manual_tags", []) or []) if str(tag).strip()]
        if manual_summary and not str(merged_scene.get("事件名称", "")).strip():
            merged_scene["事件名称"] = manual_summary
        if manual_tags and not str(merged_scene.get("视觉特征", "")).strip():
            merged_scene["视觉特征"] = "|".join(manual_tags)

        scene_annotation_text = str(item.get("scene_annotation_text", "")).strip() or _scene_annotation_to_text(merged_scene)
        if not manual_summary:
            manual_summary = str(merged_scene.get("事件名称", "")).strip()
        if not manual_tags:
            manual_tags = [seg.strip() for seg in str(merged_scene.get("视觉特征", "")).split("|") if seg.strip()]
        manual_notes = str(item.get("manual_notes", "")).strip() or scene_annotation_text

        normalized.append(
            {
                "image_id": image_id,
                "local_path": item.get("local_path", ""),
                "manual_summary": manual_summary,
                "manual_tags": manual_tags,
                "manual_notes": manual_notes,
                "scene_annotation": merged_scene,
                "scene_annotation_text": scene_annotation_text,
                "keep_for_index": bool(item.get("keep_for_index", True)),
            }
        )

    ann_payload = {
        "article_id": article_id,
        "account_id": account_id,
        "updated_at": datetime.now().isoformat(),
        "last_instruction": payload.last_instruction or "",
        "annotations": normalized,
    }

    compare_payload = {
        "article_id": article_id,
        "account_id": account_id,
        "last_instruction": payload.last_instruction or "",
        "annotations": normalized,
    }
    annotation_version = hashlib.sha1(
        json.dumps(compare_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if paths["ann_path"].exists():
        try:
            existing_payload = json.loads(paths["ann_path"].read_text(encoding="utf-8"))
            existing_compare = {
                "article_id": article_id,
                "account_id": account_id,
                "last_instruction": existing_payload.get("last_instruction", ""),
                "annotations": existing_payload.get("annotations", []),
            }
            existing_version = hashlib.sha1(
                json.dumps(existing_compare, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if existing_version == annotation_version:
                return {
                    "ok": True,
                    "duplicate": True,
                    "annotation_version": annotation_version,
                    "annotations_path": str(paths["ann_path"]),
                    "count": len(normalized),
                    "sync": {"ok": True, "skipped": True},
                }
        except Exception:
            pass

    paths["ann_path"].write_text(json.dumps(ann_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_result = _sync_annotations_safe(account_id, article_id)
    selected_images_path = paths["docs_dir"] / f"{article_id}.selected_images.json"
    try:
        payload_detail = _load_article_payload(account_id, article_id)
        selected_images = [
            {
                "image_id": image.get("image_id", ""),
                "local_path": image.get("local_path", ""),
                "url": image.get("url", ""),
                "display_index": image.get("display_index", 0),
                "manual_summary": image.get("manual_summary", ""),
                "manual_tags": image.get("manual_tags", []),
                "manual_notes": image.get("manual_notes", ""),
                "scene_annotation": image.get("scene_annotation", {}),
                "scene_annotation_text": image.get("scene_annotation_text", ""),
                "keep_for_index": image.get("keep_for_index", True),
                "indexable": image.get("indexable", False),
                "api_summary": image.get("api_summary", ""),
            }
            for image in payload_detail.get("images", [])
            if isinstance(image, dict) and bool(image.get("keep_for_index", True))
        ]
        selected_payload = {
            "article_id": article_id,
            "account_id": account_id,
            "generated_at": datetime.now().isoformat(),
            "selected_count": len(selected_images),
            "selected_images": selected_images,
        }
        selected_images_path.write_text(json.dumps(selected_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        selected_images_path = None

    response = {
        "ok": True,
        "duplicate": False,
        "annotation_version": annotation_version,
        "annotations_path": str(paths["ann_path"]),
        "count": len(normalized),
        "sync": sync_result,
    }
    if selected_images_path is not None:
        response.update({"selected_images_path": str(selected_images_path)})
    return response


@router.post("/articles/{account_id}/{article_id}/apply-instruction")
def apply_instruction(account_id: str, article_id: str, payload: NaturalLanguagePayload):
    if not payload.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction is empty")

    result = apply_nl_annotations(account_id=account_id, article_id=article_id, instruction=payload.instruction)
    sync_result = _sync_annotations_safe(account_id, article_id)
    return {
        "ok": True,
        **result,
        "article_id": article_id,
        "account_id": account_id,
        "sync": sync_result,
        "review_payload": _load_article_payload(account_id, article_id),
    }


@router.post("/articles/{account_id}/{article_id}/autofill")
def autofill_annotations(account_id: str, article_id: str, payload: AutoFillPayload):
    return _autofill_annotations(account_id=account_id, article_id=article_id, overwrite_existing=payload.overwrite_existing)


@router.get("/articles/{account_id}/{article_id}/review")
def get_review_payload(account_id: str, article_id: str):
    return _load_article_payload(account_id, article_id)


@router.post("/crawl/article-urls")
def crawl_article_urls(payload: CrawlArticleUrlsPayload) -> Dict[str, Any]:
    crawl_conf = _resolve_crawl_payload(payload)
    account_id = crawl_conf["account_id"]
    normalized_seed_urls = crawl_conf["normalized_seed_urls"]
    registry_summary = None
    previous_articles = list_articles(account_id=account_id).get("articles", []) if account_id else []
    previous_article_ids = {
        str(item.get("article_id") or "").strip()
        for item in previous_articles
        if str(item.get("article_id") or "").strip()
    }

    source_dir = WECHAT_ROOT.parent / "api_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_file = source_dir / f"{account_id}_{ts}.json"

    source_payload = {
        "accounts": [
            {
                "account_id": account_id,
                "display_name": crawl_conf["display_name"],
                "enabled": True,
                "frequency_days": crawl_conf["frequency_days"],
                "window_days": crawl_conf["window_days"],
                "max_links_from_history": crawl_conf["max_links_from_history"],
                "history_urls": [url for url in normalized_seed_urls if _normalize_wechat_history_url(url)],
                "article_urls": [url for url in normalized_seed_urls if _normalize_wechat_article_url(url)],
            }
        ]
    }

    if not normalized_seed_urls:
        refreshed = list_articles(account_id=account_id)
        return {
            "ok": True,
            "account_id": account_id,
            "input_url_count": len(payload.article_urls),
            "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
            "duplicate_article_urls": crawl_conf["duplicate_urls"],
            "resolved_url_count": 0,
            "resolved_article_urls": [],
            "run_result": {
                "processed_articles": 0,
                "new_articles": 0,
                "skipped_time_window": 0,
                "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                "blocked_articles": [],
                "failed_articles": [],
                "created_articles": [],
                "skipped_reason": "all_duplicates",
            },
            "created_articles": [],
            "local_account_registry": registry_summary,
            "refreshed": refreshed,
        }

    source_file.write_text(json.dumps(source_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        from run_wechat_collector import WeChatCollectorAgent

        conf = _build_wechat_runtime_config()
        agent = WeChatCollectorAgent(conf=conf, source_file=str(source_file))
        run_result = agent.run(
            dry_run=crawl_conf["dry_run"],
            ingest=False,
            write_report=not crawl_conf["dry_run"],
            report_dir=None,
            force=crawl_conf["force"],
        )
        if not crawl_conf["dry_run"]:
            registry_summary = _persist_wechat_local_account(
                account_id=account_id,
                display_name=crawl_conf["display_name"],
                seed_urls=crawl_conf["input_normalized_seed_urls"],
                frequency_days=crawl_conf["frequency_days"],
                window_days=crawl_conf["window_days"],
                max_links_from_history=crawl_conf["max_links_from_history"],
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"公众号抓取失败: {exc}") from exc
    finally:
        try:
            source_file.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary source file: %s", source_file)

    refreshed = list_articles(account_id=account_id)
    created_articles: List[Dict[str, str]] = []
    for item in (refreshed.get("articles") or []):
        article_id = str(item.get("article_id") or "").strip()
        if not article_id or article_id in previous_article_ids:
            continue
        created_articles.append(
            {
                "account_id": str(item.get("account_id") or account_id).strip() or account_id,
                "article_id": article_id,
                "title": str(item.get("title") or article_id).strip(),
                "source_link": str(item.get("source_link") or "").strip(),
            }
        )
    if created_articles and isinstance(run_result, dict):
        run_result["created_articles"] = created_articles
    return {
        "ok": True,
        "account_id": account_id,
        "input_url_count": len(payload.article_urls),
        "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
        "duplicate_article_urls": crawl_conf["duplicate_urls"],
        "resolved_url_count": len(normalized_seed_urls),
        "resolved_article_urls": normalized_seed_urls,
        "run_result": run_result,
        "created_articles": created_articles,
        "local_account_registry": registry_summary,
        "refreshed": refreshed,
    }


@router.post("/crawl/article-urls/stream")
async def crawl_article_urls_stream(payload: CrawlArticleUrlsPayload, request: Request):
    crawl_conf = _resolve_crawl_payload(payload)

    async def stream():
        try:
            from run_wechat_collector import WeChatCollectorAgent, AccountConfig

            yield f"data: {json.dumps({'type': 'loading', 'message': '正在初始化采集器…'}, ensure_ascii=False)}\n\n"

            conf = _build_wechat_runtime_config()
            agent = WeChatCollectorAgent(conf=conf, source_file=conf.WECHAT_SOURCE_FILE)
            account = AccountConfig(
                account_id=crawl_conf["account_id"],
                display_name=crawl_conf["display_name"],
                enabled=True,
                frequency_days=crawl_conf["frequency_days"],
                window_days=crawl_conf["window_days"],
                tags=[],
                article_urls=[url for url in crawl_conf["normalized_seed_urls"] if _normalize_wechat_article_url(url)],
                history_urls=[url for url in crawl_conf["normalized_seed_urls"] if _normalize_wechat_history_url(url)],
                max_links_from_history=crawl_conf["max_links_from_history"],
            )

            if not crawl_conf["force"]:
                state = agent._load_state()
                if not agent._should_run_account(account, state, datetime.now()):
                    yield f"data: {json.dumps({'type': 'done', 'run_result': {'processed_articles': 0, 'new_articles': 0, 'skipped_reason': 'frequency_control'}}, ensure_ascii=False)}\n\n"
                    return

            loop = asyncio.get_event_loop()
            yield f"data: {json.dumps({'type': 'loading', 'message': '正在解析公众号链接…'}, ensure_ascii=False)}\n\n"
            article_urls = await loop.run_in_executor(None, lambda: agent._resolve_account_article_urls(account))
            article_urls = article_urls[: agent.conf.WECHAT_MAX_ARTICLES_PER_ACCOUNT]

            if not article_urls:
                if crawl_conf["duplicate_urls"]:
                    yield f"data: {json.dumps({'type': 'done', 'run_result': {'processed_articles': len(crawl_conf['duplicate_urls']), 'new_articles': 0, 'skipped_reason': 'all_duplicates', 'duplicate_url_count': len(crawl_conf['duplicate_urls'])}, 'duplicate_article_urls': crawl_conf['duplicate_urls'], 'refreshed': list_articles(account_id=account.account_id)}, ensure_ascii=False)}\n\n"
                    return
                yield f"data: {json.dumps({'type': 'error', 'data': '没有可抓取的有效公众号链接'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'resolved', 'total': len(article_urls), 'urls': article_urls, 'duplicate_url_count': len(crawl_conf['duplicate_urls']), 'duplicate_urls': crawl_conf['duplicate_urls']}, ensure_ascii=False)}\n\n"

            account_dir = agent.output_dir / account.account_id
            docs_dir = account_dir / 'docs'
            meta_dir = account_dir / 'meta'
            image_dir = account_dir / 'images'
            if not crawl_conf["dry_run"]:
                docs_dir.mkdir(parents=True, exist_ok=True)
                meta_dir.mkdir(parents=True, exist_ok=True)
                image_dir.mkdir(parents=True, exist_ok=True)

            processed = 0
            new_articles = 0
            skipped_time_window = 0
            blocked_articles: List[Dict[str, str]] = []
            failed_articles: List[Dict[str, str]] = []
            created_articles: List[Dict[str, str]] = []

            for idx, article_url in enumerate(article_urls, start=1):
                if await request.is_disconnected():
                    logger.info("wechat crawl stream disconnected by client, account=%s", account.account_id)
                    break
                yield f"data: {json.dumps({'type': 'progress', 'current': idx, 'total': len(article_urls), 'url': article_url}, ensure_ascii=False)}\n\n"
                try:
                    record = await loop.run_in_executor(
                        None,
                        lambda u=article_url: agent._collect_single_article(account, u, image_dir),
                    )
                    processed += 1
                    if record is None:
                        skipped_time_window += 1
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'skipped_time_window', 'current': idx, 'total': len(article_urls), 'url': article_url}, ensure_ascii=False)}\n\n"
                        continue

                    if not crawl_conf["dry_run"]:
                        await loop.run_in_executor(
                            None,
                            lambda r=record: agent._write_article_files(r, docs_dir, meta_dir),
                        )
                    new_articles += 1
                    created_articles.append({
                        'account_id': account.account_id,
                        'article_id': record.article_id,
                        'title': record.title,
                        'source_link': record.url,
                    })

                    yield f"data: {json.dumps({'type': 'item_done', 'status': 'ok', 'current': idx, 'total': len(article_urls), 'url': article_url, 'article_id': record.article_id, 'title': record.title}, ensure_ascii=False)}\n\n"
                except Exception as exc:
                    error_text = str(exc)
                    if error_text.startswith('page_quality_guard_blocked:'):
                        blocked_reason = error_text.split(':', 1)[1].strip()
                        blocked_articles.append({"url": article_url, "reason": blocked_reason})
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'blocked_page', 'current': idx, 'total': len(article_urls), 'url': article_url, 'reason': blocked_reason}, ensure_ascii=False)}\n\n"
                    else:
                        failed_articles.append({"url": article_url, "error": error_text})
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'failed', 'current': idx, 'total': len(article_urls), 'url': article_url, 'error': error_text}, ensure_ascii=False)}\n\n"

            if not crawl_conf["dry_run"]:
                state = agent._load_state()
                state.setdefault('accounts', {})[account.account_id] = {
                    'last_run_at': datetime.now().isoformat(),
                    'last_processed_articles': processed,
                    'last_new_articles': new_articles,
                }
                agent._write_state(state)

            run_result = {
                'processed_articles': processed,
                'new_articles': new_articles,
                'skipped_time_window': skipped_time_window,
                'duplicate_url_count': len(crawl_conf['duplicate_urls']),
                'blocked_articles': blocked_articles,
                'failed_articles': failed_articles,
                'created_articles': created_articles,
            }
            refreshed = list_articles(account_id=account.account_id)
            yield f"data: {json.dumps({'type': 'done', 'run_result': run_result, 'duplicate_article_urls': crawl_conf['duplicate_urls'], 'created_articles': created_articles, 'refreshed': refreshed}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post("/crawl/account-history/stream")
async def crawl_account_history_stream(payload: CrawlHistoryAccountPayload, request: Request):
    history_conf = _resolve_history_account_payload(payload)

    async def stream():
        try:
            from run_wechat_collector import WeChatCollectorAgent, AccountConfig

            yield f"data: {json.dumps({'type': 'loading', 'message': '正在按公众号历史页准备抓取…'}, ensure_ascii=False)}\n\n"

            conf = _build_wechat_runtime_config()
            agent = WeChatCollectorAgent(conf=conf, source_file=conf.WECHAT_SOURCE_FILE)
            account = AccountConfig(
                account_id=history_conf['account_id'],
                display_name=history_conf['display_name'],
                enabled=True,
                frequency_days=history_conf['frequency_days'],
                window_days=history_conf['window_days'],
                tags=[],
                article_urls=[],
                history_urls=[history_conf['history_url']],
                max_links_from_history=history_conf['max_links_from_history'],
            )
            registry_summary = None
            if not history_conf['dry_run']:
                registry_summary = _persist_wechat_local_account(
                    account_id=history_conf['account_id'],
                    display_name=history_conf['display_name'],
                    seed_urls=[history_conf['history_url']],
                    frequency_days=history_conf['frequency_days'],
                    window_days=history_conf['window_days'],
                    max_links_from_history=history_conf['max_links_from_history'],
                )

            if not history_conf['force']:
                state = agent._load_state()
                if not agent._should_run_account(account, state, datetime.now()):
                    yield f"data: {json.dumps({'type': 'done', 'run_result': {'processed_articles': 0, 'new_articles': 0, 'skipped_reason': 'frequency_control'}, 'local_account_registry': registry_summary, 'refreshed': list_articles(account_id=account.account_id)}, ensure_ascii=False)}\n\n"
                    return

            loop = asyncio.get_event_loop()
            yield f"data: {json.dumps({'type': 'loading', 'message': '正在解析历史页文章链接…'}, ensure_ascii=False)}\n\n"
            article_urls = await loop.run_in_executor(None, lambda: agent._resolve_account_article_urls(account))
            article_urls = article_urls[: agent.conf.WECHAT_MAX_ARTICLES_PER_ACCOUNT]
            existing_urls = await loop.run_in_executor(None, lambda: agent._load_existing_source_links(agent.output_dir / account.account_id))
            article_urls = [url for url in article_urls if url not in existing_urls]

            if not article_urls:
                yield f"data: {json.dumps({'type': 'done', 'run_result': {'processed_articles': len(existing_urls), 'new_articles': 0, 'skipped_reason': 'all_duplicates_or_empty_history'}, 'local_account_registry': registry_summary, 'refreshed': list_articles(account_id=account.account_id)}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'resolved', 'total': len(article_urls), 'urls': article_urls}, ensure_ascii=False)}\n\n"

            account_dir = agent.output_dir / account.account_id
            docs_dir = account_dir / 'docs'
            meta_dir = account_dir / 'meta'
            image_dir = account_dir / 'images'
            if not history_conf['dry_run']:
                docs_dir.mkdir(parents=True, exist_ok=True)
                meta_dir.mkdir(parents=True, exist_ok=True)
                image_dir.mkdir(parents=True, exist_ok=True)

            processed = 0
            new_articles = 0
            skipped_time_window = 0
            blocked_articles: List[Dict[str, str]] = []
            failed_articles: List[Dict[str, str]] = []
            created_articles: List[Dict[str, str]] = []

            for idx, article_url in enumerate(article_urls, start=1):
                if await request.is_disconnected():
                    logger.info('wechat history crawl stream disconnected by client, account=%s', account.account_id)
                    break
                yield f"data: {json.dumps({'type': 'progress', 'current': idx, 'total': len(article_urls), 'url': article_url}, ensure_ascii=False)}\n\n"
                try:
                    record = await loop.run_in_executor(None, lambda u=article_url: agent._collect_single_article(account, u, image_dir))
                    processed += 1
                    if record is None:
                        skipped_time_window += 1
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'skipped_time_window', 'current': idx, 'total': len(article_urls), 'url': article_url}, ensure_ascii=False)}\n\n"
                        continue
                    if not history_conf['dry_run']:
                        await loop.run_in_executor(None, lambda r=record: agent._write_article_files(r, docs_dir, meta_dir))
                    new_articles += 1
                    created_articles.append({
                        'account_id': account.account_id,
                        'article_id': record.article_id,
                        'title': record.title,
                        'source_link': record.url,
                    })
                    yield f"data: {json.dumps({'type': 'item_done', 'status': 'ok', 'current': idx, 'total': len(article_urls), 'url': article_url, 'article_id': record.article_id, 'title': record.title}, ensure_ascii=False)}\n\n"
                except Exception as exc:
                    error_text = str(exc)
                    if error_text.startswith('page_quality_guard_blocked:'):
                        blocked_reason = error_text.split(':', 1)[1].strip()
                        blocked_articles.append({'url': article_url, 'reason': blocked_reason})
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'blocked_page', 'current': idx, 'total': len(article_urls), 'url': article_url, 'reason': blocked_reason}, ensure_ascii=False)}\n\n"
                    else:
                        failed_articles.append({'url': article_url, 'error': error_text})
                        yield f"data: {json.dumps({'type': 'item_done', 'status': 'failed', 'current': idx, 'total': len(article_urls), 'url': article_url, 'error': error_text}, ensure_ascii=False)}\n\n"

            if not history_conf['dry_run']:
                state = agent._load_state()
                state.setdefault('accounts', {})[account.account_id] = {
                    'last_run_at': datetime.now().isoformat(),
                    'last_processed_articles': processed,
                    'last_new_articles': new_articles,
                }
                agent._write_state(state)

            run_result = {
                'processed_articles': processed,
                'new_articles': new_articles,
                'skipped_time_window': skipped_time_window,
                'blocked_articles': blocked_articles,
                'failed_articles': failed_articles,
                'created_articles': created_articles,
            }
            refreshed = list_articles(account_id=account.account_id)
            yield f"data: {json.dumps({'type': 'done', 'run_result': run_result, 'created_articles': created_articles, 'local_account_registry': registry_summary, 'refreshed': refreshed}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post("/agent")
@router.post("/agent/command")
def run_agent_command(payload: AgentCommandPayload) -> Dict[str, Any]:
    parsed = _parse_agent_command(payload)
    account_id = str(parsed.get("account_id") or parsed.get("default_account_id") or "").strip()
    if not account_id and not parsed.get("urls"):
        raise HTTPException(status_code=400, detail="无法确定 account_id，请在指令中增加 '账号: xxx' 或 default_account_id")

    result: Dict[str, Any] = {
        "ok": True,
        "parsed": parsed,
        "steps": [],
        "annotation_entry": {
            "path": "/wechat-annotator",
            "account_id": account_id,
            "note": "可随时进入公众号标注页面进行人工标注",
        },
    }

    observation = _build_agent_observation(parsed)
    observe_eval = _evaluate_agent_step("observe", observation, parsed=parsed)
    result["steps"].append({"name": "observe", "status": observe_eval["status"], "result": observation, "evaluation": observe_eval})

    decision = _decide_agent_collect_action(parsed, observation)
    reason_eval = _evaluate_agent_step("reason", decision, parsed=parsed)
    result["steps"].append({"name": "reason", "status": reason_eval["status"], "result": decision, "evaluation": reason_eval})

    collect_action = str(decision.get("action") or "")
    clean_article_ids: List[str] = []

    if _agent_plan_step_enabled(parsed, "collect"):
        collect_exec = _execute_agent_collect_sync(parsed, decision, account_id)
        collect_name = str(collect_exec.get("step_name") or "collect")
        collect_result = collect_exec.get("result") or {}
        if isinstance(collect_result, dict):
            clean_article_ids = _extract_agent_collect_article_ids(collect_result)
        account_id = str(collect_exec.get("account_id") or account_id).strip() or account_id
        collect_eval = _evaluate_agent_step("collect", collect_result if isinstance(collect_result, dict) else {}, parsed=parsed, decision=decision)
        result["steps"].append({"name": collect_name, "status": collect_eval["status"], "result": collect_result, "evaluation": collect_eval})
        replan = _build_agent_replan(parsed, observation, decision, collect_eval)
        if replan:
            result["steps"].append({"name": "replan", "status": "done", "result": replan, "evaluation": {"success": True, "retryable": False, "status": "done", "summary": str(replan.get("reason") or "").strip(), "failure_reason": ""}})
            parsed = _apply_agent_replan(parsed, replan)
            observation = _build_agent_observation(parsed)
            observe_eval = _evaluate_agent_step("observe", observation, parsed=parsed)
            result["steps"].append({"name": "observe", "status": observe_eval["status"], "result": observation, "evaluation": observe_eval})
            decision = _decide_agent_collect_action(parsed, observation)
            reason_eval = _evaluate_agent_step("reason", decision, parsed=parsed)
            result["steps"].append({"name": "reason", "status": reason_eval["status"], "result": decision, "evaluation": reason_eval})
            collect_action = str(decision.get("action") or "")
            collect_exec = _execute_agent_collect_sync(parsed, decision, account_id)
            collect_name = str(collect_exec.get("step_name") or "collect")
            collect_result = collect_exec.get("result") or {}
            if isinstance(collect_result, dict):
                clean_article_ids = _extract_agent_collect_article_ids(collect_result)
            account_id = str(collect_exec.get("account_id") or account_id).strip() or account_id
            collect_eval = _evaluate_agent_step("collect", collect_result if isinstance(collect_result, dict) else {}, parsed=parsed, decision=decision)
            result["steps"].append({"name": collect_name, "status": collect_eval["status"], "result": collect_result, "evaluation": collect_eval})

    should_run_clean = _agent_plan_step_enabled(parsed, "clean") and (not _agent_plan_step_enabled(parsed, "collect") or collect_action in {"crawl_seed_urls", "crawl_history_url", "desktop_capture", "skip_collect"})

    if should_run_clean:
        try:
            clean_result = _run_agent_clean_step(parsed, account_id, clean_article_ids)
            clean_eval = _evaluate_agent_step("clean", clean_result, parsed=parsed)
            result["steps"].append({"name": "clean", "status": clean_eval["status"], "result": clean_result, "evaluation": clean_eval})
            ingest_eval = _evaluate_agent_step("ingest", clean_result, parsed=parsed)
            result["steps"].append({"name": "ingest", "status": ingest_eval["status"], "result": clean_result, "evaluation": ingest_eval})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"清洗/入库执行失败: {exc}") from exc

    _maybe_attach_agent_task(result, parsed, account_id, clean_article_ids)
    _maybe_run_governance_handoff(result, account_id, clean_article_ids)
    _maybe_run_evaluation_handoff(result, account_id, clean_article_ids)
    result["refreshed"] = list_articles(account_id=account_id)
    result["updated_session_memory"] = _build_agent_updated_session_memory(parsed.get("session_memory") or {}, parsed, result["steps"], account_id)
    result["orchestration"] = _build_multi_agent_orchestration(result, parsed, account_id)
    return result


@router.get("/agent/tasks")
def list_agent_tasks(limit: int = 20) -> Dict[str, Any]:
    return {"tasks": _list_agent_tasks(limit=limit)}


@router.get("/agent/tasks/{task_id}")
def get_agent_task(task_id: str) -> Dict[str, Any]:
    return {"task": _load_agent_task(task_id)}


@router.get("/agent/evaluation/history")
def get_evaluation_history(limit: int = 12) -> Dict[str, Any]:
    return {"history": _load_evaluation_history(limit=limit)}


@router.get("/agent/evaluation/history/compare")
def get_evaluation_history_compare(account_id: str = "") -> Dict[str, Any]:
    return _build_evaluation_compare_payload(account_id=account_id)


@router.post("/agent/evaluation/history/{history_id}/rerun")
def rerun_evaluation_history(history_id: str) -> Dict[str, Any]:
    entry = _find_evaluation_history_entry(history_id)
    if not entry:
        raise HTTPException(status_code=404, detail="未找到对应的评测历史记录")
    result = _rerun_evaluation_from_history_entry(entry)
    return {"result": result}


@router.get("/agent/session-state")
def get_agent_session_state(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    payload = _require_request_user(authorization)
    user_id = str(payload.get("user_id") or payload.get("username") or "").strip()
    return {"state": _load_agent_session_state(user_id)}


@router.put("/agent/session-state")
def save_agent_session_state(payload: AgentSessionStatePayload, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    user = _require_request_user(authorization)
    user_id = str(user.get("user_id") or user.get("username") or "").strip()
    return {"state": _write_agent_session_state(user_id, payload.state)}


@router.delete("/agent/session-state")
def delete_agent_session_state(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    user = _require_request_user(authorization)
    user_id = str(user.get("user_id") or user.get("username") or "").strip()
    _delete_agent_session_state(user_id)
    return {"ok": True}


@router.post("/agent/tasks/{task_id}/retry")
def retry_agent_task(task_id: str) -> Dict[str, Any]:
    return {"task": _retry_agent_task(task_id)}


@router.post("/agent/governance")
def run_knowledge_governance(payload: KnowledgeGovernancePayload) -> Dict[str, Any]:
    return _run_knowledge_governance_agent(payload)


@router.post("/agent/evaluation")
def run_evaluation_optimization(payload: EvaluationOptimizationPayload) -> Dict[str, Any]:
    return _run_evaluation_optimization_agent(payload)


@router.post("/agent/stream")
@router.post("/agent/command/stream")
async def run_agent_command_stream(payload: AgentCommandPayload, request: Request):
    parsed = _parse_agent_command(payload)
    initial_account_id = str(parsed.get("account_id") or parsed.get("default_account_id") or "").strip()
    if not initial_account_id and not parsed.get("urls"):
        raise HTTPException(status_code=400, detail="无法确定 account_id，请在指令中增加 '账号: xxx' 或 default_account_id")

    async def stream():
        async def stream_crawl_collect_events(crawl_payload: CrawlArticleUrlsPayload):
            crawl_conf = _resolve_crawl_payload(crawl_payload)
            from run_wechat_collector import WeChatCollectorAgent, AccountConfig

            conf = _build_wechat_runtime_config()
            agent = WeChatCollectorAgent(conf=conf, source_file=conf.WECHAT_SOURCE_FILE)
            account = AccountConfig(
                account_id=crawl_conf["account_id"],
                display_name=crawl_conf["display_name"],
                enabled=True,
                frequency_days=crawl_conf["frequency_days"],
                window_days=crawl_conf["window_days"],
                tags=[],
                article_urls=[url for url in crawl_conf["normalized_seed_urls"] if _normalize_wechat_article_url(url)],
                history_urls=[url for url in crawl_conf["normalized_seed_urls"] if _normalize_wechat_history_url(url)],
                max_links_from_history=crawl_conf["max_links_from_history"],
            )

            yield {"type": "loading", "message": "正在初始化公众号采集器…"}

            if not crawl_conf["force"]:
                state = agent._load_state()
                if not agent._should_run_account(account, state, datetime.now()):
                    yield {
                        "type": "done",
                        "result": {
                            "ok": True,
                            "account_id": account.account_id,
                            "input_url_count": len(crawl_payload.article_urls),
                            "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                            "duplicate_article_urls": crawl_conf["duplicate_urls"],
                            "resolved_url_count": 0,
                            "resolved_article_urls": [],
                            "run_result": {"processed_articles": 0, "new_articles": 0, "skipped_reason": "frequency_control"},
                            "local_account_registry": None,
                            "refreshed": list_articles(account_id=account.account_id),
                        },
                    }
                    return

            yield {"type": "loading", "message": "正在解析公众号链接并准备文章队列…"}
            article_urls = await loop.run_in_executor(None, lambda: agent._resolve_account_article_urls(account))
            article_urls = article_urls[: agent.conf.WECHAT_MAX_ARTICLES_PER_ACCOUNT]

            if not article_urls:
                if crawl_conf["duplicate_urls"]:
                    yield {
                        "type": "done",
                        "result": {
                            "ok": True,
                            "account_id": account.account_id,
                            "input_url_count": len(crawl_payload.article_urls),
                            "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                            "duplicate_article_urls": crawl_conf["duplicate_urls"],
                            "resolved_url_count": 0,
                            "resolved_article_urls": [],
                            "run_result": {
                                "processed_articles": len(crawl_conf["duplicate_urls"]),
                                "new_articles": 0,
                                "skipped_reason": "all_duplicates",
                                "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                            },
                            "local_account_registry": None,
                            "refreshed": list_articles(account_id=account.account_id),
                        },
                    }
                    return
                yield {"type": "error", "message": "没有可抓取的有效公众号链接"}
                return

            yield {
                "type": "resolved",
                "total": len(article_urls),
                "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                "duplicate_urls": crawl_conf["duplicate_urls"],
            }

            account_dir = agent.output_dir / account.account_id
            docs_dir = account_dir / 'docs'
            meta_dir = account_dir / 'meta'
            image_dir = account_dir / 'images'
            if not crawl_conf["dry_run"]:
                docs_dir.mkdir(parents=True, exist_ok=True)
                meta_dir.mkdir(parents=True, exist_ok=True)
                image_dir.mkdir(parents=True, exist_ok=True)

            processed = 0
            new_articles = 0
            skipped_time_window = 0
            blocked_articles: List[Dict[str, str]] = []
            failed_articles: List[Dict[str, str]] = []
            created_articles: List[Dict[str, str]] = []

            for idx, article_url in enumerate(article_urls, start=1):
                if await request.is_disconnected():
                    return
                yield {"type": "progress", "current": idx, "total": len(article_urls), "url": article_url}
                try:
                    record = await loop.run_in_executor(None, lambda u=article_url: agent._collect_single_article(account, u, image_dir))
                    processed += 1
                    if record is None:
                        skipped_time_window += 1
                        yield {"type": "item_done", "status": "skipped_time_window", "current": idx, "total": len(article_urls), "url": article_url}
                        continue
                    if not crawl_conf["dry_run"]:
                        await loop.run_in_executor(None, lambda r=record: agent._write_article_files(r, docs_dir, meta_dir))
                    new_articles += 1
                    created_articles.append({
                        "account_id": account.account_id,
                        "article_id": record.article_id,
                        "title": record.title,
                        "source_link": record.url,
                    })
                    yield {"type": "item_done", "status": "ok", "current": idx, "total": len(article_urls), "url": article_url, "article_id": record.article_id, "title": record.title}
                except Exception as exc:
                    error_text = str(exc)
                    if error_text.startswith('page_quality_guard_blocked:'):
                        blocked_reason = error_text.split(':', 1)[1].strip()
                        blocked_articles.append({"url": article_url, "reason": blocked_reason})
                        yield {"type": "item_done", "status": "blocked_page", "current": idx, "total": len(article_urls), "url": article_url, "reason": blocked_reason}
                    else:
                        failed_articles.append({"url": article_url, "error": error_text})
                        yield {"type": "item_done", "status": "failed", "current": idx, "total": len(article_urls), "url": article_url, "error": error_text}

            registry_summary = None
            if not crawl_conf["dry_run"]:
                state = agent._load_state()
                state.setdefault('accounts', {})[account.account_id] = {
                    'last_run_at': datetime.now().isoformat(),
                    'last_processed_articles': processed,
                    'last_new_articles': new_articles,
                }
                agent._write_state(state)
                registry_summary = _persist_wechat_local_account(
                    account_id=account.account_id,
                    display_name=crawl_conf["display_name"],
                    seed_urls=crawl_conf["input_normalized_seed_urls"],
                    frequency_days=crawl_conf["frequency_days"],
                    window_days=crawl_conf["window_days"],
                    max_links_from_history=crawl_conf["max_links_from_history"],
                )

            yield {
                "type": "done",
                "result": {
                    "ok": True,
                    "account_id": account.account_id,
                    "input_url_count": len(crawl_payload.article_urls),
                    "duplicate_url_count": len(crawl_conf["duplicate_urls"]),
                    "duplicate_article_urls": crawl_conf["duplicate_urls"],
                    "resolved_url_count": len(article_urls),
                    "resolved_article_urls": article_urls,
                    "run_result": {
                        "processed_articles": processed,
                        "new_articles": new_articles,
                        "skipped_time_window": skipped_time_window,
                        "duplicate_url_count": len(crawl_conf['duplicate_urls']),
                        "blocked_articles": blocked_articles,
                        "failed_articles": failed_articles,
                        "created_articles": created_articles,
                    },
                    "created_articles": created_articles,
                    "local_account_registry": registry_summary,
                    "refreshed": list_articles(account_id=account.account_id),
                },
            }

        async def stream_executor_notes(fn, messages: List[str], interval_sec: float = 3.0):
            future = loop.run_in_executor(None, fn)
            note_index = 0
            while True:
                try:
                    result = await asyncio.wait_for(asyncio.shield(future), timeout=interval_sec)
                    yield {"type": "result", "result": result}
                    return
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        yield {"type": "disconnected"}
                        return
                    if messages:
                        message = messages[min(note_index, len(messages) - 1)]
                        note_index += 1
                        yield {"type": "note", "message": message}

        try:
            loop = asyncio.get_event_loop()
            current_parsed = dict(parsed)
            current_account_id = initial_account_id
            if await request.is_disconnected():
                return

            yield f"data: {json.dumps({'type': 'loading', 'message': '正在解析 Agent 指令…'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'parsed', 'data': current_parsed}, ensure_ascii=False)}\n\n"

            steps: List[Dict[str, Any]] = []

            if not bool(current_parsed.get('capability_supported', True)):
                refreshed = await loop.run_in_executor(None, lambda: list_articles(account_id=current_account_id))
                done_payload = {
                    "ok": True,
                    "parsed": current_parsed,
                    "steps": steps,
                    "annotation_entry": {
                        "path": "/wechat-annotator",
                        "account_id": current_account_id,
                        "note": "当前仅返回能力说明，未进入抓取、清洗或入库阶段",
                    },
                    "refreshed": refreshed,
                    "updated_session_memory": _build_agent_updated_session_memory(current_parsed.get("session_memory") or {}, current_parsed, steps, current_account_id),
                }
                _maybe_run_governance_handoff(done_payload, current_account_id, clean_article_ids)
                _maybe_run_evaluation_handoff(done_payload, current_account_id, clean_article_ids)
                done_payload["orchestration"] = _build_multi_agent_orchestration(done_payload, current_parsed, current_account_id)
                yield f"data: {json.dumps({'type': 'done', 'data': done_payload}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'step_start', 'name': 'observe', 'message': '正在观察账号、cookie 与历史页状态…'}, ensure_ascii=False)}\n\n"
            observation = await loop.run_in_executor(None, lambda: _build_agent_observation(current_parsed))
            observe_eval = _evaluate_agent_step("observe", observation, parsed=current_parsed)
            observe_step = {"name": "observe", "status": observe_eval["status"], "result": observation, "evaluation": observe_eval}
            steps.append(observe_step)
            yield f"data: {json.dumps({'type': 'step_done', 'name': 'observe', 'result': observation}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'step_start', 'name': 'reason', 'message': '正在决定本轮采集入口…'}, ensure_ascii=False)}\n\n"
            decision = await loop.run_in_executor(None, lambda: _decide_agent_collect_action(current_parsed, observation))
            reason_eval = _evaluate_agent_step("reason", decision, parsed=current_parsed)
            reason_step = {"name": "reason", "status": reason_eval["status"], "result": decision, "evaluation": reason_eval}
            steps.append(reason_step)
            yield f"data: {json.dumps({'type': 'step_done', 'name': 'reason', 'result': decision}, ensure_ascii=False)}\n\n"

            collect_action = str(decision.get("action") or "")
            clean_article_ids: List[str] = []

            if _agent_plan_step_enabled(current_parsed, "collect"):
                action = collect_action
                if action in {"crawl_seed_urls", "crawl_history_url"}:
                    decided_account_id = str(decision.get("account_id") or current_account_id).strip() or current_account_id
                    yield f"data: {json.dumps({'type': 'step_start', 'name': 'collect', 'message': '开始抓取未采集公众号文章…'}, ensure_ascii=False)}\n\n"
                    crawl_payload = CrawlArticleUrlsPayload(
                        account_id=decided_account_id,
                        display_name=str(decision.get("display_name") or decided_account_id).strip() or decided_account_id,
                        article_urls=list(decision.get("seed_urls") or []),
                        frequency_days=max(1, int(current_parsed["frequency_days"])),
                        window_days=max(1, int(current_parsed["window_days"])),
                        max_links_from_history=50 if action == "crawl_history_url" else 1,
                        dry_run=bool(current_parsed["dry_run"]),
                        force=bool(current_parsed["force"]),
                    )
                    crawl_result = None
                    async for chunk in stream_crawl_collect_events(crawl_payload):
                        chunk_type = chunk.get("type")
                        if chunk_type == "error":
                            raise HTTPException(status_code=500, detail=str(chunk.get("message") or "公众号抓取失败"))
                        if chunk_type == "loading":
                            yield f"data: {json.dumps({'type': 'agent_note', 'message': chunk.get('message', '')}, ensure_ascii=False)}\n\n"
                        elif chunk_type == "resolved":
                            total = int(chunk.get("total", 0) or 0)
                            duplicate_count = int(chunk.get("duplicate_url_count", 0) or 0)
                            message = f"已解析出 {total} 条待处理文章链接"
                            if duplicate_count > 0:
                                message += f"，另外有 {duplicate_count} 条重复链接已跳过"
                            yield f"data: {json.dumps({'type': 'agent_note', 'message': message}, ensure_ascii=False)}\n\n"
                        elif chunk_type == "progress":
                            current = int(chunk.get("current", 0) or 0)
                            total = int(chunk.get("total", 0) or 0)
                            yield f"data: {json.dumps({'type': 'agent_note', 'message': f'正在处理第 {current}/{total} 条文章链接…'}, ensure_ascii=False)}\n\n"
                        elif chunk_type == "item_done":
                            status = str(chunk.get("status") or "")
                            current = int(chunk.get("current", 0) or 0)
                            total = int(chunk.get("total", 0) or 0)
                            if status == "ok":
                                title = str(chunk.get("title") or chunk.get("article_id") or "未命名文章").strip()
                                message = f"第 {current}/{total} 条处理成功：{title}"
                            elif status == "skipped_time_window":
                                message = f"第 {current}/{total} 条已跳过：超出当前抓取时间窗"
                            elif status == "blocked_page":
                                reason = str(chunk.get("reason") or "页面访问受限").strip()
                                message = f"第 {current}/{total} 条未抓取成功：公众号页面访问受限，原因 {reason}"
                            else:
                                reason = str(chunk.get("error") or "解析失败").strip()
                                message = f"第 {current}/{total} 条抓取失败：{reason}"
                            yield f"data: {json.dumps({'type': 'agent_note', 'message': message}, ensure_ascii=False)}\n\n"
                        elif chunk_type == "done":
                            crawl_result = chunk.get("result")
                    if crawl_result is None:
                        return
                    collect_eval = _evaluate_agent_step("collect", crawl_result, parsed=current_parsed, decision=decision)
                    step = {"name": "collect", "status": collect_eval["status"], "result": crawl_result, "evaluation": collect_eval}
                    steps.append(step)
                    clean_article_ids = _extract_agent_collect_article_ids(crawl_result if isinstance(crawl_result, dict) else {})
                    current_account_id = decided_account_id
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'collect', 'result': crawl_result}, ensure_ascii=False)}\n\n"
                elif action == "desktop_capture":
                    yield f"data: {json.dumps({'type': 'step_start', 'name': 'desktop_collect', 'message': '未命中可直抓入口，开始回退到桌面微信采集…'}, ensure_ascii=False)}\n\n"
                    desktop_result = None
                    async for chunk in stream_executor_notes(
                        lambda: _run_agent_desktop_collect_step(current_parsed, decision),
                        [
                            '正在连接本机微信窗口并搜索目标公众号…',
                            '正在尝试打开历史消息与目标文章，期间可能需要等待桌面界面响应…',
                            '正在整理截图采集包并准备导入结果…',
                        ],
                    ):
                        if chunk.get("type") == "disconnected":
                            return
                        if chunk.get("type") == "note":
                            yield f"data: {json.dumps({'type': 'agent_note', 'message': chunk.get('message', '')}, ensure_ascii=False)}\n\n"
                        elif chunk.get("type") == "result":
                            desktop_result = chunk.get("result")
                    if desktop_result is None:
                        return
                    collect_eval = _evaluate_agent_step("collect", desktop_result, parsed=current_parsed, decision=decision)
                    step = {"name": "desktop_collect", "status": collect_eval["status"], "result": desktop_result, "evaluation": collect_eval}
                    steps.append(step)
                    clean_article_ids = _extract_agent_collect_article_ids(desktop_result if isinstance(desktop_result, dict) else {})
                    current_account_id = str(decision.get("account_id") or current_account_id).strip() or current_account_id
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'desktop_collect', 'result': desktop_result}, ensure_ascii=False)}\n\n"
                elif action == "request_user_intervention":
                    collect_eval = _evaluate_agent_step("collect", decision, parsed=current_parsed, decision=decision)
                    step = {"name": "intervention", "status": collect_eval["status"], "result": decision, "evaluation": collect_eval}
                    steps.append(step)
                    yield f"data: {json.dumps({'type': 'step_start', 'name': 'intervention', 'message': decision.get('message', '需要人工介入')}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'intervention', 'result': decision}, ensure_ascii=False)}\n\n"
                else:
                    collect_eval = _evaluate_agent_step("collect", decision, parsed=current_parsed, decision=decision)
                    step = {"name": "collect", "status": collect_eval["status"], "result": decision, "evaluation": collect_eval}
                    steps.append(step)
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'collect', 'result': decision}, ensure_ascii=False)}\n\n"

                latest_collect = next((item for item in reversed(steps) if str(item.get("name") or "") in {"collect", "desktop_collect", "intervention"}), None)
                replan = _build_agent_replan(current_parsed, observation, decision, ((latest_collect or {}).get("evaluation") or {}))
                if replan:
                    steps.append({"name": "replan", "status": "done", "result": replan, "evaluation": {"success": True, "retryable": False, "status": "done", "summary": str(replan.get("reason") or "").strip(), "failure_reason": ""}})
                    replan_message = f"首次执行未达成成功判定，开始有限次自动重规划：{str(replan.get('reason') or 'collect_retry').strip()}"
                    yield f"data: {json.dumps({'type': 'agent_note', 'message': replan_message}, ensure_ascii=False)}\n\n"
                    current_parsed = _apply_agent_replan(current_parsed, replan)
                    yield f"data: {json.dumps({'type': 'step_start', 'name': 'observe', 'message': '正在按新计划重新观察环境…'}, ensure_ascii=False)}\n\n"
                    observation = await loop.run_in_executor(None, lambda: _build_agent_observation(current_parsed))
                    observe_eval = _evaluate_agent_step("observe", observation, parsed=current_parsed)
                    steps.append({"name": "observe", "status": observe_eval["status"], "result": observation, "evaluation": observe_eval})
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'observe', 'result': observation}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'step_start', 'name': 'reason', 'message': '正在按新计划重选采集入口…'}, ensure_ascii=False)}\n\n"
                    decision = await loop.run_in_executor(None, lambda: _decide_agent_collect_action(current_parsed, observation))
                    reason_eval = _evaluate_agent_step("reason", decision, parsed=current_parsed)
                    steps.append({"name": "reason", "status": reason_eval["status"], "result": decision, "evaluation": reason_eval})
                    yield f"data: {json.dumps({'type': 'step_done', 'name': 'reason', 'result': decision}, ensure_ascii=False)}\n\n"
                    collect_action = str(decision.get("action") or "")
                    if collect_action == "desktop_capture":
                        yield f"data: {json.dumps({'type': 'step_start', 'name': 'desktop_collect', 'message': '按重规划结果切换到桌面微信采集…'}, ensure_ascii=False)}\n\n"
                        desktop_result = None
                        async for chunk in stream_executor_notes(
                            lambda: _run_agent_desktop_collect_step(current_parsed, decision),
                            [
                                '正在连接本机微信窗口并搜索目标公众号…',
                                '正在尝试打开历史消息与目标文章，期间可能需要等待桌面界面响应…',
                                '正在整理截图采集包并准备导入结果…',
                            ],
                        ):
                            if chunk.get("type") == "disconnected":
                                return
                            if chunk.get("type") == "note":
                                yield f"data: {json.dumps({'type': 'agent_note', 'message': chunk.get('message', '')}, ensure_ascii=False)}\n\n"
                            elif chunk.get("type") == "result":
                                desktop_result = chunk.get("result")
                        if desktop_result is None:
                            return
                        collect_eval = _evaluate_agent_step("collect", desktop_result, parsed=current_parsed, decision=decision)
                        steps.append({"name": "desktop_collect", "status": collect_eval["status"], "result": desktop_result, "evaluation": collect_eval})
                        current_account_id = str(decision.get("account_id") or current_account_id).strip() or current_account_id
                        yield f"data: {json.dumps({'type': 'step_done', 'name': 'desktop_collect', 'result': desktop_result}, ensure_ascii=False)}\n\n"

            should_run_clean = _agent_plan_step_enabled(current_parsed, "clean") and (not _agent_plan_step_enabled(current_parsed, "collect") or collect_action in {"crawl_seed_urls", "crawl_history_url", "desktop_capture", "skip_collect"})

            if should_run_clean:
                yield f"data: {json.dumps({'type': 'step_start', 'name': 'clean', 'message': '开始清洗与可选入库…'}, ensure_ascii=False)}\n\n"
                clean_result = None
                async for chunk in stream_executor_notes(
                    lambda: _run_agent_clean_step(current_parsed, current_account_id, clean_article_ids),
                    [
                        '正在清洗文章内容与图片元数据…',
                        '正在生成可检索块并准备写入知识库…',
                    ],
                ):
                    if chunk.get("type") == "disconnected":
                        return
                    if chunk.get("type") == "note":
                        yield f"data: {json.dumps({'type': 'agent_note', 'message': chunk.get('message', '')}, ensure_ascii=False)}\n\n"
                    elif chunk.get("type") == "result":
                        clean_result = chunk.get("result")
                if clean_result is None:
                    return
                clean_eval = _evaluate_agent_step("clean", clean_result, parsed=current_parsed)
                step = {"name": "clean", "status": clean_eval["status"], "result": clean_result, "evaluation": clean_eval}
                steps.append(step)
                yield f"data: {json.dumps({'type': 'step_done', 'name': 'clean', 'result': clean_result}, ensure_ascii=False)}\n\n"
                ingest_eval = _evaluate_agent_step("ingest", clean_result, parsed=current_parsed)
                steps.append({"name": "ingest", "status": ingest_eval["status"], "result": clean_result, "evaluation": ingest_eval})

            refreshed = await loop.run_in_executor(None, lambda: list_articles(account_id=current_account_id))
            done_payload = {
                "ok": True,
                "parsed": current_parsed,
                "steps": steps,
                "annotation_entry": {
                    "path": "/wechat-annotator",
                    "account_id": current_account_id,
                    "note": "可随时进入公众号标注页面进行人工标注",
                },
                "refreshed": refreshed,
                "updated_session_memory": _build_agent_updated_session_memory(current_parsed.get("session_memory") or {}, current_parsed, steps, current_account_id),
            }
            _maybe_attach_agent_task(done_payload, current_parsed, current_account_id, clean_article_ids)
            _maybe_run_governance_handoff(done_payload, current_account_id, clean_article_ids)
            _maybe_run_evaluation_handoff(done_payload, current_account_id, clean_article_ids)
            done_payload["orchestration"] = _build_multi_agent_orchestration(done_payload, current_parsed, current_account_id)
            yield f"data: {json.dumps({'type': 'done', 'data': done_payload}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
