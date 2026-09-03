import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetricsJaccardDiversity(unittest.TestCase):
    def setUp(self):
        self.qm = QualityMetrics()

    def test_less_than_two_candidates(self):
        self.assertEqual(self.qm._jaccard_diversity([]), 0.0)
        self.assertEqual(self.qm._jaccard_diversity(["单个候选文本"]), 0.0)

    def test_identical_candidates(self):
        candidates = [
            "这是一个完全相同的测试段落，用于验证语义多样性。",
            "这是一个完全相同的测试段落，用于验证语义多样性。",
            "这是一个完全相同的测试段落，用于验证语义多样性。",
        ]
        # Identical candidates -> Jaccard similarity = 1.0 -> Jaccard distance = 0.0
        diversity = self.qm._jaccard_diversity(candidates)
        self.assertAlmostEqual(diversity, 0.0, places=5)

    def test_disjoint_candidates(self):
        candidates = [
            "人工智能 深度学习 神经网络 语言模型 大语言模型 算力集群",
            "红烧排骨 宫保鸡丁 麻婆豆腐 清蒸石斑 鱼香肉丝 水煮牛肉",
            "量子力学 相对论 粒子物理 宇宙膨胀 黑洞引力 弦理论",
        ]
        # Entirely different 3-grams -> similarity = 0.0 -> distance = 1.0
        diversity = self.qm._jaccard_diversity(candidates)
        self.assertAlmostEqual(diversity, 1.0, places=5)

    def test_pairwise_equivalence(self):
        candidates = [
            "夜幕降临，城市亮起了璀璨的灯火。主角在街头独步行走。",
            "夜幕降临，街道上灯火辉煌。主角在路边静静等待。",
            "深秋的夜晚十分寒冷，公园里一个人也没有。",
            "天空阴沉沉的，似乎快要下雨了。",
        ]
        # Calculate expected pairwise distance manually using ngram_jaccard(..., n=3)
        n = len(candidates)
        total_dist = 0.0
        pair_count = 0
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.qm.ngram_jaccard(candidates[i], candidates[j], n=3)
                total_dist += 1.0 - sim
                pair_count += 1
        expected = total_dist / pair_count

        actual = self.qm._jaccard_diversity(candidates)
        self.assertAlmostEqual(actual, expected, places=7)


if __name__ == "__main__":
    unittest.main()
