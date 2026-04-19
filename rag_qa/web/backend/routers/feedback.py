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

class FeedbackResponse(BaseModel):
    success: bool
    message: str

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
    if request.feedback_type == "correction" and not request.content:
        raise HTTPException(status_code=400, detail="纠错反馈必须提供内容")
    
    success = feedback_manager.submit_feedback(
        session_id=request.session_id,
        message_index=request.message_index,
        user_id=request.user_id,
        feedback_type=request.feedback_type,
        content=request.content
    )
    
    if success:
        logger.info(f"反馈已提交：{request.session_id} - {request.feedback_type}")
        return FeedbackResponse(success=True, message="反馈提交成功")
    else:
        logger.error(f"反馈提交失败：{request.session_id}")
        raise HTTPException(status_code=500, detail="反馈提交失败")

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

@router.get("/all")
def get_all_feedbacks():
    """获取所有反馈（主管用）"""
    feedbacks = feedback_manager.get_all_feedbacks()
    return {
        "total": len(feedbacks),
        "feedbacks": feedbacks
    }
