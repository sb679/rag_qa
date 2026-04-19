# -*- coding: utf-8 -*-
"""
测试集生成路由：使用 IDEA-CCNL/Randeng-BART-139M-QG-Chinese 从知识库文本生成问答对
"""
import sys
import os
import json
import random
import asyncio

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir     = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
for p in (_backend_dir, _rag_qa_path, os.path.join(_rag_qa_path, "core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import rag_service
from core.auth_manager import get_auth_manager
from base import logger

router = APIRouter()
auth_manager = get_auth_manager()

# ── BART 模型懒加载 ───────────────────────────────────────────────────────────
_bart_model     = None
_bart_tokenizer = None


def _load_bart():
    global _bart_model, _bart_tokenizer
    if _bart_model is not None:
        return True
    try:
        from transformers import BartForConditionalGeneration, AutoTokenizer
        import torch

        # 优先本地路径
        local_paths = [
            os.path.join(_rag_qa_path, "models", "Randeng-BART-139M-QG-Chinese"),
            os.path.join(_rag_qa_path, "models", "IDEA-CCNL", "Randeng-BART-139M-QG-Chinese"),
        ]
        model_path = next((p for p in local_paths if os.path.isdir(p)),
                          "IDEA-CCNL/Randeng-BART-139M-QG-Chinese")

        _bart_tokenizer = AutoTokenizer.from_pretrained(model_path)
        _bart_model     = BartForConditionalGeneration.from_pretrained(model_path)
        _bart_model.eval()
        return True
    except Exception as e:
        logger.error(f"BART 模型加载失败: {e}")
        return False


def _generate_question(context: str) -> Optional[str]:
    """从文本段落生成问题（BART QG）"""
    if not _load_bart():
        return None
    import torch

    # 提取第一句作为"答案"锚点
    first_sent = context.split("。")[0].strip()[:60] if "。" in context else context[:60]
    input_text = f"答案：{first_sent}，上下文：{context[:300]}"

    try:
        inputs = _bart_tokenizer(input_text, return_tensors="pt",
                                  max_length=512, truncation=True)
        with torch.no_grad():
            outputs = _bart_model.generate(
                inputs.input_ids,
                max_length    = 64,
                num_beams     = 4,
                early_stopping = True,
            )
        question = _bart_tokenizer.decode(outputs[0], skip_special_tokens=True)
        return question if question else None
    except Exception as e:
        logger.warning(f"问题生成失败: {e}")
        return None


class TestGenRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=20)
    source_filter: str = "mining"


class AppendTestsetRequest(BaseModel):
    target_file: str
    dataset: List[Dict[str, Any]]


def _require_supervisor(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = authorization.replace("Bearer ", "")
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可执行该操作")
    return payload


def _generated_dataset_dir() -> str:
    save_dir = os.path.join(_rag_qa_path, "rag_assesment", "generated_datasets")
    os.makedirs(save_dir, exist_ok=True)
    return save_dir


@router.get("/dataset-files")
def list_generated_dataset_files(authorization: Optional[str] = Header(None)):
    """列出可追加的问答对文件。"""
    _require_supervisor(authorization)
    save_dir = _generated_dataset_dir()
    files = []
    for name in sorted(os.listdir(save_dir), reverse=True):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(save_dir, name)
        if not os.path.isfile(path):
            continue
        files.append(
            {
                "name": name,
                "size": os.path.getsize(path),
                "updated_at": os.path.getmtime(path),
            }
        )
    return {"files": files}


@router.post("/append")
def append_generated_dataset(req: AppendTestsetRequest, authorization: Optional[str] = Header(None)):
    """将本次生成的问答对追加到已有文件。"""
    _require_supervisor(authorization)
    if not req.dataset:
        raise HTTPException(status_code=400, detail="追加数据为空")

    target_name = os.path.basename(req.target_file or "")
    if not target_name.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="目标文件必须是 JSON")

    target_path = os.path.join(_generated_dataset_dir(), target_name)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="目标文件不存在")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        if not isinstance(old_data, list):
            raise HTTPException(status_code=400, detail="目标文件格式不是数组")

        start_idx = len(old_data) + 1
        append_data = []
        for i, item in enumerate(req.dataset):
            obj = dict(item)
            obj["id"] = start_idx + i
            append_data.append(obj)

        merged = old_data + append_data
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        return {
            "target_file": target_name,
            "appended": len(append_data),
            "total": len(merged),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追加失败: {e}")


@router.post("/generate")
async def generate_testset(req: TestGenRequest, authorization: Optional[str] = Header(None)):
    """
    从知识库随机抽取文本块，用 BART 生成问答对。
    返回 SSE 流：
      {"type": "loading",   "message": "..."}
      {"type": "progress",  "current": N, "total": M, "item": {...}}
      {"type": "done",      "dataset": [...], "saved_path": "..."}
      {"type": "error",     "data": "..."}
    """
    loop = asyncio.get_event_loop()

    async def stream():
        try:
            _require_supervisor(authorization)
            yield f"data: {json.dumps({'type': 'loading', 'message': '正在加载 BART 模型…'}, ensure_ascii=False)}\n\n"

            # 加载模型
            ok = await loop.run_in_executor(None, _load_bart)
            if not ok:
                yield f"data: {json.dumps({'type': 'error', 'data': 'BART 模型加载失败，请检查模型路径'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'loading', 'message': '正在从知识库抽取文本…'}, ensure_ascii=False)}\n\n"

            # 从 Milvus 抽取文本块
            vs = rag_service.get_vector_store()
            conf = rag_service.get_config()
            try:
                source_filter = (req.source_filter or "").strip()
                filter_expr = f"source == '{source_filter}'" if source_filter else ""
                raw = vs.client.query(
                    collection_name = conf.MILVUS_COLLECTION_NAME,
                    filter          = filter_expr,
                    output_fields   = ["text", "source", "parent_content"],
                    limit           = min(req.count * 8, 1000),
                )
                # 过滤太短的文本，洗牌后取需要数量
                candidates = [r for r in raw if len(r.get("text", "")) > 80]
                random.shuffle(candidates)
                candidates = candidates[:req.count]
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'data': f'知识库查询失败: {e}'}, ensure_ascii=False)}\n\n"
                return

            if not candidates:
                yield f"data: {json.dumps({'type': 'error', 'data': '知识库中未找到符合条件的文本块'}, ensure_ascii=False)}\n\n"
                return

            total   = len(candidates)
            dataset = []

            for idx, item in enumerate(candidates, 1):
                context = item.get("parent_content") or item.get("text", "")
                # 生成问题
                question = await loop.run_in_executor(
                    None, lambda c=context: _generate_question(c)
                )
                if not question:
                    question = f"请介绍以下内容：{context[:30]}…"

                qa_item = {
                    "id":       idx,
                    "question": question,
                    "context":  context[:400],
                    "source":   item.get("source", req.source_filter),
                }
                dataset.append(qa_item)
                yield f"data: {json.dumps({'type': 'progress', 'current': idx, 'total': total, 'item': qa_item}, ensure_ascii=False)}\n\n"

            # 保存数据集 JSON
            save_dir  = os.path.join(_rag_qa_path, "rag_assesment", "generated_datasets")
            os.makedirs(save_dir, exist_ok=True)
            from datetime import datetime
            fname      = f"testset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            save_path  = os.path.join(save_dir, fname)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, ensure_ascii=False, indent=2)

            yield f"data: {json.dumps({'type': 'done', 'dataset': dataset, 'saved_path': save_path, 'count': len(dataset)}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
