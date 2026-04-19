# -*- coding: utf-8 -*-
"""
用户管理模块：处理员工账号的增删改查
"""
import json
import os
import base64
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, List
from base import logger, Config

class UserManager:
    """用户管理器"""
    
    def __init__(self):
        self._config = Config()
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.users_file = os.path.join(self.data_dir, "users.json")
        self.users = self._load_users()
        self._ensure_password_hashes()

    @staticmethod
    def _hash_password(password: str, salt: Optional[bytes] = None, rounds: int = 200000) -> str:
        if salt is None:
            salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${rounds}${salt_b64}${digest_b64}"

    @staticmethod
    def _verify_password(password: str, stored_password: str) -> bool:
        if not stored_password:
            return False

        if stored_password.startswith("pbkdf2_sha256$"):
            try:
                _, rounds_text, salt_b64, digest_b64 = stored_password.split("$", 3)
                rounds = int(rounds_text)
                salt = base64.b64decode(salt_b64.encode("ascii"))
                expected = base64.b64decode(digest_b64.encode("ascii"))
                current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
                return hmac.compare_digest(current, expected)
            except Exception:
                return False

        # 兼容历史明文密码
        return hmac.compare_digest(stored_password, password)

    def _ensure_password_hashes(self):
        """首次启动时将历史明文密码迁移为哈希存储。"""
        changed = False
        for user in self.users.values():
            raw = user.get("password", "")
            if raw and not raw.startswith("pbkdf2_sha256$"):
                user["password"] = self._hash_password(raw)
                changed = True
        if changed:
            self._save_users(self.users)
            logger.info("用户密码已从历史明文迁移到哈希存储")
    
    def _load_users(self) -> Dict[str, Dict]:
        """加载用户数据"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载用户数据失败：{e}")
        
        # 初始化三名主管
        default_users = {
            "9526": {
                "employee_id": "9526",
                "password": self._hash_password(self._config.DEFAULT_SUPERVISOR_PASSWORD),
                "role": "supervisor",
                "nickname": "主管A",
                "avatar": "",
                "created_at": datetime.now().isoformat(),
                "created_by": "system"
            },
            "9527": {
                "employee_id": "9527",
                "password": self._hash_password(self._config.DEFAULT_SUPERVISOR_PASSWORD),
                "role": "supervisor",
                "nickname": "主管B",
                "avatar": "",
                "created_at": datetime.now().isoformat(),
                "created_by": "system"
            },
            "9528": {
                "employee_id": "9528",
                "password": self._hash_password(self._config.DEFAULT_SUPERVISOR_PASSWORD),
                "role": "supervisor",
                "nickname": "主管C",
                "avatar": "",
                "created_at": datetime.now().isoformat(),
                "created_by": "system"
            }
        }
        self._save_users(default_users)
        return default_users
    
    def _save_users(self, users: Dict):
        """保存用户数据"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户数据失败：{e}")
    
    def authenticate(self, employee_id: str, password: str) -> Optional[Dict]:
        """
        用户认证
        
        Args:
            employee_id: 工号
            password: 密码
            
        Returns:
            认证成功返回用户信息，失败返回 None
        """
        user = self.users.get(employee_id)
        if user and self._verify_password(password, user.get("password", "")):
            logger.info(f"工号 {employee_id} 认证成功")
            return {
                "employee_id": user["employee_id"],
                "role": user["role"],
                "nickname": user["nickname"],
                "avatar": user.get("avatar", "")
            }
        logger.warning(f"工号 {employee_id} 认证失败")
        return None
    
    def create_user(self, employee_id: str, password: str, nickname: str, creator_id: str) -> bool:
        """
        创建用户（仅主管可调用）
        
        Args:
            employee_id: 工号
            password: 初始密码
            nickname: 昵称
            creator_id: 创建者工号
            
        Returns:
            创建成功返回 True，失败返回 False
        """
        if employee_id in self.users:
            logger.warning(f"工号 {employee_id} 已存在")
            return False
        
        # 检查创建者是否为主管
        creator = self.users.get(creator_id)
        if not creator or creator["role"] != "supervisor":
            logger.warning(f"非主管用户 {creator_id} 尝试创建账号")
            return False
        
        self.users[employee_id] = {
            "employee_id": employee_id,
            "password": self._hash_password(password),
            "role": "employee",
            "nickname": nickname,
            "avatar": "",
            "created_at": datetime.now().isoformat(),
            "created_by": creator_id
        }
        self._save_users(self.users)
        logger.info(f"主管 {creator_id} 创建了员工账号 {employee_id}")
        return True
    
    def update_user(self, employee_id: str, updates: Dict, operator_id: str) -> bool:
        """
        更新用户信息
        
        Args:
            employee_id: 工号
            updates: 更新内容（可包含 password, nickname, avatar）
            operator_id: 操作者工号
            
        Returns:
            更新成功返回 True，失败返回 False
        """
        if employee_id not in self.users:
            return False
        
        user = self.users[employee_id]
        operator = self.users.get(operator_id)
        
        # 主管可以操作员工，员工只能操作自己
        if operator and operator["role"] == "supervisor":
            if user["role"] == "supervisor" and employee_id != operator_id:
                logger.warning(f"主管 {operator_id} 尝试操作其他主管账号 {employee_id}")
                return False
        elif employee_id != operator_id:
            logger.warning(f"员工 {operator_id} 尝试操作其他账号 {employee_id}")
            return False
        
        # 更新字段
        for key in ["password", "nickname", "avatar"]:
            if key in updates:
                if key == "password":
                    user[key] = self._hash_password(updates[key])
                else:
                    user[key] = updates[key]
        
        user["updated_at"] = datetime.now().isoformat()
        user["updated_by"] = operator_id
        self._save_users(self.users)
        logger.info(f"用户 {operator_id} 更新了账号 {employee_id}")
        return True
    
    def delete_user(self, employee_id: str, operator_id: str) -> bool:
        """
        删除用户（仅主管可删除员工）
        
        Args:
            employee_id: 工号
            operator_id: 操作者工号
            
        Returns:
            删除成功返回 True，失败返回 False
        """
        if employee_id not in self.users:
            return False
        
        operator = self.users.get(operator_id)
        if not operator or operator["role"] != "supervisor":
            logger.warning(f"非主管用户 {operator_id} 尝试删除账号")
            return False
        
        user = self.users[employee_id]
        if user["role"] == "supervisor":
            logger.warning(f"主管 {operator_id} 尝试删除主管账号 {employee_id}")
            return False
        
        del self.users[employee_id]
        self._save_users(self.users)
        logger.info(f"主管 {operator_id} 删除了员工账号 {employee_id}")
        return True
    
    def list_employees(self, operator_id: str) -> List[Dict]:
        """
        列出所有员工（仅主管可调用）
        
        Args:
            operator_id: 操作者工号
            
        Returns:
            员工列表
        """
        operator = self.users.get(operator_id)
        if not operator or operator["role"] != "supervisor":
            return []
        
        employees = []
        for emp_id, user in self.users.items():
            if user["role"] == "employee":
                employees.append({
                    "employee_id": emp_id,
                    "nickname": user["nickname"],
                    "avatar": user.get("avatar", ""),
                    "created_at": user.get("created_at", ""),
                    "created_by": user.get("created_by", "")
                })
        return employees
    
    def get_user_info(self, employee_id: str) -> Optional[Dict]:
        """获取用户信息"""
        user = self.users.get(employee_id)
        if user:
            return {
                "employee_id": user["employee_id"],
                "role": user["role"],
                "nickname": user["nickname"],
                "avatar": user.get("avatar", "")
            }
        return None

# 全局用户管理器实例
_user_manager = None

def get_user_manager() -> UserManager:
    """获取全局用户管理器实例"""
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
    return _user_manager
