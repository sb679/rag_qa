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
        
        # 标签映射（与训练时一致；以模型目录中的 label_map.json 为准，会覆盖此处）
        # 训练侧实际四类策略：直接检索 / 查询扩展检索 / 查询分解检索 / 问题重写检索
        self.label_map = {
            "直接检索":     0,
            "查询扩展检索": 1,
            "查询分解检索": 2,
            "问题重写检索": 3,
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
        """基于显式语义信号做快速策略兜底。命中规则时绕过 BERT 直接返回训练侧标签。"""
        text = (query or "").strip()
        if not text:
            return None

        # 现场工况/异常处置/方案设计类 -> 问题重写检索
        rewrite_signals = [
            "我现在", "现场", "怎么办", "怎么处理", "该怎么做", "如何处置",
            "事故", "异常", "应急", "突发", "超限", "险情", "故障", "优化"
        ]
        if any(k in text for k in rewrite_signals):
            return "问题重写检索"

        # 多要素/对比/复合类问题 -> 查询分解检索
        decomposition_signals = [
            "比较", "区别", "对比", "优缺点", "分别", "同时", "并且", "以及",
            "各自", "一方面", "另一方面", "差异"
        ]
        if any(k in text for k in decomposition_signals):
            return "查询分解检索"

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
        #   定义类似私有方法，获取策略选择 Prompt 模板（与训练侧四分类标签严格对齐）
        return PromptTemplate(
            template="""
            你是采矿冶金领域的检索路由器。请分析用户查询 {query}，并从以下四种检索策略中选择一个最适合的，**只返回策略名称，不要输出任何解释或其他文字**。

            合法策略（只能从以下四个中选一个，严格按字面输出）：
            1. 直接检索
            2. 查询扩展检索
            3. 查询分解检索
            4. 问题重写检索

            策略含义与适用场景：
            - **直接检索**：查询意图明确、表达规范、目标单一的事实型问题。
              示例：露天矿山的开采工艺流程是什么？ -> 直接检索
            - **查询扩展检索**：查询较为抽象、概念宽泛、原始问句直接召回效果不佳的问题，需要通过补充语义线索缩小问题与文档的语义差距。
              示例：采矿工程对环境的影响有哪些？ -> 查询扩展检索
            - **查询分解检索**：包含多个知识维度、对比、复合要素的复杂问题，需要拆分为子查询分别召回再合并。
              示例：比较露天开采和地下开采的优缺点 -> 查询分解检索
            - **问题重写检索**：包含工况参数、约束条件、异常现象、方案设计等口语化/情境化的现场工程问题，需要先重写为标准技术表述再检索。
              示例：我有一个深部高应力矿床，应该采用什么开采方法和支护技术？ -> 问题重写检索

            用户查询：{query}
            策略名称：
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