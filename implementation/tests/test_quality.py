import unittest
from ai_novel.metrics.quality import QualityMetrics


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.qm = QualityMetrics()

    def test_ngrams(self):
        tokens = ["a", "b", "c", "d"]
        ngrams = QualityMetrics._ngrams(tokens, n=2)
        expected = [("a", "b"), ("b", "c"), ("c", "d")]
        self.assertEqual(ngrams, expected)

    def test_ngrams_short_tokens(self):
        tokens = ["a"]
        ngrams = QualityMetrics._ngrams(tokens, n=2)
        self.assertEqual(ngrams, [])

    def test_repetition_rate(self):
        text = "测试文本" * 10
        rate = self.qm.repetition_rate(text, n=2)
        self.assertGreater(rate, 0.0)

    def test_ai_ism_density(self):
        text = "值得注意的是，在这个过程中，我们赋能并闭环。"
        count = self.qm.ai_ism_density(text)
        self.assertGreater(count, 0)

    def test_ngram_jaccard(self):
        text1 = "这是一个测试文本"
        text2 = "这是一个测试文本"
        sim = self.qm.ngram_jaccard(text1, text2, n=2)
        self.assertEqual(sim, 1.0)


if __name__ == "__main__":
    unittest.main()
