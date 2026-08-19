"""
Unit tests for quality and voice fingerprint metrics.
"""

from __future__ import annotations

import math
import unittest

from ai_novel.metrics.quality import QualityMetrics
from ai_novel.metrics.voice_fingerprint import VoiceDriftMonitor, VoiceProfile


class TestQualityMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_repetition_rate_empty(self) -> None:
        self.assertEqual(self.qm.repetition_rate(""), 0.0)
        self.assertEqual(self.qm.repetition_rate("   "), 0.0)

    def test_repetition_rate_unique(self) -> None:
        text = "一二三四五六七八九十"
        # All 4-grams should be unique
        rate = self.qm.repetition_rate(text, n=4)
        self.assertEqual(rate, 0.0)

    def test_repetition_rate_repeated(self) -> None:
        text = "重复文本重复文本重复文本重复文本"
        rate = self.qm.repetition_rate(text, n=4)
        self.assertGreater(rate, 0.0)

    def test_ngram_jaccard(self) -> None:
        text1 = "这是一段用于测试的文本"
        text2 = "这是一段用于测试的文本"
        text3 = "完全不同的另外一段话"

        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2), 1.0)
        self.assertLess(self.qm.ngram_jaccard(text1, text3), 0.5)
        self.assertEqual(self.qm.ngram_jaccard("", ""), 1.0)
        self.assertEqual(self.qm.ngram_jaccard("这是一段用于测试的文本", ""), 0.0)

    def test_check_all(self) -> None:
        result = self.qm.check_all("这是一段正常不重复的文本。", layer="L4")
        self.assertIn("repetition_rate", result)
        self.assertIn("ai_ism_count", result)
        self.assertIn("passed", result)
        self.assertTrue(result["passed"])


class TestVoiceProfile(unittest.TestCase):
    def test_hash_vector_empty(self) -> None:
        vec = VoiceProfile._hash_vector("")
        self.assertEqual(len(vec), 256)
        self.assertEqual(sum(vec), 0.0)

    def test_hash_vector_norm(self) -> None:
        vec = VoiceProfile._hash_vector("这是一段测试角色声音语料的文本")
        self.assertEqual(len(vec), 256)
        norm = math.sqrt(sum(v * v for v in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_hash_vector_deterministic(self) -> None:
        text = "角色的对话声音指纹特征"
        vec1 = VoiceProfile._hash_vector(text)
        vec2 = VoiceProfile._hash_vector(text)
        self.assertEqual(vec1, vec2)

    def test_voice_profile_fit_and_deviation(self) -> None:
        vp = VoiceProfile()
        ref_texts = [
            "这是角色的参考语料一，用来建立初始声音模型。",
            "这是角色的参考语料二，同样展示性格与语气。",
            "这是角色的参考语料三，保持风格一致。",
        ]
        vp.fit(ref_texts)
        self.assertTrue(vp._fitted)

        # Deviation for similar text should be small
        dev_same = vp.deviation("这是角色的参考语料，语气非常相似。")

        # Deviation for very different text should be larger
        dev_diff = vp.deviation("1234567890!!!!!!??????#####")
        self.assertGreaterEqual(dev_diff, dev_same)

    def test_voice_drift_monitor(self) -> None:
        vp = VoiceProfile()
        ref_texts = [
            "参考语料A",
            "参考语料B",
            "参考语料C",
        ]
        vp.fit(ref_texts)
        monitor = VoiceDriftMonitor(vp)
        res = monitor.check("测试文本")
        self.assertIn("deviation", res)
        self.assertIn("drift_confirmed", res)


if __name__ == "__main__":
    unittest.main()
