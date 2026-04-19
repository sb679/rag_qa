# -*- coding:utf-8 -*-
"""
快速训练 BERT 查询分类模型（简化版）
使用更少的训练轮次和更大的批次来加速训练
"""
import os
import sys
import json
import io

# 设置控制台输出为 UTF-8，避免 Windows 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.query_classifier import QueryClassifier
from base import logger
from transformers import TrainingArguments, Trainer

def quick_train():
    """快速训练模型"""
    print("=" * 60)
    print("快速训练 BERT 查询分类模型")
    print("=" * 60)
    
    # 检查训练数据
    data_file = os.path.join(current_dir, 'classify_data', 'training_dataset_mining_5000.json')
    
    if not os.path.exists(data_file):
        print("❌ 错误：训练数据文件不存在")
        print("请先运行 generate_training_data.py")
        return False
    
    # 统计样本
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print(f"\n✓ 加载训练数据：{len(lines)} 条")
    
    # 初始化分类器（使用新目录避免文件锁定）
    print("\n初始化 BERT 分类器...")
    classifier = QueryClassifier(model_path="bert_query_classifier_new")
    
    # 修改训练参数以加速
    print("\n使用快速训练参数:")
    print("  - 训练轮次：2 epochs (减少时间)")
    print("  - 训练批次：32 (加快速度)")
    print("  - 验证批次：32")
    print("  - 预计时间：5-8 分钟")
    print("=" * 60)
    
    try:
        # 临时修改训练参数
        from transformers import TrainingArguments
        
        training_args = TrainingArguments(
            output_dir="./bert_results",
            num_train_epochs=2,  # 减少到 2 轮
            per_device_train_batch_size=32,  # 增大批次
            per_device_eval_batch_size=32,
            warmup_steps=10,
            weight_decay=0.01,
            logging_dir="./bert_logs",
            logging_steps=50,
            eval_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            save_total_limit=1,
            metric_for_best_model="eval_loss",
            fp16=False,  # CPU 不使用混合精度
            dataloader_num_workers=0,
        )
        
        # 加载数据集
        with open(data_file, "r", encoding="utf-8") as f:
            data = [json.loads(value) for value in f.readlines()]
        
        texts = [item["query"] for item in data]
        labels = [item["label"] for item in data]
        
        # 数据划分
        from sklearn.model_selection import train_test_split
        train_texts, val_texts, train_labels, val_labels = train_test_split(
            texts, labels, test_size=0.2, random_state=42
        )
        
        # 数据预处理
        train_encodings, train_labels = classifier.preprocess_data(train_texts, train_labels)
        val_encodings, val_labels = classifier.preprocess_data(val_texts, val_labels)
        
        # 创建数据集
        train_dataset = classifier.create_dataset(train_encodings, train_labels)
        val_dataset = classifier.create_dataset(val_encodings, val_labels)
        
        print(f"\n训练集：{len(train_dataset)} 条")
        print(f"验证集：{len(val_dataset)} 条")
        
        # 初始化 Trainer
        trainer = Trainer(
            model=classifier.model, 
            args=training_args,
            train_dataset=train_dataset, 
            eval_dataset=val_dataset,
            compute_metrics=classifier.compute_metrics
        )
        
        # 开始训练
        print("\n开始训练...")
        trainer.train()
        
        # 保存模型
        print("\n保存模型...")
        classifier.save_model()
        print("\n✓ 模型已保存至 bert_query_classifier_new")
        
        # 复制文件到正式目录
        import shutil
        print("\n正在复制到 bert_query_classifier 目录...")
        if os.path.exists("bert_query_classifier"):
            for file in os.listdir("bert_query_classifier"):
                if file.endswith((".safetensors", ".bin")):
                    os.remove(os.path.join("bert_query_classifier", file))
        for file in os.listdir("bert_query_classifier_new"):
            src = os.path.join("bert_query_classifier_new", file)
            dst = os.path.join("bert_query_classifier", file)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
        print("✓ 模型文件已复制到 bert_query_classifier")
        
        # 评估
        print("\n评估模型性能...")
        classifier.evaluate_model(val_texts, val_labels)
        
        # 测试
        print("\n测试模型:")
        test_queries = [
            ("露天矿山开采工艺流程是什么？", "专业咨询"),
            ("矿井通风系统设计原则", "专业咨询"),
            ("什么是 AI?", "通用知识"),
            ("Python 怎么写代码？", "通用知识"),
        ]
        
        correct = 0
        for query, expected in test_queries:
            predicted = classifier.predict_category(query)
            is_correct = predicted == expected
            if is_correct:
                correct += 1
            status = "✓" if is_correct else "✗"
            print(f"{status} '{query}' -> {predicted}")
        
        accuracy = correct / len(test_queries) * 100
        print(f"\n测试准确率：{accuracy:.0f}%")
        
        if accuracy >= 75:
            print("\n🎉 训练成功！")
        else:
            print("\n⚠️  准确率有待提升，可尝试增加训练轮次")
        
        return True
        
    except KeyboardInterrupt:
        print("\n\n⚠️  训练被用户中断")
        return False
    except Exception as e:
        print(f"\n❌ 训练失败：{e}")
        logger.error(f"训练错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = quick_train()
    if success:
        print("\n" + "=" * 60)
        print("训练完成！")
        print("=" * 60)
