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
        self.conversations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "conversations")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.feedback_cache = {}

    def _load_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            file_path = os.path.join(self.conversations_dir, f"{session_id}.json")
            if not os.path.exists(file_path):
                return []
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            history = payload.get("history", [])
            return history if isinstance(history, list) else []
        except Exception as e:
            logger.warning(f"读取会话历史失败：{session_id} error={e}")
            return []

    def _load_session_payload(self, session_id: str) -> Dict[str, Any]:
        try:
            file_path = os.path.join(self.conversations_dir, f"{session_id}.json")
            if not os.path.exists(file_path):
                return {}
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception as e:
            logger.warning(f"读取会话载荷失败：{session_id} error={e}")
            return {}

    def _resolve_session_user_id(self, payload: Dict[str, Any]) -> str:
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {}
        user_meta = metadata.get("user") if isinstance(metadata.get("user"), dict) else {}
        candidates = [
            metadata.get("user_id"),
            metadata.get("employee_id"),
            metadata.get("created_by"),
            metadata.get("user"),
            user_meta.get("employee_id"),
            user_meta.get("user_id"),
            user_meta.get("nickname"),
            user_meta.get("name"),
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    def _is_completed_history_item(self, item: Dict[str, Any]) -> bool:
        status = str(item.get("status") or "done").lower()
        if status not in {"done", "completed", "success"}:
            return False
        return bool(str(item.get("answer", "") or "").strip())

    def _build_unfeedback_items(self, feedback_keys: set) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            if not os.path.isdir(self.conversations_dir):
                return items
            for filename in os.listdir(self.conversations_dir):
                if not filename.endswith('.json'):
                    continue
                session_id = os.path.splitext(filename)[0]
                payload = self._load_session_payload(session_id)
                if not payload:
                    continue
                history = payload.get("history", [])
                if not isinstance(history, list):
                    continue
                user_id = self._resolve_session_user_id(payload)
                for history_index, record in enumerate(history):
                    if not isinstance(record, dict) or not self._is_completed_history_item(record):
                        continue
                    message_index = history_index * 2 + 1
                    if (session_id, message_index) in feedback_keys:
                        continue
                    metadata = record.get("metadata", {}) if isinstance(record.get("metadata", {}), dict) else {}
                    items.append({
                        "session_id": session_id,
                        "message_index": message_index,
                        "user_id": user_id,
                        "feedback_type": "unfeedback",
                        "content": "",
                        "question": str(record.get("question", "") or ""),
                        "answer": str(record.get("answer", "") or ""),
                        "query_type": str(metadata.get("query_type", "") or ""),
                        "strategy": str(metadata.get("strategy", "") or ""),
                        "panel_info": metadata.get("panel_info") if isinstance(metadata.get("panel_info"), dict) else None,
                        "timestamp": str(record.get("completed_at") or record.get("updated_at") or record.get("timestamp") or payload.get("updated_at") or payload.get("created_at") or ""),
                        "status": "pending",
                        "status_updated_at": None,
                        "status_updated_by": "",
                    })
        except Exception as e:
            logger.warning(f"构建未反馈明细失败：{e}")
        return items

    def _build_feedback_detail(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(feedback.get("session_id", ""))
        message_index = int(feedback.get("message_index", -1) or -1)
        question = str(feedback.get("question", "") or "")
        answer = str(feedback.get("answer", "") or "")
        query_type = str(feedback.get("query_type", "") or "")
        strategy = str(feedback.get("strategy", "") or "")
        panel_info = feedback.get("panel_info") if isinstance(feedback.get("panel_info"), dict) else None
        history = self._load_session_history(session_id)
        history_index = message_index // 2 if message_index >= 0 else -1
        fallback_index = min(history_index, len(history) - 1) if history and history_index >= 0 else -1
        if 0 <= history_index < len(history):
            item = history[history_index] if isinstance(history[history_index], dict) else {}
            question = question or str(item.get("question", "") or "")
            answer = answer or str(item.get("answer", "") or "")
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
            query_type = query_type or str(metadata.get("query_type", "") or "")
            strategy = strategy or str(metadata.get("strategy", "") or "")
            panel_info = panel_info or (metadata.get("panel_info") if isinstance(metadata.get("panel_info"), dict) else None)
        elif fallback_index >= 0:
            item = history[fallback_index] if isinstance(history[fallback_index], dict) else {}
            question = question or str(item.get("question", "") or "")
            answer = answer or str(item.get("answer", "") or "")
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
            query_type = query_type or str(metadata.get("query_type", "") or "")
            strategy = strategy or str(metadata.get("strategy", "") or "")
            panel_info = panel_info or (metadata.get("panel_info") if isinstance(metadata.get("panel_info"), dict) else None)
        return {
            **feedback,
            "question": question,
            "answer": answer,
            "query_type": query_type,
            "strategy": strategy,
            "panel_info": panel_info,
        }
    
    def submit_feedback(
        self,
        session_id: str,
        message_index: int,
        user_id: str,
        feedback_type: str,
        content: Optional[str] = None,
        *,
        question: str = "",
        answer: str = "",
        query_type: str = "",
        strategy: str = "",
        panel_info: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        提交反馈（upsert 语义：同一 session_id + message_index + user_id 只保留最新一条）
        
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
                "question": question,
                "answer": answer,
                "query_type": query_type,
                "strategy": strategy,
                "panel_info": panel_info if isinstance(panel_info, dict) else None,
                "timestamp": datetime.now().isoformat(),
                "status": "pending",
                "status_updated_at": None,
                "status_updated_by": "",
            }
            
            feedback_file = os.path.join(self.storage_dir, f"feedback_{session_id}.json")
            feedbacks = []
            if os.path.exists(feedback_file):
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    feedbacks = json.load(f)
            
            # 移除同一用户对同一消息的旧反馈，再追加最新
            feedbacks = [
                fb for fb in feedbacks
                if not (fb.get("message_index") == message_index and fb.get("user_id") == user_id)
            ]
            feedbacks.append(feedback_entry)

            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            
            logger.info(f"反馈已保存：{session_id} - {feedback_type}")
            return True
        except Exception as e:
            logger.error(f"保存反馈失败：{e}")
            return False

    def update_feedback_status(
        self,
        session_id: str,
        message_index: int,
        user_id: str,
        timestamp: str,
        status: str,
        handler_id: str = "",
    ) -> bool:
        try:
            feedback_file = os.path.join(self.storage_dir, f"feedback_{session_id}.json")
            if not os.path.exists(feedback_file):
                return False
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)

            updated = False
            for item in feedbacks:
                if (
                    str(item.get("session_id", "")) == session_id
                    and int(item.get("message_index", -1) or -1) == int(message_index)
                    and str(item.get("user_id", "")) == user_id
                    and str(item.get("timestamp", "")) == timestamp
                ):
                    item["status"] = status
                    item["status_updated_at"] = datetime.now().isoformat()
                    item["status_updated_by"] = handler_id or ""
                    updated = True
                    break

            if not updated:
                return False

            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"更新反馈状态失败：{e}")
            return False

    def cancel_feedback(self, session_id: str, message_index: int, user_id: str) -> bool:
        """撤销当前用户对某条消息的反馈。"""
        try:
            feedback_file = os.path.join(self.storage_dir, f"feedback_{session_id}.json")
            if not os.path.exists(feedback_file):
                return True
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            new_list = [
                fb for fb in feedbacks
                if not (fb.get("message_index") == message_index and fb.get("user_id") == user_id)
            ]
            if len(new_list) == len(feedbacks):
                return True
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(new_list, f, ensure_ascii=False, indent=2)
            logger.info(f"反馈已撤销：{session_id} message_index={message_index} user={user_id}")
            return True
        except Exception as e:
            logger.error(f"撤销反馈失败：{e}")
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

            feedback_keys = {
                (str(item.get("session_id", "") or ""), int(item.get("message_index", -1) or -1))
                for item in all_feedbacks
                if str(item.get("session_id", "") or "").strip() and int(item.get("message_index", -1) or -1) >= 0
            }
            unfeedback_items = self._build_unfeedback_items(feedback_keys)
            
            total = len(all_feedbacks)
            likes = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "like"])
            dislikes = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "dislike"])
            partial = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "partial_correct"])
            corrections = len([fb for fb in all_feedbacks if fb.get("feedback_type") == "correction"])
            unique_users = len({fb.get("user_id") for fb in all_feedbacks if fb.get("user_id")})
            unique_sessions = len({fb.get("session_id") for fb in all_feedbacks if fb.get("session_id")})

            def _feedback_sort_key(item: Dict[str, Any]) -> str:
                return item.get("timestamp", "")

            sorted_feedbacks = sorted([*all_feedbacks, *unfeedback_items], key=_feedback_sort_key, reverse=True)
            detailed_feedbacks = [self._build_feedback_detail(item) for item in sorted_feedbacks]
            recent_feedbacks = detailed_feedbacks[:10]
            
            return {
                "total_feedback": total,
                "likes": likes,
                "dislikes": dislikes,
                "partial_correct": partial,
                "corrections": corrections,
                "no_feedback": len(unfeedback_items),
                "satisfaction_rate": likes / total if total > 0 else 0,
                "error_rate": (dislikes + partial) / total if total > 0 else 0,
                "unique_users": unique_users,
                "unique_sessions": unique_sessions,
                "recent_feedbacks": recent_feedbacks,
                "detailed_feedbacks": detailed_feedbacks[:50],
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
