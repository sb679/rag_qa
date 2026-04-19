# -*-coding:utf-8-*-
# core/strategy_selector.py 源码
import sys, os
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
# 导入 LangChain 提示模板
from langchain.prompts import PromptTemplate
# 导入日志和配置
from base import logger, Config
# 导入 PyTorch 和 Transformers（用于本地分类器）
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import json


class StrategySelector:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(rag_qa_path, "bert_strategy_classifier")
        # 初始化本地 BERT 分类器（优先）
        self.model_path = model_path
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 标签映射（与训练时一致）
        self.label_map = {
            "直接检索": 0,
            "假设问题检索": 1,
            "子查询检索": 2,
            "场景重构检索": 3
        }
        self.id_to_label = {v: k for k, v in self.label_map.items()}
        
        # 加载本地模型
        self.load_local_model()
        
        # 备用：如果本地模型加载失败，使用 LLM API
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=Config().DASHSCOPE_API_KEY,
                                 base_url=Config().DASHSCOPE_BASE_URL)
            self.strategy_prompt_template = self._get_strategy_prompt()
        except Exception:
            self.client = None

    def _rule_based_strategy(self, query: str):
        """基于显式语义信号做快速策略兜底。"""
        text = (query or "").strip()
        if not text:
            return None

        # 现场叙事/应急处置类问题 -> 场景重构检索
        scenario_signals = [
            "我现在", "现场", "怎么办", "怎么处理", "该怎么做", "如何处置", "事故", "异常", "应急", "突发", "超限", "险情"
        ]
        if any(k in text for k in scenario_signals):
            return "场景重构检索"

        # 复合、多约束、对比类问题 -> 子查询检索
        subquery_signals = [
            "比较", "区别", "对比", "优缺点", "分别", "同时", "并且", "以及", "各自", "一方面", "另一方面"
        ]
        if any(k in text for k in subquery_signals):
            return "子查询检索"

        return None
    
    def load_local_model(self):
        """加载本地 BERT 分类器模型"""
        try:
            # 检查模型路径是否存在
            if os.path.exists(self.model_path):
                # 加载分词器
                bert_path = os.path.join(rag_qa_path, 'models', 'bert-base-chinese')
                self.tokenizer = BertTokenizer.from_pretrained(bert_path)
                
                # 加载模型
                self.model = BertForSequenceClassification.from_pretrained(self.model_path, num_labels=4)
                self.model.to(self.device)
                self.model.eval()  # 设置为评估模式
                
                # 加载标签映射（如果有）
                label_map_file = os.path.join(self.model_path, 'label_map.json')
                if os.path.exists(label_map_file):
                    with open(label_map_file, 'r', encoding='utf-8') as f:
                        self.label_map = json.load(f)
                    self.id_to_label = {v: k for k, v in self.label_map.items()}
                
                logger.info(f"✓ 加载本地策略分类器：{self.model_path} (设备：{self.device})")
            else:
                logger.warning(f"本地模型不存在：{self.model_path}，将使用 LLM API 作为备选")
        except Exception as e:
            logger.error(f"加载本地模型失败：{e}，将使用 LLM API 作为备选")
            self.model = None
    
    def select_strategy_local(self, query):
        """使用本地 BERT 分类器选择检索策略（快速、离线）"""
        if self.model is None or self.tokenizer is None:
            return None  # 本地模型不可用，回退到 LLM
        
        try:
            # 分词
            encoding = self.tokenizer(
                query,
                truncation=True,
                padding=True,
                max_length=128,
                return_tensors="pt"
            )
            encoding = {k: v.to(self.device) for k, v in encoding.items()}
            
            # 预测
            with torch.no_grad():
                outputs = self.model(**encoding)
                prediction = torch.argmax(outputs.logits, dim=1).item()
            
            # 返回策略名称
            strategy = self.id_to_label.get(prediction, "直接检索")
            logger.debug(f"[本地分类器] 查询 '{query}' → 策略 '{strategy}'")
            return strategy
            
        except Exception as e:
            logger.error(f"本地分类器预测失败：{e}")
            return None
    
    def select_strategy_llm(self, query):
        """使用 LLM API 选择检索策略（备用方案）"""
        if self.client is None:
            return "直接检索"  # 默认策略
        
        # 调用 DashScope API
        try:
            completion = self.client.chat.completions.create(
                model=Config().LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个有用的助手。"},
                    {"role": "user", "content": self.strategy_prompt_template.format(query=query)},
                ],
                temperature=0.1
            )
            strategy = completion.choices[0].message.content.strip() if completion.choices else "直接检索"
            logger.info(f"[LLM API] 为查询 '{query}' 选择的检索策略：{strategy}")
            return strategy
        except Exception as e:
            logger.error(f"DashScope API 调用失败：{e}")
            return "直接检索"
    
    def _get_strategy_prompt(self):
        #   定义类似私有方法，获取策略选择 Prompt 模板
        return PromptTemplate(
            template="""
            你是一个智能助手，负责分析用户查询 {query}，并从以下四种检索增强策略中选择一个最适合的策略，直接返回策略名称，不需要解释过程。
            
            以下是几种检索增强策略及其适用场景：
            
            1.  **直接检索：**
                * 描述：对用户查询直接进行检索，不进行任何增强处理。
                * 适用场景：适用于查询意图明确，需要从采矿知识库中检索**特定信息**的问题，例如：
                    * 示例：
                        * 查询：露天矿山的开采工艺流程是什么？
                        * 策略：直接检索
                    * 查询：矿井通风系统的设计原则有哪些？
                        * 策略：直接检索
            2.  **假设问题检索（HyDE）：**
                * 描述：使用 LLM 生成一个假设的答案，然后基于假设答案进行检索。
                * 适用场景：适用于查询较为抽象，直接检索效果不佳的问题，例如：
                    * 示例：
                        * 查询：采矿工程对环境的影响有哪些？
                        * 策略：假设问题检索
            3.  **子查询检索：**
                * 描述：将复杂的用户查询拆分为多个简单的子查询，分别检索并合并结果。
                * 适用场景：适用于查询涉及多个方面，需要分别检索不同信息的问题，例如：
                    * 示例：
                        * 查询：比较露天开采和地下开采的优缺点。
                        * 策略：子查询检索
            4.  **场景重构检索：**
                * 描述：将复杂的用户查询转化为更基础、更易于检索的问题，然后进行检索。
                * 适用场景：适用于查询较为复杂，需要简化后才能有效检索的问题，例如：
                    * 示例：
                        * 查询：我有一个深部高应力矿床，应该采用什么开采方法和支护技术？
                        * 策略：场景重构检索
            
            根据用户查询 {query}，直接返回最适合的策略名称，例如 "直接检索"。不要输出任何分析过程或其他内容。
            """
            ,
            input_variables=["query"],
        )
    #   定义方法，选择检索策略（优先使用本地分类器）
    def select_strategy(self, query):
        # 先走规则兜底，确保明显场景命中合理策略
        rule_strategy = self._rule_based_strategy(query)
        if rule_strategy is not None:
            logger.info(f"[规则兜底] 查询 '{query}' -> 策略 '{rule_strategy}'")
            return rule_strategy

        # 优先使用本地 BERT 分类器（快速、离线）
        strategy = self.select_strategy_local(query)
        
        # 如果本地模型不可用，回退到 LLM API
        if strategy is None:
            logger.warning("本地分类器不可用，回退到 LLM API")
            strategy = self.select_strategy_llm(query)
        
        logger.info(f"为查询 '{query}' 选择的检索策略：{strategy}")
        return strategy

if __name__ == '__main__':
    ss = StrategySelector()
    # print(f'ss.clinet--->{ss.client}')
    # result = ss.call_dashscope(prompt="你是谁")
    # print(f'result--》{result}')
    ss.select_strategy(query="Mysql数据库能不能支持100w个样本的插入")