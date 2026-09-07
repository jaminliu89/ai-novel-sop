import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetricsJaccardDiversity(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_jaccard_diversity_empty_and_single(self) -> None:
        self.assertEqual(self.qm._jaccard_diversity([]), 0.0)
        self.assertEqual(self.qm._jaccard_diversity(["单独文本"]), 0.0)

    def test_jaccard_diversity_identical_candidates(self) -> None:
        candidates = ["这是一段测试文本", "这是一段测试文本", "这是一段测试文本"]
        diversity = self.qm._jaccard_diversity(candidates)
        self.assertAlmostEqual(diversity, 0.0)

    def test_jaccard_diversity_disjoint_candidates(self) -> None:
        candidates = ["苹果 香蕉 桔子", "飞机 火车 轮船", "量子 相对论 弦理论"]
        diversity = self.qm._jaccard_diversity(candidates)
        self.assertAlmostEqual(diversity, 1.0)

    def test_jaccard_diversity_partial_overlap(self) -> None:
        candidates = [
            "共振体是一种新型神经植入设备，能够同步人类情绪与神经网络。",
            "共振体是一种新型神经植入设备，但引发了严重的静默死区现象。",
            "完全不相关的神秘科技设施，不涉及任何植入或共振。",
        ]
        diversity = self.qm._jaccard_diversity(candidates)
        self.assertTrue(0.0 < diversity < 1.0)

    def test_jaccard_diversity_empty_strings(self) -> None:
        self.assertAlmostEqual(self.qm._jaccard_diversity(["", ""]), 0.0)

    def test_ngram_jaccard_consistency(self) -> None:
        text1 = "这是第一段落测试"
        text2 = "这是第二段落测试"
        jaccard_sim = self.qm.ngram_jaccard(text1, text2, n=3)
        diversity = self.qm._jaccard_diversity([text1, text2])
        self.assertAlmostEqual(diversity, 1.0 - jaccard_sim)


if __name__ == "__main__":
    unittest.main()
