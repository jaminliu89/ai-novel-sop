"""
Unit tests for quality metrics and voice fingerprinting modules.
"""

import unittest
from ai_novel.metrics.quality import QualityMetrics
from ai_novel.metrics.voice_fingerprint import VoiceProfile, VoiceDriftMonitor


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.metrics = QualityMetrics()

    def test_repetition_rate(self):
        unique_text = "这是 一个 完全 不重复 的 句子 样本 测试"
        repetitive_text = "重复 重复 重复 重复 重复 重复 重复 重复"
        self.assertLess(self.metrics.repetition_rate(unique_text), 0.5)
        self.assertGreater(self.metrics.repetition_rate(repetitive_text), 0.5)

    def test_ngram_jaccard(self):
        text1 = "夜色渐深 冷风吹过 悬崖 边石亭 的 轻纱"
        text2 = "夜色渐深 冷风吹过 悬崖 边石亭 的 轻纱"
        text3 = "完全 不同的 文本 内容 毫无 关联"
        self.assertAlmostEqual(self.metrics.ngram_jaccard(text1, text2), 1.0)
        self.assertLess(self.metrics.ngram_jaccard(text1, text3), 0.2)

    def test_check_all(self):
        text = "这是一个测试文本"
        res = self.metrics.check_all(text)
        self.assertIn("repetition_rate", res)
        self.assertIn("ai_ism_count", res)
        self.assertIn("passed", res)


class TestVoiceProfile(unittest.TestCase):
    def setUp(self):
        self.profile = VoiceProfile()
        self.reference_texts = [
            "夜色渐深，冷风拂过悬崖边石亭的轻纱。李林手中握着半块缺角的青铜令牌。",
            "林萧站在三步之外，目光沉沉地下视。这一战非同小可，成败全在此一举。",
        ]
        self.profile.fit(self.reference_texts)

    def test_deviation(self):
        text = "夜色渐深，冷风拂过悬崖边石亭的轻纱。"
        dev = self.profile.deviation(text)
        self.assertIsInstance(dev, float)
        self.assertGreaterEqual(dev, 0.0)

    def test_drift_monitor(self):
        monitor = VoiceDriftMonitor(self.profile)
        res = monitor.check("测试文本")
        self.assertIn("deviation", res)
        self.assertIn("drift_confirmed", res)


if __name__ == "__main__":
    unittest.main()
