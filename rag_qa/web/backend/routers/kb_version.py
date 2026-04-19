# -*- coding: utf-8 -*-
"""
知识库版本路由：处理版本创建、发布、回滚、查询
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

from core.knowledge_version_manager import get_kb_version_manager
from base import logger

router = APIRouter()
kb_version_manager = get_kb_version_manager()

class CreateVersionRequest(BaseModel):
    version: str
    description: str = ""
    status: str = "draft"

class PublishVersionRequest(BaseModel):
    version: str

class VersionResponse(BaseModel):
    success: bool
    message: str

@router.get("/list")
def list_versions():
    """获取所有版本"""
    versions = kb_version_manager.list_versions()
    current = kb_version_manager.get_current_version()
    return {
        "current_version": current,
        "versions": versions,
        "total": len(versions)
    }

@router.get("/current")
def get_current_version():
    """获取当前版本"""
    current = kb_version_manager.get_current_version()
    detail = kb_version_manager.get_version_detail(current)
    return {
        "current_version": current,
        "detail": detail
    }

@router.get("/detail/{version}")
def get_version_detail(version: str):
    """获取版本详情"""
    detail = kb_version_manager.get_version_detail(version)
    if not detail:
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    return detail

@router.post("/create", response_model=VersionResponse)
def create_version(request: CreateVersionRequest):
    """创建新版本（主管用）"""
    success = kb_version_manager.create_version(
        version=request.version,
        description=request.description,
        status=request.status
    )
    if success:
        logger.info(f"创建版本成功：{request.version}")
        return VersionResponse(success=True, message=f"版本 {request.version} 创建成功")
    else:
        logger.warning(f"创建版本失败：{request.version}")
        raise HTTPException(status_code=400, detail="版本已存在或创建失败")

@router.post("/publish", response_model=VersionResponse)
def publish_version(request: PublishVersionRequest):
    """发布版本（主管用）"""
    success = kb_version_manager.publish_version(request.version)
    if success:
        logger.info(f"发布版本成功：{request.version}")
        return VersionResponse(success=True, message=f"版本 {request.version} 已发布")
    else:
        logger.warning(f"发布版本失败：{request.version}")
        raise HTTPException(status_code=404, detail="版本不存在或发布失败")

@router.post("/rollback", response_model=VersionResponse)
def rollback_version(request: PublishVersionRequest):
    """回滚到指定版本（主管用）"""
    success = kb_version_manager.rollback_version(request.version)
    if success:
        logger.info(f"回滚版本成功：{request.version}")
        return VersionResponse(success=True, message=f"已回滚到版本 {request.version}")
    else:
        logger.warning(f"回滚版本失败：{request.version}")
        raise HTTPException(status_code=404, detail="版本不存在或回滚失败")
