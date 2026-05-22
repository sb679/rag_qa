import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RAG_QA_ROOT = os.path.dirname(CURRENT_DIR)
if RAG_QA_ROOT not in sys.path:
    sys.path.insert(0, RAG_QA_ROOT)


class TestStrategySelector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.strategy_selector import StrategySelector

        cls.selector = StrategySelector()
        if cls.selector.model is None:
            raise unittest.SkipTest("本地策略分类模型不可用")

    def test_simple_factual_queries_prefer_direct_retrieval(self):
        cases = [
            "露天矿山的开采工艺流程是什么？",
            "矿井通风系统的设计原则有哪些？",
            "矿石贫化率的定义是什么？",
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(self.selector.select_strategy(query), "直接检索")

    def test_abstract_queries_prefer_query_expansion(self):
        cases = [
            "采矿工程对环境的影响有哪些？",
            "绿色矿山建设的意义是什么？",
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(self.selector.select_strategy(query), "查询扩展检索")

    def test_comparison_queries_prefer_query_decomposition(self):
        cases = [
            "比较露天开采和地下开采的优缺点。",
            "浮选法和磁选法的区别是什么？",
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(self.selector.select_strategy(query), "查询分解检索")

    def test_scene_queries_prefer_query_rewrite(self):
        cases = [
            "尾矿库坝体出现裂缝，浸润线抬高3米，怎样进行除险加固以确保安全？",
            "深部开采面临高地应力、高井温和高渗透压的三高问题，综合技术方案应该如何设计？",
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(self.selector.select_strategy(query), "问题重写检索")


if __name__ == '__main__':
    unittest.main()