# -*- coding: utf-8 -*-
"""Lightweight backend entrypoint for standalone WeChat annotation.

This app only serves the local WeChat annotation router and does not import
the main RAG chat/knowledge/session stack.
"""
from __future__ import annotations

import os
import sys

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_web_dir = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
for path in (_rag_qa_path, _backend_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import wechat_annotator


app = FastAPI(
    title="采矿安全智能问答系统公众号标注服务",
    description="仅用于本地公众号图片标注，不依赖 RAG 主系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wechat_annotator.router, prefix="/api/wechat-annotator", tags=["公众号标注"])


@app.on_event("startup")
def startup_tasks():
    wechat_annotator.ensure_agent_task_worker_started()


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "standalone-wechat-annotator"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("wechat_annotator_main:app", host="0.0.0.0", port=8001, reload=True)