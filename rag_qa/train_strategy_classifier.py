"""
使用现有 BERT-base-chinese 模型训练检索策略分类器
========================================
特点：
- 直接使用项目中已有的模型
- 无需下载任何新文件
- CPU/GPU 都能运行
- 快速出结果
"""

import json
import os
import torch
from torch.utils.data import Dataset
from transformers import BertTokenizer, BertForSequenceClassification
from transformers import TrainingArguments, Trainer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score, confusion_matrix
import numpy as np

# ==================== 配置参数 ====================

class Config:
    # 数据路径
    DATA_PATH = "classify_data/strategy_classification_8000.json"
    
    # 模型路径（使用现有模型）
    MODEL_PATH = "models/bert-base-chinese"
    
    # 输出路径
    OUTPUT_DIR = "./bert_strategy_results"
    LOGS_DIR = "./bert_strategy_logs"
    
    # 标签映射（4 分类）
    LABEL_MAP = {
        "直接检索": 0,
        "假设问题检索": 1,
        "子查询检索": 2,
        "场景重构检索": 3
    }
    
    ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}
    
    # 训练参数
    MAX_LENGTH = 128
    BATCH_SIZE = 16 if torch.cuda.is_available() else 8
    NUM_EPOCHS = 5
    LEARNING_RATE = 2e-5
    
    # 设备
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ==================== 数据集类 ====================

class StrategyDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels
    
    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item
    
    def __len__(self):
        return len(self.labels)


# ==================== 主训练流程 ====================

def load_and_preprocess_data():
    """加载并预处理数据"""
    print("="*80)
    print("步骤 1: 加载数据")
    print("="*80)
    
    # 加载数据
    data = []
    with open(Config.DATA_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    
    print(f"✓ 已加载 {len(data)} 条数据")
    
    # 提取文本和标签
    texts = [item['query'] for item in data]
    labels = [Config.LABEL_MAP[item['strategy']] for item in data]
    
    # 数据划分（分层抽样）
    train_texts, temp_texts, train_labels, temp_labels = train_test_split(
        texts, labels, 
        test_size=0.2, 
        stratify=labels,
        random_state=42
    )
    
    val_texts, test_texts, val_labels, test_labels = train_test_split(
        temp_texts, temp_labels,
        test_size=0.5,
        stratify=temp_labels,
        random_state=42
    )
    
    print(f"✓ 训练集：{len(train_texts)} 条")
    print(f"✓ 验证集：{len(val_texts)} 条")
    print(f"✓ 测试集：{len(test_texts)} 条")
    
    return train_texts, val_texts, test_texts, train_labels, val_labels, test_labels


def tokenize_data(train_texts, val_texts, test_texts):
    """分词处理"""
    print("\n" + "="*80)
    print("步骤 2: 分词处理")
    print("="*80)
    
    # 加载分词器（使用现有模型）
    tokenizer = BertTokenizer.from_pretrained(Config.MODEL_PATH)
    
    print(f"✓ 已加载分词器：{Config.MODEL_PATH}")
    
    # 分词
    train_encodings = tokenizer(train_texts, truncation=True, padding=True, 
                                max_length=Config.MAX_LENGTH)
    val_encodings = tokenizer(val_texts, truncation=True, padding=True, 
                              max_length=Config.MAX_LENGTH)
    test_encodings = tokenizer(test_texts, truncation=True, padding=True, 
                               max_length=Config.MAX_LENGTH)
    
    print(f"✓ 分词完成，最大长度：{Config.MAX_LENGTH}")
    
    return tokenizer, train_encodings, val_encodings, test_encodings


def create_datasets(train_encodings, val_encodings, test_encodings, 
                    train_labels, val_labels, test_labels):
    """创建 Dataset 对象"""
    train_dataset = StrategyDataset(train_encodings, train_labels)
    val_dataset = StrategyDataset(val_encodings, val_labels)
    test_dataset = StrategyDataset(test_encodings, test_labels)
    
    print(f"✓ 创建训练数据集：{len(train_dataset)} 条")
    print(f"✓ 创建验证数据集：{len(val_dataset)} 条")
    print(f"✓ 创建测试数据集：{len(test_dataset)} 条")
    
    return train_dataset, val_dataset, test_dataset


def load_model():
    """加载 BERT 模型"""
    print("\n" + "="*80)
    print("步骤 3: 加载模型")
    print("="*80)
    
    # 加载预训练模型（4 分类）
    model = BertForSequenceClassification.from_pretrained(
        Config.MODEL_PATH,
        num_labels=len(Config.LABEL_MAP),  # 4 分类
        output_attentions=False,
        output_hidden_states=False
    )
    
    model.to(Config.DEVICE)
    
    print(f"✓ 已加载模型：{Config.MODEL_PATH}")
    print(f"✓ 设备：{Config.DEVICE}")
    print(f"✓ 分类数：{len(Config.LABEL_MAP)}")
    
    return model


def compute_metrics(eval_pred):
    """计算评估指标"""
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    
    # 计算 F1 分数
    f1_macro = f1_score(labels, predictions, average='macro')
    f1_weighted = f1_score(labels, predictions, average='weighted')
    accuracy = (predictions == labels).mean()
    
    return {
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted
    }


def train_model(model, tokenizer, train_dataset, val_dataset):
    """训练模型"""
    print("\n" + "="*80)
    print("步骤 4: 开始训练")
    print("="*80)
    
    # 训练参数
    training_args = TrainingArguments(
        output_dir=Config.OUTPUT_DIR,
        num_train_epochs=Config.NUM_EPOCHS,
        per_device_train_batch_size=Config.BATCH_SIZE,
        per_device_eval_batch_size=Config.BATCH_SIZE * 2,
        learning_rate=Config.LEARNING_RATE,
        warmup_steps=50,
        weight_decay=0.01,
        
        # 评估策略
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        save_total_limit=2,
        metric_for_best_model="eval_f1_macro",
        greater_is_better=True,
        
        # 日志
        logging_dir=Config.LOGS_DIR,
        logging_steps=50,
        
        # 其他
        fp16=Config.DEVICE.type == 'cuda',  # GPU 启用混合精度
        dataloader_num_workers=0,
        seed=42,
    )
    
    # 初始化 Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )
    
    # 开始训练
    print(f"\n📊 训练配置:")
    print(f"   - 训练轮次：{Config.NUM_EPOCHS}")
    print(f"   - 批次大小：{Config.BATCH_SIZE}")
    print(f"   - 学习率：{Config.LEARNING_RATE}")
    print(f"   - 设备：{'GPU' if Config.DEVICE.type == 'cuda' else 'CPU'}")
    print(f"\n⏳ 开始训练...\n")
    
    trainer.train()
    
    print("\n✅ 训练完成！")
    
    return trainer


def evaluate_model(trainer, test_dataset, test_labels):
    """在测试集上评估"""
    print("\n" + "="*80)
    print("步骤 5: 测试集评估")
    print("="*80)
    
    # 预测
    predictions = trainer.predict(test_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=-1)
    
    # 详细报告
    print("\n📊 分类报告:")
    print(classification_report(
        test_labels, 
        pred_labels,
        target_names=list(Config.LABEL_MAP.keys()),
        digits=4
    ))
    
    # 混淆矩阵
    print("\n📊 混淆矩阵:")
    cm = confusion_matrix(test_labels, pred_labels)
    print(cm)
    
    # 保存模型
    print("\n" + "="*80)
    print("步骤 6: 保存模型")
    print("="*80)
    
    save_path = "./bert_strategy_classifier"
    trainer.model.save_pretrained(save_path)
    
    # 保存分词器
    tokenizer = trainer.tokenizer
    tokenizer.save_pretrained(save_path)
    
    # 保存标签映射
    label_map_path = os.path.join(save_path, "label_map.json")
    with open(label_map_path, 'w', encoding='utf-8') as f:
        json.dump(Config.LABEL_MAP, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 模型已保存至：{save_path}")
    print(f"✓ 标签映射已保存至：{label_map_path}")
    
    return pred_labels


def main():
    """主函数"""
    print("\n" + "="*80)
    print("🚀 BERT 检索策略分类器训练")
    print("使用现有模型：models/bert-base-chinese")
    print("="*80 + "\n")
    
    # 1. 加载数据
    train_texts, val_texts, test_texts, train_labels, val_labels, test_labels = \
        load_and_preprocess_data()
    
    # 2. 分词
    tokenizer, train_encodings, val_encodings, test_encodings = \
        tokenize_data(train_texts, val_texts, test_texts)
    
    # 3. 创建数据集
    train_dataset, val_dataset, test_dataset = \
        create_datasets(train_encodings, val_encodings, test_encodings,
                       train_labels, val_labels, test_labels)
    
    # 4. 加载模型
    model = load_model()
    
    # 5. 训练
    trainer = train_model(model, tokenizer, train_dataset, val_dataset)
    
    # 6. 评估
    pred_labels = evaluate_model(trainer, test_dataset, test_labels)
    
    print("\n" + "="*80)
    print("🎉 全部完成！")
    print("="*80)
    print("\n下一步:")
    print("1. 测试模型效果：python test_strategy_classifier.py")
    print("2. 集成到 RAG 系统：修改 QueryClassifier")
    print("3. 更新 StrategySelector 使用本地分类器")


if __name__ == "__main__":
    main()
