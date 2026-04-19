# -*- coding: utf-8 -*-
"""
来源引用管理模块：负责整理检索证据、生成引用信息、页码/段落展示
"""
import re
from typing import List, Dict, Any, Optional
from base import logger

class CitationManager:
    """来源引用管理器"""
    
    def __init__(self):
        pass
    
    def format_source(self, doc: Dict[str, Any], idx: int) -> Dict[str, Any]:
        """格式化单条来源引用"""
        return {
            "ref_id": idx,
            "content": doc.get("content") or doc.get("text", ""),
            "source": doc.get("source", "unknown"),
            "score": float(doc.get("score", 0.0)),
            "page_num": doc.get("page_num"),
            "chunk_index": doc.get("chunk_index"),
            "doc_title": doc.get("doc_title"),
            "section_name": doc.get("section_name"),
        }
    
    def build_citation_block(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成引用列表"""
        sources = []
        for i, doc in enumerate(docs, 1):
            sources.append(self.format_source(doc, i))
        return sources
    
    def build_citation_text(self, sources: List[Dict[str, Any]]) -> str:
        """生成可展示的引用文本"""
        lines = []
        for src in sources:
            location = []
            if src.get("doc_title"):
                location.append(src["doc_title"])
            if src.get("page_num") is not None:
                location.append(f"p.{src['page_num']}")
            if src.get("section_name"):
                location.append(src["section_name"])
            if src.get("chunk_index") is not None:
                location.append(f"段落{src['chunk_index']}")
            loc_text = "，".join(location) if location else src.get("source", "unknown")
            lines.append(f"[{src['ref_id']}] {loc_text}")
        return "\n".join(lines)
    
    def inject_citations(self, answer_text: str, sources: List[Dict[str, Any]]) -> str:
        """将引用附加到答案末尾"""
        citation_text = self.build_citation_text(sources)
        if not citation_text:
            return answer_text
        return f"{answer_text}\n\n【来源引用】\n{citation_text}"
    
    def extract_reference_numbers(self, text: str) -> List[int]:
        """从答案中提取引用编号，如 [1][2]"""
        matches = re.findall(r'\[(\d+)\]', text)
        return [int(m) for m in matches]

# 全局引用管理器实例
_citation_manager = None

def get_citation_manager() -> CitationManager:
    """获取全局引用管理器实例"""
    global _citation_manager
    if _citation_manager is None:
        _citation_manager = CitationManager()
    return _citation_manager
