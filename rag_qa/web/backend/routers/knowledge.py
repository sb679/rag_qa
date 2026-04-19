# -*- coding: utf-8 -*-
import sys
import os

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter
import rag_service

router = APIRouter()


@router.get("/status")
def get_status():
    return {
        "system":    rag_service.get_system_status(),
        "knowledge": rag_service.get_knowledge_stats(),
    }
