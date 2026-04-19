# -*- coding: utf-8 -*-
"""
将采矿评估数据转换为 RAGAS 格式
用于后续的 RAGAS 评估
"""

import json
import os

def convert_to_ragas_format():
    """将评估数据转换为 RAGAS 需要的格式"""
    
    # 加载采矿评估数据
    eval_file = 'rag_assesment/mining_evaluation_data.json'
    with open(eval_file, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"加载了 {len(qa_pairs)} 个问答对")
    
    # 转换为 RAGAS 格式
    ragas_data = {
        "question": [qa['question'] for qa in qa_pairs],
        "answer": [qa['answer'] for qa in qa_pairs],
        "contexts": [qa['context'] for qa in qa_pairs],
        "ground_truth": [qa['ground_truth'] for qa in qa_pairs]
    }
    
    # 保存为 RAGAS 格式
    output_file = 'rag_assesment/rag_evaluate_data_mining.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ragas_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ RAGAS 格式数据已保存到：{output_file}")
    
    # 显示统计信息
    print("\n数据统计:")
    print(f"  - 问题数量：{len(ragas_data['question'])}")
    print(f"  - 平均 context 数量：{sum(len(c) for c in ragas_data['contexts']) / len(ragas_data['contexts']):.1f}")
    print(f"  - 平均 ground_truth 长度：{sum(len(gt) for gt in ragas_data['ground_truth']) / len(ragas_data['ground_truth']):.1f} 字符")
    
    # 显示前 3 个样例
    print("\n前 3 个样例:")
    for i in range(3):
        print(f"\n样例 {i+1}:")
        print(f"  问题：{ragas_data['question'][i]}")
        print(f"  答案：{ragas_data['answer'][i][:100]}...")
        print(f"  真实答案：{ragas_data['ground_truth'][i]}")
        print(f"  Context 数量：{len(ragas_data['contexts'][i])}")

if __name__ == '__main__':
    print("="*80)
    print("转换采矿评估数据为 RAGAS 格式")
    print("="*80)
    
    convert_to_ragas_format()
    
    print("\n" + "="*80)
    print("转换完成！")
    print("="*80)
