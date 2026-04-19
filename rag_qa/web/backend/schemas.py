# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    source_filter: Optional[str] = None
    include_source_details: bool = True


class SourceDocument(BaseModel):
    content: str
    source: str
    score: float


class RetrievalInfo(BaseModel):
    query_type: str                      # "通用知识" | "专业咨询"
    strategy: Optional[str] = None
    candidate_count: int = 0
    final_count: int = 0
    sources: List[SourceDocument] = []
    error_type: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None


class NewSessionRequest(BaseModel):
    metadata: Optional[Dict[str, Any]] = None
