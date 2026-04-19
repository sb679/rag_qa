# -*- coding:utf-8 -*-
"""
生成采矿工程专业领域的查询分类训练数据集
目标：生成 5000 条高质量、类别均衡的训练数据
"""
import json
import random
import os

# 设置随机种子以保证可重复性
random.seed(42)

def generate_mining_professional_queries():
    """生成采矿工程专业咨询类查询"""
    queries = []
    
    # 1. 开采工艺类
    mining_topics = [
        "露天开采", "地下开采", "井工开采", "充填开采", "空场开采", "崩落开采",
        "采矿方法", "开采顺序", "采场布置", "矿块划分", "开采强度", "开采回采率"
    ]
    for topic in mining_topics:
        queries.extend([
            f"{topic}的工艺流程是什么？",
            f"如何优化{topic}技术？",
            f"{topic}有哪些关键技术要点？",
            f"请详细介绍{topic}的实施步骤",
            f"{topic}的安全注意事项有哪些？"
        ])
    
    # 2. 矿井建设类
    mine_construction = [
        "矿井设计", "巷道布置", "井筒施工", "矿井通风", "矿井排水", "矿井供电",
        "矿井提升", "矿井运输", "巷道支护", "井壁支护", "硐室设计", "矿井防水"
    ]
    for topic in mine_construction:
        queries.extend([
            f"{topic}的设计原则是什么？",
            f"如何进行{topic}的计算？",
            f"{topic}的技术标准有哪些？",
            f"{topic}施工中常见问题及解决方法",
            f"现代{topic}技术的发展趋势"
        ])
    
    # 3. 矿物加工类
    mineral_processing = [
        "破碎工艺", "磨矿分级", "浮选分离", "磁选技术", "重选方法", "化学选矿",
        "尾矿处理", "精矿脱水", "选矿药剂", "选矿设备", "选矿流程", "品位控制"
    ]
    for topic in mineral_processing:
        queries.extend([
            f"{topic}的基本原理是什么？",
            f"如何提高{topic}的效率？",
            f"{topic}的主要设备有哪些？",
            f"{topic}的工艺参数如何控制？",
            f"{topic}的技术经济指标分析"
        ])
    
    # 4. 矿山安全类
    safety_topics = [
        "瓦斯防治", "煤尘爆炸", "矿井火灾", "矿井水害", "顶板管理", "冲击地压",
        "边坡稳定", "尾矿库安全", "爆破安全", "职业健康", "应急救援", "安全监测"
    ]
    for topic in safety_topics:
        queries.extend([
            f"{topic}的预防措施有哪些？",
            f"如何识别{topic}的风险？",
            f"{topic}的治理技术方案",
            f"{topic}相关的法规标准",
            f"{topic}事故案例分析与启示"
        ])
    
    # 5. 矿产资源类
    resource_topics = [
        "矿床勘探", "储量计算", "矿产普查", "地质勘查", "矿体圈定", "品位估算",
        "资源评价", "矿业权管理", "矿产资源规划", "综合利用", "绿色矿山", "矿山复垦"
    ]
    for topic in resource_topics:
        queries.extend([
            f"{topic}的方法和技术",
            f"如何进行{topic}？",
            f"{topic}的标准和规范",
            f"{topic}的最新研究进展",
            f"{topic}在实际中的应用"
        ])
    
    # 6. 矿山机械类
    machinery_topics = [
        "采煤机", "掘进机", "液压支架", "刮板输送机", "提升机", "通风机",
        "水泵", "空压机", "破碎机", "球磨机", "浮选机", "磁选机"
    ]
    for topic in machinery_topics:
        queries.extend([
            f"{topic}的工作原理是什么？",
            f"如何选择{topic}的型号？",
            f"{topic}的维护保养要点",
            f"{topic}常见故障及排除方法",
            f"新型{topic}的技术特点"
        ])
    
    # 7. 综合技术问题
    comprehensive_queries = [
        "如何提高矿产资源的回收率？",
        "矿山开采对环境的影响及防治措施",
        "智能化矿山建设的关键技术",
        "深部开采面临的技术挑战",
        "难采矿体的开采技术选择",
        "低品位矿石的经济利用途径",
        "矿山废水处理方法与技术",
        "井下粉尘综合治理方案",
        "矿山节能减排技术措施",
        "数字化矿山系统的构建方案"
    ]
    queries.extend(comprehensive_queries)
    
    return queries


def generate_general_knowledge_queries():
    """生成通用知识类查询"""
    queries = []
    
    # 1. 数学计算类
    math_queries = [
        "1+1 等于几？",
        "如何计算圆的面积？",
        "勾股定理是什么？",
        "求 100 的平方根",
        "解方程 2x+5=15",
        "什么是微积分？",
        "如何计算概率？",
        "三角函数有哪些？",
        "等差数列求和公式",
        "矩阵乘法怎么计算？"
    ]
    queries.extend(math_queries)
    
    # 2. 编程代码类
    coding_queries = [
        "Python 怎么定义函数？",
        "Java 中的继承如何实现？",
        "C++指针怎么用？",
        "JavaScript 如何操作 DOM？",
        "SQL 查询语句怎么写？",
        "HTML 表格如何创建？",
        "CSS 如何让元素居中？",
        "Linux 常用命令有哪些？",
        "Git 如何创建分支？",
        "Python 列表和元组有什么区别？"
    ]
    queries.extend(coding_queries)
    
    # 3. 概念解释类（非采矿）
    concept_queries = [
        "什么是人工智能？",
        "区块链是什么技术？",
        "云计算有什么特点？",
        "大数据的定义是什么？",
        "物联网的应用有哪些？",
        "机器学习的基本原理",
        "深度学习与机器学习的区别",
        "什么是元宇宙？",
        "量子计算是什么？",
        "5G 技术的特点"
    ]
    queries.extend(concept_queries)
    
    # 4. 日常生活类
    daily_queries = [
        "北京今天天气怎么样？",
        "如何做西红柿炒鸡蛋？",
        "感冒了吃什么药？",
        "从北京到上海怎么走？",
        "推荐几本好看的书",
        "如何学习英语口语？",
        "健身新手应该从哪里开始？",
        "如何缓解工作压力？",
        "信用卡逾期怎么办？",
        "买房需要注意什么？"
    ]
    queries.extend(daily_queries)
    
    # 5. 历史文化类
    history_queries = [
        "中国有多少个朝代？",
        "唐朝的建立者是谁？",
        "文艺复兴是什么时候？",
        "第一次世界大战的原因",
        "孔子的主要思想是什么？",
        "长城是什么时候修建的？",
        "四大发明都有哪些？",
        "丝绸之路的路线是怎样的？",
        "明朝的皇帝有哪些？",
        "二战结束于哪一年？"
    ]
    queries.extend(history_queries)
    
    # 6. 科学技术类（通用）
    science_queries = [
        "光速是多少？",
        "水的沸点是多少度？",
        "地球有多大年纪？",
        "太阳系有几大行星？",
        "DNA 是什么结构？",
        "牛顿三大定律是什么？",
        "相对论是谁提出的？",
        "原子由什么组成？",
        "光合作用的过程",
        "电磁感应现象是什么？"
    ]
    queries.extend(science_queries)
    
    # 7. 扩展问题（增加多样性）
    extended_general = []
    templates = [
        "如何{}",
        "什么是{}",
        "{}的原理",
        "为什么{}",
        "{}有哪些应用",
        "请解释{}",
        "{}是什么意思",
        "怎样{}",
        "{}的方法",
        "{}的步骤"
    ]
    
    general_topics = [
        "学习编程", "减肥", "摄影", "绘画", "音乐创作", "视频剪辑",
        "投资理财", "心理健康", "时间管理", "沟通技巧", "创业", "就业"
    ]
    
    for template in templates:
        for topic in random.sample(general_topics, min(5, len(general_topics))):
            extended_general.append(template.format(topic))
    
    queries.extend(extended_general)
    
    return queries


def balance_and_shuffle(mining_queries, general_queries, target_count=5000):
    """平衡两类数据并打乱顺序"""
    # 确保两类数据数量相等
    min_count = min(len(mining_queries), len(general_queries))
    target_per_class = target_count // 2
    
    if min_count < target_per_class:
        print(f"⚠️  警告：某类数据不足，专业咨询:{len(mining_queries)}, 通用知识:{len(general_queries)}")
        print(f"需要每类{target_per_class}条，但最少的一类只有{min_count}条")
        print("将使用重复采样来补充数据")
        
        # 如果数据不足，通过重复采样来补充
        if len(mining_queries) < target_per_class:
            additional_needed = target_per_class - len(mining_queries)
            mining_queries += random.choices(mining_queries, k=additional_needed)
        
        if len(general_queries) < target_per_class:
            additional_needed = target_per_class - len(general_queries)
            general_queries += random.choices(general_queries, k=additional_needed)
    
    # 截取目标数量
    mining_queries = mining_queries[:target_per_class]
    general_queries = general_queries[:target_per_class]
    
    # 添加标签
    labeled_data = []
    for query in mining_queries:
        labeled_data.append({"query": query, "label": "专业咨询"})
    
    for query in general_queries:
        labeled_data.append({"query": query, "label": "通用知识"})
    
    # 打乱顺序
    random.shuffle(labeled_data)
    
    return labeled_data


def save_training_data(data, output_file="training_dataset_mining_5000.json"):
    """保存训练数据为 JSON 格式（每行一个 JSON 对象）"""
    output_path = os.path.join(os.path.dirname(__file__), 'classify_data', output_file)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"✓ 训练数据已保存至：{output_path}")
    print(f"  总样本数：{len(data)}")
    
    # 统计类别分布
    professional_count = sum(1 for item in data if item['label'] == '专业咨询')
    general_count = sum(1 for item in data if item['label'] == '通用知识')
    print(f"  专业咨询：{professional_count} 条")
    print(f"  通用知识：{general_count} 条")
    print(f"  类别比例：{professional_count}:{general_count}")


def main():
    """主函数：生成训练数据集"""
    print("=" * 60)
    print("生成采矿工程专业领域查询分类训练数据集")
    print("=" * 60)
    
    # 生成专业咨询类查询
    print("\n正在生成专业咨询类查询...")
    mining_queries = generate_mining_professional_queries()
    print(f"✓ 生成了 {len(mining_queries)} 条专业咨询类查询")
    
    # 生成通用知识类查询
    print("\n正在生成通用知识类查询...")
    general_queries = generate_general_knowledge_queries()
    print(f"✓ 生成了 {len(general_queries)} 条通用知识类查询")
    
    # 平衡并打乱数据（默认生成 5000 条，如需增加可修改为 10000）
    print("\n正在平衡数据并打乱顺序...")
    balanced_data = balance_and_shuffle(mining_queries, general_queries, target_count=5000)
    
    # 保存数据
    print("\n正在保存训练数据...")
    save_training_data(balanced_data)
    
    print("\n" + "=" * 60)
    print("数据集生成完成！")
    print("下一步：运行 train_classifier.py 训练模型")
    print("=" * 60)


if __name__ == '__main__':
    main()
