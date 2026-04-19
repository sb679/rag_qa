# -*- coding: utf-8 -*-
"""
用户管理路由：处理员工账号的增删改查
"""
import sys
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from fastapi.responses import FileResponse

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_web_dir = os.path.dirname(_backend_dir)
_rag_qa_path = os.path.dirname(_web_dir)
_core_path = os.path.join(_rag_qa_path, "core")
for p in (_rag_qa_path, _core_path, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.user_manager import get_user_manager
from core.auth_manager import get_auth_manager
from base import logger

router = APIRouter()
user_manager = get_user_manager()
auth_manager = get_auth_manager()
AVATAR_ROOT = Path(_rag_qa_path) / "user_data" / "avatars"
AVATAR_ROOT.mkdir(parents=True, exist_ok=True)

class LoginRequest(BaseModel):
    employee_id: str
    password: str

class LoginResponse(BaseModel):
    token: str
    employee_id: str
    role: str
    nickname: str
    avatar: str

class CreateUserRequest(BaseModel):
    employee_id: str
    password: str
    nickname: str

class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None

class UserResponse(BaseModel):
    employee_id: str
    nickname: str
    avatar: str
    created_at: str
    created_by: str

def verify_token_header(authorization: Optional[str] = Header(None)) -> dict:
    """验证 token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    
    token = authorization.replace("Bearer ", "")
    payload = auth_manager.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    
    return payload

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    用户登录（工号 + 密码）
    
    默认账号：
    - 主管：9526/9526, 9527/9527, 9528/9528
    """
    user = user_manager.authenticate(request.employee_id, request.password)
    if not user:
        logger.warning(f"登录失败：{request.employee_id}")
        raise HTTPException(status_code=401, detail="工号或密码错误")
    
    token = auth_manager.create_token(
        user_id=user["employee_id"],
        username=user["employee_id"],
        role=user["role"]
    )
    
    auth_manager.log_action(
        user_id=user["employee_id"],
        username=user["employee_id"],
        action="login",
        resource="auth",
        details={"role": user["role"]}
    )
    
    logger.info(f"用户登录成功：{request.employee_id} ({user['role']})")
    return LoginResponse(
        token=token,
        employee_id=user["employee_id"],
        role=user["role"],
        nickname=user["nickname"],
        avatar=user["avatar"]
    )

@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    """用户登出"""
    payload = verify_token_header(authorization)
    auth_manager.log_action(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        action="logout",
        resource="auth"
    )
    logger.info(f"用户登出：{payload.get('username')}")
    return {"message": "登出成功"}

@router.get("/profile")
def get_profile(authorization: Optional[str] = Header(None)):
    """获取当前用户信息"""
    payload = verify_token_header(authorization)
    user_info = user_manager.get_user_info(payload.get("user_id"))
    if not user_info:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user_info

@router.put("/profile")
def update_profile(
    request: UpdateUserRequest,
    authorization: Optional[str] = Header(None)
):
    """更新当前用户信息"""
    payload = verify_token_header(authorization)
    employee_id = payload.get("user_id")
    
    updates = {}
    if request.password is not None:
        updates["password"] = request.password
    if request.nickname is not None:
        updates["nickname"] = request.nickname
    if request.avatar is not None:
        updates["avatar"] = request.avatar
    
    success = user_manager.update_user(employee_id, updates, employee_id)
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    
    return {"message": "更新成功"}


@router.post("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """上传头像并更新当前用户头像地址。"""
    payload = verify_token_header(authorization)
    employee_id = payload.get("user_id")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/webp/gif/bmp")

    avatar_name = f"{employee_id}_{uuid.uuid4().hex[:10]}{ext}"
    avatar_path = AVATAR_ROOT / avatar_name

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="头像大小不能超过 5MB")

    with open(avatar_path, "wb") as f:
        f.write(content)

    avatar_url = f"/api/users/avatar/{avatar_name}"
    success = user_manager.update_user(employee_id, {"avatar": avatar_url}, employee_id)
    if not success:
        raise HTTPException(status_code=400, detail="头像保存失败")

    return {"message": "头像上传成功", "avatar": avatar_url}


@router.get("/avatar/{avatar_name}")
def get_avatar(avatar_name: str):
    avatar_path = AVATAR_ROOT / avatar_name
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(str(avatar_path))

@router.get("/employees", response_model=List[UserResponse])
def list_employees(authorization: Optional[str] = Header(None)):
    """列出所有员工（仅主管）"""
    payload = verify_token_header(authorization)
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可访问")
    
    employees = user_manager.list_employees(payload.get("user_id"))
    return employees

@router.post("/employees")
def create_employee(
    request: CreateUserRequest,
    authorization: Optional[str] = Header(None)
):
    """创建员工账号（仅主管）"""
    payload = verify_token_header(authorization)
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可创建账号")
    
    success = user_manager.create_user(
        employee_id=request.employee_id,
        password=request.password,
        nickname=request.nickname,
        creator_id=payload.get("user_id")
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="工号已存在或创建失败")
    
    auth_manager.log_action(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        action="create_user",
        resource="user",
        details={"target_employee_id": request.employee_id}
    )
    
    return {"message": "创建成功"}

@router.put("/employees/{employee_id}")
def update_employee(
    employee_id: str,
    request: UpdateUserRequest,
    authorization: Optional[str] = Header(None)
):
    """更新员工信息（仅主管）"""
    payload = verify_token_header(authorization)
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可操作")
    
    updates = {}
    if request.password is not None:
        updates["password"] = request.password
    if request.nickname is not None:
        updates["nickname"] = request.nickname
    if request.avatar is not None:
        updates["avatar"] = request.avatar
    
    success = user_manager.update_user(employee_id, updates, payload.get("user_id"))
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    
    auth_manager.log_action(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        action="update_user",
        resource="user",
        details={"target_employee_id": employee_id, "updates": list(updates.keys())}
    )
    
    return {"message": "更新成功"}

@router.delete("/employees/{employee_id}")
def delete_employee(
    employee_id: str,
    authorization: Optional[str] = Header(None)
):
    """删除员工账号（仅主管）"""
    payload = verify_token_header(authorization)
    if payload.get("role") != "supervisor":
        raise HTTPException(status_code=403, detail="仅主管可删除账号")
    
    success = user_manager.delete_user(employee_id, payload.get("user_id"))
    if not success:
        raise HTTPException(status_code=400, detail="删除失败或无权限")
    
    auth_manager.log_action(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        action="delete_user",
        resource="user",
        details={"target_employee_id": employee_id}
    )
    
    return {"message": "删除成功"}
