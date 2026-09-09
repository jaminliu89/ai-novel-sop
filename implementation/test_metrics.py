import unittest
from ai_novel.metrics.quality import QualityMetrics
from ai_novel.metrics.voice_fingerprint import VoiceProfile


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.qm = QualityMetrics()
        self.vp = VoiceProfile()

    def test_ai_ism_density(self):
        text = "值得注意的是，在这个过程中，不由自主地发生了变化。"
        count = self.qm.ai_ism_density(text)
        self.assertEqual(count, 3)

    def test_repetition_rate(self):
        text = "测试文本" * 10
        rate = self.qm.repetition_rate(text)
        self.assertGreater(rate, 0.0)

    def test_check_all(self):
        text = "这是一个普通的句子，没有任何问题。"
        res = self.qm.check_all(text, layer="L4")
        self.assertIn("repetition_rate", res)
        self.assertIn("ai_ism_count", res)
        self.assertIn("passed", res)

    def test_voice_profile_stat_features(self):
        text = "沈语冰在日常使用植入体时发现前同事陈静周围出现死区。"
        features = self.vp._extract_stat_features(text)
        self.assertEqual(len(features), 23)


if __name__ == "__main__":
    unittest.main()
