import tempfile
import unittest
from ai_novel.memory.vector_store import VectorStore, _TfidfBackend, _segment


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_segment_function(self):
        text = "这是一个测试分词能力的句子。"
        segmented = _segment(text)
        self.assertIsInstance(segmented, str)
        self.assertIn("测试", segmented)

    def test_tfidf_backend_caching_and_query(self):
        backend = _TfidfBackend(self.temp_dir.name)
        docs = [
            "第一章：沈语冰在黑市中搜寻古老的技术元件。",
            "第二章：在都市边缘的死区，陈静发现了神秘的机械符文。",
        ]
        metas = [{"chapter": 1}, {"chapter": 2}]
        ids = ["ch1", "ch2"]

        backend.add_documents("chapters", docs, metas, ids)

        # 验证预处理分词 _segmented 已经生成并缓存
        bucket = backend._data["chapters"]
        self.assertEqual(len(bucket), 2)
        self.assertIn("_segmented", bucket[0])
        self.assertIn("黑市", bucket[0]["_segmented"])

        # 执行查询
        results = backend.query("chapters", "黑市 沈语冰", n_results=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "ch1")
        self.assertEqual(results[0]["metadata"]["chapter"], 1)

    def test_vector_store_few_shot_and_chapter(self):
        store = VectorStore(self.temp_dir.name)
        store.add_few_shot("sample_1", "高潮战斗场景：刀光闪烁，气氛十分紧迫。", {"scene_type": "高潮"})
        store.add_few_shot("sample_2", "日常对话场景：阳光照在小巷深处。", {"scene_type": "日常"})

        results = store.retrieve_few_shot("高潮", "战斗", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "sample_1")

        store.add_chapter("c1", "陈静在实验室里分析数据。", "摘要1", {"chapter": 1})
        ctx_results = store.retrieve_context("实验室 数据", top_k=1)
        self.assertEqual(len(ctx_results), 1)
        self.assertEqual(ctx_results[0]["id"], "c1")


if __name__ == "__main__":
    unittest.main()
