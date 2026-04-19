import json

# 分析训练数据
data = [json.loads(line) for line in open('classify_data/training_dataset_mining_5000.json', 'r', encoding='utf-8')]

# 统计标签分布
labels = {}
for item in data:
    label = item['label']
    labels[label] = labels.get(label, 0) + 1

print('标签分布:', labels)
print('总样本数:', len(data))
print('\n示例数据:')
for i in range(5):
    print(f"{i+1}. {data[i]}")
