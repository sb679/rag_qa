# -*- coding: utf-8 -*-
"""
数据集管理路由：文档上传 + 增量向量化入库
支持 PDF / Word / PPT / TXT 等格式，增量添加，不清空已有数据
"""
import sys
import os
import json
import shutil
import asyncio
import uuid
from pathlib import Path

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir     = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
for p in (_backend_dir, _rag_qa_path, os.path.join(_rag_qa_path, "core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header
from fastapi.responses import StreamingResponse, FileResponse
from typing import Optional

from core.document_processor import process_documents
from core.auth_manager import get_auth_manager
import rag_service

router = APIRouter()
auth_manager = get_auth_manager()

# 支持的文件类型
ALLOWED_EXT = {".pdf", ".docx", ".ppt", ".pptx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
KNOWLEDGE_FILES_ROOT = Path(_rag_qa_path) / "user_data" / "knowledge_files"


def _ensure_source_dir(source: str) -> Path:
    source_dir = KNOWLEDGE_FILES_ROOT / source
    source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def _require_supervisor(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = authorization.replace("Bearer ", "")
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可上传知识库文件")


@router.post("/upload")
async def upload_document(
    file:   UploadFile = File(...),
    source: str        = Form("mining"),
    authorization: Optional[str] = Header(None),
):
    """
    上传文档并增量入库，返回 SSE 进度流：
      {"type": "progress", "step": "...", "pct": 0-100}
      {"type": "done",     "chunks": N, "filename": "..."}
      {"type": "error",    "data": "..."}
    """
    _require_supervisor(authorization)

    # 校验文件类型
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"不支持的文件类型 {ext}，支持：{', '.join(ALLOWED_EXT)}"}

    # 保存文件到持久目录：user_data/knowledge_files/{source}/{file_id}__{original_name}
    source_dir = _ensure_source_dir(source)
    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}__{file.filename}"
    file_path = str(source_dir / stored_name)
    content  = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    conf         = rag_service.get_config()
    vector_store = rag_service.get_vector_store()
    loop         = asyncio.get_event_loop()

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'step': f'文件已保存：{file.filename}', 'pct': 10}, ensure_ascii=False)}\n\n"

            # 文档处理（分块）
            chunks = await loop.run_in_executor(
                None,
                lambda: process_documents(
                    str(source_dir),
                    conf.PARENT_CHUNK_SIZE,
                    conf.CHILD_CHUNK_SIZE,
                    conf.CHUNK_OVERLAP,
                ),
            )
            yield f"data: {json.dumps({'type': 'progress', 'step': f'文本分块完成：{len(chunks)} 个块', 'pct': 45}, ensure_ascii=False)}\n\n"

            if not chunks:
                yield f"data: {json.dumps({'type': 'error', 'data': '未提取到文本内容，请检查文件'}, ensure_ascii=False)}\n\n"
                return

            # 向量化 + 入库（增量，不清空）
            yield f"data: {json.dumps({'type': 'progress', 'step': '正在向量化并写入数据库…', 'pct': 60}, ensure_ascii=False)}\n\n"
            await loop.run_in_executor(None, lambda: vector_store.add_documents([c for c in chunks if c.metadata.get("file_id") == file_id]))

            file_chunks = len([c for c in chunks if c.metadata.get("file_id") == file_id])
            yield f"data: {json.dumps({'type': 'done', 'chunks': file_chunks, 'filename': file.filename, 'file_id': file_id}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/files")
def list_files(source: str = ""):
    """返回原始上传文件清单（来自持久目录），并附带向量块数量。"""
    vector_store = rag_service.get_vector_store()
    knowledge_stats = rag_service.get_knowledge_stats()
    overview_files = {
        f.get("file_id") or f.get("name"): f
        for f in knowledge_stats.get("files", [])
    }

    source_dirs = []
    if source:
        source_dirs = [_ensure_source_dir(source)]
    else:
        if KNOWLEDGE_FILES_ROOT.exists():
            source_dirs = [p for p in KNOWLEDGE_FILES_ROOT.iterdir() if p.is_dir()]

    files = []
    for src_dir in source_dirs:
        src_name = src_dir.name
        if not src_dir.exists():
            continue

        for file_path in sorted(src_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not file_path.is_file():
                continue
            if file_path.name.endswith('.ocr_cache.json'):
                continue

            stored_name = file_path.name
            if "__" in stored_name:
                file_id, original_name = stored_name.split("__", 1)
            else:
                file_id, original_name = "", stored_name

            chunks = 0
            can_delete = bool(file_id)
            if file_id:
                rows = vector_store.get_file_rows(file_id, limit=16384)
                chunks = len(rows)

            files.append(
                {
                    "file_id": file_id,
                    "name": original_name,
                    "source": src_name,
                    "chunks": chunks,
                    "ratio": 0,
                    "can_view": True,
                    "can_delete": can_delete,
                }
            )

    seen_keys = {f.get("file_id") or f.get("name") for f in files}
    for key, item in overview_files.items():
        if key in seen_keys:
            continue
        files.append(
            {
                "file_id": item.get("file_id", ""),
                "name": item.get("name", key),
                "source": item.get("source", "unknown"),
                "chunks": item.get("chunks", 0),
                "ratio": item.get("ratio", 0),
                "can_view": bool(item.get("file_id")),
                "can_delete": bool(item.get("file_id")),
            }
        )

    return {"files": files}


@router.get("/files/{file_id}/download")
def download_file(file_id: str):
    """下载/查看原始上传文件。"""
    candidate = None
    pattern = f"{file_id}__*"
    if KNOWLEDGE_FILES_ROOT.exists():
        matches = [p for p in KNOWLEDGE_FILES_ROOT.rglob(pattern) if p.is_file()]
        non_cache = [p for p in matches if not p.name.endswith('.ocr_cache.json')]
        selected = non_cache or matches
        candidate = selected[0] if selected else None

    if (not candidate or not candidate.exists()) and file_id:
        vector_store = rag_service.get_vector_store()
        rows = vector_store.get_file_rows(file_id, limit=1)
        if rows:
            file_path = rows[0].get("file_path")
            if file_path and os.path.exists(file_path):
                candidate = Path(file_path)

    if not candidate or not candidate.exists():
        raise HTTPException(status_code=404, detail="原始文件不存在")

    name = candidate.name.split("__", 1)[1] if "__" in candidate.name else candidate.name
    return FileResponse(path=str(candidate), filename=name)


@router.get("/files/legacy/download")
def download_legacy_file(name: str, source: str = ""):
    """尝试按历史元数据定位并下载原始文件。"""
    vector_store = rag_service.get_vector_store()
    rows = vector_store.get_file_rows_by_name(name, source=source, limit=100)
    if not rows:
        raise HTTPException(status_code=404, detail="未找到历史文件元数据")

    # 优先返回真实原文件，避免返回 OCR 缓存文件
    valid_paths = []
    for row in rows:
        fp = row.get("file_path")
        if fp and os.path.exists(fp):
            valid_paths.append(fp)

    if not valid_paths:
        raise HTTPException(status_code=404, detail="历史文件原始路径不存在")

    non_cache = [p for p in valid_paths if not p.endswith('.ocr_cache.json')]
    candidate = non_cache[0] if non_cache else valid_paths[0]
    download_name = os.path.basename(candidate)
    if "__" in download_name:
        download_name = download_name.split("__", 1)[1]

    return FileResponse(path=candidate, filename=download_name)


@router.delete("/files/{file_id}")
def delete_file(file_id: str):
    """删除文件对应向量块，并删除本地原始文件。"""
    vector_store = rag_service.get_vector_store()
    result = vector_store.delete_file_by_id(file_id)

    removed_files = 0
    pattern = f"{file_id}__*"
    if KNOWLEDGE_FILES_ROOT.exists():
        for fp in KNOWLEDGE_FILES_ROOT.rglob(pattern):
            if fp.is_file():
                try:
                    os.remove(fp)
                    removed_files += 1
                except Exception:
                    pass

    if removed_files == 0:
        for fp in result.get("file_paths", []):
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                    removed_files += 1
                except Exception:
                    pass

    return {
        "file_id": file_id,
        "deleted_chunks": result.get("deleted_chunks", 0),
        "deleted_files": removed_files,
    }
