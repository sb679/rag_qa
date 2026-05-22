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
       - 当问题中包含指代（如"第一个问题"、"刚才那个"、"上面提到的"等），必须结合下方"对话历史"进行解析；如果对话历史为空或不相关，再说明"信息不足"。
         - 若提供了检索上下文，回答必须优先以检索上下文为依据，不补充上下文中没有直接支持的常识扩展。

    2. **生成回答**：
         - 直接给出答案，不要先写分析过程，不要使用生活化比喻，不要举额外例子，不要做常识延伸。
         - 回答尽量贴近上下文原意，优先复用上下文中的关键术语、关键步骤、关键条件、关键数值。
         - 若问题是步骤类、措施类、检查项类，优先使用短条目列出要点；除非问题明确要求解释，否则不要额外解释原因。
         - 禁止无意义铺垫、冗余背景介绍、总结性抒写和长篇大论。
         - 若上下文中没有直接依据，不要补充推测性内容。
         - 若上下文与对话历史均不足以回答问题，优先明确指出缺少哪些关键信息，例如场景、设备、工艺环节、事故类型、作业条件或时间范围，并请用户补充后再继续回答。
         - 只有当问题属于高风险现场操作、事故处置、制度性核验，且在缺少足够依据时不能安全作答，才回复："当前知识库依据不足，暂不能给出可靠结论，请联系人工客服，电话：{phone}。"

     3. **输出格式约束**：
         - 不要出现“根据提供的文档”“核心分析”“生活中可以理解为”等固定铺垫语。
         - 不要输出超过问题所需范围的信息。
         - 若参考信息可用 3 到 5 个短要点说清，就不要扩写成多段说明。

    **对话历史（最近若干轮，可能为空）**:
     {history}

    **检索到的上下文（可能为空）**:
     {context}

    **当前问题**:
     {question}

    **回答**:
            """,
            input_variables=["context", "question", "history", "phone"],
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