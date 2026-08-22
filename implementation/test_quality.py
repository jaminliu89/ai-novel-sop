import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_ngrams_normal(self) -> None:
        tokens = ["a", "b", "c", "d", "e"]
        ngrams = self.qm._ngrams(tokens, 3)
        expected = [("a", "b", "c"), ("b", "c", "d"), ("c", "d", "e")]
        self.assertEqual(ngrams, expected)

    def test_ngrams_short_tokens(self) -> None:
        tokens = ["a", "b"]
        ngrams = self.qm._ngrams(tokens, 3)
        self.assertEqual(ngrams, [])

    def test_ngrams_empty_tokens(self) -> None:
        ngrams = self.qm._ngrams([], 4)
        self.assertEqual(ngrams, [])

    def test_repetition_rate(self) -> None:
        # Repeating text should have high repetition rate
        repeating_text = "测试文本" * 10
        rep_rate = self.qm.repetition_rate(repeating_text, n=2)
        self.assertGreater(rep_rate, 0.5)

        # Unique text should have 0 or low repetition rate
        unique_text = "一二三四五六七八九十"
        unique_rep = self.qm.repetition_rate(unique_text, n=2)
        self.assertEqual(unique_rep, 0.0)

    def test_ai_ism_density(self) -> None:
        text = "值得注意的是，在这个过程中，我们需要打法和抓手。"
        count = self.qm.ai_ism_density(text)
        self.assertEqual(count, 4)  # "值得注意的是", "在这个过程中", "打法", "抓手"

    def test_ngram_jaccard(self) -> None:
        text1 = "这是一个测试文本"
        text2 = "这是一个测试文本"
        text3 = "完全不相同的另一段文字"

        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2, n=2), 1.0)
        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text3, n=2), 0.0)

    def test_check_all(self) -> None:
        result = self.qm.check_all("这是正常的测试段落。没有违规词汇和严重重复。", layer="L4")
        self.assertIn("repetition_rate", result)
        self.assertIn("ai_ism_count", result)
        self.assertIn("passed", result)
        self.assertIn("issues", result)
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
