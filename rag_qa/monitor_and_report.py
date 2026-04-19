"""
后台监控训练进度并在完成后自动生成报告
"""

import os
import time
import json
from datetime import datetime

def monitor_training():
    """监控训练进度"""
    print("="*80)
    print("🔍 开始监控训练进度")
    print("="*80)
    
    results_dir = "./bert_strategy_results"
    
    while True:
        # 检查 trainer_state.json 是否存在
        state_file = os.path.join(results_dir, "trainer_state.json")
        
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                # 提取关键信息
                log_history = state.get('log_history', [])
                
                if log_history:
                    last_log = log_history[-1]
                    
                    if 'loss' in last_log:
                        current_loss = last_log['loss']
                        epoch = last_log.get('epoch', 0)
                        step = last_log.get('step', 0)
                        
                        print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] "
                              f"训练进度：Epoch {epoch:.2f}, Step {step}, Loss {current_loss:.4f}")
                    
                    # 检查是否完成
                    if state.get('is_world_process_zero', False):
                        print("\n✅ 检测到训练完成状态！")
                        break
                
            except Exception as e:
                print(f"⚠️  读取状态失败：{e}")
        
        # 检查是否有 checkpoint 生成
        checkpoints = []
        if os.path.exists(results_dir):
            for item in os.listdir(results_dir):
                if item.startswith("checkpoint-"):
                    checkpoints.append(item)
            
            if checkpoints:
                latest_checkpoint = sorted(checkpoints)[-1]
                print(f"💾 最新检查点：{latest_checkpoint}")
        
        # 等待 30 秒后再次检查
        time.sleep(30)


def auto_generate_report():
    """训练完成后自动生成报告"""
    print("\n" + "="*80)
    print("📊 开始生成评估报告")
    print("="*80)
    
    # 运行报告生成脚本
    os.system("python generate_training_report.py")
    
    print("\n" + "="*80)
    print("🎉 全部完成！")
    print("="*80)


if __name__ == "__main__":
    try:
        # 监控训练
        monitor_training()
        
        # 生成报告
        auto_generate_report()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断监控")
    except Exception as e:
        print(f"\n❌ 发生错误：{e}")
