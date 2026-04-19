# -*- coding:utf-8 -*-
"""
测试会话管理功能
功能演示：
1. 创建/加载会话
2. 多轮对话（自动保存历史）
3. 查看历史记录
4. 基于历史的检索增强
5. 导出会话
"""

import sys
import os

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.conversation_manager import ConversationManager
from base import logger


def test_conversation_manager():
    """测试会话管理器基本功能"""
    
    print("=" * 80)
    print("测试会话管理器功能")
    print("=" * 80)
    
    # 初始化会话管理器
    manager = ConversationManager(storage_dir="test_conversations")
    
    # ==================== 测试 1: 创建会话 ====================
    print("\n【测试 1】创建新会话")
    session_id = manager.create_session(
        metadata={
            "user": "test_user",
            "description": "测试会话"
        }
    )
    print(f"✓ 创建会话 ID: {session_id}")
    
    # ==================== 测试 2: 添加对话记录 ====================
    print("\n【测试 2】添加多轮对话")
    
    conversations = [
        ("什么是机器学习？", "机器学习是人工智能的一个分支，它使计算机能够从数据中学习..."),
        ("监督学习有哪些常见算法？", "监督学习的常见算法包括：线性回归、逻辑回归、决策树、随机森林..."),
        ("什么是过拟合？如何避免？", "过拟合是指模型在训练集上表现很好但在测试集上表现差的现象。避免方法..."),
        ("交叉验证的作用是什么？", "交叉验证用于评估模型的泛化能力，常见的有 K 折交叉验证..."),
        ("深度学习与传统机器学习的区别？", "深度学习使用多层神经网络，能够自动学习特征，而传统机器学习..."),
    ]
    
    for question, answer in conversations:
        manager.add_message(
            question=question,
            answer=answer,
            metadata={"query_type": "AI 知识"}
        )
        print(f"✓ 添加：{question[:30]}...")
    
    # ==================== 测试 3: 获取历史记录 ====================
    print("\n【测试 3】获取历史记录")
    
    # 获取最近 5 条
    recent_history = manager.get_history(limit=5)
    print(f"\n最近 5 条历史记录:")
    for i, record in enumerate(recent_history, 1):
        print(f"{i}. Q: {record['question'][:50]}...")
        print(f"   A: {record['answer'][:50]}...")
        print()
    
    # ==================== 测试 4: 获取相关历史 ====================
    print("\n【测试 4】获取相关历史记录")
    
    current_query = "神经网络的训练方法"
    relevant_history = manager.get_relevant_history(current_query=current_query, limit=3)
    print(f"\n与'{current_query}'相关的历史记录:")
    if relevant_history:
        for i, record in enumerate(relevant_history, 1):
            print(f"{i}. Q: {record['question']}")
            print(f"   A: {record['answer'][:80]}...")
            print()
    else:
        print("未找到相关历史记录")
    
    # ==================== 测试 5: 构建历史上下文 ====================
    print("\n【测试 5】构建历史上下文")
    
    history_context = manager.get_context_from_history(limit=3)
    print("\n格式化的历史上下文:")
    print(history_context)
    
    # ==================== 测试 6: 会话统计 ====================
    print("\n【测试 6】会话统计信息")
    
    stats = manager.get_session_stats()
    print(f"\n会话统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # ==================== 测试 7: 保存和加载会话 ====================
    print("\n【测试 7】保存和加载会话")
    
    # 手动保存
    manager.save_current_session()
    print(f"✓ 会话已保存到文件")
    
    # 创建新管理器实例并加载
    new_manager = ConversationManager(storage_dir="test_conversations")
    success = new_manager.load_session(session_id)
    if success:
        print(f"✓ 成功加载会话：{session_id}")
        
        # 验证历史是否完整
        loaded_history = new_manager.get_history(limit=10)
        print(f"✓ 加载的历史记录数：{len(loaded_history)}")
    
    # ==================== 测试 8: 列出所有会话 ====================
    print("\n【测试 8】列出所有会话")
    
    all_sessions = manager.list_sessions()
    print(f"\n共有 {len(all_sessions)} 个会话:")
    for session in all_sessions:
        print(f"  - ID: {session['session_id']}")
        print(f"    创建时间：{session['created_at']}")
        print(f"    消息数：{session['message_count']}")
        print()
    
    # ==================== 测试 9: 导出会话 ====================
    print("\n【测试 9】导出会话")
    
    export_path = os.path.join(manager.storage_dir, f"export_{session_id}.txt")
    success = manager.export_session(export_path)
    if success:
        print(f"✓ 会话已导出到：{export_path}")
    
    # ==================== 测试 10: 清空历史 ====================
    print("\n【测试 10】清空历史记录")
    
    manager.clear_history()
    remaining_history = manager.get_history()
    print(f"✓ 清空后剩余历史记录数：{len(remaining_history)}")
    
    # ==================== 测试 11: 删除会话 ====================
    print("\n【测试 11】删除会话")
    
    success = manager.delete_session(session_id)
    if success:
        print(f"✓ 会话已删除：{session_id}")
    
    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)


def test_rag_with_history():
    """测试 RAG 系统集成会话管理"""
    
    print("\n" + "=" * 80)
    print("测试 RAG 系统集成的会话管理")
    print("=" * 80)
    
    try:
        import sys
        # 确保 core 目录在路径中
        core_dir = os.path.join(current_dir, 'core')
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        
        from new_rag_system import RAGSystem
        from vector_store import VectorStore
        from conversation_manager import ConversationManager
        from openai import OpenAI
        from base import Config
        
        # 初始化组件
        print("\n初始化 RAG 系统...")
        vector_store = VectorStore()
        
        # 创建 LLM 调用函数
        def call_dashscope(prompt):
            client = OpenAI(
                api_key=Config().DASHSCOPE_API_KEY,
                base_url=Config().DASHSCOPE_BASE_URL
            )
            try:
                completion = client.chat.completions.create(
                    model=Config().LLM_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个有用的助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=30,
                    stream=True
                )
                
                full_answer = ""
                for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_answer += content
                
                return full_answer
            except Exception as e:
                logger.error(f"LLM 调用失败：{e}")
                return f"错误：{e}"
        
        # 创建 RAG 系统（带会话管理）
        rag_system = RAGSystem(vector_store, call_dashscope)
        
        print("✓ RAG 系统初始化完成")
        
        # 第一轮对话
        print("\n【第 1 轮】提问：什么是机器学习？")
        answers = list(rag_system.generate_answer(
            query="什么是机器学习？",
            use_history=True
        ))
        print(f"答案：{answers[0][:100]}...")
        
        # 第二轮对话
        print("\n【第 2 轮】提问：监督学习有哪些算法？")
        answers = list(rag_system.generate_answer(
            query="监督学习有哪些算法？",
            use_history=True
        ))
        print(f"答案：{answers[0][:100]}...")
        
        # 第三轮对话
        print("\n【第 3 轮】提问：它和 unsupervised learning 有什么区别？")
        answers = list(rag_system.generate_answer(
            query="它和 unsupervised learning 有什么区别？",
            use_history=True
        ))
        print(f"答案：{answers[0][:100]}...")
        
        # 查看当前会话历史
        session_id = rag_system.conversation_manager.current_session_id
        history = rag_system.conversation_manager.get_history(limit=5)
        
        print(f"\n✓ 当前会话 ID: {session_id}")
        print(f"✓ 历史记录数：{len(history)}")
        
        for i, record in enumerate(history, 1):
            print(f"\n{i}. Q: {record['question']}")
            print(f"   A: {record['answer'][:100]}...")
        
        print("\n" + "=" * 80)
        print("RAG 集成测试完成！")
        print("=" * 80)
        
    except ImportError as e:
        print(f"\n⚠️  跳过 RAG 集成测试：缺少依赖 - {e}")
    except Exception as e:
        print(f"\n❌ RAG 集成测试失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # 运行基础测试
    test_conversation_manager()
    
    # 运行 RAG 集成测试
    test_rag_with_history()
