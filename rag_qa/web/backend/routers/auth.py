# -*- coding: utf-8 -*-
"""
认证路由：处理登录、登出、token 验证
"""
import sys
import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
_core_path = os.path.join(_rag_qa_path, "core")
for p in (_rag_qa_path, _core_path, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.auth_manager import get_auth_manager
from base import logger, Config

router = APIRouter()
auth_manager = get_auth_manager()
_config = Config()

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user_id: str
    username: str
    role: str
    email: str

class CredentialsResponse(BaseModel):
    """演示用：返回可用的账号密码"""
    accounts: list


def _resolve_token(token: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1).strip()
    return token

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    用户登录
    
    演示账号密码由环境变量控制，避免硬编码在代码中。
    """
    user = auth_manager.authenticate(request.username, request.password)
    if not user:
        logger.warning(f"登录失败：{request.username}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    token = auth_manager.create_token(user["user_id"], user["username"], user["role"])
    
    auth_manager.log_action(
        user_id=user["user_id"],
        username=user["username"],
        action="login",
        resource="auth",
        details={"ip": "127.0.0.1"}
    )
    
    logger.info(f"用户登录成功：{request.username}")
    return LoginResponse(
        token=token,
        user_id=user["user_id"],
        username=user["username"],
        role=user["role"],
        email=user["email"]
    )

@router.post("/logout")
def logout(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """用户登出"""
    token = _resolve_token(token, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 无效")
    payload = auth_manager.verify_token(token)
    if payload:
        auth_manager.log_action(
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            action="logout",
            resource="auth"
        )
        logger.info(f"用户登出：{payload.get('username')}")
        return {"message": "登出成功"}
    raise HTTPException(status_code=401, detail="Token 无效")

@router.get("/verify")
def verify_token(token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """验证 token"""
    token = _resolve_token(token, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "valid": True
    }

@router.get("/credentials", response_model=CredentialsResponse)
def get_demo_credentials():
    """
    获取演示账号（仅用于开发/演示）
    """
    return CredentialsResponse(
        accounts=[
            {
                "username": "supervisor",
                "password": "<由 EDURAG_DEFAULT_SUPERVISOR_PASSWORD 提供>",
                "role": "主管",
                "description": "可以查看所有反馈、会话、管理知识库版本"
            },
            {
                "username": "user",
                "password": "demo-user-pass-change-me",
                "role": "普通用户",
                "description": "可以提问、提交反馈"
            }
        ]
    )
