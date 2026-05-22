# -*- coding:utf-8 -*-
"""
训练查询分类模型。
默认使用 MacBERT 基座与 v2 二分类数据集进行微调。
"""
import os
import sys
import json
from collections import Counter

# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.query_classifier import QueryClassifier
from demo_experiment_paths import QUERY_CLASSIFIER_EXPERIMENT_DIR
from base import logger


DEFAULT_MODEL_DIR = str(QUERY_CLASSIFIER_EXPERIMENT_DIR / 'model_snapshot')
DEFAULT_BACKBONE_DIR = os.path.join(current_dir, 'models', 'chinese-macbert-base')

def train_model():
    """训练查询分类模型"""
    print("=" * 60)
    print("开始训练查询分类模型（默认 MacBERT）")
    print("=" * 60)
    
    # 检查训练数据文件是否存在
    data_file = str(QUERY_CLASSIFIER_EXPERIMENT_DIR / 'artifacts' / 'query_classifier_dataset_v2.jsonl')
    
    if not os.path.exists(data_file):
        print(f"❌ 错误：训练数据文件不存在：{data_file}")
        print("请先运行 build_query_classifier_dataset_v2.py 生成训练数据")
        return False
    
    print(f"\n✓ 找到训练数据文件：{data_file}")
    
    # 统计训练数据
    with open(data_file, 'r', encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]

    total_samples = len(rows)
    label_counts = Counter(row['label'] for row in rows)
    source_counts = Counter(row.get('source', 'unknown') for row in rows)

    print(f"  总样本数：{total_samples}")
    print("  全量标签统计：")
    print(f"    专业咨询：{label_counts.get('专业咨询', 0)}")
    print(f"    通用知识：{label_counts.get('通用知识', 0)}")
    if source_counts:
        print("  来源统计（Top 5）：")
        for source, count in source_counts.most_common(5):
            print(f"    {source}: {count}")
    
    # 初始化分类器
    print("\n正在初始化查询分类器...")
    classifier = QueryClassifier(model_path=DEFAULT_MODEL_DIR, base_model_path=DEFAULT_BACKBONE_DIR)
    print("✓ 分类器初始化完成")
    print(f"  输出模型目录：{classifier.model_path}")
    print(f"  基础模型：{classifier.backbone_name}")
    
    # 开始训练
    print("\n" + "=" * 60)
    print("开始训练...")
    print("=" * 60)
    print("训练过程可能需要几分钟，请耐心等待...")
    print("\n训练参数:")
    print("  - 训练轮次：3 epochs")
    print("  - 训练批次：16 (GPU 可调大)")
    print("  - 验证批次：16")
    print("  - 学习率预热：20 steps")
    print("  - 权重衰减：0.01")
    print("=" * 60)
    
    try:
        # 调用训练方法
        classifier.train_model(data_file=data_file)
        
        print("\n" + "=" * 60)
        print("✓ 训练完成！")
        print("=" * 60)
        
        # 测试训练好的模型
        print("\n测试训练后的模型:")
        test_queries = [
            "露天矿山开采工艺流程是什么？",
            "矿井通风系统设计原则",
            "什么是 AI?",
            "Python 怎么写代码？"
        ]
        
        correct = 0
        expected_labels = ["专业咨询", "专业咨询", "通用知识", "通用知识"]
        
        for i, query in enumerate(test_queries):
            label = classifier.predict_category(query)
            is_correct = label == expected_labels[i]
            if is_correct:
                correct += 1
            status = "✓" if is_correct else "✗"
            print(f"{status} '{query}' -> {label} (预期：{expected_labels[i]})")
        
        accuracy = correct / len(test_queries) * 100
        print(f"\n测试准确率：{accuracy:.0f}% ({correct}/{len(test_queries)})")
        
        if accuracy >= 75:
            print("\n🎉 模型训练成功！准确率达到要求（≥75%）")
        else:
            print(f"\n⚠️  模型准确率较低，建议:")
            print("   1. 增加训练数据量")
            print("   2. 调整训练参数（增加 epochs）")
            print("   3. 检查训练数据质量")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 训练失败：{e}")
        logger.error(f"训练过程中出错：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = train_model()
    if success:
        print("\n" + "=" * 60)
        print(f"训练完成！模型已保存至 {DEFAULT_MODEL_DIR}")
        print("可以开始使用 RAG 系统进行查询了")
        print("=" * 60)
    else:
        print("\n训练未能完成，请检查错误信息")
