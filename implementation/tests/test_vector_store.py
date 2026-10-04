import unittest
import os
import shutil
from ai_novel.memory.vector_store import VectorStore, _TfidfBackend, _segment

class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.test_dir = "/tmp/test_vector_store_unit"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_tfidf_backend_caching_and_query(self):
        backend = _TfidfBackend(self.test_dir)
        docs = ["科幻小说主角沈语冰在死区调查", "故事发生在未来的高科技都市"]
        metas = [{"scene_type": "高潮"}, {"scene_type": "日常"}]
        ids = ["doc_1", "doc_2"]

        backend.add_documents("few_shot", docs, metas, ids)

        # 验证 segmented_doc 是否已在插入时预计算并缓存
        bucket = backend._data["few_shot"]
        self.assertEqual(len(bucket), 2)
        self.assertIn("segmented_doc", bucket[0])
        self.assertIn("死区", bucket[0]["segmented_doc"])

        # 验证查询召回
        results = backend.query("few_shot", "沈语冰", n_results=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "doc_1")

        # 验证元数据过滤 where
        filtered = backend.query("few_shot", "高科技", n_results=5, where={"scene_type": "日常"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "doc_2")

    def test_vector_store_few_shot_and_chapter(self):
        vs = VectorStore(self.test_dir)
        vs.add_few_shot("fs_1", "沉浸式对决场景", {"scene_type": "高潮"})
        results = vs.retrieve_few_shot("高潮", "对决", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "fs_1")

        vs.add_chapter("ch_1", "第一章 沈语冰发现了异样", "发现死区", {"chapter_index": 1})
        ctx = vs.retrieve_context("沈语冰", top_k=1)
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["id"], "ch_1")

    def test_vector_store_invalid_lengths(self):
        vs = VectorStore(self.test_dir)
        with self.assertRaises(ValueError):
            vs.add_documents("test", ["doc1"], [{"m": 1}], ["id1", "id2"])

if __name__ == "__main__":
    unittest.main()
