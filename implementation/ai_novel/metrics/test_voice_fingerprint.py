"""
Voice fingerprint metrics unit tests.
"""

import unittest
from implementation.ai_novel.metrics.voice_fingerprint import VoiceProfile, VoiceDriftMonitor


class TestVoiceFingerprint(unittest.TestCase):
    def setUp(self):
        self.profile = VoiceProfile()
        self.sample_text = (
            "这是一个包含标点符号和功能词的长段落测试文本。"
            "“这到底是怎么回事？”他问道！……——；："
        )

    def test_split_sentences(self):
        sentences = self.profile._split_sentences(self.sample_text)
        self.assertTrue(len(sentences) > 0)
        for s in sentences:
            self.assertTrue(len(s) > 0)

    def test_hash_vector_properties(self):
        vec1 = self.profile._hash_vector(self.sample_text)
        vec2 = self.profile._hash_vector(self.sample_text)

        self.assertEqual(len(vec1), 256)
        self.assertEqual(vec1, vec2)

        # Check normalization (L2 norm should be ~1.0 unless all zeros)
        norm_sq = sum(v * v for v in vec1)
        self.assertAlmostEqual(norm_sq, 1.0, places=5)

    def test_extract_stat_features(self):
        features = self.profile._extract_stat_features(self.sample_text)
        self.assertEqual(len(features), 23)

    def test_voice_profile_fit_and_deviation(self):
        ref_texts = [
            "这是角色的第一句说话台词，带有特定功能词。",
            "这是角色的第二句说话台词，语气非常强烈！",
            "这是角色的第三句说话台词……似乎在思考问题？",
        ]
        self.profile.fit(ref_texts)
        self.assertTrue(self.profile._fitted)

        dev = self.profile.deviation(self.sample_text)
        self.assertIsInstance(dev, float)
        self.assertGreaterEqual(dev, 0.0)

    def test_voice_drift_monitor(self):
        ref_texts = ["测试句子一", "测试句子二"]
        self.profile.fit(ref_texts)
        monitor = VoiceDriftMonitor(self.profile)

        result = monitor.check(self.sample_text)
        self.assertIn("deviation", result)
        self.assertIn("drift_confirmed", result)


if __name__ == "__main__":
    unittest.main()
