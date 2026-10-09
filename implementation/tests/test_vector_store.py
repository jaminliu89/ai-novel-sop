import tempfile
import unittest
from pathlib import Path

from ai_novel.memory.vector_store import VectorStore, _TfidfBackend


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name)
        self.store = VectorStore(persist_path=self.store_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_query_documents(self):
        docs = [
            "第一章 萧炎在乌坦城修炼斗气，坚守信念。",
            "第二章 药老指点萧炎突破瓶颈，炼制丹药。",
            "第三章 纳兰嫣然上门退婚，立下三年之约。",
        ]
        metas = [
            {"chapter": 1, "scene_type": "日常"},
            {"chapter": 2, "scene_type": "修炼"},
            {"chapter": 3, "scene_type": "高潮"},
        ]
        ids = ["ch_1", "ch_2", "ch_3"]

        self.store.add_documents("chapters", docs, metas, ids)

        results = self.store.query("chapters", "退婚 三年之约", n_results=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "ch_3")

    def test_add_few_shot_and_retrieve(self):
        self.store.add_few_shot("sample_1", "退婚场景精彩对话", {"scene_type": "高潮"})
        self.store.add_few_shot("sample_2", "日常修练场景描述", {"scene_type": "日常"})

        results = self.store.retrieve_few_shot("高潮", "退婚", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "sample_1")

    def test_add_chapter_and_retrieve_context(self):
        self.store.add_chapter("ch_1", "萧炎与药老在山谷练习斗技", "萧炎练习斗技", {"chapter": 1})
        results = self.store.retrieve_context("药老 斗技", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "ch_1")

    def test_tfidf_cache_invalidation(self):
        backend = _TfidfBackend(self.store_path / "tfidf_test")
        backend.add_documents(
            "test_col",
            ["文档一 斗气修炼", "文档二 丹药炼制"],
            [{}, {}],
            ["doc_1", "doc_2"],
        )

        res1 = backend.query("test_col", "斗气", n_results=1)
        self.assertEqual(res1[0]["id"], "doc_1")
        self.assertIn("test_col", backend._tfidf_cache)

        # 添加新文档应使缓存失效
        backend.add_documents(
            "test_col",
            ["文档三 萧炎突破"],
            [{}],
            ["doc_3"],
        )
        self.assertNotIn("test_col", backend._tfidf_cache)

        res2 = backend.query("test_col", "萧炎", n_results=1)
        self.assertEqual(res2[0]["id"], "doc_3")
        self.assertIn("test_col", backend._tfidf_cache)


if __name__ == "__main__":
    unittest.main()
