# -*- coding: utf-8 -*-
"""
RAG 服务层（真实模式）
- 并行运行 RAG 检索 + 通用 LLM，两路答案同时流式输出
- 会话管理使用 ConversationManager（文件存储）
"""
import sys
import os
import time
import asyncio
import threading
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, AsyncGenerator, Dict, Any, List
from queue import Queue
from urllib.parse import urljoin

# ── 路径 ─────────────────────────────────────────────────────────────────────
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_web_dir     = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
_core_path   = os.path.join(_rag_qa_path, "core")
for p in (_rag_qa_path, _core_path, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 初始化所有组件 ────────────────────────────────────────────────────────────
from base import Config, logger
from core.conversation_manager import get_conversation_manager
from core.vector_store import VectorStore
from core.new_rag_system import RAGSystem
from openai import OpenAI

_config       = Config()
_conv_manager = get_conversation_manager()
_init_error: Optional[str] = None
_init_duration_sec: float = 0.0

_CLASSIFY_TIMEOUT_SEC = 8
_PLAN_TIMEOUT_SEC = 20
_MAIN_STREAM_TOTAL_TIMEOUT_SEC = 150
_MAIN_STREAM_IDLE_TIMEOUT_SEC = 30
_COMPARE_STREAM_TOTAL_TIMEOUT_SEC = 60
_COMPARE_STREAM_IDLE_TIMEOUT_SEC = 20
_SAVE_TIMEOUT_SEC = 8

# 子块（rerank 后）相似度低于该阈值视为"检索结果与查询无关"，
# 此时降级为通用知识，避免向 LLM 灌入无关上下文（例如把 Python 代码题
# 误判为采矿专业咨询）。
_OFF_TOPIC_SCORE_THRESHOLD = 0.50

# BGE-Reranker 原始 logits：正值=相关，负值=不相关。
# 阈值=0 即"模型判定为不相关"才降级；调高（例如 1.0）会更激进地降级。
_OFF_TOPIC_RERANK_THRESHOLD = 0.15
_PROMOTE_RERANK_THRESHOLD = 0.35

# 二分类查询分类器（通用知识 vs 专业咨询）置信度阈值：
# 当 BERT 预测为"专业咨询"但概率低于该阈值且文本中无领域关键词时，
# 视为分类器过拟合一边倒，降级为通用知识。
_SPECIALTY_PROB_THRESHOLD = 0.85

_LLM_CIRCUIT_THRESHOLD = 3
_LLM_CIRCUIT_COOLDOWN_SEC = 90
_llm_failure_count = 0
_llm_circuit_open_until = 0.0
_llm_circuit_lock = threading.Lock()
_general_model_cache: Dict[str, Any] = {
    "resolved_model": None,
    "checked_at": 0.0,
    "source": "unresolved",
    "last_error": None,
}
_general_model_cache_lock = threading.Lock()
_compare_model_cache: Dict[str, Any] = {
    "resolved_model": None,
    "checked_at": 0.0,
    "source": "unresolved",
    "last_error": None,
}
_compare_model_cache_lock = threading.Lock()
_COMPARE_MODEL_CACHE_TTL_SEC = 1800
_COMPARE_MODEL_PREFERENCES = [
    "gpt-5.4",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-6-thinking",
    "claude-opus-4-7-thinking",
    "MiniMax-M2.5",
    "MiniMax-M2.1",
]

_CHAT_EXAMPLES_SCHEMA_VERSION = 2
_CHAT_EXAMPLES_WINDOW_DAYS = 7
_CHAT_EXAMPLES_LIMIT = 10
_CHAT_EXAMPLES_CACHE_TTL_SEC = 6 * 3600
_CHAT_EXAMPLES_DEFAULTS = [
    "矿井通风安全有哪些规定？",
    "瓦斯超标应该如何处理？",
    "顶板管理的主要安全措施？",
    "爆破作业安全规程是什么？",
    "矿山水害预防措施？",
    "采矿特种作业人员资质要求？",
]

_DOMAIN_SIGNALS = [
    "矿井", "井下", "瓦斯", "通风", "顶板", "支护", "爆破", "采掘",
    "安全规程", "安全手册", "边坡", "露天矿", "露天矿山", "高边坡", "监测频率",
    "事故处置", "冶金", "选矿", "炼铁", "炼钢", "矿石", "矿床",
    "采矿", "开采", "尾矿", "尾矿库", "冲击地压", "探放水", "回风系统",
    "局部通风机", "浮选", "磨矿", "分段崩落法", "充填采矿法",
]

_BOUNDARY_NEGATIVE_SIGNALS = [
    "就业前景", "实习报告", "高等数学", "校招", "面试", "简历", "职业规划",
    "学习计划", "校园分享", "英语口语", "论文写作", "时间管理",
]

def _extract_error_code(exc: Exception) -> Optional[int]:
    text = str(exc)
    match = re.search(r"\b(401|403|408|409|429|500|502|503|504)\b", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _classify_error(exc: Exception) -> Dict[str, Any]:
    text = str(exc)
    lowered = text.lower()
    code = _extract_error_code(exc)

    if code in (401, 403) or "无效的令牌" in text or "invalid" in lowered and "token" in lowered:
        return {"error_type": "auth", "error_code": code, "error_message": text}
    if code == 429 or "rate" in lowered and "limit" in lowered or "too many requests" in lowered or "限流" in text:
        return {"error_type": "rate_limit", "error_code": code, "error_message": text}
    if code is not None and code >= 500:
        return {"error_type": "upstream", "error_code": code, "error_message": text}
    return {"error_type": "unknown", "error_code": code, "error_message": text}


def _has_domain_signals(text: str) -> bool:
    normalized = (text or "").strip()
    return any(signal in normalized for signal in _DOMAIN_SIGNALS)


def _matches_boundary_negative(text: str) -> bool:
    normalized = (text or "").strip()
    return any(signal in normalized for signal in _BOUNDARY_NEGATIVE_SIGNALS)


def _is_llm_circuit_open() -> bool:
    return time.time() < _llm_circuit_open_until


def _record_llm_success():
    global _llm_failure_count, _llm_circuit_open_until
    with _llm_circuit_lock:
        _llm_failure_count = 0
        _llm_circuit_open_until = 0.0


def _record_llm_failure():
    global _llm_failure_count, _llm_circuit_open_until
    with _llm_circuit_lock:
        _llm_failure_count += 1
        if _llm_failure_count >= _LLM_CIRCUIT_THRESHOLD:
            _llm_circuit_open_until = time.time() + _LLM_CIRCUIT_COOLDOWN_SEC

_llm_client = OpenAI(
    api_key  = _config.DASHSCOPE_API_KEY,
    base_url = _config.DASHSCOPE_BASE_URL,
)
_general_llm_client = OpenAI(
    api_key  = _config.GENERAL_API_KEY,
    base_url = _config.GENERAL_BASE_URL,
)
_compare_llm_client = OpenAI(
    api_key  = _config.COMPARE_API_KEY,
    base_url = _config.COMPARE_BASE_URL,
)


def _is_demo_like_key(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return (not lowered) or lowered.startswith("demo-key") or "change-me" in lowered


def _looks_like_text_model(model_name: str) -> bool:
    lowered = (model_name or "").strip().lower()
    if not lowered:
        return False
    if any(flag in lowered for flag in ("image", "embedding", "rerank", "tts", "speech", "whisper", "vision", "vl")):
        return False
    return True


def _probe_model(client: OpenAI, model_name: str, label: str) -> bool:
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Reply with OK only."}],
            stream=False,
            max_tokens=8,
            timeout=20,
        )
        base_resp = getattr(completion, "base_resp", None)
        status_code = getattr(base_resp, "status_code", 0) if base_resp is not None else 0
        if status_code not in (0, None):
            return False
        return True
    except Exception as exc:
        logger.warning("%s model probe failed for %s: %s", label, model_name, exc)
        return False


def _fetch_models(client: OpenAI, base_url: str, label: str) -> List[str]:
    try:
        response = client.models.list()
        data = getattr(response, "data", None) or []
        return [item.id for item in data if _looks_like_text_model(getattr(item, "id", ""))]
    except Exception as exc:
        logger.warning("fetch %s models failed from %s: %s", label, base_url, exc)
        return []


def _resolve_text_model(
    configured: str,
    fallback: str,
    client: OpenAI,
    base_url: str,
    cache: Dict[str, Any],
    cache_lock: threading.Lock,
    label: str,
) -> str:
    configured = (configured or "").strip()
    now = time.time()
    with cache_lock:
        if (
            cache.get("resolved_model")
            and (now - float(cache.get("checked_at", 0.0)) < _COMPARE_MODEL_CACHE_TTL_SEC)
        ):
            return cache["resolved_model"]

    candidates: List[str] = []
    if configured and configured.lower() != "auto":
        candidates.append(configured)

    available = _fetch_models(client, base_url, label)
    preferred_candidates = [name for name in _COMPARE_MODEL_PREFERENCES if name in available]
    fallback_candidates = [name for name in available if name not in preferred_candidates and name not in candidates]
    for model_name in preferred_candidates:
        if model_name not in candidates:
            candidates.append(model_name)
    candidates.extend(fallback_candidates)

    resolved = None
    source = f"fallback_{label}"
    last_error = None
    for model_name in candidates:
        if _probe_model(client, model_name, label):
            resolved = model_name
            source = "configured" if model_name == configured and configured.lower() != "auto" else "auto_probe"
            last_error = None
            break
        last_error = f"no usable {label} model found in advertised list from {base_url}"

    if not resolved:
        resolved = fallback

    with cache_lock:
        cache.update({
            "resolved_model": resolved,
            "checked_at": now,
            "source": source,
            "last_error": last_error,
        })
    return resolved


def _resolve_compare_model() -> str:
    return _resolve_text_model(
        configured=_config.COMPARE_LLM_MODEL,
        fallback=_config.LLM_MODEL,
        client=_compare_llm_client,
        base_url=_config.COMPARE_BASE_URL,
        cache=_compare_model_cache,
        cache_lock=_compare_model_cache_lock,
        label="compare",
    )


def _resolve_general_model() -> str:
    return _resolve_text_model(
        configured=_config.GENERAL_LLM_MODEL,
        fallback=_config.LLM_MODEL,
        client=_general_llm_client,
        base_url=_config.GENERAL_BASE_URL,
        cache=_general_model_cache,
        cache_lock=_general_model_cache_lock,
        label="general",
    )

# ── LLM 调用（生成器，yield token） ───────────────────────────────────────────
def _call_llm(prompt: str, system: str = "你是采矿安全领域的专家智能助手，回答准确、专业、有条理。"):
    if _is_llm_circuit_open():
        raise RuntimeError("LLM 熔断中，请稍后重试")

    completion = _llm_client.chat.completions.create(
        model    = _config.LLM_MODEL,
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        stream  = True,
        timeout = 120,
    )
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def _call_compare_llm(prompt: str, system: str = "你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了。"):
    model_name = _resolve_compare_model()
    completion = _compare_llm_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        stream=True,
        timeout=120,
    )
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def _call_general_llm(prompt: str, system: str = "你是一个通用知识助手。直接回答常识、人物、机构、学校、生活与通用技术问题。若问题缺少必要对象、时间或上下文，就明确指出缺了什么，并请用户补充；不要让用户联系人工客服。"):
    model_name = _resolve_general_model()
    completion = _general_llm_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        stream=True,
        timeout=120,
    )
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# 初始化 VectorStore 和 RAGSystem（容错：Milvus 不可用时允许服务降级启动）
_vector_store = None
_rag_system = None
try:
    _init_started = time.time()
    _vector_store = VectorStore(
        collection_name = _config.MILVUS_COLLECTION_NAME,
        host            = _config.MILVUS_HOST,
        port            = _config.MILVUS_PORT,
        database        = _config.MILVUS_DATABASE_NAME,
    )
    _rag_system = RAGSystem(_vector_store, _call_llm, _conv_manager)
    _init_duration_sec = round(time.time() - _init_started, 3)
    logger.info("RAG service ready")
except Exception as e:
    _init_error = str(e)
    _init_duration_sec = round(time.time() - _init_started, 3)
    logger.exception("RAG service 初始化失败，进入降级模式")

# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class RagResult:
    answer:        str
    retrieval_info: Dict[str, Any]


# ── 内部：获取历史上下文 ───────────────────────────────────────────────────────
def _get_history_context(session_id: str) -> str:
    try:
        if _conv_manager.current_session_id != session_id:
            _conv_manager.load_session(session_id)
        recent = _conv_manager.get_history(limit=5)
        if not recent:
            return ""
        lines = []
        for i, r in enumerate(recent, 1):
            a_preview = r["answer"][:80].replace("\n", " ") + "…"
            lines.append(f"第{i}轮:\n  问：{r['question']}\n  答：{a_preview}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"获取历史失败: {e}")
        return ""


def _build_panel_compact(meta: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not meta:
        return None
    try:
        sources = meta.get("sources") or []
        return {
            "query_type":      meta.get("query_type"),
            "strategy":        meta.get("strategy"),
            "candidate_count": meta.get("candidate_count"),
            "final_count":     meta.get("final_count"),
            "strategy_k":      meta.get("strategy_k"),
            "context_limit":   meta.get("context_limit"),
            "direct_child_hits": meta.get("direct_child_hits"),
            "parent_only_hits": meta.get("parent_only_hits"),
            "evidence_note":   meta.get("evidence_note"),
            "time":            meta.get("time"),
            "sources": [
                {
                    "source":           s.get("source"),
                    "file_name":        s.get("file_name"),
                    "score":            s.get("score"),
                    "search_score":     s.get("search_score"),
                    "rerank_score":     s.get("rerank_score"),
                    "evidence_status":  s.get("evidence_status"),
                    "evidence_note":    s.get("evidence_note"),
                    "content":          (s.get("content") or "")[:300],
                    "parent_content":   (s.get("parent_content") or "")[:1500],
                    "matched_children": (s.get("matched_children") or [])[:3],
                }
                for s in sources[:6]
            ],
        }
    except Exception:
        return None


def _build_persisted_metadata(meta: Optional[Dict[str, Any]], error_message: str = "") -> Dict[str, Any]:
    panel_compact = _build_panel_compact(meta)
    payload = {
        "query_type":      meta.get("query_type") if meta else None,
        "strategy":        meta.get("strategy") if meta else None,
        "processing_time": meta.get("time") if meta else None,
        "panel_info":      panel_compact,
        "had_image":       bool((meta or {}).get("had_image")),
    }
    compare_answer = (meta or {}).get("compare_answer")
    if compare_answer:
        payload["compare_answer"] = compare_answer
    if error_message:
        payload["error_message"] = error_message
    return payload


def _save_pending_question(session_id: str, question: str) -> int:
    try:
        if _conv_manager.current_session_id != session_id:
            _conv_manager.load_session(session_id)
        return _conv_manager.add_pending_message(question, metadata={})
    except Exception as e:
        logger.warning(f"保存待完成问题失败: {e}")
        return -1


def _save_conversation(session_id: str, question: str, answer: str, meta: dict, history_index: Optional[int] = None):
    try:
        if _conv_manager.current_session_id != session_id:
            _conv_manager.load_session(session_id)
        metadata = _build_persisted_metadata(meta)
        if history_index is not None and history_index >= 0:
            updated = _conv_manager.update_message(
                history_index,
                answer=answer,
                metadata=metadata,
                status="done",
                error_message="",
            )
            if updated:
                return
        _conv_manager.add_message(question, answer, metadata=metadata)
        _conv_manager.save_current_session()
    except Exception as e:
        logger.warning(f"保存会话失败: {e}")


def _mark_conversation_interrupted(
    session_id: str,
    answer: str,
    meta: Optional[Dict[str, Any]],
    history_index: Optional[int],
    error_message: str,
):
    try:
        if history_index is None or history_index < 0:
            return
        if _conv_manager.current_session_id != session_id:
            _conv_manager.load_session(session_id)
        _conv_manager.update_message(
            history_index,
            answer=answer,
            metadata=_build_persisted_metadata(meta, error_message=error_message),
            status="interrupted",
            error_message=error_message,
        )
    except Exception as e:
        logger.warning(f"标记会话中断失败: {e}")


# ── 内部：完整 RAG 流程（同步，在线程池中运行） ──────────────────────────────
_SOURCE_DISPLAY = {
    "mining": "《采矿安全手册》",
}


def _clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _normalize_strategy_name(strategy: Optional[str]) -> Optional[str]:
    """统一到训练侧四分类标签：
        直接检索 / 查询扩展检索 / 查询分解检索 / 问题重写检索
    历史命名（假设问题检索 / 子查询检索 / 场景重构检索 / 回溯问题检索）需转为新命名。
    """
    legacy_map = {
        "假设问题检索": "查询扩展检索",
        "HyDE":         "查询扩展检索",
        "子查询检索":   "查询分解检索",
        "场景重构检索": "问题重写检索",
        "回溯问题检索": "问题重写检索",
    }
    return legacy_map.get(strategy, strategy)


def _resolve_km_by_strategy(strategy: Optional[str], use_strategy_km_policy: bool) -> tuple[int, int]:
    if not use_strategy_km_policy:
        return _config.RETRIEVAL_K, _config.CANDIDATE_M

    normalized = _normalize_strategy_name(strategy)
    # 需要调用 LLM 生成中间查询的复杂策略，适当上调 k/m
    if normalized in {"查询分解检索", "问题重写检索", "查询扩展检索"}:
        return 8, 3
    return 5, 2


def _build_source_details(context_docs: List[Any], query: str, source_filter: Optional[str]) -> List[Dict[str, Any]]:
    """构建前端来源详情：包含完整父块与命中的子块片段。"""
    if _vector_store is None:
        return []

    sub_chunks = []
    try:
        sub_chunks = _vector_store.search_subchunks(
            query,
            k=max(_config.RETRIEVAL_K, 8),
            source_filter=source_filter,
        )
    except Exception as e:
        logger.warning(f"子块详情检索失败: {e}")

    subchunk_map: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in sub_chunks:
        parent_id = chunk.metadata.get("parent_id")
        if not parent_id:
            continue
        subchunk_map.setdefault(parent_id, []).append({
            "content": chunk.page_content,
            "score": chunk.metadata.get("search_score", 0.0),
        })

    sources = []
    for idx, doc in enumerate(context_docs):
        raw_source = doc.metadata.get("source", "mining")
        file_name = doc.metadata.get("file_name") or "未命名文档"
        parent_id = doc.metadata.get("parent_id")
        children = (subchunk_map.get(parent_id) or [])[:3]
        rerank_score = doc.metadata.get("rerank_score") if hasattr(doc, "metadata") else None
        search_score = 0.0
        if children:
            search_score = max(_clamp_score(child.get("score"), 0.0) for child in children)
        evidence_status = "child_evidence"
        evidence_note = "已命中子块证据，可作为细粒度参考。"
        rerank_value = None
        if rerank_score is not None:
            try:
                rerank_value = float(rerank_score)
            except Exception:
                rerank_value = None
        if search_score <= 0 and rerank_value is not None and rerank_value > 0:
            evidence_status = "parent_rerank_only"
            evidence_note = "仅命中父块主题相关内容，缺少稳定子块证据。"
        elif search_score < _OFF_TOPIC_SCORE_THRESHOLD:
            evidence_status = "weak_child_evidence"
            evidence_note = "子块证据较弱，只能作为辅助参考。"

        sources.append({
            "content": doc.page_content[:220],
            "source": _SOURCE_DISPLAY.get(raw_source, f"《{raw_source}资料》"),
            "file_name": file_name,
            "parent_id": parent_id,
            "parent_content": doc.page_content,
            "matched_children": children,
            # 主展示分只使用真实检索分，避免把 rerank logits 伪装成百分比可信度。
            "score": search_score,
            "search_score": search_score,
            "rerank_score": rerank_score,
            "evidence_status": evidence_status,
            "evidence_note": evidence_note,
        })
    return sources


def _build_evidence_note(query: str, sources: List[Dict[str, Any]], max_sub_score: float, max_rerank: Optional[float]) -> Optional[str]:
    if not sources:
        return None

    parent_only_hits = [src for src in sources if src.get("evidence_status") == "parent_rerank_only"]
    weak_child_hits = [src for src in sources if src.get("evidence_status") == "weak_child_evidence"]

    if parent_only_hits:
        return (
            "当前检索主要命中了主题相关的父块内容，但缺少稳定的子块级证据；"
            "这说明知识库里存在相关条文方向，却不足以单独支撑高风险现场的完整处置方案。"
        )

    if weak_child_hits and _has_domain_signals(query):
        return (
            f"当前已命中部分相关子块，但细粒度证据偏弱（最高子块检索分 {max_sub_score:.3f}，"
            f"最高重排分 {0.0 if max_rerank is None else max_rerank:.4f}）；"
            "回答应结合条文方向，并明确仍缺少现场关键参数。"
        )

    return None


def _summarize_source_evidence(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    direct_child_hits = 0
    parent_only_hits = 0
    for src in sources or []:
        direct_child_hits += len(src.get("matched_children") or [])
        if src.get("evidence_status") == "parent_rerank_only":
            parent_only_hits += 1
    return {
        "direct_child_hits": direct_child_hits,
        "parent_only_hits": parent_only_hits,
    }


def _run_full_rag(
    query:          str,
    source_filter:  Optional[str],
    query_type:     str,
    history_context: str,
    include_source_details: bool = True,
    use_strategy_km_policy: bool = False,
) -> RagResult:
    t0 = time.time()

    if query_type == "专业咨询":
        strategy     = _normalize_strategy_name(_rag_system.strategy_selector.select_strategy(query))
        retrieval_k, candidate_m = _resolve_km_by_strategy(strategy, use_strategy_km_policy)
        context_docs = _rag_system.retrieve_and_merge(
            query,
            source_filter=source_filter,
            strategy=strategy,
            retrieval_k=retrieval_k,
            candidate_m=candidate_m,
        )

        sources = _build_source_details(context_docs, query, source_filter) if include_source_details else []

        retrieval_info = {
            "query_type":      query_type,
            "strategy":        strategy,
            "candidate_count": retrieval_k,
            "final_count":     len(context_docs),
            "sources":         sources,
            "error_type":      None,
            "error_code":      None,
            "error_message":   None,
            "time":            0.0,
        }
        context = "\n\n---\n\n".join([doc.page_content for doc in context_docs])
    else:
        retrieval_info = {
            "query_type":      query_type,
            "strategy":        None,
            "candidate_count": 0,
            "final_count":     0,
            "sources":         [],
            "error_type":      None,
            "error_code":      None,
            "error_message":   None,
            "time":            0.0,
        }
        context = ""

    # 生成答案
    prompt = _rag_system.rag_prompt.format(
        context  = context,
        question = query,
        history  = history_context,
        phone    = _config.CUSTOMER_SERVICE_PHONE,
    )
    answer = "".join(list(_call_llm(prompt)))
    retrieval_info["time"] = round(time.time() - t0, 3)
    return RagResult(answer=answer, retrieval_info=retrieval_info)


def _run_direct_llm(query: str) -> str:
    """直接调用 LLM，不加 RAG 上下文，用于对比"""
    answer = "".join(list(_call_llm(
        prompt = query,
        system = "你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了。",
    )))
    return answer


def _normalize_query_type(query: str, raw_type: str, prob: float = 1.0) -> str:
    """兼容历史模型标签，保证最终只有"通用知识/专业咨询"两类。

    增加：
    1) 关键词硬规则——明显跨领域问题（代码/数学/生活/通用 IT 等）直接降级为通用知识，
       不再交给后续 BERT/检索误判；
    2) 置信度阈值——BERT 输出"专业咨询"但概率低于 _SPECIALTY_PROB_THRESHOLD 时，
       降级为通用知识（避免分类器过拟合一边倒）。
    """
    text = (query or "").strip()

    # 1) 跨领域硬规则：代码/编程/通用 IT
    code_signals = [
        "python", "javascript", "java ", "c++", "c#", "golang", "rust ",
        "node.js", "node ", "vue", "react", "django", "flask", "spring",
        "代码", "函数", "数组", "列表切片", "切片", "字典", "类的", "面向对象",
        "sql", "select ", "update ", "insert ", "delete ", "mysql", "postgres",
        "mongodb", "redis", "docker", "kubernetes", "linux", "shell", "git ",
        "import ", "def ", "console.log", "println", "print(",
        "lst[", "list[", "[:", ":-", "rpartition", "lstrip", "rstrip",
        "html", "css", "ajax", "http", "tcp", "udp",
    ]
    lower_text = text.lower()
    if any(sig in lower_text for sig in code_signals):
        return "通用知识"

    # 数学/学科性强但非采矿冶金
    generic_signals = [
        "微积分", "线性代数", "概率论", "数据结构", "算法题", "leetcode", "牛客",
        "翻译成", "用英文", "请用英语", "今天天气", "讲个笑话", "做菜", "菜谱",
        "电影推荐", "游戏攻略",
    ]
    if any(sig in text for sig in generic_signals):
        return "通用知识"

    valid_types = {"通用知识", "专业咨询"}
    if raw_type in valid_types:
        # 仅保留“低置信度专业 -> 通用”的保守兜底。
        # 不再因为出现领域词就硬拉为专业咨询，避免把边界类问题误判成要走知识库。
        hit_mining = _has_domain_signals(text)

        # 置信度兜底：BERT 说专业咨询但是概率不高，且文本里没有任何专业信号 → 通用知识
        if raw_type == "专业咨询" and prob < _SPECIALTY_PROB_THRESHOLD and not hit_mining:
            logger.info(
                f"查询 '{text[:30]}...' BERT 判'专业咨询'但概率仅 {prob:.2f}，无领域关键词，降级为通用知识"
            )
            return "通用知识"
        return raw_type

    # 兼容"错误地返回了策略标签"的历史情况
    strategy_like = {
        "直接检索", "查询扩展检索", "查询分解检索", "问题重写检索",
        "假设问题检索", "子查询检索", "场景重构检索", "回溯问题检索",
    }
    if raw_type in strategy_like:
        return "专业咨询"

    return "通用知识"


def _extract_forced_query_type(query: str) -> tuple[str, Optional[str]]:
    text = str(query or "").strip()
    if not text:
        return text, None

    prefixes = {
        "专业知识": "专业咨询",
        "专业咨询": "专业咨询",
        "通用知识": "通用知识",
        "通用咨询": "通用知识",
    }
    match = re.match(r"^\s*(专业知识|专业咨询|通用知识|通用咨询)\s*[:：]\s*(.*)$", text, flags=re.IGNORECASE)
    if not match:
        return text, None

    raw_prefix = str(match.group(1) or "").strip()
    stripped_query = str(match.group(2) or "").strip()
    forced_type = prefixes.get(raw_prefix)
    if not forced_type:
        return text, None
    return stripped_query or text, forced_type


def _promote_query_type_by_retrieval(query: str, query_type: str, source_filter: Optional[str]) -> str:
    """当分类器判断为通用知识，但知识库已有明显命中时，提升为专业咨询。

    这样新上传的领域文档不会因为分类器泛化不足而直接走纯 LLM 回答。
    """
    if query_type != "通用知识":
        return query_type

    if _vector_store is None:
        return query_type

    if (not _has_domain_signals(query)) or _matches_boundary_negative(query):
        return query_type

    try:
        docs = _vector_store.hybrid_search_with_rerank(query, k=2, source_filter=source_filter)
    except Exception as e:
        logger.warning(f"通用知识提升检索失败: {e}")
        return query_type

    max_rerank = None
    for doc in docs:
        rs = doc.metadata.get("rerank_score") if hasattr(doc, "metadata") else None
        if rs is None:
            continue
        try:
            rs = float(rs)
        except Exception:
            continue
        if max_rerank is None or rs > max_rerank:
            max_rerank = rs

    if docs and max_rerank is not None and max_rerank >= _PROMOTE_RERANK_THRESHOLD:
        logger.info(f"查询 '{query}' 命中知识库，自动从通用知识提升为专业咨询")
        return "专业咨询"

    return query_type


async def stream_compare_response(query: str) -> AsyncGenerator[Dict[str, Any], None]:
    """按需生成通用 LLM 对比回答。"""
    if not (query or "").strip():
        yield {"type": "error", "data": "问题不能为空"}
        return

    if _is_demo_like_key(_config.COMPARE_API_KEY):
        yield {"type": "error", "data": "通用对比模型未配置"}
        return

    try:
        async for token in _stream_sync_tokens(
            lambda: _call_compare_llm(
                prompt=query,
                system="你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了。",
            ),
            total_timeout_sec=_COMPARE_STREAM_TOTAL_TIMEOUT_SEC,
            idle_timeout_sec=_COMPARE_STREAM_IDLE_TIMEOUT_SEC,
        ):
            yield {"type": "llm_token", "data": token}
        yield {"type": "done", "data": {}}
    except Exception as exc:
        logger.warning(f"按需通用 LLM 对比生成失败: {exc}")
        yield {"type": "error", "data": f"通用 LLM 对比生成失败: {exc}"}


def _prepare_query_plan(
    query: str,
    source_filter: Optional[str],
    query_type: str,
    history_context: str,
    include_source_details: bool = True,
    use_strategy_km_policy: bool = False,
) -> Dict[str, Any]:
    """准备检索信息与主回答 Prompt，不生成最终答案。"""
    t0 = time.time()

    if query_type == "专业咨询":
        strategy = _normalize_strategy_name(_rag_system.strategy_selector.select_strategy(query))
        retrieval_k, candidate_m = _resolve_km_by_strategy(strategy, use_strategy_km_policy)
        context_docs = _rag_system.retrieve_and_merge(
            query,
            source_filter=source_filter,
            strategy=strategy,
            retrieval_k=retrieval_k,
            candidate_m=candidate_m,
        )

        sources = _build_source_details(context_docs, query, source_filter) if include_source_details else []

        # 检索结果相关性过低时降级为"通用知识"，避免把跨领域问题(如代码题/无关图片)
        # 误标为"专业咨询"，并避免把不相关上下文塞进 prompt 干扰回答。
        # 综合两个信号：(a) BGE-Reranker 对父块的 logits（最权威，>0 才相关）；
        #              (b) Milvus hybrid 子块分数兜底。
        max_sub_score = 0.0
        for src in sources:
            for child in src.get("matched_children") or []:
                try:
                    score = float(child.get("score") or 0.0)
                    if score > max_sub_score:
                        max_sub_score = score
                except Exception:
                    pass

        max_rerank = None
        for doc in context_docs:
            rs = doc.metadata.get("rerank_score") if hasattr(doc, "metadata") else None
            if rs is None:
                continue
            try:
                rs = float(rs)
                if max_rerank is None or rs > max_rerank:
                    max_rerank = rs
            except Exception:
                pass

        rerank_off_topic = (max_rerank is not None) and (max_rerank < _OFF_TOPIC_RERANK_THRESHOLD)
        sub_off_topic    = max_sub_score < _OFF_TOPIC_SCORE_THRESHOLD
        hit_domain       = _has_domain_signals(query)

        evidence_note = _build_evidence_note(query, sources, max_sub_score, max_rerank)
        evidence_stats = _summarize_source_evidence(sources)

        if ((not context_docs) or rerank_off_topic or (max_rerank is None and sub_off_topic)) and not hit_domain:
            logger.info(
                f"查询 '{query[:40]}...' 检索相关性不足 "
                f"(rerank={max_rerank}, sub={max_sub_score:.3f})，降级为通用知识"
            )
            query_type = "通用知识"
            retrieval_info = {
                "query_type":      query_type,
                "strategy":        None,
                "candidate_count": 0,
                "final_count":     0,
                "sources":         [],
                "error_type":      None,
                "error_code":      None,
                "error_message":   None,
                "evidence_note":   None,
                "time":            0.0,
            }
            context = ""
        else:
            if ((not context_docs) or rerank_off_topic or (max_rerank is None and sub_off_topic)) and hit_domain:
                logger.info(
                    f"查询 '{query[:40]}...' 命中强领域信号，保留专业咨询判定 "
                    f"(rerank={max_rerank}, sub={max_sub_score:.3f})"
                )
            retrieval_info = {
                "query_type":      query_type,
                "strategy":        strategy,
                "candidate_count": retrieval_k,
                "final_count":     len(context_docs),
                "strategy_k":      retrieval_k,
                "context_limit":   candidate_m,
                "direct_child_hits": evidence_stats["direct_child_hits"],
                "parent_only_hits": evidence_stats["parent_only_hits"],
                "sources":         sources,
                "error_type":      None,
                "error_code":      None,
                "error_message":   None,
                "evidence_note":   evidence_note,
                "time":            0.0,
            }
            context = "\n\n---\n\n".join([doc.page_content for doc in context_docs])
            if evidence_note:
                context = f"【证据状态】\n{evidence_note}\n\n---\n\n{context}"
    else:
        retrieval_info = {
            "query_type":      query_type,
            "strategy":        None,
            "candidate_count": 0,
            "final_count":     0,
            "sources":         [],
            "error_type":      None,
            "error_code":      None,
            "error_message":   None,
            "evidence_note":   None,
            "time":            0.0,
        }
        context = ""

    if query_type == "专业咨询":
        prompt = _rag_system.rag_prompt.format(
            context=context,
            question=query,
            history=history_context,
            phone=_config.CUSTOMER_SERVICE_PHONE,
        )
        system = None
    else:
        prompt = query
        system = None
    retrieval_info["time"] = round(time.time() - t0, 3)

    return {
        "prompt": prompt,
        "system": system,
        "retrieval_info": retrieval_info,
    }


async def _stream_sync_tokens(
    token_factory,
    total_timeout_sec: int,
    idle_timeout_sec: int,
) -> AsyncGenerator[str, None]:
    """将同步 token 生成器桥接为异步流，确保真正实时推送。"""
    queue: Queue = Queue()
    done_marker = object()
    loop = asyncio.get_running_loop()

    def worker():
        try:
            for token in token_factory():
                queue.put(token)
        except Exception as e:
            queue.put(e)
        finally:
            queue.put(done_marker)

    threading.Thread(target=worker, daemon=True).start()

    started = time.time()
    while True:
        elapsed = time.time() - started
        if elapsed > total_timeout_sec:
            raise TimeoutError(f"流式输出超时（>{total_timeout_sec}s）")

        item = await asyncio.wait_for(
            loop.run_in_executor(None, queue.get),
            timeout=idle_timeout_sec,
        )
        if item is done_marker:
            break
        if isinstance(item, Exception):
            raise item
        yield item


# ── 公开 API ──────────────────────────────────────────────────────────────────
def get_system_status() -> Dict[str, Any]:
    milvus_connected = _vector_store is not None
    try:
        if _vector_store is None:
            raise RuntimeError(_init_error or "vector store unavailable")
        count = _vector_store.client.get_collection_stats(_config.MILVUS_COLLECTION_NAME)
        row_count = count.get("row_count", "未知")
    except Exception:
        row_count = "连接中"

    return {
        "rag_available":    _rag_system is not None,
        "service_ready":    (_rag_system is not None and _vector_store is not None),
        "mode":             "真实模式",
        "milvus_connected": milvus_connected,
        "llm_model":        _config.LLM_MODEL,
        "general_llm_model": _resolve_general_model() if not _is_demo_like_key(_config.GENERAL_API_KEY) else _config.GENERAL_LLM_MODEL,
        "general_llm_base_url": _config.GENERAL_BASE_URL,
        "compare_llm_model": _resolve_compare_model() if not _is_demo_like_key(_config.COMPARE_API_KEY) else _config.COMPARE_LLM_MODEL,
        "compare_llm_base_url": _config.COMPARE_BASE_URL,
        "embedding_model":  "BGE-M3",
        "reranker_model":   "BGE-Reranker-Large",
        "query_classifier_model": getattr(getattr(_rag_system, 'query_classifier', None), 'status_name', 'bert_query_classifier_new'),
        "strategy_classifier_model": os.path.basename(getattr(getattr(_rag_system, 'strategy_selector', None), 'model_path', 'bert_strategy_classifier')),
        "collection":       _config.MILVUS_COLLECTION_NAME,
        "retrieval_k":      _config.RETRIEVAL_K,
        "candidate_m":      _config.CANDIDATE_M,
        "chunk_size":       f"{_config.PARENT_CHUNK_SIZE}/{_config.CHILD_CHUNK_SIZE}",
        "parent_chunk_size": _config.PARENT_CHUNK_SIZE,
        "child_chunk_size": _config.CHILD_CHUNK_SIZE,
        "chunk_overlap": _config.CHUNK_OVERLAP,
        "chunking_mode": _config.CHUNKING_MODE,
        "chunking_mode_by_source": _config.CHUNKING_MODE_BY_SOURCE,
        "semantic_model_path": _config.SEMANTIC_MODEL_PATH,
        "semantic_sim_threshold": _config.SEMANTIC_SIM_THRESHOLD,
        "semantic_min_chunk_size": _config.SEMANTIC_MIN_CHUNK_SIZE,
        "semantic_max_chunk_size": _config.SEMANTIC_MAX_CHUNK_SIZE,
        "retrieval_stack": "BGE-M3 dense+sparse + Milvus hybrid search + BGE reranker",
        "total_vectors":    row_count,
        "init_error":       _init_error,
        "init_duration_sec": _init_duration_sec,
        "dependency_checks": {
            "llm_client": True,
            "general_llm_client": not _is_demo_like_key(_config.GENERAL_API_KEY),
            "compare_llm_client": not _is_demo_like_key(_config.COMPARE_API_KEY),
            "milvus": milvus_connected,
            "query_classifier": (_rag_system is not None),
            "strategy_selector": (_rag_system is not None),
            "vector_store": (_vector_store is not None),
        },
        "timeouts": {
            "classify_sec": _CLASSIFY_TIMEOUT_SEC,
            "plan_sec": _PLAN_TIMEOUT_SEC,
            "main_stream_total_sec": _MAIN_STREAM_TOTAL_TIMEOUT_SEC,
            "main_stream_idle_sec": _MAIN_STREAM_IDLE_TIMEOUT_SEC,
            "compare_stream_total_sec": _COMPARE_STREAM_TOTAL_TIMEOUT_SEC,
            "compare_stream_idle_sec": _COMPARE_STREAM_IDLE_TIMEOUT_SEC,
            "save_sec": _SAVE_TIMEOUT_SEC,
        },
        "llm_circuit": {
            "open": _is_llm_circuit_open(),
            "failure_count": _llm_failure_count,
            "cooldown_sec": _LLM_CIRCUIT_COOLDOWN_SEC,
        },
        "general_llm_resolution": dict(_general_model_cache),
        "compare_llm_resolution": dict(_compare_model_cache),
    }


def get_knowledge_stats() -> Dict[str, Any]:
    if _vector_store is None:
        return {
            "total_chunks": 0,
            "total_books": 0,
            "source_count": 0,
            "avg_chunks_per_book": 0,
            "sources": [],
            "files": [],
        }

    try:
        return _vector_store.get_knowledge_overview()
    except Exception as e:
        logger.warning(f"知识库统计降级: {e}")
        return {
            "total_chunks": 0,
            "total_books": 0,
            "source_count": 0,
            "avg_chunks_per_book": 0,
            "sources": [],
            "files": [],
        }


def create_session(metadata: Optional[Dict] = None) -> str:
    return _conv_manager.create_session(metadata=metadata)


def list_sessions() -> List[Dict]:
    return _conv_manager.list_sessions()


def delete_session(session_id: str) -> bool:
    return _conv_manager.delete_session(session_id)


def get_session_messages(session_id: str) -> List[Dict]:
    """直接读取会话文件，不改变 _conv_manager 状态，供前端历史回显"""
    import json as _json
    try:
        conv_dir  = os.path.join(_rag_qa_path, "conversations")
        file_path = os.path.join(conv_dir, f"{session_id}.json")
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        history = data.get("history", [])
        msgs = []
        for item in history:
            ts = item.get("timestamp", "")[:16].replace("T", " ")
            md = item.get("metadata", {}) or {}
            status = str(item.get("status") or "done").lower()
            is_done = status in {"done", "completed", "success"}
            stream_error = str(item.get("error_message") or md.get("error_message") or "")
            msgs.append({"role": "user",      "content": item.get("question", ""), "time": ts})
            msgs.append({
                "role":    "assistant",
                "content": item.get("answer", ""),
                "time":    ts,
                "meta": {
                    "query_type": md.get("query_type"),
                    "strategy":   md.get("strategy"),
                    "time":       md.get("processing_time"),
                    "panel_info": md.get("panel_info"),
                    "compare_answer": md.get("compare_answer", ""),
                    "user_query": item.get("question", ""),
                    "stream_status": "done" if is_done else "interrupted",
                    "stream_error": stream_error,
                    "had_image": bool(md.get("had_image")),
                },
            })
        return msgs
    except Exception as e:
        logger.warning(f"加载会话消息失败: {e}")
        return []


def get_vector_store():
    return _vector_store


def get_config():
    return _config


def _examples_cache_path() -> str:
    return os.path.join(_rag_qa_path, "user_data", "chat_examples.json")


def _normalize_question(question: str) -> str:
    normalized = re.sub(r"\s+", "", question or "")
    normalized = re.sub(r"[？?。！!；;，,、·\-—_\[\]【】()（）<>《》\"'“”‘’:]", "", normalized)
    return normalized.lower()


def _parse_question_timestamp(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _read_session_questions(within_days: Optional[int] = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    conv_dir = os.path.join(_rag_qa_path, "conversations")
    if not os.path.isdir(conv_dir):
        return questions

    cutoff_ts = None
    if within_days is not None and within_days > 0:
        cutoff_ts = time.time() - within_days * 24 * 3600

    for name in os.listdir(conv_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(conv_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            session_ts = (
                _parse_question_timestamp(data.get("updated_at"))
                or _parse_question_timestamp(data.get("created_at"))
            )
            for item in data.get("history", []):
                status = str(item.get("status") or "done").lower()
                if status not in {"done", "completed", "success"}:
                    continue
                question = (item.get("question") or "").strip()
                normalized = _normalize_question(question)
                if len(question) < 4 or len(normalized) < 4:
                    continue
                question_ts = _parse_question_timestamp(item.get("timestamp")) or session_ts
                if cutoff_ts is not None:
                    if question_ts is None or question_ts < cutoff_ts:
                        continue
                questions.append({
                    "question": question,
                    "timestamp": question_ts,
                })
        except Exception:
            continue
    return questions


def _build_example_prompt(top_questions: List[str], desired_count: int) -> str:
    joined = "\n".join(f"- {q}" for q in top_questions[:20])
    return (
        "你是采矿安全智能问答系统的产品助手。\n"
        f"请基于下面这些历史高频提问，生成 {desired_count} 条适合首页展示的引导问题。\n"
        "要求：\n"
        "1. 每条尽量简短，适合用户直接点击提问。\n"
        "2. 内容应贴近高频关注点，覆盖不同角度。\n"
        "3. 只输出 JSON 数组，每个元素是字符串，不要额外解释。\n\n"
        f"历史高频提问：\n{joined}"
    )


def _default_chat_example_items() -> List[Dict[str, Any]]:
    return [
        {"question": question, "count": None, "source": "guide", "label": "引导问题"}
        for question in _CHAT_EXAMPLES_DEFAULTS
    ]


def _is_recent_hot_example_candidate(question: str) -> bool:
    normalized = (question or "").strip()
    lowered = normalized.lower()
    if len(_normalize_question(normalized)) < 6:
        return False
    if "[图片ocr识别文本]" in lowered:
        return False
    if re.match(r"^回答第[一二三四五六七八九十0-9]+个问题", normalized):
        return False
    if _matches_boundary_negative(normalized):
        return False
    return _has_domain_signals(normalized)


def _collect_ranked_questions(question_records: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for record in question_records:
        question = (record.get("question") or "").strip()
        normalized = _normalize_question(question)
        if len(normalized) < 4 or not _is_recent_hot_example_candidate(question):
            continue
        ts = record.get("timestamp") or 0.0
        entry = buckets.setdefault(normalized, {
            "question": question,
            "count": 0,
            "last_seen_at": ts,
        })
        entry["count"] += 1
        if ts >= entry.get("last_seen_at", 0.0):
            entry["question"] = question
            entry["last_seen_at"] = ts

    ranked = sorted(
        buckets.values(),
        key=lambda item: (-int(item["count"]), -float(item.get("last_seen_at") or 0.0), item["question"]),
    )
    return ranked[:limit]


def _generate_chat_examples_from_history(limit: int = 6) -> List[str]:
    question_records = _read_session_questions()
    questions = [record["question"] for record in question_records]
    if not questions:
        return _CHAT_EXAMPLES_DEFAULTS[:limit]

    counter = Counter(_normalize_question(q) for q in questions if _normalize_question(q))
    top_questions: List[str] = []
    seen = set()
    for question, _ in counter.most_common(20):
        for original in questions:
            if _normalize_question(original) == question and original not in seen:
                top_questions.append(original)
                seen.add(original)
                break

    prompt = _build_example_prompt(top_questions, desired_count=limit)
    try:
        raw = "".join(_call_llm(prompt, system="你是一个只输出 JSON 的助手。"))
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            items = [str(item).strip() for item in parsed if str(item).strip()]
            if len(items) >= limit:
                return items[:limit]
    except Exception as e:
        logger.warning(f"生成引导问题失败，回退到频率问句: {e}")

    fallback = []
    for q in top_questions[:limit]:
        fallback.append(q)
    while len(fallback) < limit:
        fallback.append((_CHAT_EXAMPLES_DEFAULTS + fallback)[len(fallback) % len(_CHAT_EXAMPLES_DEFAULTS)])
    return fallback[:limit]


def _build_recent_hot_example_items(within_days: int, limit: int) -> List[Dict[str, Any]]:
    ranked = _collect_ranked_questions(_read_session_questions(within_days=within_days), limit=limit)
    items: List[Dict[str, Any]] = []
    for entry in ranked:
        count = int(entry["count"])
        items.append({
            "question": entry["question"],
            "count": count,
            "source": "recent_hot",
            "label": f"近 {within_days} 天 {count} 次",
        })
    return items


def get_chat_hot_windows(limit: int = 5) -> List[Dict[str, Any]]:
    windows = [
        (1, "单天热搜", "1d"),
        (3, "三天热搜", "3d"),
        (7, "一周热搜", "7d"),
    ]
    payload: List[Dict[str, Any]] = []
    for days, label, key in windows:
        payload.append({
            "key": key,
            "label": label,
            "days": days,
            "items": _build_recent_hot_example_items(days, limit),
        })
    return payload


def _merge_example_items(primary_items: List[Dict[str, Any]], supplemental_questions: List[str], limit: int) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()

    for item in primary_items:
        normalized = _normalize_question(item.get("question") or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(item)

    for question in supplemental_questions:
        normalized = _normalize_question(question)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append({
            "question": question,
            "count": None,
            "source": "guide",
            "label": "引导问题",
        })
        if len(merged) >= limit:
            break

    if not merged:
        return _default_chat_example_items()[:limit]
    return merged[:limit]


def load_or_refresh_chat_examples(force: bool = False) -> List[Dict[str, Any]]:
    cache_path = _examples_cache_path()
    now = time.time()
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            generated_at = float(cached.get("generated_at", 0))
            schema_version = int(cached.get("schema_version", 0) or 0)
            items = cached.get("items", [])
            if items and schema_version == _CHAT_EXAMPLES_SCHEMA_VERSION and (now - generated_at) < _CHAT_EXAMPLES_CACHE_TTL_SEC:
                return items[:_CHAT_EXAMPLES_LIMIT]
        except Exception:
            pass

    recent_hot_items = _build_recent_hot_example_items(_CHAT_EXAMPLES_WINDOW_DAYS, _CHAT_EXAMPLES_LIMIT)
    guided_questions = _generate_chat_examples_from_history(limit=_CHAT_EXAMPLES_LIMIT)
    items = _merge_example_items(recent_hot_items, guided_questions, _CHAT_EXAMPLES_LIMIT)
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema_version": _CHAT_EXAMPLES_SCHEMA_VERSION,
                    "generated_at": now,
                    "window_days": _CHAT_EXAMPLES_WINDOW_DAYS,
                    "items": items,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.warning(f"保存引导问题缓存失败: {e}")
    return items[:_CHAT_EXAMPLES_LIMIT]


def get_chat_examples() -> List[Dict[str, Any]]:
    return load_or_refresh_chat_examples(force=False)


def refresh_chat_examples(force: bool = False) -> List[Dict[str, Any]]:
    return load_or_refresh_chat_examples(force=force)


async def stream_chat_response(
    query:         str,
    session_id:    Optional[str],
    source_filter: Optional[str],
    include_source_details: bool = True,
    enable_compare: bool = False,
) -> AsyncGenerator[Dict, None]:
    """
    SSE 事件流：
      {"type": "retrieval_info", "data": {...}}
      {"type": "token",     "data": "字"}   ← RAG 专业答案
      {"type": "llm_token", "data": "字"}   ← 通用 LLM 答案（仅专业咨询）
      {"type": "done",  "data": {"session_id": "..."}}
      {"type": "error", "data": "..."}
    """
    if _rag_system is None or _vector_store is None:
        yield {"type": "error", "data": f"RAG 服务未就绪: {_init_error or '请检查 Milvus 与模型环境'}"}
        return

    if not session_id:
        session_id = create_session()

    loop = asyncio.get_event_loop()
    retrieval_info: Dict[str, Any] = {}
    answer_parts: List[str] = []
    pending_history_index: Optional[int] = None
    effective_query, forced_query_type = _extract_forced_query_type(query)

    async def _finalize_pending(status: str, *, error_message: str = ""):
        nonlocal pending_history_index
        if pending_history_index is None or pending_history_index < 0:
            return
        try:
            if status == "done":
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: _save_conversation(
                            session_id,
                            query,
                            "".join(answer_parts),
                            retrieval_info,
                            history_index=pending_history_index,
                        ),
                    ),
                    timeout=_SAVE_TIMEOUT_SEC,
                )
            else:
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: _mark_conversation_interrupted(
                            session_id,
                            "".join(answer_parts),
                            retrieval_info,
                            pending_history_index,
                            error_message,
                        ),
                    ),
                    timeout=_SAVE_TIMEOUT_SEC,
                )
        except TimeoutError:
            logger.warning("保存会话状态超时，已跳过本次持久化")

    # 1. 获取历史（在异步上下文，线程安全）
    history_context = _get_history_context(session_id)
    pending_history_index = await loop.run_in_executor(None, lambda: _save_pending_question(session_id, query))

    try:
        # 2. 查询分类（快速）
        try:
            raw_query_type = forced_query_type
            raw_prob = 1.0
            if forced_query_type:
                query_type = forced_query_type
            else:
                cls_result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: _rag_system.query_classifier.predict_category(effective_query, return_proba=True),
                    ),
                    timeout=_CLASSIFY_TIMEOUT_SEC,
                )
                if isinstance(cls_result, tuple):
                    raw_query_type, raw_prob = cls_result
                else:
                    raw_query_type, raw_prob = cls_result, 1.0
                query_type = _normalize_query_type(effective_query, raw_query_type, prob=raw_prob)

                # 仅在 normalize 之后仍是"通用知识"时才走 promote（命中知识库就升级专业咨询）
                if query_type == "通用知识":
                    query_type = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, lambda: _promote_query_type_by_retrieval(effective_query, query_type, source_filter)
                        ),
                        timeout=_CLASSIFY_TIMEOUT_SEC,
                    )
        except TimeoutError:
            await _finalize_pending("interrupted", error_message="查询分类超时，请稍后重试")
            yield {"type": "error", "data": "查询分类超时，请稍后重试"}
            return
        except Exception as e:
            await _finalize_pending("interrupted", error_message=f"查询分类失败: {e}")
            yield {"type": "error", "data": f"查询分类失败: {e}"}
            return

        # 3. 准备检索信息与回答 Prompt
        try:
            plan = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _prepare_query_plan(
                        effective_query,
                        source_filter,
                        query_type,
                        history_context,
                        include_source_details=include_source_details,
                        use_strategy_km_policy=True,
                    ),
                ),
                timeout=_PLAN_TIMEOUT_SEC,
            )
        except TimeoutError:
            await _finalize_pending("interrupted", error_message="检索规划超时，请稍后重试")
            yield {"type": "error", "data": "检索规划超时，请稍后重试"}
            return
        except Exception as e:
            await _finalize_pending("interrupted", error_message=f"检索/生成失败: {e}")
            yield {"type": "error", "data": f"检索/生成失败: {e}"}
            return

        # 4. 先发检索信息，减少前端等待首包时间
        retrieval_info = plan["retrieval_info"]
        if forced_query_type:
            retrieval_info = {
                **retrieval_info,
                "query_type": query_type,
                "query_type_source": "user_forced",
                "forced_query_type": forced_query_type,
            }
        yield {"type": "retrieval_info", "data": retrieval_info}

        # 5. 主答案 + 通用 LLM 对比 —— 真正并行流式输出
        # 只有专业咨询且前端显式启用对比时才走并行第二路 LLM，
        # 避免同模型/同 API 同时起两路互抢限流，也减少计算资源浪费。
        expect_compare = enable_compare and (query_type == "专业咨询")

        merged: asyncio.Queue = asyncio.Queue()
        DONE = object()

        async def _drain(agen, kind: str, *, total_timeout: int, idle_timeout: int):
            try:
                async for token in _stream_sync_tokens(
                    agen,
                    total_timeout_sec=total_timeout,
                    idle_timeout_sec=idle_timeout,
                ):
                    await merged.put((kind, token))
            except Exception as e:
                await merged.put((f"{kind}_err", e))
            finally:
                await merged.put((f"{kind}_done", None))

        primary_call = (
            (lambda: _call_llm(plan["prompt"], system="你是采矿安全领域的专家智能助手，回答准确、专业、有条理。"))
            if query_type == "专业咨询"
            else (lambda: _call_general_llm(plan["prompt"]))
        )
        rag_task = asyncio.create_task(_drain(
            primary_call,
            "rag",
            total_timeout=_MAIN_STREAM_TOTAL_TIMEOUT_SEC,
            idle_timeout=_MAIN_STREAM_IDLE_TIMEOUT_SEC,
        ))
        cmp_task = None
        if expect_compare:
            cmp_task = asyncio.create_task(_drain(
                lambda: _call_compare_llm(
                    prompt=effective_query,
                    system="你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了。",
                ),
                "llm",
                total_timeout=_COMPARE_STREAM_TOTAL_TIMEOUT_SEC,
                idle_timeout=_COMPARE_STREAM_IDLE_TIMEOUT_SEC,
            ))

        rag_done = False
        llm_done = not expect_compare
        rag_failed = False
        rag_error_message = ""
        try:
            while not (rag_done and llm_done):
                kind, payload = await merged.get()
                if kind == "rag":
                    answer_parts.append(payload)
                    yield {"type": "token", "data": payload}
                elif kind == "rag_done":
                    rag_done = True
                elif kind == "rag_err":
                    rag_failed = True
                    rag_done = True
                    _record_llm_failure()
                    err_meta = _classify_error(payload)
                    retrieval_info = {**retrieval_info, **err_meta}
                    rag_error_message = f"主答案流式生成失败: {payload}"
                    yield {"type": "retrieval_info", "data": retrieval_info}
                    yield {"type": "error", "data": rag_error_message}
                elif kind == "llm":
                    yield {"type": "llm_token", "data": payload}
                elif kind == "llm_done":
                    llm_done = True
                elif kind == "llm_err":
                    logger.warning(f"通用 LLM 对比生成失败: {payload}")
                    llm_done = True
        finally:
            # 确保后台任务收尾，避免悬挂
            for t in (rag_task, cmp_task):
                if t and not t.done():
                    t.cancel()
                    try:
                        await t
                    except Exception:
                        pass

        if rag_failed:
            await _finalize_pending("interrupted", error_message=rag_error_message or "主答案流式生成失败")
            return
        _record_llm_success()

        # 7. 保存会话
        await _finalize_pending("done")

        yield {"type": "done", "data": {"session_id": session_id}}
    except asyncio.CancelledError:
        await _finalize_pending("interrupted", error_message="页面刷新或连接中断，回答未完成，请重试。")
        raise
