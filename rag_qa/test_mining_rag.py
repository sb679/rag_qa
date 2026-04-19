# -*- coding: utf-8 -*-
"""
基于采矿文档构建测试集
使用实际的 RAG 系统检索文档内容来生成问题和答案
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import json
from core.new_rag_system import RAGSystem
from typing import List, Dict

def load_evaluation_data() -> List[Dict]:
    """加载评估数据"""
    eval_file = os.path.join(project_root, 'rag_assesment', 'mining_evaluation_data.json')
    with open(eval_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_rag_with_questions(qa_pairs: List[Dict], top_k: int = 3):
    """使用 RAG 系统测试问答对"""
    
    # 初始化 RAG 系统
    print("初始化 RAG 系统...")
    rag_system = RAGSystem(
        knowledge_base_dir=os.path.join(project_root, 'data', 'mining'),
        embedding_model_path=os.path.join(project_root, 'models', 'bge-m3'),
        reranker_model_path=os.path.join(project_root, 'models', 'bge-reranker-large'),
        use_deepseek=True
    )
    
    test_results = []
    
    for i, qa in enumerate(qa_pairs, 1):
        print(f"\n处理问题 {i}/{len(qa_pairs)}: {qa['question']}")
        
        # 使用 RAG 系统查询
        try:
            result = rag_system.query(
                query=qa['question'],
                top_k=top_k,
                use_reranker=True
            )
            
            test_result = {
                'question': qa['question'],
                'rag_answer': result['answer'],
                'expected_answer': qa['answer'],
                'ground_truth': qa['ground_truth'],
                'contexts': [doc.page_content for doc in result.get('source_documents', [])],
                'metadata': {
                    'score': result.get('score', 0),
                    'docs_count': len(result.get('source_documents', []))
                }
            }
            
            test_results.append(test_result)
            
            print(f"  ✓ RAG 回答：{result['answer'][:100]}...")
            print(f"  ✓ 检索文档数：{len(result.get('source_documents', []))}")
            
        except Exception as e:
            print(f"  ✗ 错误：{e}")
            test_results.append({
                'question': qa['question'],
                'error': str(e)
            })
    
    return test_results

def save_test_results(results: List[Dict], output_file: str):
    """保存测试结果"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 测试结果已保存到：{output_file}")

def main():
    print("="*80)
    print("开始构建采矿文档测试集")
    print("="*80)
    
    # 加载评估数据
    eval_file = os.path.join(project_root, 'rag_assesment', 'mining_evaluation_data.json')
    if not os.path.exists(eval_file):
        print(f"✗ 评估文件不存在：{eval_file}")
        print("请先运行 build_mining_evaluation_dataset.py")
        return
    
    qa_pairs = load_evaluation_data()
    print(f"✓ 加载了 {len(qa_pairs)} 个问答对")
    
    # 测试 RAG 系统
    test_results = test_rag_with_questions(qa_pairs, top_k=3)
    
    # 保存测试结果
    output_file = os.path.join(project_root, 'rag_assesment', 'mining_test_results.json')
    save_test_results(test_results, output_file)
    
    # 统计结果
    success_count = sum(1 for r in test_results if 'error' not in r)
    print("\n" + "="*80)
    print(f"测试完成！成功：{success_count}/{len(test_results)}")
    print("="*80)

if __name__ == '__main__':
    main()
