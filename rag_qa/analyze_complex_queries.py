import json

# 分析训练数据中的复杂问题
data = [json.loads(line) for line in open('classify_data/training_dataset_mining_5000.json', 'r', encoding='utf-8')]

# 找出所有专业咨询类的问题
professional_queries = [item['query'] for item in data if item['label'] == '专业咨询']

print(f'专业咨询问题总数：{len(professional_queries)}\n')

# 找出可能适合回溯检索的复杂问题（包含多个技术要素）
complex_keywords = ['如何', '怎样', '应该', '方案', '设计', '优化', '改进', '解决', '措施', '方法']
complex_queries = []

for query in professional_queries:
    # 包含 2 个及以上关键词的可能是复杂问题
    count = sum(1 for kw in complex_keywords if kw in query)
    if count >= 2 or len(query) > 25:  # 长问题或包含多个关键词
        complex_queries.append(query)

print(f'可能的复杂问题数量：{len(complex_queries)}\n')
print('示例复杂问题:')
for i, query in enumerate(complex_queries[:30], 1):
    print(f'{i}. {query}')

# 分析问题长度分布
lengths = [len(q) for q in professional_queries]
print(f'\n问题长度统计:')
print(f'最短：{min(lengths)} 字符')
print(f'最长：{max(lengths)} 字符')
print(f'平均：{sum(lengths)/len(lengths):.1f} 字符')

# 找出超长问题
long_queries = [q for q in professional_queries if len(q) > 30]
print(f'\n超长问题 (>30 字符) 数量：{len(long_queries)}')
if long_queries:
    print('示例:')
    for i, query in enumerate(long_queries[:10], 1):
        print(f'{i}. {query} ({len(query)}字符)')
