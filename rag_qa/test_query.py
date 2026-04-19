# -*-coding:utf-8-*-
"""测试 RAG 系统查询功能"""
import os
import sys

rag_qa_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, rag_qa_path)
core_path = os.path.join(rag_qa_path, 'core')
sys.path.insert(0, core_path)

from base import Config, logger
from core.new_rag_system import RAGSystem
from core.vector_store import VectorStore
from openai import OpenAI

conf = Config()

def test_query(question):
    """测试单个查询"""
    print(f"\n{'='*60}")
    print(f"测试问题：{question}")
    print(f"{'='*60}\n")
    
    # 初始化 LLM 客户端
    client = OpenAI(api_key=conf.DASHSCOPE_API_KEY,
                    base_url=conf.DASHSCOPE_BASE_URL)
    
    def call_dashscope(prompt):
        try:
            completion = client.chat.completions.create(
                model=conf.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个有用的助手."},
                    {"role": "user", "content": prompt},
                ]
            )
            if completion.choices and completion.choices[0].message:
                return completion.choices[0].message.content
            else:
                logger.error("LLM API 调用返回无效响应或空消息")
                return "错误：LLM 返回无效响应"
        except Exception as e:
            logger.error(f"LLM API (call_dashscope) 调用失败：{e}")
            return f"错误：调用 LLM 失败 - {e}"
    
    # 初始化 VectorStore
    vector_store = VectorStore(
        collection_name=conf.MILVUS_COLLECTION_NAME,
        host=conf.MILVUS_HOST,
        port=conf.MILVUS_PORT,
        database=conf.MILVUS_DATABASE_NAME,
    )
    
    # 初始化 RAGSystem
    rag_system = RAGSystem(vector_store, call_dashscope)
    
    # 执行查询
    try:
        answer = rag_system.generate_answer(question)
        print(f"\n答案：{answer}\n")
        return answer
    except Exception as e:
        print(f"\n查询失败：{str(e)}\n")
        logger.error(f"处理查询 '{question}' 时失败：{str(e)}")
        return None

if __name__ == '__main__':
    # 测试几个关于采矿的问题
    questions = [
        "什么是露天采矿？",
        "地下采矿的方法有哪些？",
        "采矿工程的基本流程是什么？",
    ]
    
    for question in questions:
        try:
            test_query(question)
        except Exception as e:
            print(f"\n测试问题 '{question}' 时发生异常：{e}\n")
        
        print("\n" + "="*60 + "\n")
