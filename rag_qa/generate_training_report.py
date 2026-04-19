"""
检索策略分类器训练报告生成器
自动生成包含评价指标的完整报告
"""

import json
import os
from datetime import datetime
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score
import matplotlib.pyplot as plt
import seaborn as sns


class TrainingReportGenerator:
    def __init__(self):
        self.report_data = {}
        self.label_map = {
            "直接检索": 0,
            "假设问题检索": 1,
            "子查询检索": 2,
            "场景重构检索": 3
        }
        self.id_to_label = {v: k for k, v in self.label_map.items()}
    
    def load_training_results(self, results_dir="./bert_strategy_results"):
        """加载训练结果"""
        print("正在加载训练结果...")
        
        # 查找最新的检查点
        checkpoints = []
        if os.path.exists(results_dir):
            for item in os.listdir(results_dir):
                if item.startswith("checkpoint-"):
                    checkpoints.append(item)
        
        if not checkpoints:
            print("❌ 未找到训练检查点")
            return False
        
        # 选择最终模型
        final_checkpoint = sorted(checkpoints)[-1]
        print(f"✓ 使用检查点：{final_checkpoint}")
        
        # 加载 trainer_state.json
        state_file = os.path.join(results_dir, final_checkpoint, "trainer_state.json")
        if not os.path.exists(state_file):
            state_file = os.path.join(results_dir, "trainer_state.json")
        
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                self.trainer_state = json.load(f)
            print(f"✓ 已加载训练状态")
        else:
            print("⚠️  未找到 trainer_state.json")
            self.trainer_state = None
        
        return True
    
    def load_test_predictions(self, test_labels_path="./test_labels.json", 
                             pred_labels_path="./pred_labels.json"):
        """加载测试集预测结果"""
        try:
            # 加载真实标签
            if os.path.exists(test_labels_path):
                with open(test_labels_path, 'r', encoding='utf-8') as f:
                    self.test_labels = json.load(f)
                print(f"✓ 已加载测试标签：{len(self.test_labels)} 条")
            
            # 加载预测标签
            if os.path.exists(pred_labels_path):
                with open(pred_labels_path, 'r', encoding='utf-8') as f:
                    self.pred_labels = json.load(f)
                print(f"✓ 已加载预测标签：{len(self.pred_labels)} 条")
                
                return True
        except Exception as e:
            print(f"⚠️  加载失败：{e}")
        
        return False
    
    def compute_metrics(self):
        """计算各项评价指标"""
        if not hasattr(self, 'test_labels') or not hasattr(self, 'pred_labels'):
            print("❌ 无法计算指标：缺少预测结果")
            return
        
        print("\n正在计算评价指标...")
        
        # 整体准确率
        self.accuracy = accuracy_score(self.test_labels, self.pred_labels)
        
        # 宏平均和加权平均 F1
        self.f1_macro = f1_score(self.test_labels, self.pred_labels, average='macro')
        self.f1_weighted = f1_score(self.test_labels, self.pred_labels, average='weighted')
        
        # 详细分类报告
        self.class_report = classification_report(
            self.test_labels, 
            self.pred_labels,
            target_names=list(self.label_map.keys()),
            output_dict=True,
            digits=4
        )
        
        # 混淆矩阵
        self.conf_matrix = confusion_matrix(self.test_labels, self.pred_labels)
        
        print(f"✓ 计算完成")
        print(f"  - 准确率：{self.accuracy:.4f}")
        print(f"  - F1 Macro: {self.f1_macro:.4f}")
        print(f"  - F1 Weighted: {self.f1_weighted:.4f}")
    
    def generate_text_report(self, output_file="训练评估报告.txt"):
        """生成文本格式的详细报告"""
        print("\n正在生成文本报告...")
        
        report_lines = []
        report_lines.append("="*80)
        report_lines.append("检索策略分类器训练评估报告")
        report_lines.append("="*80)
        report_lines.append(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"模型架构：BERT-base-chinese + 4 分类头\n")
        
        # 一、训练配置
        report_lines.append("="*80)
        report_lines.append("一、训练配置")
        report_lines.append("="*80)
        report_lines.append("数据集：classify_data/strategy_classification_8000.json")
        report_lines.append("训练集样本数：6320 条")
        report_lines.append("验证集样本数：790 条")
        report_lines.append("测试集样本数：790 条")
        report_lines.append("\n超参数配置:")
        report_lines.append("  - 最大序列长度：128")
        report_lines.append("  - 训练轮次：5")
        report_lines.append("  - 批次大小：8 (CPU)")
        report_lines.append("  - 学习率：2e-05")
        report_lines.append("  - 优化器：AdamW")
        report_lines.append("  - 权重衰减：0.01")
        
        # 二、整体性能
        report_lines.append("\n" + "="*80)
        report_lines.append("二、整体性能指标")
        report_lines.append("="*80)
        report_lines.append(f"\n✓ 准确率 (Accuracy): {self.accuracy:.4f} ({self.accuracy*100:.2f}%)")
        report_lines.append(f"✓ 宏平均 F1 (Macro F1): {self.f1_macro:.4f}")
        report_lines.append(f"✓ 加权 F1 (Weighted F1): {self.f1_weighted:.4f}")
        
        # 性能评级
        if self.f1_macro >= 0.85:
            rating = "优秀 ⭐⭐⭐⭐⭐"
        elif self.f1_macro >= 0.80:
            rating = "良好 ⭐⭐⭐⭐"
        elif self.f1_macro >= 0.75:
            rating = "合格 ⭐⭐⭐"
        else:
            rating = "需改进 ⭐⭐"
        
        report_lines.append(f"\n综合评级：{rating}")
        
        # 三、各类别详细指标
        report_lines.append("\n" + "="*80)
        report_lines.append("三、各类别详细指标")
        report_lines.append("="*80)
        
        headers = ["策略类别", "Precision", "Recall", "F1-Score", "样本数"]
        report_lines.append(f"\n{headers[0]:<15} {headers[1]:>12} {headers[2]:>12} {headers[3]:>12} {headers[4]:>10}")
        report_lines.append("-"*65)
        
        for label in self.label_map.keys():
            if label in self.class_report:
                metrics = self.class_report[label]
                support = metrics.get('support', 0)
                report_lines.append(
                    f"{label:<15} {metrics['precision']:>12.4f} {metrics['recall']:>12.4f} "
                    f"{metrics['f1-score']:>12.4f} {support:>10}"
                )
        
        # 添加平均行
        report_lines.append("-"*65)
        report_lines.append(
            f"{'宏平均':<15} {self.class_report['macro avg']['precision']:>12.4f} "
            f"{self.class_report['macro avg']['recall']:>12.4f} "
            f"{self.class_report['macro avg']['f1-score']:>12.4f} {len(self.test_labels):>10}"
        )
        
        # 四、混淆矩阵
        report_lines.append("\n" + "="*80)
        report_lines.append("四、混淆矩阵")
        report_lines.append("="*80)
        report_lines.append("\n预测值 →")
        report_lines.append("真实值 ↓\t" + "\t".join(list(self.label_map.keys())))
        
        for i, label in enumerate(self.label_map.keys()):
            row = self.conf_matrix[i]
            report_lines.append(f"{label}\t" + "\t".join(map(str, row)))
        
        # 五、关键发现
        report_lines.append("\n" + "="*80)
        report_lines.append("五、关键发现与分析")
        report_lines.append("="*80)
        
        # 找出表现最好和最差的类别
        f1_scores = {label: self.class_report[label]['f1-score'] 
                    for label in self.label_map.keys() if label in self.class_report}
        
        best_label = max(f1_scores, key=f1_scores.get)
        worst_label = min(f1_scores, key=f1_scores.get)
        
        report_lines.append(f"\n1. 表现最好的类别：{best_label} (F1={f1_scores[best_label]:.4f})")
        report_lines.append(f"   可能原因：样本数量充足，特征明显")
        
        report_lines.append(f"\n2. 表现最弱的类别：{worst_label} (F1={f1_scores[worst_label]:.4f})")
        report_lines.append(f"   改进建议：增加训练样本，数据增强")
        
        # 分析错误类型
        report_lines.append(f"\n3. 常见错误分析:")
        
        # 找出混淆最严重的类别对
        conf_matrix_norm = self.conf_matrix.astype('float') / self.conf_matrix.sum(axis=1)[:, np.newaxis]
        np.fill_diagonal(conf_matrix_norm, 0)  # 忽略对角线
        
        max_confusion = np.unravel_index(np.argmax(conf_matrix_norm), conf_matrix_norm.shape)
        true_label = list(self.label_map.keys())[max_confusion[0]]
        pred_label = list(self.label_map.keys())[max_confusion[1]]
        confusion_rate = conf_matrix_norm[max_confusion]
        
        report_lines.append(
            f"   - 最易混淆：{true_label} → 被误判为 {pred_label} (比率：{confusion_rate:.2%})"
        )
        
        # 六、改进建议
        report_lines.append("\n" + "="*80)
        report_lines.append("六、改进建议")
        report_lines.append("="*80)
        
        report_lines.append("\n针对弱类的优化策略:")
        report_lines.append(f"  1. 增加 {worst_label} 的训练样本")
        report_lines.append(f"  2. 针对性数据增强")
        report_lines.append(f"  3. 调整类别权重")
        report_lines.append(f"  4. 集成多个模型")
        
        report_lines.append("\n下一步工作:")
        report_lines.append("  1. 部署到生产环境测试")
        report_lines.append("  2. 收集真实用户反馈")
        report_lines.append("  3. 持续迭代优化")
        
        # 七、结论
        report_lines.append("\n" + "="*80)
        report_lines.append("七、结论")
        report_lines.append("="*80)
        
        report_lines.append(f"\n✅ 模型训练成功完成！")
        report_lines.append(f"✅ 整体准确率达到 {self.accuracy:.2%}")
        report_lines.append(f"✅ 宏平均 F1 达到 {self.f1_macro:.4f}")
        
        if self.f1_macro >= 0.80:
            report_lines.append(f"✅ 达到预期目标，可以投入使用！")
        else:
            report_lines.append(f"⚠️  基本满足要求，建议继续优化")
        
        report_lines.append("\n" + "="*80)
        report_lines.append("报告结束")
        report_lines.append("="*80)
        
        # 保存报告
        report_text = "\n".join(report_lines)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(f"✓ 文本报告已保存至：{output_file}")
        
        return report_text
    
    def generate_charts(self, output_prefix="训练报告_"):
        """生成可视化图表"""
        print("\n正在生成可视化图表...")
        
        if not hasattr(self, 'conf_matrix'):
            print("⚠️  跳过图表生成：缺少混淆矩阵")
            return
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 图 1: 混淆矩阵热图
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            self.conf_matrix,
            annot=True,
            fmt='d',
            cmap='Blues',
            xticklabels=list(self.label_map.keys()),
            yticklabels=list(self.label_map.keys())
        )
        plt.title('混淆矩阵', fontsize=14)
        plt.xlabel('预测标签', fontsize=12)
        plt.ylabel('真实标签', fontsize=12)
        plt.tight_layout()
        plt.savefig(f'{output_prefix}混淆矩阵.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ 已保存：混淆矩阵.png")
        
        # 图 2: F1 分数对比
        plt.figure(figsize=(10, 6))
        labels = list(self.label_map.keys())
        f1_scores = [self.class_report[label]['f1-score'] 
                    for label in labels if label in self.class_report]
        
        colors = ['#2ecc71' if f1 >= 0.80 else '#f39c12' if f1 >= 0.75 else '#e74c3c' 
                 for f1 in f1_scores]
        
        bars = plt.bar(labels, f1_scores, color=colors)
        plt.axhline(y=0.80, color='red', linestyle='--', label='目标线 (0.80)')
        plt.ylim(0, 1.0)
        plt.title('各类别 F1 分数对比', fontsize=14)
        plt.xlabel('策略类别', fontsize=12)
        plt.ylabel('F1 分数', fontsize=12)
        plt.xticks(rotation=15)
        plt.legend()
        
        # 在柱子上标注数值
        for bar, f1 in zip(bars, f1_scores):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{f1:.3f}', ha='center', va='bottom', fontsize=10)
        
        plt.tight_layout()
        plt.savefig(f'{output_prefix}F1 分数对比.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ 已保存：F1 分数对比.png")
        
        # 图 3: Precision-Recall 对比
        plt.figure(figsize=(10, 6))
        x = np.arange(len(labels))
        width = 0.35
        
        precisions = [self.class_report[label]['precision'] 
                     for label in labels if label in self.class_report]
        recalls = [self.class_report[label]['recall'] 
                  for label in labels if label in self.class_report]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        rects1 = ax.bar(x - width/2, precisions, width, label='Precision', color='#3498db')
        rects2 = ax.bar(x + width/2, recalls, width, label='Recall', color='#e74c3c')
        
        ax.set_ylabel('分数', fontsize=12)
        ax.set_title('Precision & Recall 对比', fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=15)
        ax.legend()
        ax.set_ylim(0, 1.0)
        
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'{output_prefix}PR 对比.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ 已保存：PR 对比.png")
    
    def generate_full_report(self):
        """生成完整报告"""
        print("="*80)
        print("开始生成训练评估报告")
        print("="*80)
        
        # 加载结果
        if not self.load_training_results():
            return
        
        # 尝试加载预测（如果有）
        self.load_test_predictions()
        
        # 计算指标
        self.compute_metrics()
        
        # 生成文本报告
        report_text = self.generate_text_report()
        
        # 生成图表
        try:
            self.generate_charts()
        except Exception as e:
            print(f"⚠️  图表生成失败：{e}")
        
        print("\n" + "="*80)
        print("✅ 报告生成完成！")
        print("="*80)
        print("\n生成的文件:")
        print("  📄 训练评估报告.txt")
        print("  📊 混淆矩阵.png")
        print("  📊 F1 分数对比.png")
        print("  📊 PR 对比.png")


if __name__ == "__main__":
    generator = TrainingReportGenerator()
    generator.generate_full_report()
