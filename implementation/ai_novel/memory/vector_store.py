"""
向量检索层
==========

封装 ChromaDB 提供语义检索能力，用于：
- few-shot 样本按场景类型检索
- 已定稿章节的相关前文检索

当 chromadb 不可用时，自动降级为基于 scikit-learn 的 TF-IDF 检索，
保证流水线在最小依赖下也能运行（牺牲语义精度，保留关键词召回）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_novel.memory.vector_store")

# 尝试导入 chromadb；失败则标记降级
try:
    import chromadb  # type: ignore[import-untyped]

    _CHROMA_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    chromadb = None  # type: ignore[assignment]
    _CHROMA_AVAILABLE = False
    logger.warning("chromadb 不可用，VectorStore 将降级为 TF-IDF 检索")

# 尝试导入 scikit-learn（降级路径依赖）
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    _SKLEARN_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    _SKLEARN_AVAILABLE = False

# 尝试导入 jieba（中文分词，提升 TF-IDF 召回质量；不可用时按字符切分）
try:
    import jieba  # type: ignore[import-untyped]

    _JIEBA_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    jieba = None  # type: ignore[assignment]
    _JIEBA_AVAILABLE = False


# 内置集合名常量
_FEW_SHOT_COLLECTION = "few_shot"
_CHAPTERS_COLLECTION = "chapters"


def _segment(text: str) -> str:
    """中文分词，返回空格分隔的 token 字符串。

    优先使用 jieba 分词；jieba 不可用时退化为逐字符切分。
    预分词是 TF-IDF 在中文上有效的前提：默认的 \\b\\w+\\b 会把整段无空格
    中文当作单个 token，导致检索失效。
    """
    if not text:
        return ""
    if _JIEBA_AVAILABLE:
        return " ".join(w for w in jieba.cut(text) if w.strip())
    # 降级：逐字符切分（标点等非词字符保留为噪声 token，影响有限）
    return " ".join(text)


def _sanitize_metadata(metadata: dict | None) -> dict[str, Any]:
    """将 metadata 规整为 ChromaDB 可接受的扁平原始类型。

    ChromaDB 的 metadata 值只允许 str/int/float/bool；嵌套对象会被序列化为 JSON 字符串。
    """
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
        else:
            safe[str(key)] = json.dumps(value, ensure_ascii=False)
    return safe


class _ChromaBackend:
    """基于 ChromaDB 的向量检索后端。"""

    def __init__(self, persist_path: str | Path) -> None:
        self.persist_path: Path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        # PersistentClient 本地持久化
        self._client = chromadb.PersistentClient(path=str(self.persist_path))
        logger.info("ChromaDB 后端已初始化，持久化路径: %s", self.persist_path)

    def _get_collection(self, name: str) -> Any:
        """获取或创建集合。"""
        return self._client.get_or_create_collection(name=name)

    def add_documents(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
    ) -> None:
        """添加文档（upsert 语义，重复 id 会被覆盖）。"""
        if not documents:
            return
        col = self._get_collection(collection)
        safe_metas = [_sanitize_metadata(m) for m in metadatas]
        col.upsert(documents=documents, metadatas=safe_metas, ids=ids)

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """语义检索。

        Args:
            collection: 集合名。
            query_text: 查询文本。
            n_results: 返回条数上限。
            where: 元数据过滤条件（ChromaDB where 子句）。

        Returns:
            结果列表，每项含 id / document / metadata / distance。
        """
        col = self._get_collection(collection)
        # 多取一些再裁剪，避免 where 过滤后不足
        fetch_n = max(n_results * 3, n_results)
        kwargs: dict[str, Any] = {"query_texts": [query_text], "n_results": fetch_n}
        if where:
            kwargs["where"] = where
        try:
            raw = col.query(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ChromaDB 查询失败(%s): %s", collection, exc)
            return []
        return _unpack_chroma_results(raw, n_results)


def _unpack_chroma_results(raw: dict, n_results: int) -> list[dict]:
    """将 ChromaDB 的嵌套结果解包为扁平字典列表。"""
    results: list[dict] = []
    ids_list = raw.get("ids") or [[]]
    docs_list = raw.get("documents") or [[]]
    metas_list = raw.get("metadatas") or [[]]
    dists_list = raw.get("distances") or [[]]
    ids = ids_list[0] if ids_list else []
    docs = docs_list[0] if docs_list else []
    metas = metas_list[0] if metas_list else []
    dists = dists_list[0] if dists_list else []
    for idx in range(min(len(ids), n_results)):
        meta = metas[idx] if idx < len(metas) else {}
        results.append(
            {
                "id": ids[idx],
                "document": docs[idx] if idx < len(docs) else "",
                "metadata": meta or {},
                "distance": dists[idx] if idx < len(dists) else None,
            }
        )
    return results


class _TfidfBackend:
    """基于 scikit-learn TF-IDF 的降级检索后端。

    文档以 JSON 文件持久化，查询时即时计算余弦相似度。
    适用于小规模语料；语义能力弱于向量检索，但无需额外模型。
    """

    def __init__(self, persist_path: str | Path) -> None:
        self.persist_path: Path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self._store_file: Path = self.persist_path / "tfidf_store.json"
        # 内存中的全量文档：{collection: [{"id","document","metadata"}]}
        self._data: dict[str, list[dict]] = self._load()

    def _load(self) -> dict[str, list[dict]]:
        """从磁盘加载已持久化的文档。"""
        if self._store_file.exists():
            try:
                return json.loads(self._store_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("TF-IDF 存储文件损坏，重新初始化: %s", self._store_file)
        return {}

    def _save(self) -> None:
        """将文档落盘。"""
        self._store_file.write_text(
            json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
        )

    def add_documents(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
    ) -> None:
        """添加文档（按 id 去重覆盖）。"""
        bucket = self._data.setdefault(collection, [])
        index_map = {item["id"]: i for i, item in enumerate(bucket)}
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            entry = {
                "id": doc_id,
                "document": doc,
                "metadata": _sanitize_metadata(meta),
            }
            if doc_id in index_map:
                bucket[index_map[doc_id]] = entry
            else:
                bucket.append(entry)
                index_map[doc_id] = len(bucket) - 1
        self._save()

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """TF-IDF 余弦相似度检索。"""
        bucket = self._data.get(collection, [])
        # 先按 where 过滤元数据
        if where:
            bucket = [
                item
                for item in bucket
                if all(item["metadata"].get(k) == v for k, v in where.items())
            ]
        if not bucket:
            return []

        if not _SKLEARN_AVAILABLE:
            # 无 scikit-learn 时退化为子串匹配
            return self._substring_match(bucket, query_text, n_results)

        corpus = [item["document"] for item in bucket]
        # 对语料与查询做中文预分词，避免默认 token_pattern 把整段中文当作单 token
        seg_corpus = [_segment(doc) for doc in corpus]
        seg_query = _segment(query_text)
        try:
            # token_pattern 接受 1 个及以上词字符，兼容逐字符切分与 jieba 词级切分
            vectorizer = TfidfVectorizer(token_pattern=r"(?u)\w+")
            tfidf = vectorizer.fit_transform(seg_corpus + [seg_query])
            sims = cosine_similarity(tfidf[-1], tfidf[:-1]).flatten()
        except ValueError as exc:
            logger.warning("TF-IDF 计算失败，退化为子串匹配: %s", exc)
            return self._substring_match(bucket, query_text, n_results)

        # 按相似度降序取 top_k；过滤零相似度项以保证召回相关性
        ranked_idx = [i for i in np.argsort(sims)[::-1] if sims[i] > 0][:n_results]
        results: list[dict] = []
        for idx in ranked_idx:
            item = bucket[int(idx)]
            results.append(
                {
                    "id": item["id"],
                    "document": item["document"],
                    "metadata": item["metadata"],
                    "distance": float(1.0 - sims[int(idx)]),  # 转为距离语义
                }
            )
        return results

    @staticmethod
    def _substring_match(
        bucket: list[dict], query_text: str, n_results: int
    ) -> list[dict]:
        """无 scikit-learn 时的兜底：按查询词出现次数排序。"""
        scored: list[tuple[float, dict]] = []
        for item in bucket:
            doc = item["document"]
            score = float(doc.count(query_text)) if query_text else 0.0
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": item["id"],
                "document": item["document"],
                "metadata": item["metadata"],
                "distance": 1.0 - score,
            }
            for score, item in scored[:n_results]
        ]


class VectorStore:
    """向量检索统一入口。

    优先使用 ChromaDB；chromadb 不可用时降级为 TF-IDF。
    对外接口与后端无关，调用方无需感知差异。
    """

    def __init__(self, persist_path: str | Path) -> None:
        """初始化向量存储。

        Args:
            persist_path: 持久化目录路径。
        """
        self.persist_path: Path = Path(persist_path)
        if _CHROMA_AVAILABLE:
            self._backend: _ChromaBackend | _TfidfBackend = _ChromaBackend(
                self.persist_path
            )
        else:
            logger.warning("使用 TF-IDF 降级后端（persist_path=%s）", self.persist_path)
            self._backend = _TfidfBackend(self.persist_path)

    # ------------------------------------------------------------------
    # 通用文档操作
    # ------------------------------------------------------------------
    def add_documents(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
    ) -> None:
        """向指定集合批量添加文档。

        Args:
            collection: 集合名。
            documents: 文档文本列表。
            metadatas: 与文档一一对应的元数据列表。
            ids: 与文档一一对应的唯一 id 列表。
        """
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError(
                "documents/metadatas/ids 长度不一致: "
                f"{len(documents)}/{len(metadatas)}/{len(ids)}"
            )
        self._backend.add_documents(collection, documents, metadatas, ids)

    def query(
        self, collection: str, query_text: str, n_results: int = 5
    ) -> list[dict]:
        """在指定集合中进行语义检索。

        Args:
            collection: 集合名。
            query_text: 查询文本。
            n_results: 返回条数上限，默认 5。

        Returns:
            结果列表，每项含 id / document / metadata / distance。
        """
        return self._backend.query(collection, query_text, n_results=n_results)

    # ------------------------------------------------------------------
    # few-shot 样本
    # ------------------------------------------------------------------
    def add_few_shot(self, sample_id: str, content: str, metadata: dict) -> None:
        """添加单个 few-shot 样本。

        metadata 中应包含 scene_type 字段以便按场景类型检索。

        Args:
            sample_id: 样本唯一 id。
            content: 样本文本内容。
            metadata: 元数据（建议含 scene_type / genre 等）。
        """
        self._backend.add_documents(
            _FEW_SHOT_COLLECTION, [content], [metadata], [sample_id]
        )

    def retrieve_few_shot(
        self, scene_type: str, query: str, top_k: int = 3
    ) -> list[dict]:
        """按场景类型检索 few-shot 样本。

        Args:
            scene_type: 场景类型（如 "高潮" / "日常" / "转折"）。
            query: 查询文本。
            top_k: 返回条数上限，默认 3。

        Returns:
            匹配的 few-shot 样本列表。
        """
        where = {"scene_type": scene_type}
        # 两个后端均支持 where 元数据过滤，统一调用即可
        return self._backend.query(
            _FEW_SHOT_COLLECTION, query, n_results=top_k, where=where
        )

    # ------------------------------------------------------------------
    # 已定稿章节
    # ------------------------------------------------------------------
    def add_chapter(
        self, chapter_id: str, content: str, summary: str, metadata: dict
    ) -> None:
        """添加已定稿章节。

        将章节正文作为可检索文档，摘要与其它信息存入 metadata。

        Args:
            chapter_id: 章节唯一 id。
            content: 章节正文。
            summary: 章节摘要。
            metadata: 额外元数据（如章节号、场景标记等）。
        """
        meta = dict(metadata) if metadata else {}
        meta["summary"] = summary
        self._backend.add_documents(
            _CHAPTERS_COLLECTION, [content], [meta], [chapter_id]
        )

    def retrieve_context(self, query: str, top_k: int = 5) -> list[dict]:
        """检索与查询相关的已定稿章节（前文上下文召回）。

        Args:
            query: 查询文本（如当前要写的场景描述）。
            top_k: 返回条数上限，默认 5。

        Returns:
            相关章节列表，每项含 id / document(正文) / metadata(含 summary)。
        """
        return self._backend.query(_CHAPTERS_COLLECTION, query, n_results=top_k)
