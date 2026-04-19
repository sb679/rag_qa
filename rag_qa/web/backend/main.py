# -*- coding: utf-8 -*-
import sys
import os

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_web_dir     = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
sys.path.insert(0, _rag_qa_path)
sys.path.insert(0, _backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from base import logger
from routers import chat, sessions, knowledge, dataset, testgen, auth, feedback, kb_version, users

_startup_errors = []

app = FastAPI(
    title       = "EduRAG 采矿安全智能问答系统",
    description = "基于 RAG 的采矿安全知识问答 API",
    version     = "2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(users.router,     prefix="/api/users",     tags=["用户管理"])
app.include_router(auth.router,      prefix="/api/auth",      tags=["认证"])
app.include_router(feedback.router,  prefix="/api/feedback",  tags=["反馈"])
app.include_router(kb_version.router, prefix="/api/kb-version", tags=["知识库版本"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["对话"])
app.include_router(sessions.router,  prefix="/api/sessions",  tags=["会话"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(dataset.router,   prefix="/api/dataset",   tags=["数据集管理"])
app.include_router(testgen.router,   prefix="/api/testgen",   tags=["测试集生成"])


@app.on_event("startup")
def startup_tasks():
    chat.start_examples_scheduler()
    try:
        import rag_service
        rag_service.load_or_refresh_chat_examples(force=False)
    except Exception as e:
        _startup_errors.append(str(e))
        logger.exception("启动预热失败")

@app.get("/api/health")
def health():
    if _startup_errors:
        return {
            "status": "degraded",
            "mode": "真实模式",
            "startup_errors": _startup_errors[-3:],
        }
    return {"status": "ok", "mode": "真实模式"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
