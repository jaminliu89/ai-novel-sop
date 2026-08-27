"""Unit tests for QualityMetrics in ai_novel/metrics/quality.py."""

import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_jaccard_diversity_basic(self) -> None:
        candidates = [
            "苹果 香蕉 橘子 鸭梨 西瓜 葡萄",
            "汽车 飞机 火车 轮船 高铁 火箭",
            "电脑 手机 键盘 鼠标 显示器 显卡",
        ]
        div = self.qm._jaccard_diversity(candidates)
        self.assertGreaterEqual(div, 0.0)
        self.assertLessEqual(div, 1.0)

    def test_jaccard_diversity_identical_candidates(self) -> None:
        candidates = [
            "这是一个完全相同的文本测试内容",
            "这是一个完全相同的文本测试内容",
        ]
        div = self.qm._jaccard_diversity(candidates)
        # Identical text should have 0 diversity (Jaccard similarity = 1.0)
        self.assertAlmostEqual(div, 0.0)

    def test_jaccard_diversity_single_candidate(self) -> None:
        div = self.qm._jaccard_diversity(["单个候选"])
        self.assertEqual(div, 0.0)

    def test_jaccard_diversity_empty_candidates(self) -> None:
        div = self.qm._jaccard_diversity([])
        self.assertEqual(div, 0.0)


if __name__ == "__main__":
    unittest.main()
