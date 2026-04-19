# -*- coding: utf-8 -*-
import sys
import os

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_web_dir     = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
sys.path.insert(0, _rag_qa_path)
sys.path.insert(0, _backend_dir)

from fastapi import FastAPI
from fastapi import Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response
import time
import uuid
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest
from base import logger, log_event, ErrorAlertMonitor, Config
from routers import chat, sessions, knowledge, dataset, testgen, auth, feedback, kb_version, users

_startup_errors = []
_config = Config()
_error_alert_monitor = ErrorAlertMonitor(
    threshold=_config.LOG_ALERT_ERROR_THRESHOLD,
    window_sec=_config.LOG_ALERT_WINDOW_SEC,
)
_http_request_total = Counter(
    "edurag_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
_http_request_duration_ms = Histogram(
    "edurag_http_request_duration_ms",
    "HTTP request duration in milliseconds",
    ["method", "path"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)

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


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            "error",
            "request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(e),
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-Id"] = request_id
    level = "warning" if response.status_code >= 400 else "info"
    _http_request_total.labels(request.method, request.url.path, str(response.status_code)).inc()
    _http_request_duration_ms.labels(request.method, request.url.path).observe(duration_ms)
    log_event(
        level,
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    if response.status_code >= 500:
        alert = _error_alert_monitor.record_error()
        if alert:
            log_event(
                "error",
                "error_alert_triggered",
                request_id=request_id,
                status_code=response.status_code,
                **alert,
            )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        alert = _error_alert_monitor.record_error()
        if alert:
            log_event(
                "error",
                "error_alert_triggered",
                path=request.url.path,
                status_code=exc.status_code,
                **alert,
            )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    alert = _error_alert_monitor.record_error()
    if alert:
        log_event(
            "error",
            "error_alert_triggered",
            path=request.url.path,
            status_code=500,
            **alert,
        )
    logger.exception("未处理异常")
    return JSONResponse(status_code=500, content={"detail": "内部服务错误"})


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


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
