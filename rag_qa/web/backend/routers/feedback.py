# -*- coding: utf-8 -*-
"""
反馈路由：处理用户反馈提交、查询、统计
"""
import sys
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
_core_path = os.path.join(_rag_qa_path, "core")
for p in (_rag_qa_path, _core_path, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.feedback_manager import get_feedback_manager
from base import logger

router = APIRouter()
feedback_manager = get_feedback_manager()

class FeedbackSubmitRequest(BaseModel):
    session_id: str
    message_index: int
    user_id: str
    feedback_type: str  # like, dislike, partial_correct, correction
    content: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    query_type: Optional[str] = None
    strategy: Optional[str] = None
    panel_info: Optional[dict] = None

class FeedbackResponse(BaseModel):
    success: bool
    message: str


class FeedbackStatusUpdateRequest(BaseModel):
    session_id: str
    message_index: int
    user_id: str
    timestamp: str
    status: str
    handler_id: Optional[str] = None

@router.post("/submit", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackSubmitRequest):
    """
    提交反馈
    
    feedback_type 可选值：
    - like: 点赞
    - dislike: 点踩
    - partial_correct: 部分正确
    - correction: 纠错（需要提供 content）
    """
    if request.feedback_type in {"partial_correct", "correction"} and not request.content:
        detail = "部分正确反馈必须说明哪些内容正确、哪些内容需要补充" if request.feedback_type == "partial_correct" else "纠错反馈必须提供内容"
        raise HTTPException(status_code=400, detail=detail)
    
    success = feedback_manager.submit_feedback(
        session_id=request.session_id,
        message_index=request.message_index,
        user_id=request.user_id,
        feedback_type=request.feedback_type,
        content=request.content,
        question=request.question or "",
        answer=request.answer or "",
        query_type=request.query_type or "",
        strategy=request.strategy or "",
        panel_info=request.panel_info,
    )
    
    if success:
        logger.info(f"反馈已提交：{request.session_id} - {request.feedback_type}")
        return FeedbackResponse(success=True, message="反馈提交成功")
    else:
        logger.error(f"反馈提交失败：{request.session_id}")
        raise HTTPException(status_code=500, detail="反馈提交失败")


class FeedbackCancelRequest(BaseModel):
    session_id: str
    message_index: int
    user_id: str


@router.post("/cancel", response_model=FeedbackResponse)
def cancel_feedback(request: FeedbackCancelRequest):
    """撤销当前用户对某条消息的反馈。"""
    ok = feedback_manager.cancel_feedback(
        session_id=request.session_id,
        message_index=request.message_index,
        user_id=request.user_id,
    )
    if ok:
        return FeedbackResponse(success=True, message="反馈已撤销")
    raise HTTPException(status_code=500, detail="撤销反馈失败")

@router.get("/session/{session_id}")
def get_session_feedback(session_id: str):
    """获取会话的所有反馈"""
    feedbacks = feedback_manager.get_session_feedback(session_id)
    return {
        "session_id": session_id,
        "feedbacks": feedbacks,
        "total": len(feedbacks)
    }

@router.get("/user/{user_id}")
def get_user_feedback(user_id: str):
    """获取用户的所有反馈"""
    feedbacks = feedback_manager.get_user_feedback(user_id)
    return {
        "user_id": user_id,
        "feedbacks": feedbacks,
        "total": len(feedbacks)
    }

@router.get("/stats")
def get_feedback_stats():
    """获取反馈统计（主管用）"""
    stats = feedback_manager.get_feedback_stats()
    return {
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "stats": stats
    }


@router.post("/status", response_model=FeedbackResponse)
def update_feedback_status(request: FeedbackStatusUpdateRequest):
    valid_statuses = {"pending", "reviewed", "resolved", "ignored"}
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="无效的反馈处理状态")

    ok = feedback_manager.update_feedback_status(
        session_id=request.session_id,
        message_index=request.message_index,
        user_id=request.user_id,
        timestamp=request.timestamp,
        status=request.status,
        handler_id=request.handler_id or "",
    )
    if ok:
        return FeedbackResponse(success=True, message="反馈处理状态已更新")
    raise HTTPException(status_code=404, detail="未找到对应反馈记录")

@router.get("/all")
def get_all_feedbacks():
    """获取所有反馈（主管用）"""
    feedbacks = feedback_manager.get_all_feedbacks()
    return {
        "total": len(feedbacks),
        "feedbacks": feedbacks
    }
