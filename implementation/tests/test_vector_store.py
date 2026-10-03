"""
Unit tests for VectorStore and _TfidfBackend performance & retrieval correctness.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest

from ai_novel.memory.vector_store import VectorStore, _TfidfBackend, _segment


class TestVectorStore(unittest.TestCase):
    """VectorStore 及 TF-IDF 后端单元测试。"""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_segment_non_empty(self) -> None:
        """验证 _segment 分词正常输出空格分隔 token。"""
        text = "在东方的古老森林里，林羽手握沉重的玄铁剑。"
        segmented = _segment(text)
        self.assertTrue(len(segmented) > 0)
        self.assertIn(" ", segmented)

    def test_tfidf_backend_query_and_caching(self) -> None:
        """测试 _TfidfBackend 文档添加、检索及 _seg_doc 缓存。"""
        backend = _TfidfBackend(self.tmp_dir)
        docs = [
            "主角林羽在魔域森林寻找传说的灵药。",
            "沈语冰在研究所分析诡异的系统数据。",
            "林羽遇到了可怕的魔兽并展开激烈决斗。",
        ]
        ids = ["doc_1", "doc_2", "doc_3"]
        metas = [
            {"scene_type": "战斗"},
            {"scene_type": "调查"},
            {"scene_type": "战斗"},
        ]

        backend.add_documents("chapters", docs, metas, ids)

        # 首次查询，触发 _seg_doc 缓存
        results = backend.query("chapters", "林羽 森林 战斗", n_results=2)
        self.assertTrue(len(results) > 0)
        # 匹配最高的应是 doc_1 或 doc_3
        matched_ids = [r["id"] for r in results]
        self.assertIn("doc_1", matched_ids)

        # 检查 bucket 中各项是否已建立 _seg_doc 缓存
        bucket = backend._data.get("chapters", [])
        self.assertEqual(len(bucket), 3)
        for item in bucket:
            self.assertIn("_seg_doc", item)
            self.assertTrue(len(item["_seg_doc"]) > 0)

        # 第二次查询，使用已缓存的 _seg_doc
        results2 = backend.query("chapters", "林羽 森林 战斗", n_results=2)
        self.assertEqual(len(results2), len(results))
        self.assertEqual(results2[0]["id"], results[0]["id"])

    def test_vector_store_wrapper(self) -> None:
        """测试 VectorStore 包装层 API 调用。"""
        vs = VectorStore(self.tmp_dir)
        vs.add_few_shot("sample_1", "高潮战斗场景：双方对拼异能", {"scene_type": "高潮"})
        retrieved = vs.retrieve_few_shot("高潮", "异能 战斗", top_k=1)
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["id"], "sample_1")


if __name__ == "__main__":
    unittest.main()
