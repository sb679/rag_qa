#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""检查 Milvus 数据库中的内容"""

from core.vector_store import VectorStore

try:
    vs = VectorStore()
    
    # 获取集合统计信息
    stats = vs.client.get_collection_stats(collection_name="edurag_final")
    
    print("=" * 60)
    print("📊 Milvus 数据库状态")
    print("=" * 60)
    print(f"集合名称：edurag_final")
    print(f"文档总数：{stats['row_count']}")
    print("=" * 60)
    
    # 查询前 5 条数据
    results = vs.client.query(
        collection_name='edurag_final',
        filter='',
        output_fields=['text', 'source'],
        limit=5
    )
    
    print("\n📋 前 5 条数据示例:")
    print("-" * 60)
    for i, r in enumerate(results):
        text_preview = r['text'][:80].replace('\n', ' ')
        print(f"{i+1}. 来源：{r['source']}")
        print(f"   内容：{text_preview}...")
        print("-" * 60)
    
    # 按来源统计
    all_results = vs.client.query(
        collection_name='edurag_final',
        filter='',
        output_fields=['source'],
        limit=stats['row_count']
    )
    
    source_count = {}
    for r in all_results:
        source = r.get('source', 'unknown')
        source_count[source] = source_count.get(source, 0) + 1
    
    print("\n📚 数据来源分布:")
    print("-" * 60)
    for source, count in sorted(source_count.items(), key=lambda x: x[1], reverse=True):
        print(f"   {source}: {count} 条")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ 查询失败：{e}")
