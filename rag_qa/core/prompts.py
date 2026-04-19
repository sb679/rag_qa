# core/prompts.py
# 导入 PromptTemplate 类，用于创建 Prompt 模板
from langchain.prompts import PromptTemplate


# 定义 RAGPrompts 类，用于管理所有 Prompt 模板
class RAGPrompts:
    # 定义 RAG 提示模板
    # @staticmethod
    # def rag_prompt():
    #     # 创建并返回 PromptTemplate 对象
    #     return PromptTemplate(
    #         template="""
    #         你是一个智能助手，帮助用户回答问题。
    #         如果提供了上下文，请基于上下文回答；如果没有上下文，请直接根据你的知识回答。
    #         如果答案来源于检索到的文档，请在回答中说明。
    #
    #         上下文: {context}
    #         问题: {question}
    #
    #         如果无法回答，请回复：“信息不足，无法回答，请联系人工客服，电话：{phone}。”
    #         回答:
    #         """,
    #         #   定义输入变量
    #         input_variables=["context", "question", "phone"],
    #     )
    #
    #     # 定义假设问题生成的 Prompt 模板
    @staticmethod
    def rag_prompt():
        '''采矿冶金领域专家级智能助手 RAG 系统提示词模板'''
        return PromptTemplate(
            template="""
    你是深耕采矿冶金领域各个角度的专家级智能助手，需按以下规则处理用户问题：

    1. **分析问题和上下文**：
       - 聚焦采矿冶金问题核心，结合提供的上下文（如有）和领域知识回答，不偏离核心、不答非所问。
       - 若答案来源于检索到的文档，需明确说明：“根据提供的文档，……”。

    2. **生成回答**：
       - 先分析问题核心，再给出简洁精炼的回答；解释概念优先使用生动形象的生活化比喻，避免堆砌专业术语。
       - 禁止无意义铺垫、冗余背景介绍和长篇大论，拒绝复杂难懂的解释或方案。
       - 若上下文不足以回答问题，请回复：“信息不足，无法回答，请联系人工客服，电话：{phone}。”

    **上下文**:
     {context}
    **问题**:
     {question}

    **回答**:
            """,
            input_variables=["context", "question", "phone"],
        )

    @staticmethod
    def hyde_prompt():
        #   创建并返回 PromptTemplate 对象
        return PromptTemplate(
            template="""  
               假设你是用户，想了解以下问题，请生成一个简短的假设答案：  
               问题: {query}  
               假设答案:  
               """,
            #   定义输入变量
            input_variables=["query"],
        )

    #   定义子查询生成的 Prompt 模板
    @staticmethod
    def subquery_prompt():
        #   创建并返回 PromptTemplate 对象
        return PromptTemplate(
            template="""  
               将以下复杂查询分解为多个简单子查询，每行一个子查询，最多生成两个子查询（只保留子查询问题，其他的文本都不需要）：
               eg: 
               用户原始query："Milvus 和 Zilliz Cloud 在功能上有什么不同？
               子查询："Milvus 有哪些功能？"，"Zilliz Cloud 有哪些功能？"
               
               查询: {query}  
               子查询:  
               """,
            #   定义输入变量
            input_variables=["query"],
        )

    #   定义场景重构问题生成的 Prompt 模板（兼容旧的 backtracking 命名）
    @staticmethod
    def scene_reconstruction_prompt():
        #   创建并返回 PromptTemplate 对象
        return PromptTemplate(
            template="""  
               将以下复杂查询简化为一个更简单的问题：  
               查询: {query}  
               简化问题:  
               """,
            #   定义输入变量
            input_variables=["query"],
        )

    @staticmethod
    def backtracking_prompt():
        # 历史兼容：旧代码仍可调用 backtracking_prompt
        return RAGPrompts.scene_reconstruction_prompt()
if __name__ == '__main__':
    # rga_prompt = RAGPrompts.rag_prompt()
    # result = rga_prompt.format(context="黑马程序员", question="这个机构叫什么名称", phone="12345")
    # print(f'result-->{result}')
    hyde = RAGPrompts.subquery_prompt()
    result = hyde.format(query="AI和JAVA有什么区别")
    print(result)