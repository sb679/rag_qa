# -*- coding:utf-8 -*-
"""
场景 2: 交互式问答 - 启动 RAG 问答系统

使用方法:
    python examples_02_interactive_qa.py
"""
import sys, os
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from core.vector_store import VectorStore
from core.new_rag_system import RAGSystem
from openai import OpenAI
from base import Config, logger

conf = Config()


def create_llm_client():
    """创建 LLM 客户端"""
    try:
        client = OpenAI(
            api_key=conf.DASHSCOPE_API_KEY,
            base_url=conf.DASHSCOPE_BASE_URL
        )
        print("✅ LLM 客户端初始化成功")
        return client
    except Exception as e:
        print(f"❌ LLM 客户端初始化失败：{e}")
        return None


def call_llm(prompt):
    """LLM 调用函数（流式输出）"""
    client = create_llm_client()
    if not client:
        return "错误：LLM 不可用"
    
    try:
        completion = client.chat.completions.create(
            model=conf.LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是采矿冶金领域的专家级智能助手。"},
                {"role": "user", "content": prompt}
            ],
            stream=True
        )
        
        answer = ""
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                answer += content
                # 实时打印（流式效果）
                print(content, end='', flush=True)
        
        return answer
        
    except Exception as e:
        logger.error(f"LLM 调用失败：{e}")
        return f"抱歉，处理问题时出错：{e}"


def interactive_qa():
    """交互式问答"""
    print("="*80)
    print("🤖 EduRAG 交互式问答系统")
    print("="*80)
    
    # 初始化组件
    print("\n正在初始化系统...")
    
    try:
        vector_store = VectorStore()
        print("✅ Milvus 连接成功")
    except Exception as e:
        print(f"❌ Milvus 连接失败：{e}")
        return
    
    rag_system = RAGSystem(vector_store, call_llm)
    print("✅ RAG 系统初始化完成\n")
    
    # 打印使用说明
    print("="*80)
    print("💡 使用说明:")
    print("  - 输入问题开始问答")
    print("  - 输入 'clear' 清空对话历史")
    print("  - 输入 'history' 查看当前对话历史")
    print("  - 输入 'exit' 或 'quit' 退出系统")
    print("="*80 + "\n")
    
    # 主循环
    while True:
        try:
            query = input("🔍 请输入您的问题：").strip()
            
            if not query:
                continue
            
            # 处理特殊命令
            if query.lower() in ['exit', 'quit', 'q']:
                print("\n再见！")
                break
            
            if query.lower() == 'clear':
                rag_system.conversation_manager.clear_history()
                print("✅ 对话历史已清空\n")
                continue
            
            if query.lower() == 'history':
                history = rag_system.conversation_manager.get_history(limit=5)
                if history:
                    print(f"\n📜 最近 {len(history)} 轮对话:")
                    for i, record in enumerate(history, 1):
                        print(f"\n[{i}] Q: {record['question']}")
                        print(f"    A: {record['answer'][:100]}...")
                else:
                    print("\n暂无对话历史")
                print()
                continue
            
            # 回答问题
            print("\n🤖 AI 回答:")
            print("-"*80)
            answers = list(rag_system.generate_answer(
                query=query,
                use_history=True
            ))
            print("\n" + "-"*80)
            
            # 显示统计信息
            stats = rag_system.conversation_manager.get_session_stats()
            if stats:
                print(f"📊 当前会话共 {stats.get('total_messages', 0)} 轮对话\n")
            
        except KeyboardInterrupt:
            print("\n\n程序中断，再见！")
            break
        except Exception as e:
            print(f"\n❌ 发生错误：{e}")
            logger.error(f"问答过程出错：{e}")


if __name__ == '__main__':
    interactive_qa()
