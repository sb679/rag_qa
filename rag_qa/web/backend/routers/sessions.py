# -*- coding: utf-8 -*-
import sys
import os

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter, HTTPException
from schemas import NewSessionRequest
import rag_service

router = APIRouter()


@router.get("/")
def list_sessions():
    return {"sessions": rag_service.list_sessions()}


@router.post("/")
def create_session(req: NewSessionRequest = None):
    meta       = req.metadata if req else None
    session_id = rag_service.create_session(meta)
    return {"session_id": session_id}


@router.get("/{session_id}/messages")
def get_session_messages(session_id: str):
    """返回某会话的历史消息列表，用于切换会话时回显"""
    msgs = rag_service.get_session_messages(session_id)
    return {"messages": msgs}


@router.delete("/{session_id}")
def delete_session(session_id: str):
    ok = rag_service.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True}
