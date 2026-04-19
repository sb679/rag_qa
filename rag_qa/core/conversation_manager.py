# -*- coding:utf-8 -*-
"""
会话管理模块：负责多轮对话的历史记录管理
功能：
1. 创建、加载、保存会话
2. 添加对话记录（问题 + 答案）
3. 获取最近 N 条历史记录
4. 基于历史对话的检索增强
5. 持久化存储到 JSON 文件
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any
from uuid import uuid4

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
rag_qa_path = os.path.dirname(current_dir)
sys.path.insert(0, rag_qa_path)

from base import logger


class ConversationManager:
    """会话管理器类"""
    
    def __init__(self, storage_dir: str = "conversations"):
        """
        初始化会话管理器
        
        Args:
            storage_dir: 会话文件存储目录
        """
        self.storage_dir = os.path.join(rag_qa_path, storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # 当前活动的会话
        self.current_session_id: Optional[str] = None
        self.current_session_data: Dict[str, Any] = {}
        
        # 内存中的会话缓存
        self.sessions_cache: Dict[str, Dict] = {}
        
        logger.info(f"会话管理器已初始化，存储目录：{self.storage_dir}")
    
    # ==================== 会话管理 ====================
    
    def create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        """
        创建新会话
        
        Args:
            session_id: 可选的自定义会话 ID，不提供则自动生成
            metadata: 可选的元数据（如用户信息、开始时间等）
            
        Returns:
            str: 会话 ID
        """
        if session_id is None:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        
        session_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "history": []  # 历史对话列表
        }
        
        self.current_session_id = session_id
        self.current_session_data = session_data
        self.sessions_cache[session_id] = session_data
        
        # 立即保存到文件
        self._save_session_to_file(session_id, session_data)
        
        logger.info(f"创建新会话：{session_id}")
        return session_id
    
    def load_session(self, session_id: str) -> bool:
        """
        加载已有会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否加载成功
        """
        # 先从缓存查找
        if session_id in self.sessions_cache:
            self.current_session_id = session_id
            self.current_session_data = self.sessions_cache[session_id]
            logger.info(f"从缓存加载会话：{session_id}")
            return True
        
        # 从文件加载
        file_path = self._get_session_file_path(session_id)
        if not os.path.exists(file_path):
            logger.error(f"会话文件不存在：{file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            self.current_session_id = session_id
            self.current_session_data = session_data
            self.sessions_cache[session_id] = session_data
            
            logger.info(f"从文件加载会话：{session_id}")
            return True
            
        except Exception as e:
            logger.error(f"加载会话失败：{e}")
            return False
    
    def save_current_session(self) -> bool:
        """保存当前会话到文件"""
        if not self.current_session_id:
            logger.warning("没有活动的会话")
            return False
        
        self.current_session_data["updated_at"] = datetime.now().isoformat()
        self.sessions_cache[self.current_session_id] = self.current_session_data
        
        return self._save_session_to_file(
            self.current_session_id, 
            self.current_session_data
        )
    
    def _save_session_to_file(self, session_id: str, session_data: Dict) -> bool:
        """
        将会话保存到文件
        
        Args:
            session_id: 会话 ID
            session_data: 会话数据
            
        Returns:
            bool: 是否保存成功
        """
        try:
            file_path = self._get_session_file_path(session_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"会话已保存到文件：{file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话文件失败：{e}")
            return False
    
    def _get_session_file_path(self, session_id: str) -> str:
        """获取会话文件路径"""
        return os.path.join(self.storage_dir, f"{session_id}.json")
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        file_path = self._get_session_file_path(session_id)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"删除会话：{session_id}")
            
            # 从缓存移除
            if session_id in self.sessions_cache:
                del self.sessions_cache[session_id]
            
            if self.current_session_id == session_id:
                self.current_session_id = None
                self.current_session_data = {}
            
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败：{e}")
            return False
    
    def list_sessions(self) -> List[Dict]:
        """
        列出所有会话
        
        Returns:
            List[Dict]: 会话信息列表
        """
        sessions = []
        
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(self.storage_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    
                    sessions.append({
                        "session_id": session_data.get("session_id"),
                        "created_at": session_data.get("created_at"),
                        "updated_at": session_data.get("updated_at"),
                        "message_count": len(session_data.get("history", [])),
                        "metadata": session_data.get("metadata", {})
                    })
                except Exception as e:
                    logger.error(f"读取会话文件失败 {filename}: {e}")
        
        # 按更新时间排序
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        return sessions
    
    # ==================== 对话管理 ====================
    
    def add_message(self, question: str, answer: str, metadata: Optional[Dict] = None) -> bool:
        """
        添加对话记录
        
        Args:
            question: 用户问题
            answer: 系统回答
            metadata: 可选的元数据（如查询类型、检索策略等）
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_session_id:
            logger.warning("没有活动的会话，无法添加消息")
            return False
        
        message = {
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.current_session_data["history"].append(message)
        
        # 每添加 5 条消息就保存一次，避免频繁 IO
        history_len = len(self.current_session_data["history"])
        if history_len % 5 == 0:
            self.save_current_session()
        
        logger.debug(f"添加消息到会话 {self.current_session_id} (历史总数：{history_len})")
        return True
    
    def get_history(self, limit: int = 5) -> List[Dict]:
        """
        获取最近的历史记录
        
        Args:
            limit: 返回的历史记录数量，默认 5 条
            
        Returns:
            List[Dict]: 历史记录列表，每条包含 question 和 answer
        """
        if not self.current_session_id:
            logger.warning("没有活动的会话")
            return []
        
        history = self.current_session_data.get("history", [])
        recent_history = history[-limit:] if limit > 0 else history
        
        logger.debug(f"获取最近 {len(recent_history)} 条历史记录")
        return recent_history
    
    def clear_history(self) -> bool:
        """清空当前会话历史"""
        if not self.current_session_id:
            return False
        
        self.current_session_data["history"] = []
        self.save_current_session()
        
        logger.info(f"清空会话 {self.current_session_id} 的历史记录")
        return True
    
    # ==================== 检索增强 ====================
    
    def get_relevant_history(self, current_query: str, limit: int = 5) -> List[Dict]:
        """
        获取与当前查询相关的历史记录
        
        Args:
            current_query: 当前查询
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 相关历史记录
        """
        # TODO: 后续可以用向量相似度检索
        # 目前简单返回最近的记录
        history = self.get_history(limit=limit * 2)  # 先多取一些
        
        # 简单的相关性判断：检查问题中是否有共同的关键词
        query_keywords = set(current_query.lower().split())
        
        scored_history = []
        for record in history:
            question = record.get("question", "")
            # 计算关键词重叠度
            overlap = len(query_keywords & set(question.lower().split()))
            if overlap > 0:
                scored_history.append((overlap, record))
        
        # 按相关性排序
        scored_history.sort(key=lambda x: x[0], reverse=True)
        
        # 返回最相关的 limit 条
        relevant = [record for _, record in scored_history[:limit]]
        
        logger.debug(f"找到 {len(relevant)} 条相关历史记录")
        return relevant
    
    def get_context_from_history(self, limit: int = 5) -> str:
        """
        从历史记录构建上下文
        
        Args:
            limit: 历史记录数量限制
            
        Returns:
            str: 格式化的历史上下文字符串
        """
        history = self.get_history(limit=limit)
        
        if not history:
            return ""
        
        context_lines = []
        for i, record in enumerate(history, 1):
            context_lines.append(f"第{i}轮:")
            context_lines.append(f"  问：{record.get('question', '')}")
            context_lines.append(f"  答：{record.get('answer', '')}")
        
        return "\n".join(context_lines)
    
    # ==================== 统计信息 ====================
    
    def get_session_stats(self) -> Dict:
        """获取当前会话统计信息"""
        if not self.current_session_id:
            return {}
        
        history = self.current_session_data.get("history", [])
        
        return {
            "session_id": self.current_session_id,
            "total_messages": len(history),
            "created_at": self.current_session_data.get("created_at"),
            "last_updated": self.current_session_data.get("updated_at")
        }
    
    def export_session(self, output_path: str) -> bool:
        """
        导出当前会话到指定文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            bool: 是否导出成功
        """
        if not self.current_session_id:
            return False
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_session_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"会话已导出到：{output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出会话失败：{e}")
            return False


# 全局单例（可选）
_default_manager: Optional[ConversationManager] = None


def get_conversation_manager(storage_dir: str = "conversations") -> ConversationManager:
    """获取全局会话管理器实例"""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConversationManager(storage_dir)
    return _default_manager


if __name__ == '__main__':
    # 测试代码
    manager = ConversationManager()
    
    # 创建会话
    session_id = manager.create_session(metadata={"user": "test_user"})
    print(f"创建会话：{session_id}")
    
    # 添加消息
    manager.add_message("什么是机器学习？", "机器学习是...")
    manager.add_message("监督学习有哪些算法？", "监督学习包括...")
    
    # 获取历史
    history = manager.get_history(limit=5)
    print(f"\n历史记录 ({len(history)}条):")
    for record in history:
        print(f"Q: {record['question']}")
        print(f"A: {record['answer']}\n")
    
    # 获取统计
    stats = manager.get_session_stats()
    print(f"\n会话统计：{stats}")
