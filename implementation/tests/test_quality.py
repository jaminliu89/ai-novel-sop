import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.qm = QualityMetrics()

    def test_semantic_diversity_empty_or_single(self):
        self.assertEqual(self.qm.semantic_diversity([]), 0.0)
        self.assertEqual(self.qm.semantic_diversity(["单独候选段落"]), 0.0)

    def test_semantic_diversity_identical_candidates(self):
        cand1 = "这是一个用于测试相同的段落内容。夜幕低垂，微风吹拂。"
        cand2 = "这是一个用于测试相同的段落内容。夜幕低垂，微风吹拂。"
        diversity = self.qm.semantic_diversity([cand1, cand2])
        # Identical candidates should have 0.0 diversity (1.0 - 1.0 Jaccard similarity)
        self.assertAlmostEqual(diversity, 0.0, places=5)

    def test_semantic_diversity_different_candidates(self):
        candidates = [
            "夜幕低垂，繁星点点，月光洒在平原上。",
            "代码重构与性能优化是现代软件工程的核心关注点。",
            "小明走进厨房，做了一顿丰盛的晚餐。",
        ]
        diversity = self.qm.semantic_diversity(candidates)
        # Distinct candidates should have higher diversity (> 0.5)
        self.assertGreater(diversity, 0.5)

    def test_ngram_jaccard(self):
        text1 = "落日余晖洒在城市天际线上"
        text2 = "落日余晖洒在城市天际线上"
        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2), 1.0)

        text3 = "完全不同的另外一句话"
        self.assertLess(self.qm.ngram_jaccard(text1, text3), 0.2)

    def test_check_all(self):
        text = "这是一个普通的测试文本。没有出现明显的禁用词。"
        res = self.qm.check_all(text, layer="L4")
        self.assertIn("repetition_rate", res)
        self.assertIn("ai_ism_count", res)
        self.assertIn("passed", res)
        self.assertTrue(res["passed"])


if __name__ == "__main__":
    unittest.main()
