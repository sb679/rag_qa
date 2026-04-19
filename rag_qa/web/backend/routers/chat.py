# -*- coding: utf-8 -*-
import json
import sys
import os
import asyncio
import shutil
import tempfile
import threading
import time

# 确保能 import 兄弟目录的 schemas 和 rag_service
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from schemas import ChatRequest
import rag_service
from edu_document_loaders import OCRIMGLoader

router = APIRouter()
_scheduler_started = False


def _extract_image_text(image_path: str) -> str:
    loader = OCRIMGLoader(img_path=image_path)
    documents = loader.load()
    return "\n".join(doc.page_content for doc in documents if doc.page_content).strip()


def _error_stream(message: str):
    async def generator():
        yield f"data: {json.dumps({'type': 'error', 'data': message}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _refresh_examples_loop():
    while True:
        try:
            rag_service.refresh_chat_examples(force=False)
        except Exception:
            pass
        time.sleep(24 * 3600)


def start_examples_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_refresh_examples_loop, daemon=True).start()


@router.post("/send")
async def chat_send(request: ChatRequest):
    """
    发送消息，返回 SSE 流。
    前端通过 fetch + ReadableStream 接收，事件格式：
      data: {"type": "retrieval_info", "data": {...}}
      data: {"type": "token",          "data": "字"}
      data: {"type": "done",           "data": {"session_id": "..."}}
      data: {"type": "error",          "data": "..."}
    """
    async def generate():
        async for event in rag_service.stream_chat_response(
            query         = request.query,
            session_id    = request.session_id,
            source_filter = request.source_filter,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/examples")
def get_examples():
    return {"items": rag_service.get_chat_examples()}


@router.post("/send-image")
async def chat_send_image(
    image: UploadFile = File(...),
    query: str = Form(""),
    session_id: str | None = Form(None),
    source_filter: str | None = Form(None),
):
    """
    先 OCR 图片，再把识别文本拼入问题进入现有 RAG 流。
    """
    ext = os.path.splitext(image.filename or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
        return _error_stream(f"不支持的图片类型 {ext}")

    tmp_dir = tempfile.mkdtemp(prefix="chat_image_")
    image_path = os.path.join(tmp_dir, image.filename or f"upload{ext}")

    try:
        with open(image_path, "wb") as file_handle:
            file_handle.write(await image.read())

        loop = asyncio.get_running_loop()
        ocr_text = await loop.run_in_executor(None, lambda: _extract_image_text(image_path))
        merged_query = (query or "").strip()
        if ocr_text:
            merged_query = f"{merged_query}\n\n[图片OCR识别文本]\n{ocr_text}".strip() if merged_query else f"[图片OCR识别文本]\n{ocr_text}"

        if not merged_query:
            return _error_stream("图片未识别到可用文本，请补充文字说明后重试")

        async def generate():
            async for event in rag_service.stream_chat_response(
                query         = merged_query,
                session_id    = session_id,
                source_filter = source_filter,
            ):
                if event.get("type") == "retrieval_info":
                    event = {
                        **event,
                        "data": {**event["data"], "image_ocr_text": ocr_text[:500]},
                    }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            generate(),
            media_type = "text/event-stream",
            headers    = {
                "Cache-Control":   "no-cache",
                "X-Accel-Buffering": "no-cache",
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
