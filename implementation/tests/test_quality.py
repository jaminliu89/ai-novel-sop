"""
QualityMetrics 单元测试
"""

from __future__ import annotations

import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_tokenize(self) -> None:
        text = "测试字符分词"
        tokens = self.qm._tokenize(text)
        self.assertIsInstance(tokens, list)
        self.assertGreater(len(tokens), 0)

    def test_ngrams(self) -> None:
        tokens = ["a", "b", "c", "d", "e"]
        ngrams_4 = self.qm._ngrams(tokens, 4)
        self.assertEqual(ngrams_4, [("a", "b", "c", "d"), ("b", "c", "d", "e")])

        # 长度小于 n
        self.assertEqual(self.qm._ngrams(tokens, 10), [])

    def test_ngram_set(self) -> None:
        text = "这是测试文本内容"
        ngram_set = self.qm._ngram_set(text, 3)
        self.assertIsInstance(ngram_set, set)
        self.assertGreater(len(ngram_set), 0)

    def test_repetition_rate(self) -> None:
        text = "重复文本重复文本" * 5
        rate = self.qm.repetition_rate(text, n=2)
        self.assertGreater(rate, 0.0)

        empty_rate = self.qm.repetition_rate("", n=4)
        self.assertEqual(empty_rate, 0.0)

    def test_ai_ism_density(self) -> None:
        text = "值得注意的是，在这个过程中，不由自主地..."
        density = self.qm.ai_ism_density(text)
        self.assertGreaterEqual(density, 3)

    def test_check_all(self) -> None:
        clean_text = "这是一个干净的段落，描述故事的发展过程。"
        result = self.qm.check_all(clean_text, layer="L4")
        self.assertIn("passed", result)
        self.assertIn("repetition_rate", result)
        self.assertIn("ai_ism_count", result)

    def test_ngram_jaccard(self) -> None:
        text1 = "这是第一段文字描述。"
        text2 = "这是第一段文字描述。"
        text3 = "完全不同的另外内容。"

        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2), 1.0)
        self.assertLess(self.qm.ngram_jaccard(text1, text3), 0.5)

    def test_jaccard_diversity(self) -> None:
        # 少于 2 个候选
        self.assertEqual(self.qm._jaccard_diversity([]), 0.0)
        self.assertEqual(self.qm._jaccard_diversity(["单个候选"]), 0.0)

        # 完全相同的候选
        same = ["完全相同的内容", "完全相同的内容"]
        self.assertAlmostEqual(self.qm._jaccard_diversity(same), 0.0)

        # 不同的候选
        diff = ["第一种极有创意的设定", "第二种完全不同的背景", "第三个奇幻色彩故事"]
        diversity = self.qm._jaccard_diversity(diff)
        self.assertGreater(diversity, 0.5)

    def test_foreshadow_recovery_rate(self) -> None:
        registry = [
            {"harvested": True},
            {"harvested": False},
            {"status": "已回收"},
        ]
        rate = self.qm.foreshadow_recovery_rate(registry)
        self.assertAlmostEqual(rate, 2 / 3)


if __name__ == "__main__":
    unittest.main()
