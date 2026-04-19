import json

# 加载训练数据
with open('classify_data/training_dataset_mining_5000.json', 'r', encoding='utf-8') as f:
    data = [json.loads(line) for line in f.readlines()]

# 统计类别分布
generic_count = sum(1 for item in data if item['label'] == '通用知识')
professional_count = sum(1 for item in data if item['label'] == '专业咨询')

print(f'总样本数：{len(data)}')
print(f'通用知识：{generic_count}')
print(f'专业咨询：{professional_count}')
print(f'\n通用知识样本示例:')
generic_samples = [item for item in data if item['label'] == '通用知识']
for i, item in enumerate(generic_samples[:20], 1):
    print(f'{i}. {item["query"]} - {item["label"]}')
