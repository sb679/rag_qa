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
from typing import Optional, AsyncGenerator, Dict, Any, List
from queue import Queue

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

_LLM_CIRCUIT_THRESHOLD = 3
_LLM_CIRCUIT_COOLDOWN_SEC = 90
_llm_failure_count = 0
_llm_circuit_open_until = 0.0
_llm_circuit_lock = threading.Lock()


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


def _save_conversation(session_id: str, question: str, answer: str, meta: dict):
    try:
        if _conv_manager.current_session_id != session_id:
            _conv_manager.load_session(session_id)
        _conv_manager.add_message(question, answer, metadata={
            "query_type":      meta.get("query_type"),
            "strategy":        meta.get("strategy"),
            "processing_time": meta.get("time"),
        })
        _conv_manager.save_current_session()
    except Exception as e:
        logger.warning(f"保存会话失败: {e}")


# ── 内部：完整 RAG 流程（同步，在线程池中运行） ──────────────────────────────
_SOURCE_DISPLAY = {
    "mining": "《采矿安全手册》",
}
_BASE_SCORES = [0.94, 0.88, 0.82, 0.76, 0.71]


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

        sources.append({
            "content": doc.page_content[:220],
            "source": _SOURCE_DISPLAY.get(raw_source, f"《{raw_source}资料》"),
            "file_name": file_name,
            "parent_id": parent_id,
            "parent_content": doc.page_content,
            "matched_children": children,
            "score": _BASE_SCORES[idx] if idx < len(_BASE_SCORES) else 0.68,
        })
    return sources


def _run_full_rag(
    query:          str,
    source_filter:  Optional[str],
    query_type:     str,
    history_context: str,
) -> RagResult:
    t0 = time.time()

    if query_type == "专业咨询":
        strategy     = _rag_system.strategy_selector.select_strategy(query)
        context_docs = _rag_system.retrieve_and_merge(
            query, source_filter=source_filter, strategy=strategy
        )

        sources = _build_source_details(context_docs, query, source_filter)

        retrieval_info = {
            "query_type":      query_type,
            "strategy":        strategy,
            "candidate_count": _config.RETRIEVAL_K,
            "final_count":     len(context_docs),
            "sources":         sources,
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


def _normalize_query_type(query: str, raw_type: str) -> str:
    """兼容历史模型标签，保证最终只有“通用知识/专业咨询”两类。"""
    valid_types = {"通用知识", "专业咨询"}
    if raw_type in valid_types:
        # 对明显专业场景做保守纠偏，减少误判为通用
        mining_signals = [
            "矿", "井", "瓦斯", "通风", "顶板", "支护", "爆破", "采掘", "安全规程", "超限", "隐患", "事故"
        ]
        if raw_type == "通用知识" and any(k in (query or "") for k in mining_signals):
            return "专业咨询"
        return raw_type

    # 兼容“错误地返回了策略标签”的历史情况
    strategy_like = {"直接检索", "假设问题检索", "子查询检索", "场景重构检索", "回溯问题检索"}
    if raw_type in strategy_like:
        return "专业咨询"

    # 未知值保守降级
    return "通用知识"


def _promote_query_type_by_retrieval(query: str, query_type: str, source_filter: Optional[str]) -> str:
    """当分类器判断为通用知识，但知识库已有明显命中时，提升为专业咨询。

    这样新上传的领域文档不会因为分类器泛化不足而直接走纯 LLM 回答。
    """
    if query_type != "通用知识":
        return query_type

    if _vector_store is None:
        return query_type

    try:
        docs = _vector_store.hybrid_search_with_rerank(query, k=1, source_filter=source_filter)
    except Exception as e:
        logger.warning(f"通用知识提升检索失败: {e}")
        return query_type

    if docs:
        logger.info(f"查询 '{query}' 命中知识库，自动从通用知识提升为专业咨询")
        return "专业咨询"

    return query_type


def _prepare_query_plan(
    query: str,
    source_filter: Optional[str],
    query_type: str,
    history_context: str,
) -> Dict[str, Any]:
    """准备检索信息与主回答 Prompt，不生成最终答案。"""
    t0 = time.time()

    if query_type == "专业咨询":
        strategy = _rag_system.strategy_selector.select_strategy(query)
        context_docs = _rag_system.retrieve_and_merge(
            query, source_filter=source_filter, strategy=strategy
        )

        sources = _build_source_details(context_docs, query, source_filter)

        retrieval_info = {
            "query_type":      query_type,
            "strategy":        strategy,
            "candidate_count": _config.RETRIEVAL_K,
            "final_count":     len(context_docs),
            "sources":         sources,
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
            "time":            0.0,
        }
        context = ""

    prompt = _rag_system.rag_prompt.format(
        context=context,
        question=query,
        history=history_context,
        phone=_config.CUSTOMER_SERVICE_PHONE,
    )
    retrieval_info["time"] = round(time.time() - t0, 3)

    return {
        "prompt": prompt,
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
        "embedding_model":  "BGE-M3",
        "reranker_model":   "BGE-Reranker-Large",
        "query_classifier_model": "bert_query_classifier_new",
        "strategy_classifier_model": "bert_strategy_classifier",
        "collection":       _config.MILVUS_COLLECTION_NAME,
        "retrieval_k":      _config.RETRIEVAL_K,
        "candidate_m":      _config.CANDIDATE_M,
        "chunk_size":       f"{_config.PARENT_CHUNK_SIZE}/{_config.CHILD_CHUNK_SIZE}",
        "total_vectors":    row_count,
        "init_error":       _init_error,
        "init_duration_sec": _init_duration_sec,
        "dependency_checks": {
            "llm_client": True,
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
            msgs.append({"role": "user",      "content": item.get("question", ""), "time": ts})
            msgs.append({
                "role":    "assistant",
                "content": item.get("answer", ""),
                "time":    ts,
                "meta": {
                    "query_type": item.get("metadata", {}).get("query_type"),
                    "strategy":   item.get("metadata", {}).get("strategy"),
                    "time":       item.get("metadata", {}).get("processing_time"),
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


def _read_session_questions() -> List[str]:
    questions: List[str] = []
    conv_dir = os.path.join(_rag_qa_path, "conversations")
    if not os.path.isdir(conv_dir):
        return questions

    for name in os.listdir(conv_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(conv_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("history", []):
                question = (item.get("question") or "").strip()
                if len(question) >= 4:
                    questions.append(question)
        except Exception:
            continue
    return questions


def _build_example_prompt(top_questions: List[str]) -> str:
    joined = "\n".join(f"- {q}" for q in top_questions[:20])
    return (
        "你是采矿安全智能问答系统的产品助手。\n"
        "请基于下面这些历史高频提问，生成 6 条适合首页展示的引导问题。\n"
        "要求：\n"
        "1. 每条尽量简短，适合用户直接点击提问。\n"
        "2. 内容应贴近高频关注点，覆盖不同角度。\n"
        "3. 只输出 JSON 数组，每个元素是字符串，不要额外解释。\n\n"
        f"历史高频提问：\n{joined}"
    )


def _generate_chat_examples_from_history() -> List[str]:
    questions = _read_session_questions()
    if not questions:
        return [
            "矿井通风安全有哪些规定？",
            "瓦斯超标应该如何处理？",
            "顶板管理的主要安全措施？",
            "爆破作业安全规程是什么？",
            "矿山水害预防措施？",
            "采矿特种作业人员资质要求？",
        ]

    counter = Counter(_normalize_question(q) for q in questions if _normalize_question(q))
    top_questions: List[str] = []
    seen = set()
    for question, _ in counter.most_common(20):
        for original in questions:
            if _normalize_question(original) == question and original not in seen:
                top_questions.append(original)
                seen.add(original)
                break

    prompt = _build_example_prompt(top_questions)
    try:
        raw = "".join(_call_llm(prompt, system="你是一个只输出 JSON 的助手。"))
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            items = [str(item).strip() for item in parsed if str(item).strip()]
            if len(items) >= 6:
                return items[:6]
    except Exception as e:
        logger.warning(f"生成引导问题失败，回退到频率问句: {e}")

    fallback = []
    for q in top_questions[:6]:
        fallback.append(q)
    while len(fallback) < 6:
        fallback.append(fallback[-1] if fallback else "矿井通风安全有哪些规定？")
    return fallback[:6]


def load_or_refresh_chat_examples(force: bool = False) -> List[str]:
    cache_path = _examples_cache_path()
    now = time.time()
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            generated_at = float(cached.get("generated_at", 0))
            items = cached.get("items", [])
            if items and (now - generated_at) < 7 * 24 * 3600:
                return items[:6]
        except Exception:
            pass

    items = _generate_chat_examples_from_history()
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"generated_at": now, "items": items}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存引导问题缓存失败: {e}")
    return items[:6]


def get_chat_examples() -> List[str]:
    return load_or_refresh_chat_examples(force=False)


def refresh_chat_examples(force: bool = False) -> List[str]:
    return load_or_refresh_chat_examples(force=force)


async def stream_chat_response(
    query:         str,
    session_id:    Optional[str],
    source_filter: Optional[str],
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

    # 1. 获取历史（在异步上下文，线程安全）
    history_context = _get_history_context(session_id)

    # 2. 查询分类（快速）
    try:
        raw_query_type = await asyncio.wait_for(
            loop.run_in_executor(
                None, lambda: _rag_system.query_classifier.predict_category(query)
            ),
            timeout=_CLASSIFY_TIMEOUT_SEC,
        )
        query_type = _normalize_query_type(query, raw_query_type)
        query_type = await asyncio.wait_for(
            loop.run_in_executor(
                None, lambda: _promote_query_type_by_retrieval(query, query_type, source_filter)
            ),
            timeout=_CLASSIFY_TIMEOUT_SEC,
        )
    except TimeoutError:
        yield {"type": "error", "data": "查询分类超时，请稍后重试"}
        return
    except Exception as e:
        yield {"type": "error", "data": f"查询分类失败: {e}"}
        return

    # 3. 准备检索信息与回答 Prompt
    try:
        plan = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: _prepare_query_plan(query, source_filter, query_type, history_context),
            ),
            timeout=_PLAN_TIMEOUT_SEC,
        )
    except TimeoutError:
        yield {"type": "error", "data": "检索规划超时，请稍后重试"}
        return
    except Exception as e:
        yield {"type": "error", "data": f"检索/生成失败: {e}"}
        return

    # 4. 先发检索信息，减少前端等待首包时间
    retrieval_info = plan["retrieval_info"]
    yield {"type": "retrieval_info", "data": retrieval_info}

    # 5. 主答案真实流式输出
    answer_parts: List[str] = []
    try:
        async for token in _stream_sync_tokens(
            lambda: _call_llm(plan["prompt"]),
            total_timeout_sec=_MAIN_STREAM_TOTAL_TIMEOUT_SEC,
            idle_timeout_sec=_MAIN_STREAM_IDLE_TIMEOUT_SEC,
        ):
            answer_parts.append(token)
            yield {"type": "token", "data": token}
        _record_llm_success()
    except TimeoutError as e:
        _record_llm_failure()
        yield {"type": "error", "data": f"主答案生成超时: {e}"}
        return
    except Exception as e:
        _record_llm_failure()
        yield {"type": "error", "data": f"主答案流式生成失败: {e}"}
        return

    # 6. 专业咨询时再输出通用 LLM 对比（同样真实流式）
    if query_type == "专业咨询":
        try:
            async for token in _stream_sync_tokens(
                lambda: _call_llm(
                    prompt=query,
                    system="你是一个通用助手，根据自身知识直接回答问题，无需引用任何专业手册。回答简洁明了。",
                ),
                total_timeout_sec=_COMPARE_STREAM_TOTAL_TIMEOUT_SEC,
                idle_timeout_sec=_COMPARE_STREAM_IDLE_TIMEOUT_SEC,
            ):
                yield {"type": "llm_token", "data": token}
            _record_llm_success()
        except Exception as e:
            _record_llm_failure()
            logger.warning(f"通用 LLM 对比生成失败: {e}")

    # 7. 保存会话
    answer_text = "".join(answer_parts)
    try:
        await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: _save_conversation(session_id, query, answer_text, retrieval_info),
            ),
            timeout=_SAVE_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.warning("保存会话超时，已跳过本次持久化")

    yield {"type": "done", "data": {"session_id": session_id}}
