"""
Unit tests for quality and voice fingerprint metrics.
"""

from __future__ import annotations

import unittest
from ai_novel.metrics.quality import QualityMetrics
from ai_novel.metrics.voice_fingerprint import VoiceProfile, VoiceDriftMonitor


class TestQualityMetrics(unittest.TestCase):

    def setUp(self) -> None:
        self.qm = QualityMetrics()

    def test_repetition_rate(self) -> None:
        text_repeated = "沈语冰站在大厦门口。沈语冰站在大厦门口。沈语冰站在大厦门口。"
        rate_high = self.qm.repetition_rate(text_repeated)
        self.assertGreater(rate_high, 0.0)

        text_unique = "沈语冰站在大厦门口。陈静走出了大厅。走廊里静悄悄的，夜色渐浓。"
        rate_low = self.qm.repetition_rate(text_unique)
        self.assertLess(rate_low, rate_high)

    def test_ai_ism_density(self) -> None:
        clean_text = "沈语冰在走廊里向前走去。"
        self.assertEqual(self.qm.ai_ism_density(clean_text), 0)

        ai_text = "值得注意的是，沈语冰不由自主地停下脚步，仿佛某种程度上受到了吸引。"
        self.assertGreater(self.qm.ai_ism_density(ai_text), 0)

    def test_check_all(self) -> None:
        clean_text = "沈语冰推开重音室的门，走廊里的白光照在玻璃隔板上。"
        res = self.qm.check_all(clean_text, layer="L4")
        self.assertTrue(res["passed"])
        self.assertEqual(res["ai_ism_count"], 0)

    def test_jaccard_diversity(self) -> None:
        candidates = [
            "沈语冰站在大厦前，心中充满了疑惑和恐惧。",
            "沈语冰在大厦门口停下脚步，冷气从门缝刺进来。",
            "走廊里的灯光忽明忽暗，沈语冰感到左手发麻。",
            "苏映在地下实验室里调试着仪器，荧光屏跳动。",
            "陈静露出完美而缺乏温度的微笑，声音平淡。",
        ]
        div_score = self.qm._jaccard_diversity(candidates)
        self.assertGreater(div_score, 0.0)
        self.assertLessEqual(div_score, 1.0)

    def test_ngram_jaccard(self) -> None:
        text1 = "沈语冰站在共感科技大厦前。"
        text2 = "沈语冰站在共感科技大厦前。"
        self.assertAlmostEqual(self.qm.ngram_jaccard(text1, text2), 1.0)

        text3 = "完全不相干的一段文本，讨论机械结构与电路设计。"
        self.assertLess(self.qm.ngram_jaccard(text1, text3), 0.5)


class TestVoiceProfile(unittest.TestCase):

    def setUp(self) -> None:
        self.vp = VoiceProfile()

    def test_fit_and_deviation(self) -> None:
        ref_texts = [
            "陈静露出标准笑容：'请稍等，数据正在传输。'",
            "陈静的声音没有起伏：'权限认证通过，请进入。'",
            "陈静整理了一下衣角：'温度正常，无异常信号。'",
        ]
        self.vp.fit(ref_texts)
        self.assertTrue(self.vp._fitted)

        dev_same = self.vp.deviation("陈静面无表情：'系统更新完毕。'")
        dev_diff = self.vp.deviation("疯狂的浪潮涌上心头，他歇斯底里地高喊起来！")
        self.assertIsNotNone(dev_same)
        self.assertIsNotNone(dev_diff)

    def test_voice_drift_monitor(self) -> None:
        ref_texts = [
            "沈语冰看着屏幕发呆。",
            "沈语冰记下了这行数据。",
            "沈语冰感到左手冰凉。",
        ]
        self.vp.fit(ref_texts)
        monitor = VoiceDriftMonitor(self.vp)
        result = monitor.check("沈语冰走进了大楼。")
        self.assertIn("deviation", result)
        self.assertIn("drift_confirmed", result)


if __name__ == "__main__":
    unittest.main()
