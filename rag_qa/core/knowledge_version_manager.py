# -*- coding: utf-8 -*-
"""
知识库版本管理模块：负责知识库版本创建、切换、回滚、列表
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from base import logger

class KnowledgeVersionManager:
    """知识库版本管理器"""
    
    def __init__(self, storage_dir: str = "knowledge_versions"):
        self.storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.meta_file = os.path.join(self.storage_dir, "kb_versions.json")
        self._init_storage()
    
    def _init_storage(self):
        if not os.path.exists(self.meta_file):
            default_data = {
                "current_version": "v1",
                "versions": [
                    {
                        "version": "v1",
                        "status": "published",
                        "created_at": datetime.now().isoformat(),
                        "description": "初始版本"
                    }
                ]
            }
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
    
    def _load_meta(self) -> Dict[str, Any]:
        try:
            with open(self.meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载知识库版本元数据失败：{e}")
            return {"current_version": "v1", "versions": []}
    
    def _save_meta(self, data: Dict[str, Any]) -> bool:
        try:
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存知识库版本元数据失败：{e}")
            return False
    
    def list_versions(self) -> List[Dict[str, Any]]:
        """获取所有版本"""
        meta = self._load_meta()
        return meta.get("versions", [])
    
    def get_current_version(self) -> str:
        """获取当前版本"""
        meta = self._load_meta()
        return meta.get("current_version", "v1")
    
    def create_version(self, version: str, description: str = "", status: str = "draft") -> bool:
        """创建新版本"""
        meta = self._load_meta()
        versions = meta.get("versions", [])
        
        # 检查版本是否已存在
        if any(v.get("version") == version for v in versions):
            logger.warning(f"版本 {version} 已存在")
            return False
        
        version_entry = {
            "version": version,
            "status": status,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "description": description,
            "document_count": 0,
            "documents": [],
        }
        versions.append(version_entry)
        meta["versions"] = versions
        
        success = self._save_meta(meta)
        if success:
            logger.info(f"创建知识库版本成功：{version}")
        return success
    
    def publish_version(self, version: str) -> bool:
        """发布版本"""
        meta = self._load_meta()
        versions = meta.get("versions", [])
        found = False
        
        for v in versions:
            if v.get("version") == version:
                v["status"] = "published"
                v["updated_at"] = datetime.now().isoformat()
                found = True
            elif v.get("status") == "published":
                v["status"] = "archived"
        
        if found:
            meta["current_version"] = version
            success = self._save_meta(meta)
            if success:
                logger.info(f"发布知识库版本成功：{version}")
            return success
        
        logger.warning(f"未找到版本 {version}")
        return False
    
    def rollback_version(self, target_version: str) -> bool:
        """回滚到指定版本"""
        return self.publish_version(target_version)
    
    def get_version_detail(self, version: str) -> Optional[Dict[str, Any]]:
        """获取版本详情"""
        versions = self.list_versions()
        for v in versions:
            if v.get("version") == version:
                return v
        return None
    
    def update_version_info(self, version: str, **kwargs) -> bool:
        """更新版本信息"""
        meta = self._load_meta()
        versions = meta.get("versions", [])
        
        for v in versions:
            if v.get("version") == version:
                for k, val in kwargs.items():
                    v[k] = val
                v["updated_at"] = datetime.now().isoformat()
                meta["versions"] = versions
                return self._save_meta(meta)
        return False
    
    def add_document_to_version(self, version: str, file_name: str, file_hash: str) -> bool:
        """记录某个版本下的文档"""
        meta = self._load_meta()
        versions = meta.get("versions", [])
        
        for v in versions:
            if v.get("version") == version:
                if "documents" not in v:
                    v["documents"] = []
                v["documents"].append({
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "added_at": datetime.now().isoformat(),
                })
                v["document_count"] = len(v["documents"])
                meta["versions"] = versions
                return self._save_meta(meta)
        return False

# 全局知识库版本管理器实例
_kb_version_manager = None

def get_kb_version_manager() -> KnowledgeVersionManager:
    """获取全局知识库版本管理器实例"""
    global _kb_version_manager
    if _kb_version_manager is None:
        _kb_version_manager = KnowledgeVersionManager()
    return _kb_version_manager
