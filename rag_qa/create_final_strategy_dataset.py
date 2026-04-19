"""
最终版检索策略分类数据集
目标：构建平衡、高质量的数据集
- 直接检索：~1000 条
- 假设问题检索：~800 条
- 子查询检索：~800 条
- 场景重构检索：~1200 条
总计：~3800 条
"""

import json
import random

random.seed(42)

def load_and_process_data():
    """加载并处理原始数据"""
    print("="*80)
    print("构建最终版检索策略分类数据集")
    print("="*80)
    
    # 1. 加载原始 8000 条数据
    with open('classify_data/strategy_classification_8000.json', 'r', encoding='utf-8') as f:
        original_data = [json.loads(line) for line in f]
    
    print(f"\n1. 已加载原始数据：{len(original_data)} 条")
    
    # 2. 去重
    seen = set()
    unique_data = []
    duplicates = 0
    
    for item in original_data:
        query_key = item['query']
        if query_key not in seen:
            seen.add(query_key)
            unique_data.append(item)
        else:
            duplicates += 1
    
    print(f"2. 去重后剩余：{len(unique_data)} 条 (移除重复：{duplicates} 条)")
    
    # 3. 按策略分组
    grouped = {}
    for item in unique_data:
        strategy = item['strategy']
        if strategy not in grouped:
            grouped[strategy] = []
        grouped[strategy].append(item)
    
    print(f"\n3. 去重后的策略分布:")
    for strategy, items in sorted(grouped.items()):
        print(f"   {strategy}: {len(items)} 条")
    
    return grouped


def generate_hyde_queries(target_count=800, existing_count=41):
    """生成假设问题检索数据"""
    print(f"\n4. 生成假设问题检索数据 (目标：{target_count}条)...")
    
    templates = [
        "采矿工程对环境的影响有哪些？",
        "绿色矿山建设的意义是什么？",
        "智能化开采技术的发展趋势如何？",
        "矿产资源综合利用的价值体现在哪些方面？",
        "数字化矿山建设对企业竞争力的影响？",
        "尾矿资源化利用的前景怎样？",
        "矿山生态修复的作用和重要性？",
        "矿业权流转制度的意义？",
        "现代矿井提升技术的发展趋势",
        "选矿技术未来的发展方向",
        "深部开采面临的挑战与机遇",
        "矿山安全管理的现代化趋势",
        "循环经济与矿山可持续发展的关系",
        "矿业政策变化对行业的影响",
        "新技术在矿山安全监测中的应用前景",
    ]
    
    variations = []
    needed = target_count - existing_count
    
    for i in range(needed):
        base = random.choice(templates)
        # 添加变体
        variant_type = i % 5
        if variant_type == 0:
            query = base
        elif variant_type == 1:
            query = "请问" + base
        elif variant_type == 2:
            query = base + "？请详细说明。"
        elif variant_type == 3:
            query = base.replace("？", "？具体表现在哪些方面？")
        else:
            query = base + "有什么重要意义？"
        
        variations.append({"query": query, "strategy": "假设问题检索"})
    
    print(f"   生成：{len(variations)} 条")
    return variations


def generate_subquery_queries(target_count=800, existing_count=26):
    """生成子查询检索数据"""
    print(f"\n5. 生成子查询检索数据 (目标：{target_count}条)...")
    
    templates = [
        "比较露天开采和地下开采的优缺点。",
        "浮选法和磁选法的区别是什么？",
        "充填采矿法与空场采矿法的差异对比。",
        "国内外的采矿技术标准有何不同？",
        "破碎流程和磨矿流程的区别？",
        "矿井通风方式中中央式与对角式的差异。",
        "露天矿运输系统中汽车运输和铁路运输的优劣对比。",
        "常规爆破与微差爆破的区别及应用场景。",
        "重选、浮选、磁选三种方法的适用条件对比。",
        "竖井开拓与斜井开拓的技术经济比较。",
        "全面采矿法与房柱采矿法的异同点。",
        "干式磨矿与湿式磨矿的优劣分析。",
        "连续采矿机与传统钻爆法的对比。",
        "有线通信与无线通信在矿井下的应用对比。",
        "固定式破碎机与移动式破碎机的性能比较。",
    ]
    
    variations = []
    needed = target_count - existing_count
    
    for i in range(needed):
        base = random.choice(templates)
        variant_type = i % 4
        if variant_type == 0:
            query = base
        elif variant_type == 1:
            query = "请分析" + base
        elif variant_type == 2:
            query = base + "从技术经济角度分析。"
        else:
            query = "试比较" + base
        
        variations.append({"query": query, "strategy": "子查询检索"})
    
    print(f"   生成：{len(variations)} 条")
    return variations


def generate_scenario_queries(target_count=1200, existing_count=494):
    """生成场景重构检索数据"""
    print(f"\n6. 生成场景重构检索数据 (目标：{target_count}条)...")
    
    templates = [
        # 参数化工程问题
        "我有一个埋深{depth}米的{mineral}矿床，矿体倾角{angle}度，厚度{thickness}米，围岩稳固性{stability}，应该选择什么开采方法？",
        "某{mineral}矿矿体埋藏深度达{depth}米，采用露天开采，边坡角{angle}度，如何优化开采参数以确保安全高效？",
        
        # 故障诊断
        "选矿厂{process}过程中{problem1}，同时{problem2}，从哪些方面排查问题并优化工艺参数？",
        "矿山{equipment}设备频繁出现故障，{symptom}，是设备选型问题还是维护保养不到位？",
        
        # 方案设计
        "某矿井瓦斯涌出量{gas_rate}m³/min，工作面温度{temp}℃，如何设计通风系统以确保作业环境安全？",
        "尾矿库坝体出现{dam_issue}，浸润线抬高{height}米，怎样进行除险加固以确保安全？",
        
        # 工艺优化
        "采用{mining_method}采矿法，但矿石损失率达{loss}%，贫化率{dilution}%，如何改进{improve_aspect}？",
        "某铁矿磁性铁回收率只有{recovery}%，远低于设计指标，{process_link}环节存在什么问题？",
        
        # 多因素综合
        "露天矿境界优化时如何平衡剥采比、资源回收率和边坡稳定性三个相互制约的因素？",
        "深部开采面临高地应力、高井温和高渗透压的'三高'问题，综合技术方案应该如何设计？",
        
        # 新模板
        "矿区具有{condition1}、{condition2}等复杂地质条件，推荐采用什么样的{solution}方案？",
        "在{scenario}环境下，{risk}风险显著增加，需要采取哪些综合防控措施？",
        "拟建设年处理{capacity}万吨的{facility}，关键技术参数应该如何确定？",
        "{pollution}污染超标，需要在{time}内完成治理，技术方案如何设计？",
    ]
    
    params = {
        "depth": [200, 300, 400, 500, 600, 800, 1000],
        "mineral": ["铜", "铁", "金", "铅锌", "钨", "锡", "铝土", "镍"],
        "angle": [30, 45, 60, 75],
        "thickness": [5, 8, 10, 15, 20, 30],
        "stability": ["较差", "一般", "较好", "极差", "良好"],
        "process": ["浮选", "磁选", "重选", "浸出", "氰化"],
        "problem1": ["精矿品位偏低", "回收率下降", "药剂消耗增加", "泡沫层变薄"],
        "problem2": ["尾矿品位异常", "设备磨损加剧", "水质恶化", "能耗升高"],
        "equipment": ["提升机", "通风机", "水泵", "破碎机", "球磨机"],
        "symptom": ["振动异常", "温度过高", "噪音大", "效率降低"],
        "gas_rate": [5, 10, 15, 20, 30],
        "temp": [28, 30, 32, 35],
        "dam_issue": ["渗水现象", "裂缝", "局部滑移", "管涌"],
        "height": [2, 3, 5, 8],
        "mining_method": ["无底柱分段崩落", "充填", "房柱", "分段凿岩阶段矿房"],
        "loss": [15, 18, 20, 25],
        "dilution": [10, 12, 15, 18],
        "improve_aspect": ["放矿管理", "采矿参数", "支护方案", "工艺流程"],
        "recovery": [65, 70, 75, 78],
        "process_link": ["磨矿", "磁选", "浮选", "过滤"],
        "condition1": ["矿体埋藏深", "围岩破碎", "水文地质复杂", "地温梯度大"],
        "condition2": ["瓦斯含量高", "矿岩硬度大", "生态环境脆弱"],
        "solution": ["开采方法", "支护方案", "通风系统", "排水系统"],
        "scenario": ["高温", "高湿", "高应力", "强腐蚀", "多粉尘"],
        "risk": ["瓦斯积聚", "顶板冒落", "边坡滑移", "透水"],
        "capacity": [30, 50, 100, 150, 200],
        "facility": ["选矿厂", "充填站", "尾矿库", "通风井"],
        "pollution": ["废水", "废气", "废渣", "噪声"],
        "time": ["3 个月", "半年", "一年"],
    }
    
    variations = []
    needed = target_count - existing_count
    
    for i in range(needed):
        template = random.choice(templates)
        query = template
        
        # 填充参数
        for key, values in params.items():
            placeholder = "{" + key + "}"
            while placeholder in query:
                query = query.replace(placeholder, str(random.choice(values)), 1)
        
        variations.append({"query": query, "strategy": "场景重构检索"})
    
    print(f"   生成：{len(variations)} 条")
    
    # 显示示例
    print(f"   示例（前 3 条）:")
    for j, item in enumerate(variations[:3], 1):
        print(f"      {j}. {item['query']}")
    
    return variations


def create_final_dataset():
    """创建最终数据集"""
    # 1. 加载并处理原始数据
    grouped = load_and_process_data()
    
    # 2. 生成补充数据
    hyde_data = generate_hyde_queries(target_count=800, existing_count=len(grouped.get("假设问题检索", [])))
    subquery_data = generate_subquery_queries(target_count=800, existing_count=len(grouped.get("子查询检索", [])))
    scenario_data = generate_scenario_queries(target_count=1200, existing_count=len(grouped.get("场景重构检索", [])))
    
    # 3. 合并所有数据
    final_data = []
    
    # 添加原始数据（直接使用）
    for strategy, items in grouped.items():
        final_data.extend(items)
    
    # 添加生成的数据
    final_data.extend(hyde_data)
    final_data.extend(subquery_data)
    final_data.extend(scenario_data)
    
    # 4. 打乱顺序
    random.shuffle(final_data)
    
    # 5. 统计分布
    strategy_counts = {}
    for item in final_data:
        strategy = item['strategy']
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    
    # 6. 保存
    output_file = "classify_data/strategy_classification_final.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in final_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print("\n" + "="*80)
    print("✅ 最终版数据集构建完成！")
    print("="*80)
    print(f"\n输出文件：{output_file}")
    print(f"总样本数：{len(final_data)} 条")
    print(f"\n最终策略分布:")
    for strategy, count in sorted(strategy_counts.items()):
        percentage = count / len(final_data) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {strategy:10s}: {count:4d} 条 ({percentage:5.1f}%) {bar}")
    
    # 7. 质量检查
    print(f"\n质量检查:")
    
    # 检查重复
    queries = [item['query'] for item in final_data]
    unique_queries = set(queries)
    dup_count = len(queries) - len(unique_queries)
    if dup_count > 0:
        print(f"  ⚠️  发现 {dup_count} 条重复查询")
    else:
        print(f"  ✓ 无重复查询")
    
    # 检查场景重构检索质量
    scenario_queries = [item['query'] for item in final_data if item['strategy'] == '场景重构检索']
    complex_count = sum(1 for q in scenario_queries 
                       if any(c.isdigit() for c in q) or q.count(",") >= 2 or len(q) > 25)
    quality_rate = complex_count / len(scenario_queries) * 100 if scenario_queries else 0
    print(f"  场景重构检索质量：{complex_count}/{len(scenario_queries)} ({quality_rate:.1f}%)")
    
    if quality_rate >= 80:
        print(f"  ✓ 质量达标！")
    else:
        print(f"  ⚠️  建议继续优化")
    
    print("\n" + "="*80)
    print("数据集已保存到 classify_data/strategy_classification_final.json")
    print("="*80)
    
    return final_data


if __name__ == "__main__":
    final_data = create_final_dataset()
