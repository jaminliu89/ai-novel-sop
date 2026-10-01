import unittest
from ai_novel.metrics.quality import QualityMetrics

class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.metrics = QualityMetrics()

    def test_repetition_rate(self):
        # 相同词循环的重复文本
        repeated_text = "测试 文本 测试 文本 测试 文本 测试 文本 测试 文本"
        rate = self.metrics.repetition_rate(repeated_text, n=2)
        self.assertGreater(rate, 0.0)

        # 唯一无重复文本
        unique_text = "苹果 香蕉 橘子 鸭梨 西瓜 葡萄"
        unique_rate = self.metrics.repetition_rate(unique_text, n=2)
        self.assertEqual(unique_rate, 0.0)

    def test_ai_ism_density(self):
        # 包含禁用词的文本
        text_with_ai_ism = "值得注意的是，在这个过程中，我们成功赋能了整个闭环生态。"
        count = self.metrics.ai_ism_density(text_with_ai_ism)
        self.assertGreaterEqual(count, 3)

        # 干净的文本
        clean_text = "他走进房间，关上了门。"
        clean_count = self.metrics.ai_ism_density(clean_text)
        self.assertEqual(clean_count, 0)

    def test_check_all(self):
        clean_text = "这是一个普通的简短句子。"
        result = self.metrics.check_all(clean_text, layer="L4")
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["issues"]), 0)

        bad_text = "值得注意的是 值得注意的是 值得注意的是 值得注意的是 赋能 闭环"
        bad_result = self.metrics.check_all(bad_text, layer="L4")
        self.assertFalse(bad_result["passed"])
        self.assertGreater(len(bad_result["issues"]), 0)

if __name__ == "__main__":
    unittest.main()
