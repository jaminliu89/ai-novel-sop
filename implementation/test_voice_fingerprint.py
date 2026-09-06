"""
Unit tests for VoiceProfile and VoiceDriftMonitor performance optimization and correctness.
"""

import math
import unittest
from ai_novel.metrics.voice_fingerprint import VoiceProfile, VoiceDriftMonitor


class TestVoiceFingerprint(unittest.TestCase):

    def setUp(self):
        self.sample_text1 = (
            "沈语冰在黑夜中睁开眼睛，植入体传来微弱的共振，如同冰水渗入骨髓。"
            "她摸了摸左手小指，指尖发麻的感觉比昨天更明显了。"
        )
        self.sample_text2 = (
            "陈静的态度依然冷漠，仿佛什么事都没有发生过。"
            "值得注意的是，这种现象在过去三个月里出现了七次。"
        )

    def test_hash_vector_length_and_normalization(self):
        """Test hash vector length and L2 norm."""
        vec = VoiceProfile._hash_vector(self.sample_text1, dim=256)
        self.assertEqual(len(vec), 256)

        norm = math.sqrt(sum(v * v for v in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_hash_vector_empty_text(self):
        """Test hash vector on empty string."""
        vec = VoiceProfile._hash_vector("", dim=256)
        self.assertEqual(len(vec), 256)
        self.assertTrue(all(v == 0.0 for v in vec))

    def test_voice_profile_fit_and_deviation(self):
        """Test VoiceProfile fit and deviation calculation."""
        vp = VoiceProfile()
        ref_texts = [self.sample_text1, self.sample_text1]
        vp.fit(ref_texts)

        # Deviation for identical text should be close to 0
        dev_same = vp.deviation(self.sample_text1)
        self.assertAlmostEqual(dev_same, 0.0, places=4)

        # Deviation for different text should be greater than 0
        dev_diff = vp.deviation(self.sample_text2)
        self.assertGreater(dev_diff, 0.0)

    def test_voice_drift_monitor(self):
        """Test VoiceDriftMonitor check functionality."""
        vp = VoiceProfile()
        vp.fit([self.sample_text1, self.sample_text2])

        monitor = VoiceDriftMonitor(vp)
        res = monitor.check(self.sample_text1)

        self.assertIn("deviation", res)
        self.assertIn("slope", res)
        self.assertIn("max_late", res)
        self.assertIn("drift_confirmed", res)


if __name__ == "__main__":
    unittest.main()
