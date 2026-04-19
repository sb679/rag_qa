"""
构建检索策略分类训练数据集
目标：生成包含四种检索策略标签的训练数据
- 直接检索
- 假设问题检索 (HyDE)
- 子查询检索
- 场景重构检索（新增）
"""

import json
import random
from typing import List, Dict

# 设置随机种子，确保可重复性
random.seed(42)

class StrategyDatasetBuilder:
    def __init__(self):
        # 加载原始数据集
        self.raw_data = self.load_raw_data()
        
        # 定义策略分类规则关键词
        self.strategy_keywords = {
            "直接检索": {
                "length_range": (5, 18),
                "keywords": ["是什么", "有哪些", "包括", "定义", "概念", "原理", "特点"],
                "exclude": ["如何", "怎样", "对比", "区别", "影响", "优化", "设计"]
            },
            "假设问题检索": {
                "keywords": ["影响", "意义", "作用", "趋势", "前景", "关系", "重要性", "价值"],
                "abstract_concepts": True
            },
            "子查询检索": {
                "keywords": ["对比", "区别", "差异", "优劣", "比较", "和", "与", "及"],
                "multi_topic": True
            },
            "场景重构检索": {
                "length_range": (25, 60),
                "has_numbers": True,
                "multi_clauses": True,
                "keywords": ["如何", "怎样", "应该", "方案", "设计", "优化", "解决", "措施", "故障", "异常"]
            }
        }
    
    def load_raw_data(self) -> List[Dict]:
        """加载原始训练数据"""
        data = []
        with open('classify_data/training_dataset_mining_5000.json', 'r', encoding='utf-8') as f:
            for line in f:
                data.append(json.loads(line))
        print(f"已加载原始数据 {len(data)} 条")
        return data
    
    def classify_single_query(self, query: str) -> str:
        """
        根据规则对单个查询进行策略分类
        返回：策略名称
        """
        length = len(query)
        
        # 规则 1: 检查是否包含抽象概念词 → 假设问题检索
        abstract_words = ["影响", "意义", "作用", "趋势", "前景", "关系", "重要性", "价值", "效果"]
        if any(word in query for word in abstract_words):
            return "假设问题检索"
        
        # 规则 2: 检查是否为对比类问题 → 子查询检索
        comparison_words = ["对比", "区别", "差异", "优劣", "比较", "哪个更好", "有何不同"]
        if any(word in query for word in comparison_words):
            return "子查询检索"
        
        # 规则 3: 检查是否为复杂工程问题 → 场景重构检索
        complex_indicators = [
            length > 25,  # 长度较长
            query.count(",") >= 2,  # 多个分句
            any(c.isdigit() for c in query),  # 包含数字参数
            any(kw in query for kw in ["如何", "怎样", "应该", "方案", "设计", "优化", "解决", "故障", "异常"])
        ]
        if sum(complex_indicators) >= 2:  # 满足 2 个以上条件
            return "场景重构检索"
        
        # 规则 4: 其余情况 → 直接检索
        return "直接检索"
    
    def transform_existing_data(self, sample_size: int = 3000) -> List[Dict]:
        """
        从现有数据集中选择并转换一部分数据
        sample_size: 采样数量
        """
        print(f"\n正在从现有数据集转换 {sample_size} 条数据...")
        
        # 分层采样，确保各类别平衡
        professional_queries = [item for item in self.raw_data if item['label'] == '专业咨询']
        generic_queries = [item for item in self.raw_data if item['label'] == '通用知识']
        
        # 按比例采样（专业咨询占 70%，通用知识占 30%）
        prof_sample = random.sample(professional_queries, min(int(sample_size * 0.7), len(professional_queries)))
        gen_sample = random.sample(generic_queries, min(int(sample_size * 0.3), len(generic_queries)))
        
        sampled_data = prof_sample + gen_sample
        random.shuffle(sampled_data)
        
        # 转换为策略标签
        transformed_data = []
        strategy_counts = {}
        
        for item in sampled_data:
            query = item['query']
            strategy = self.classify_single_query(query)
            
            transformed_item = {
                "query": query,
                "strategy": strategy,
                "source": "existing"
            }
            transformed_data.append(transformed_item)
            
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        print(f"转换完成，策略分布:")
        for strategy, count in sorted(strategy_counts.items()):
            print(f"  - {strategy}: {count} 条")
        
        return transformed_data
    
    def generate_new_complex_queries(self, count: int = 500) -> List[Dict]:
        """
        生成新的复杂工程问题（场景重构检索专用）
        """
        print(f"\n正在生成 {count} 条新的复杂工程问题...")
        
        # 定义采矿领域的场景模板
        scenarios = [
            # 开采方法选择类
            ("我有一个埋深{depth}米的{mineral_type}矿床，矿体倾角{angle}度，厚度{thickness}米，围岩稳固性{stability}，应该选择什么开采方法？", "场景重构检索"),
            ("某{mineral_type}矿矿体埋藏深度达{depth}米，采用露天开采，边坡角{angle}度，如何优化开采参数以确保安全高效？", "场景重构检索"),
            
            # 故障诊断类
            ("选矿厂{process_type}过程中{problem_phenomenon}，同时{related_issue}，从哪些方面排查问题并优化工艺参数？", "场景重构检索"),
            ("矿山{equipment_type}设备频繁出现故障，{specific_problem}，是设备选型问题还是维护保养不到位？", "场景重构检索"),
            
            # 方案设计类
            ("某矿井瓦斯涌出量{gas_rate}m³/min，工作面温度{temperature}℃，如何设计通风系统以确保作业环境安全？", "场景重构检索"),
            ("尾矿库坝体出现{dam_problem}，浸润线抬高{height}米，怎样进行除险加固以确保安全？", "场景重构检索"),
            
            # 工艺优化类
            ("采用{mining_method}采矿法，但矿石损失率达{loss_rate}%，贫化率{dilution_rate}%，如何改进{improve_aspect}？", "场景重构检索"),
            ("某铁矿磁性铁回收率只有{recovery_rate}%，远低于设计指标，{process_link}环节存在什么问题？", "场景重构检索"),
            
            # 多因素综合类
            ("露天矿境界优化时如何平衡剥采比、资源回收率和边坡稳定性三个相互制约的因素？", "场景重构检索"),
            ("深部开采面临高地应力、高井温和高渗透压的'三高'问题，综合技术方案应该如何设计？", "场景重构检索"),
        ]
        
        # 填充参数
        params = {
            "depth": [200, 300, 400, 500, 600, 800, 1000],
            "mineral_type": ["铜", "铁", "金", "铅锌", "钨", "锡", "铝土"],
            "angle": [30, 45, 60, 75],
            "thickness": [5, 8, 10, 15, 20, 30],
            "stability": ["较差", "一般", "较好", "极差"],
            "process_type": ["浮选", "磁选", "重选", "氰化", "浸出"],
            "problem_phenomenon": ["精矿品位持续偏低", "回收率下降", "药剂消耗量增加", "泡沫层变薄"],
            "related_issue": ["尾矿品位异常", "设备磨损加剧", "水质恶化"],
            "equipment_type": ["提升机", "通风机", "水泵", "破碎机", "球磨机"],
            "specific_problem": ["钢丝绳磨损严重", "振动异常", "温度过高", "噪音大"],
            "gas_rate": [5, 10, 15, 20, 30],
            "temperature": [28, 30, 32, 35],
            "dam_problem": ["渗水现象", "裂缝", "局部滑移", "管涌"],
            "height": [2, 3, 5, 8],
            "mining_method": ["无底柱分段崩落", "充填", "房柱", "分段凿岩阶段矿房"],
            "loss_rate": [15, 18, 20, 25],
            "dilution_rate": [10, 12, 15, 18],
            "improve_aspect": ["放矿管理", "采矿参数", "支护方案", "工艺流程"],
            "recovery_rate": [65, 70, 75, 78],
            "process_link": ["磨矿", "磁选", "浮选", "过滤"]
        }
        
        generated_data = []
        
        for i in range(count):
            template, strategy = random.choice(scenarios)
            
            # 随机填充参数
            filled_query = template
            for key, values in params.items():
                placeholder = "{" + key + "}"
                if placeholder in filled_query:
                    filled_query = filled_query.replace(placeholder, str(random.choice(values)))
            
            generated_item = {
                "query": filled_query,
                "strategy": strategy,
                "source": "generated"
            }
            generated_data.append(generated_item)
        
        print(f"生成完成，共 {len(generated_data)} 条复杂工程问题")
        return generated_data
    
    def generate_other_strategies(self, count_per_strategy: int = 300) -> List[Dict]:
        """
        生成其他三种策略的补充数据
        """
        print(f"\n正在生成其他策略的训练数据...")
        
        # 假设问题检索模板
        hyde_templates = [
            "采矿工程对环境的影响有哪些？",
            "绿色矿山建设的意义是什么？",
            "智能化开采技术的发展趋势如何？",
            "矿产资源综合利用的价值体现在哪些方面？",
            "数字化矿山建设对企业竞争力的影响？",
            "尾矿资源化利用的前景怎样？",
            "矿山生态修复的作用和重要性？",
            "矿业权流转制度的意义？",
        ]
        
        # 子查询检索模板
        subquery_templates = [
            "比较露天开采和地下开采的优缺点。",
            "浮选法和磁选法的区别是什么？",
            "充填采矿法与空场采矿法的差异对比。",
            "国内外的采矿技术标准有何不同？",
            "破碎流程和磨矿流程的区别？",
            "矿井通风方式中中央式与对角式的差异。",
            "露天矿运输系统中汽车运输和铁路运输的优劣对比。",
            "常规爆破与微差爆破的区别及应用场景。",
        ]
        
        # 直接检索模板（从现有数据中抽取简单问题）
        direct_samples = [q for q in self.raw_data 
                         if len(q['query']) < 18 and q['label'] == '专业咨询'
                         and "，" not in q['query']]
        
        generated_data = []
        
        # 生成假设问题检索数据（带一些变体）
        for i in range(count_per_strategy):
            base_template = random.choice(hyde_templates)
            # 添加一些变体
            variations = [
                base_template,
                base_template.replace("？", "？请详细说明。"),
                "请问" + base_template,
                base_template + "具体表现在哪些方面？"
            ]
            query = random.choice(variations)
            
            generated_data.append({
                "query": query,
                "strategy": "假设问题检索",
                "source": "generated"
            })
        
        # 生成子查询检索数据
        for i in range(count_per_strategy):
            base_template = random.choice(subquery_templates)
            variations = [
                base_template,
                "请分析" + base_template,
                base_template + "？从技术经济角度分析。",
            ]
            query = random.choice(variations)
            
            generated_data.append({
                "query": query,
                "strategy": "子查询检索",
                "source": "generated"
            })
        
        # 生成直接检索数据
        for i in range(count_per_strategy):
            if direct_samples:
                query = random.choice(direct_samples)['query']
            else:
                # 如果样本不够，构造一些简单问题
                simple_templates = [
                    "什么是充填采矿法？",
                    "矿井通风的基本原则是什么？",
                    "浮选药剂有哪些类型？",
                    "矿山安全规程对瓦斯浓度的要求？",
                    "破碎机的工作原理是什么？",
                    "如何计算矿山服务年限？",
                    "尾矿库选址的要求有哪些？",
                    "什么是矿体倾角？",
                ]
                query = random.choice(simple_templates)
            
            generated_data.append({
                "query": query,
                "strategy": "直接检索",
                "source": "generated"
            })
        
        print(f"生成其他策略数据共 {len(generated_data)} 条")
        return generated_data
    
    def build_dataset(self, output_file: str = "classify_data/strategy_classification_8000.json"):
        """
        构建完整的数据集
        """
        print("="*80)
        print("开始构建检索策略分类训练数据集")
        print("="*80)
        
        # 1. 从现有数据转换
        existing_data = self.transform_existing_data(sample_size=4000)
        
        # 2. 生成新的复杂工程问题（场景重构检索）
        complex_data = self.generate_new_complex_queries(count=1500)
        
        # 3. 生成其他策略的补充数据
        other_data = self.generate_other_strategies(count_per_strategy=800)
        
        # 合并所有数据
        all_data = existing_data + complex_data + other_data
        
        # 打乱顺序
        random.shuffle(all_data)
        
        # 统计分布
        strategy_distribution = {}
        source_distribution = {"existing": 0, "generated": 0}
        
        for item in all_data:
            strategy = item['strategy']
            source = item['source']
            strategy_distribution[strategy] = strategy_distribution.get(strategy, 0) + 1
            source_distribution[source] += 1
        
        # 保存数据集
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in all_data:
                # 移除 source 字段，只保留 query 和 strategy
                output_item = {
                    "query": item['query'],
                    "strategy": item['strategy']
                }
                f.write(json.dumps(output_item, ensure_ascii=False) + '\n')
        
        print("\n" + "="*80)
        print("数据集构建完成！")
        print("="*80)
        print(f"\n输出文件：{output_file}")
        print(f"总样本数：{len(all_data)} 条")
        print(f"\n数据来源分布:")
        for source, count in source_distribution.items():
            percentage = count / len(all_data) * 100
            print(f"  - {source}: {count} 条 ({percentage:.1f}%)")
        print(f"\n策略分布:")
        for strategy, count in sorted(strategy_distribution.items()):
            percentage = count / len(all_data) * 100
            print(f"  - {strategy}: {count} 条 ({percentage:.1f}%)")
        
        print("\n" + "="*80)
        print("示例数据（前 10 条）:")
        print("="*80)
        for i, item in enumerate(all_data[:10], 1):
            print(f"{i}. [{item['strategy']}] {item['query']}")
        
        return all_data


if __name__ == "__main__":
    builder = StrategyDatasetBuilder()
    dataset = builder.build_dataset()
    
    print("\n✅ 数据集已成功生成并保存到 classify_data/strategy_classification_8000.json")
