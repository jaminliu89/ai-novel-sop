import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.qm = QualityMetrics()

    def test_repetition_rate_empty(self):
        self.assertEqual(self.qm.repetition_rate(""), 0.0)

    def test_repetition_rate(self):
        text = "测试文本" * 10
        rate = self.qm.repetition_rate(text, n=2)
        self.assertGreater(rate, 0.0)

    def test_ai_ism_density(self):
        text = "值得注意的是，在这个过程中，不得不提的是某种程度上。"
        density = self.qm.ai_ism_density(text)
        self.assertGreater(density, 0)

    def test_ngram_jaccard(self):
        text1 = "这是一个测试文本"
        text2 = "这是一个测试文本"
        text3 = "完全不同的另一个内容"
        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2, n=2), 1.0)
        self.assertLess(self.qm.ngram_jaccard(text1, text3, n=2), 1.0)

    def test_jaccard_diversity(self):
        candidates = [
            "这是第1个候选文本，用于测试语义多样性",
            "这是第2个候选文本，内容有一些不同和变化",
            "这是第3个候选文本，完全描述了不同的情节",
        ]
        div = self.qm._jaccard_diversity(candidates)
        self.assertGreater(div, 0.0)
        self.assertLessEqual(div, 1.0)

    def test_check_all(self):
        res = self.qm.check_all("简单文本", layer="L4")
        self.assertIn("repetition_rate", res)
        self.assertIn("ai_ism_count", res)
        self.assertIn("passed", res)


if __name__ == "__main__":
    unittest.main()
