import unittest
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RAG_QA_ROOT = os.path.dirname(CURRENT_DIR)
if RAG_QA_ROOT not in sys.path:
    sys.path.insert(0, RAG_QA_ROOT)


class TestSmoke(unittest.TestCase):
    def test_config_can_init(self):
        from base import Config

        conf = Config()
        self.assertIsNotNone(conf)
        self.assertIsInstance(conf.RETRIEVAL_K, int)
        self.assertIsInstance(conf.CANDIDATE_M, int)

    def test_supported_extensions_exists(self):
        doc_processor = os.path.join(RAG_QA_ROOT, 'core', 'document_processor.py')
        with open(doc_processor, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('".pdf"', content)
        self.assertIn('".txt"', content)


if __name__ == '__main__':
    unittest.main()
