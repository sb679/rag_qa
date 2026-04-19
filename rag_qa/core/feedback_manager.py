# -*- coding: utf-8 -*-
"""
反馈管理模块：处理用户反馈、反馈统计、反馈持久化
"""
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from base import logger

class FeedbackManager:
    """反馈管理器"""
    
    def __init__(self, storage_dir: str = "feedback_data"):
        self.storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.feedback_cache = {}
    
    def submit_feedback(self, session_id: str, message_index: int, user_id: str, 
                       feedback_type: str, content: Optional[str] = None) -> bool:
        """
        提交反馈
        
        Args:
            session_id: 会话 ID
            message_index: 消息索引
            user_id: 用户 ID
            feedback_type: 反馈类型（like, dislike, partial_correct, correction）
            content: 反馈内容（纠错时使用）
            
        Returns:
            是否提交成功
        """
        try:
            feedback_entry = {
                "session_id": session_id,
                "message_index": message_index,
                "user_id": user_id,
                "feedback_type": feedback_type,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
            
            # 保存到文件
            feedback_file = os.path.join(self.storage_dir, f"feedback_{session_id}.json")
            feedbacks = []
            if os.path.exists(feedback_file):
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks = json.load(f)
            
            feedbacks.append(feedback_entry)
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            
            logger.info(f"反馈已保存：{session_id} - {feedback_type}")
            return True
        except Exception as e:
            logger.error(f"保存反馈失败：{e}")
            return False
    
    def get_session_feedback(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取会话的所有反馈
        
        Args:
            session_id: 会话 ID
            
        Returns:
            反馈列表
        """
        try:
            feedback_file = os.path.join(self.storage_dir, f"feedback_{session_id}.json")
            if os.path.exists(feedback_file):
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"读取反馈失败：{e}")
        return []
    
    def get_user_feedback(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有反馈
        
        Args:
            user_id: 用户 ID
            
        Returns:
            反馈列表
        """
        all_feedbacks = []
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    filepath = os.path.join(self.storage_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        feedbacks = json.load(f)
                        all_feedbacks.extend([fb for fb in feedbacks if fb.get("user_id") == user_id])
        except Exception as e:
            logger.error(f"读取用户反馈失败：{e}")
        return all_feedbacks
    
    def get_feedback_stats(self) -> Dict[str, Any]:
        """
        获取反馈统计
        
        Returns:
            统计数据
        """
        try:
            all_feedbacks = []
            for filename in os.listdir(self.storage_dir):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    filepath = os.path.join(self.storage_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        feedbacks = json.load(f)
                        all_feedbacks.extend(feedbacks)
            
            total = len(all_feedbacks)
            likes = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "like"])
            dislikes = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "dislike"])
            partial = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "partial_correct"])
            corrections = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "correction"])
            unique_users = len({fb.get("user_id") for fb in all_feedbacks if fb.get("user_id")})
            unique_sessions = len({fb.get("session_id") for fb in all_feedbacks if fb.get("session_id")})

            def _feedback_sort_key(item: Dict[str, Any]) -> str:
                return item.get("timestamp", "")

            recent_feedbacks = sorted(all_feedbacks, key=_feedback_sort_key, reverse=True)[:5]
            
            return {
                "total_feedback": total,
                "likes": likes,
                "dislikes": dislikes,
                "partial_correct": partial,
                "corrections": corrections,
                "satisfaction_rate": likes / total if total > 0 else 0,
                "error_rate": (dislikes + partial) / total if total > 0 else 0,
                "unique_users": unique_users,
                "unique_sessions": unique_sessions,
                "recent_feedbacks": recent_feedbacks,
            }
        except Exception as e:
            logger.error(f"计算反馈统计失败：{e}")
            return {}
    
    def get_all_feedbacks(self) -> List[Dict[str, Any]]:
        """
        获取所有反馈（主管用）
        
        Returns:
            所有反馈列表
        """
        all_feedbacks = []
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    filepath = os.path.join(self.storage_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        feedbacks = json.load(f)
                        all_feedbacks.extend(feedbacks)
        except Exception as e:
            logger.error(f"读取所有反馈失败：{e}")
        return all_feedbacks

# 全局反馈管理器实例
_feedback_manager = None

def get_feedback_manager() -> FeedbackManager:
    """获取全局反馈管理器实例"""
    global _feedback_manager
    if _feedback_manager is None:
        _feedback_manager = FeedbackManager()
    return _feedback_manager
