# -*- coding:utf-8 -*-
"""
测试 OCR 和查询分类器的诊断工具
"""
import os
import sys

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.query_classifier import QueryClassifier
from base import logger

def test_query_classifier():
    """测试查询分类器的性能"""
    print("=" * 60)
    print("测试查询分类器")
    print("=" * 60)
    
    classifier = QueryClassifier()
    
    # 测试用例
    test_cases = [
        ("什么是 AI?", "通用知识"),
        ("Python 怎么写代码？", "通用知识"),
        ("1+1 等于几？", "通用知识"),
        ("露天矿山开采工艺流程是什么？", "专业咨询"),
        ("矿井通风系统设计原则", "专业咨询"),
        ("选矿厂尾矿处理技术", "专业咨询"),
        ("地下矿山巷道支护方法", "专业咨询"),
        ("如何计算数学题？", "通用知识"),
        ("矿床勘探方法有哪些？", "专业咨询"),
        ("帮我写一个排序算法", "通用知识"),
    ]
    
    correct = 0
    total = len(test_cases)
    
    for query, expected_label in test_cases:
        predicted_label = classifier.predict_category(query)
        is_correct = predicted_label == expected_label
        if is_correct:
            correct += 1
        
        status = "✓" if is_correct else "✗"
        print(f"{status} 查询：'{query}'")
        print(f"  预期：{expected_label}, 预测：{predicted_label}\n")
    
    accuracy = correct / total * 100
    print("=" * 60)
    print(f"准确率：{accuracy:.2f}% ({correct}/{total})")
    print("=" * 60)
    
    if accuracy < 80:
        print("⚠️  警告：分类器准确率低于 80%，需要重新训练！")
        print("建议：使用 generate_training_data.py 生成训练数据并训练模型")
    else:
        print("✓ 分类器性能良好")
    
    return accuracy

if __name__ == '__main__':
    test_query_classifier()
