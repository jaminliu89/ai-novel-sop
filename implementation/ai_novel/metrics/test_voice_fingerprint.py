"""
UnitTest for VoiceProfile hash_vector optimization and VoiceDriftMonitor.
"""

from __future__ import annotations

import collections
import hashlib
import math
import unittest

from ai_novel.metrics.voice_fingerprint import VoiceProfile, VoiceDriftMonitor


class TestVoiceFingerprint(unittest.TestCase):
    """VoiceProfile 声音指纹与 VoiceDriftMonitor 模块单元测试。"""

    def test_hash_vector_identical_to_unbatched(self) -> None:
        """验证 Counter 批处理 hash_vector 与单 token 循环的数学输出完全一致。"""
        text = "这是一个包含重复字符和重复词语的测试文本。测试文本测试文本。"

        tokens = VoiceProfile._tokenize(text)
        expected_vec = [0.0] * 256
        for t in tokens:
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
            idx = h % 256
            expected_vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in expected_vec))
        if norm > 1e-8:
            expected_vec = [v / norm for v in expected_vec]

        actual_vec = VoiceProfile._hash_vector(text)

        self.assertEqual(len(actual_vec), len(expected_vec))
        for a, e in zip(actual_vec, expected_vec):
            self.assertAlmostEqual(a, e, places=7)

    def test_voice_profile_and_monitor(self) -> None:
        """测试 VoiceProfile fit 及 VoiceDriftMonitor check 逻辑。"""
        ref_texts = ["角色说话语气特征" * 5 for _ in range(10)]
        vp = VoiceProfile()
        vp.fit(ref_texts)
        self.assertTrue(vp._fitted)

        monitor = VoiceDriftMonitor(vp)
        res = monitor.check("新生成的文本")
        self.assertIn("deviation", res)
        self.assertIn("drift_confirmed", res)


if __name__ == "__main__":
    unittest.main()
