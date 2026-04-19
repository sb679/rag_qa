"""
分析生成的检索策略分类数据集
"""

import json
from collections import Counter

def analyze_dataset(file_path="classify_data/strategy_classification_8000.json"):
    print("="*80)
    print("检索策略分类数据集质量分析")
    print("="*80)
    
    # 加载数据
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    
    print(f"\n📊 基本统计信息")
    print(f"总样本数：{len(data)} 条")
    
    # 策略分布
    strategies = [item['strategy'] for item in data]
    strategy_counts = Counter(strategies)
    
    print(f"\n📈 策略分布:")
    for strategy, count in sorted(strategy_counts.items()):
        percentage = count / len(data) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {strategy:10s}: {count:4d} 条 ({percentage:5.1f}%) {bar}")
    
    # 分析每种策略的文本长度
    print(f"\n📏 文本长度分析:")
    for strategy in ["直接检索", "假设问题检索", "子查询检索", "场景重构检索"]:
        queries = [item['query'] for item in data if item['strategy'] == strategy]
        lengths = [len(q) for q in queries]
        
        if lengths:
            avg_length = sum(lengths) / len(lengths)
            min_length = min(lengths)
            max_length = max(lengths)
            
            print(f"\n  {strategy}:")
            print(f"    平均长度：{avg_length:.1f} 字符")
            print(f"    长度范围：{min_length} - {max_length} 字符")
            
            # 显示示例
            print(f"    示例:")
            sample_queries = queries[:3]
            for i, query in enumerate(sample_queries, 1):
                print(f"      {i}. {query}")
    
    # 检查数据质量
    print(f"\n✅ 数据质量检查:")
    
    # 1. 检查是否有空查询
    empty_queries = [item for item in data if not item['query'].strip()]
    if empty_queries:
        print(f"  ⚠️  发现 {len(empty_queries)} 条空查询")
    else:
        print(f"  ✓ 无空查询")
    
    # 2. 检查是否有重复
    query_set = set(item['query'] for item in data)
    duplicates = len(data) - len(query_set)
    if duplicates > 0:
        print(f"  ⚠️  发现 {duplicates} 条重复查询")
    else:
        print(f"  ✓ 无重复查询")
    
    # 3. 检查策略标签有效性
    valid_strategies = {"直接检索", "假设问题检索", "子查询检索", "场景重构检索"}
    invalid_items = [item for item in data if item['strategy'] not in valid_strategies]
    if invalid_items:
        print(f"  ⚠️  发现 {len(invalid_items)} 条无效策略标签")
    else:
        print(f"  ✓ 所有策略标签有效")
    
    # 4. 场景重构检索的质量检查
    scenario_queries = [item['query'] for item in data if item['strategy'] == '场景重构检索']
    complex_indicators = []
    for query in scenario_queries:
        has_numbers = any(c.isdigit() for c in query)
        has_multi_clauses = query.count(",") >= 2
        is_long = len(query) > 25
        
        if sum([has_numbers, has_multi_clauses, is_long]) >= 2:
            complex_indicators.append(query)
    
    quality_rate = len(complex_indicators) / len(scenario_queries) * 100 if scenario_queries else 0
    print(f"\n  场景重构检索质量:")
    print(f"    符合复杂问题特征的样本：{len(complex_indicators)}/{len(scenario_queries)} ({quality_rate:.1f}%)")
    
    if quality_rate < 80:
        print(f"    ⚠️  建议增加更多高质量复杂工程问题")
    else:
        print(f"    ✓ 质量良好")
    
    print("\n" + "="*80)
    print("分析完成！")
    print("="*80)
    
    return data


if __name__ == "__main__":
    data = analyze_dataset()
