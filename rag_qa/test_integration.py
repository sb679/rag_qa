# -*-coding:utf-8-*-
"""
测试集成后的策略分类器
验证 QueryClassifier 和 StrategySelector 是否正常工作
"""

import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.query_classifier import QueryClassifier
from core.strategy_selector import StrategySelector

def test_query_classifier():
    """测试 QueryClassifier"""
    print("="*80)
    print("测试 QueryClassifier（BERT 本地分类器）")
    print("="*80)
    
    classifier = QueryClassifier()
    
    # 测试用例
    test_queries = [
        ("矿床勘探类型划分", "直接检索"),
        ("绿色矿山建设的意义是什么？", "假设问题检索"),
        ("比较露天开采和地下开采的优缺点。", "子查询检索"),
        ("某铁矿矿体埋藏深度达 500 米，采用露天开采，边坡角 30 度，如何优化开采参数？", "场景重构检索"),
    ]
    
    correct = 0
    for query, expected in test_queries:
        result = classifier.predict_category(query)
        status = "✓" if result == expected else "✗"
        if result == expected:
            correct += 1
        print(f"{status} 查询：{query[:40]}...")
        print(f"  预期：{expected} | 预测：{result}\n")
    
    accuracy = correct / len(test_queries) * 100
    print(f"准确率：{accuracy:.1f}% ({correct}/{len(test_queries)})")


def test_strategy_selector():
    """测试 StrategySelector"""
    print("\n" + "="*80)
    print("测试 StrategySelector（优先使用本地分类器）")
    print("="*80)
    
    selector = StrategySelector()
    
    # 测试用例
    test_queries = [
        "什么是浮选法？",
        "采矿工程对环境的影响有哪些？",
        "比较浮选法和磁选法的区别。",
        "我有一个埋深 500 米的铜矿，采用露天开采，边坡稳定性差，如何优化？",
    ]
    
    for query in test_queries:
        strategy = selector.select_strategy(query)
        print(f"查询：{query}")
        print(f"策略：{strategy}\n")


if __name__ == "__main__":
    try:
        # 测试 QueryClassifier
        test_query_classifier()
        
        # 测试 StrategySelector
        test_strategy_selector()
        
        print("\n" + "="*80)
        print("✅ 集成测试完成！")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
