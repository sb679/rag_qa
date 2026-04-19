# -*- coding: utf-8 -*-
"""
权限管理模块：处理用户认证、角色权限、审计日志
"""
import jwt
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any
import json
import os
from base import logger, Config

class UserRole(Enum):
    """用户角色枚举"""
    ADMIN = "admin"          # 管理员
    SUPERVISOR = "supervisor"  # 主管
    USER = "user"            # 普通用户

class AuthManager:
    """认证管理器"""
    
    def __init__(self, secret_key: Optional[str] = None):
        cfg = Config()
        self.secret_key = secret_key or cfg.JWT_SECRET
        self.default_supervisor_password = cfg.DEFAULT_SUPERVISOR_PASSWORD
        self.users = self._init_users()
        self.audit_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audit_logs")
        os.makedirs(self.audit_log_dir, exist_ok=True)
    
    def _init_users(self) -> Dict[str, Dict]:
        """初始化用户数据（演示用，实际应该用数据库）"""
        return {
            "supervisor": {
                "user_id": "supervisor_001",
                "username": "supervisor",
                "password": self.default_supervisor_password,
                "role": UserRole.SUPERVISOR.value,
                "email": "supervisor@rag-qa.com",
                "created_at": datetime.now().isoformat(),
            },
            "user": {
                "user_id": "user_001",
                "username": "user",
                "password": "demo-user-pass-change-me",
                "role": UserRole.USER.value,
                "email": "user@rag-qa.com",
                "created_at": datetime.now().isoformat(),
            }
        }
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            认证成功返回用户信息，失败返回 None
        """
        user = self.users.get(username)
        if user and user["password"] == password:
            logger.info(f"用户 {username} 认证成功")
            return {
                "user_id": user["user_id"],
                "username": user["username"],
                "role": user["role"],
                "email": user["email"],
            }
        logger.warning(f"用户 {username} 认证失败")
        return None
    
    def create_token(self, user_id: str, username: str, role: str, expires_in_hours: int = 24) -> str:
        """
        生成 JWT token
        
        Args:
            user_id: 用户 ID
            username: 用户名
            role: 用户角色
            expires_in_hours: token 过期时间（小时）
            
        Returns:
            JWT token
        """
        payload = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=expires_in_hours)
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        logger.info(f"为用户 {username} 生成 token")
        return token
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 JWT token
        
        Args:
            token: JWT token
            
        Returns:
            验证成功返回 payload，失败返回 None
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token 已过期")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Token 无效")
            return None
    
    def log_action(self, user_id: str, username: str, action: str, resource: str, details: Optional[Dict] = None):
        """
        记录审计日志
        
        Args:
            user_id: 用户 ID
            username: 用户名
            action: 操作类型（如 login, query, feedback, upload）
            resource: 资源类型（如 session, document, feedback）
            details: 操作详情
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "username": username,
            "action": action,
            "resource": resource,
            "details": details or {}
        }
        
        # 保存到日志文件
        log_file = os.path.join(self.audit_log_dir, f"audit_{datetime.now().strftime('%Y%m%d')}.json")
        try:
            logs = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            logs.append(log_entry)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
            logger.info(f"审计日志已记录：{username} - {action} - {resource}")
        except Exception as e:
            logger.error(f"记录审计日志失败：{e}")
    
    def get_audit_logs(self, date: Optional[str] = None) -> list:
        """
        获取审计日志
        
        Args:
            date: 日期（格式：YYYYMMDD），不指定则返回今天的日志
            
        Returns:
            审计日志列表
        """
        if not date:
            date = datetime.now().strftime('%Y%m%d')
        
        log_file = os.path.join(self.audit_log_dir, f"audit_{date}.json")
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取审计日志失败：{e}")
        return []

# 全局认证管理器实例
_auth_manager = None

def get_auth_manager() -> AuthManager:
    """获取全局认证管理器实例"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
