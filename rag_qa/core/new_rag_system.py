'''
todo: 和之前的rag_system不一样的地方是：生成答案时，考虑了历史对话记录，以及我们大模型输出结果时stream流式输出结果
'''
# -*-coding:utf-8-*-
# core/rag_system.py 源码
# 导入标准库
import sys, os
from typing import Optional  # 添加类型注解支持
# 导入 OpenAI 客户端，用于调用 DashScope API
from openai import OpenAI
# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# print(f'current_dir--》{current_dir}')
# 获取core文件所在的目录的绝对路径
rag_qa_path = os.path.dirname(current_dir)
# print(f'rag_qa_path--》{rag_qa_path}')
sys.path.insert(0, rag_qa_path)
# 获取根目录文件所在的绝对位置
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)
from prompts import RAGPrompts
#   导入 time 模块，用于计算时间
import time
from base import logger, Config
from query_classifier import QueryClassifier  # 导入查询分类器
from strategy_selector import StrategySelector  # 导入策略选择器
from vector_store import VectorStore  # 导入向量数据库对象
from conversation_manager import ConversationManager, get_conversation_manager  # 导入会话管理器

conf = Config()


#   定义 RAGSystem 类，封装 RAG 系统的核心逻辑
class RAGSystem:
    #   初始化方法，设置 RAG 系统的基本参数
    def __init__(self, vector_store, llm, conversation_manager: Optional[ConversationManager] = None):
        #   设置向量数据库对象
        self.vector_store = vector_store
        #   设置大语言模型调用函数
        self.llm = llm
        #   获取 RAG 提示模板
        self.rag_prompt = RAGPrompts.rag_prompt()
        #   初始化查询分类器（使用二分类模型：通用知识 vs 专业咨询）
        classifier_path = os.path.join(rag_qa_path, 'bert_query_classifier_new')
        self.query_classifier = QueryClassifier(model_path=classifier_path)
        #   初始化策略选择器
        self.strategy_selector = StrategySelector()
        #   初始化会话管理器（支持传入自定义或创建默认）
        self.conversation_manager = conversation_manager or get_conversation_manager()
        #   定义方法，生成答案

    #   定义类似私有方法，使用回溯问题进行检索 （注意讲义中没有加source_filter参数，这里补齐了）
    def _retrieve_with_backtracking(self, query, source_filter):
        logger.info(f"使用回溯问题策略进行检索 (查询: '{query}')")
        #   获取回溯问题生成的 Prompt 模板
        backtrack_prompt_template = RAGPrompts.backtracking_prompt()  # 使用 template 后缀区分
        try:
            #   调用大语言模型生成回溯问题
            simplified_query = self.llm(backtrack_prompt_template.format(query=query)).strip()
            logger.info(f"生成的回溯问题: '{simplified_query}'")
            #   使用回溯问题进行检索，并返回检索结果
            return self.vector_store.hybrid_search_with_rerank(
                simplified_query, k=conf.RETRIEVAL_K, source_filter=source_filter  # 使用 K
            )
        except Exception as e:
            logger.error(f"回溯问题策略执行失败: {e}")
            return []

    #   定义类似私有方法，使用子查询进行检索（注意讲义中没有加source_filter参数，这里补齐了）
    def _retrieve_with_subqueries(self, query, source_filter):
        logger.info(f"使用子查询策略进行检索 (查询: '{query}')")
        #   获取子查询生成的 Prompt 模板
        subquery_prompt_template = RAGPrompts.subquery_prompt()  # 使用 template 后缀区分
        try:
            #   调用大语言模型生成子查询列表
            subqueries_text = self.llm(subquery_prompt_template.format(query=query)).strip()
            # print(f'subqueries_text--》{subqueries_text}')
            subqueries = [q.strip() for q in subqueries_text.split("\n") if q.strip()]
            logger.info(f"生成的子查询: {subqueries}")
            if not subqueries:
                logger.warning("未能生成有效的子查询")
                return []
            #   初始化空列表，用于存储所有子查询的检索结果
            all_docs = []
            #   遍历每个子查询
            for sub_q in subqueries:
                #   使用子查询进行检索，并将结果添加到列表中
                #   这里对每个子查询都执行了 hybrid search + rerank，开销可能较大
                # 这里面的k是conf.CANDIDATE_M//2 onf.CANDIDATE_M是它的一半
                docs = self.vector_store.hybrid_search_with_rerank(
                    sub_q, k=conf.CANDIDATE_M // 2, source_filter=source_filter  # 使用 K
                )
                all_docs.extend(docs)
                logger.info(f"子查询 '{sub_q}' 检索到 {len(docs)} 个文档")
            # print(f'all_docs-->{len(all_docs)}')
            # print(f'all_docs[0]-->{all_docs[0]}')
            #   对所有检索结果进行去重 (基于对象内存地址，如果 Document 内容相同但对象不同则无法去重)
            #   更可靠的去重方式是基于文档内容或 ID
            unique_docs_dict = {doc.page_content: doc for doc in all_docs}  # 基于内容去重
            unique_docs = list(unique_docs_dict.values())

            logger.info(f"所有子查询共检索到 {len(all_docs)} 个文档, 去重后剩 {len(unique_docs)} 个")
            return unique_docs  # 返回所有唯一文档，让 retrieve_and_merge 处理数量
        except Exception as e:
            logger.error(f'子查询存在错误：{e}')
            return []

    #   定义私有方法，使用假设文档进行检索（HyDE）
    def _retrieve_with_hyde(self, query, source_filter):
        logger.info(f"使用 HyDE 策略进行检索 (查询: '{query}')")
        #   获取假设问题生成的 Prompt 模板
        hyde_prompt_template = RAGPrompts.hyde_prompt()  # 使用 template 后缀区分
        #   调用大语言模型生成假设答案
        try:
            hypo_answer = self.llm(hyde_prompt_template.format(query=query)).strip()
            logger.info(f"HyDE 生成的假设答案: '{hypo_answer}'")
            #   使用假设答案进行检索，并返回检索结果
            return self.vector_store.hybrid_search_with_rerank(
                hypo_answer, k=conf.RETRIEVAL_K, source_filter=source_filter  # 使用 K 而非 M
            )
        except Exception as e:
            logger.error(f"HyDE 策略执行失败: {e}")
            return []

    def retrieve_and_merge(self, query, source_filter=None, strategy=None):
        #   如果未指定检索策略，则使用策略选择器选择
        if not strategy:
            strategy = self.strategy_selector.select_strategy(query)

        # 兼容历史命名，统一到“场景重构检索”
        normalized_strategy = {
            "回溯问题检索": "场景重构检索",
        }.get(strategy, strategy)

        # 根据检索策略选择不同的检索方式
        ranked_chunks = []  # 初始化
        if normalized_strategy == "场景重构检索":
            ranked_chunks = self._retrieve_with_backtracking(query, source_filter)
        elif normalized_strategy == '子查询检索':
            ranked_chunks = self._retrieve_with_subqueries(query, source_filter)
        elif normalized_strategy == "假设问题检索":
            ranked_chunks = self._retrieve_with_hyde(query, source_filter)
        else:
            # 直接检索：
            logger.info(f"使用直接检索策略 (查询: '{query}')")
            ranked_chunks = self.vector_store.hybrid_search_with_rerank(
                query, k=conf.RETRIEVAL_K, source_filter=source_filter
            )  # 注意 hybrid_search_with_rerank 返回的是 rerank 后的父文档
            # print(f'ranked_chunks--》{ranked_chunks}')

        logger.info(f"策略 '{normalized_strategy}' 检索到 {len(ranked_chunks)} 个候选文档 (可能已是父文档)")
        final_context_docs = ranked_chunks[:conf.CANDIDATE_M]
        logger.info(f"最终选取 {len(final_context_docs)} 个文档作为上下文")
        return final_context_docs

    def generate_answer(self, query, source_filter=None, session_id: Optional[str] = None, use_history: bool = True):
        """
        生成答案（支持会话管理和历史对话增强）
            
        Args:
            query: 用户查询
            source_filter: 数据源过滤
            session_id: 可选的会话 ID，不提供则使用当前活动会话
            use_history: 是否使用历史对话增强
        """
        #   记录查询开始时间
        start_time = time.time()
        logger.info(f"开始处理查询：'{query}', 学科过滤：{source_filter}")
            
        # 加载或创建会话
        if session_id:
            # 尝试加载指定会话
            if not self.conversation_manager.load_session(session_id):
                # 如果加载失败，创建新会话
                session_id = self.conversation_manager.create_session(
                    metadata={"source_filter": source_filter}
                )
        else:
            # 使用当前活动会话，如果没有则创建
            if not self.conversation_manager.current_session_id:
                session_id = self.conversation_manager.create_session(
                    metadata={"source_filter": source_filter}
                )
            else:
                session_id = self.conversation_manager.current_session_id
            
        logger.info(f"使用会话：{session_id}")
            
        # 获取历史对话记录（最近 5 条）
        history_context = ''
        if use_history:
            # 方法 1: 获取简单的历史对话列表
            recent_history = self.conversation_manager.get_history(limit=5)
                
            # 方法 2: 获取相关的历史对话（基于关键词匹配）
            relevant_history = self.conversation_manager.get_relevant_history(
                current_query=query, 
                limit=5
            )
                
            # 构建历史上下文
            if recent_history:
                history_lines = []
                for i, record in enumerate(recent_history, 1):
                    history_lines.append(f"第{i}轮对话:")
                    history_lines.append(f"  问：{record['question']}")
                    history_lines.append(f"  答：{record['answer']}")
                history_context = "\n".join(history_lines)
                logger.info(f'使用最近 {len(recent_history)} 轮对话历史')
                
            # 如果有相关历史，也加入考虑
            if relevant_history and relevant_history != recent_history:
                logger.info(f'额外参考 {len(relevant_history)} 条相关历史记录')
            
        # 验证历史（兼容旧的 history 参数方式）
        # 注：现在优先使用 conversation_manager 的历史记录

        #   判断查询类型
        query_category = self.query_classifier.predict_category(query)
        logger.info(f"查询分类结果：{query_category} (查询：'{query}')")
                
        #   如果查询属于"通用知识"类别，则直接使用 LLM 回答
        if query_category == "通用知识":
            logger.info("查询为通用知识，直接调用 LLM")
            context = ''
            answer = ""
            try:
                # 使用大模型获得输出结果（包含历史上下文）
                prompt_with_history = self.rag_prompt.format(
                    context=context,
                    question=query,
                    history=history_context,
                    phone=conf.CUSTOMER_SERVICE_PHONE
                )
                for token in self.llm(prompt_with_history):
                    answer += token
            except Exception as e:
                logger.error(f'调用 LLM 失败:{e}')
                answer = f'抱歉，处理问题时出错，请你联系人工客服：{conf.CUSTOMER_SERVICE_PHONE}'
        else:
            logger.info("查询为专业咨询，执行 RAG 流程")
            #   选择检索策略
            strategy = self.strategy_selector.select_strategy(query)
                    
            # 增强检索：考虑历史对话
            if use_history and history_context:
                logger.info("使用历史对话增强检索")
                # 可以将历史上下文加入到查询中，或者调整检索策略
                # 这里我们保持原有逻辑，但在 Prompt 中包含历史
                    
            context_docs = self.retrieve_and_merge(query, source_filter=source_filter, strategy=strategy)
            if context_docs:
                context = "\n\n".join([doc.page_content for doc in context_docs])  # 使用换行符分隔文档
                logger.info(f"构建上下文完成，包含 {len(context_docs)} 个文档块")
                # logger.debug(f"上下文内容:\n{context[:500]}...") # Debug 日志可以打印部分上下文
            else:
                context = ""
                logger.info("未检索到相关文档，上下文为空")
                    
            answer = ""
            prompt_input = self.rag_prompt.format(context=context,
                                                  question=query,
                                                  history=history_context,
                                                  phone=conf.CUSTOMER_SERVICE_PHONE)
            try:
                # 使用大模型获得输出结果：
                for token in self.llm(prompt_input):
                    answer += token
                process_time = time.time() - start_time
                logger.info(f'LLM 查询处理完成（耗时：{process_time:.2f}s, 查询：{query})')
            except Exception as e:
                logger.error(f'调用 LLM 失败:{e}')
                answer = f'抱歉，处理问题时出错，请你联系人工客服：{conf.CUSTOMER_SERVICE_PHONE}'
                
        # 保存对话记录到会话历史
        if use_history:
            self.conversation_manager.add_message(
                question=query,
                answer=answer,
                metadata={
                    "query_category": query_category,
                    "strategy": strategy if query_category != "通用知识" else None,
                    "source_filter": source_filter,
                    "processing_time": time.time() - start_time
                }
            )
            # 保存会话到文件
            self.conversation_manager.save_current_session()
                
        # 流式返回答案
        yield answer


if __name__ == '__main__':
    vector_store = VectorStore()
    def call_dashscope(prompt):
        client = OpenAI(api_key= Config().DASHSCOPE_API_KEY,
                        base_url=Config().DASHSCOPE_BASE_URL)
        """调用DashScope API生成答案（流式输出）"""
        try:
            # 创建聊天完成请求，启用流式输出
            completion = client.chat.completions.create(
                model= Config().LLM_MODEL,  # 使用配置中的语言模型
                messages=[
                    {"role": "system", "content": "你是一个有用的助手。"},  # 系统提示
                    {"role": "user", "content": prompt},  # 用户输入的提示
                ],
                timeout=30,  # 设置 30 秒超时
                stream=True  # 启用流式输出
            )
            # 遍历流式输出的每个 chunk
            for chunk in completion:
                # print(f'chunk--》{chunk}')
                # print("*"*80)
                if chunk.choices and chunk.choices[0].delta.content:
                    #         # 获取当前 chunk 的内容
                    content = chunk.choices[0].delta.content
                    yield content
        except Exception as e:
            # 记录 API 调用失败的错误日志
            logger.error(f"LLM调用失败: {e}")
            # 返回错误信息
            return f"错误：LLM调用失败 - {e}"
    # print(llm(prompt="什么是AI"))
    rag_system = RAGSystem(vector_store, call_dashscope)
    answer = rag_system.generate_answer(query="AI学科的课程大纲内容有什么", source_filter="ai")
    for vlaue in answer:
        print(vlaue)
    # rag_system._retrieve_with_subqueries(query="AI和JAVA的区别是什么？", source_filter="ai")
    # result = rag_system._retrieve_with_hyde(query="AI课程的NLP的技术有哪些?",source_filter="ai")
    # print(result)
    # print(len(result))
