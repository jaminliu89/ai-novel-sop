"""
质量度量模块

提供以下度量功能：
- repetition_rate:       n-gram 重复率检测
- ai_ism_density:        AI 腔禁用词计数
- check_all:             全量质量检测（重复率 + AI 腔 + 阈值判定）
- semantic_diversity:    候选间语义多样性（嵌入余弦距离 / Jaccard 降级）
- foreshadow_recovery_rate: 伏笔回收率
- ngram_jaccard:         n-gram Jaccard 相似度（用于版权检测）

外部依赖降级策略：
- jieba 不可用 → 降级为字符级分词
- sentence-transformers 不可用 → 语义多样性降级为 Jaccard 距离
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 外部依赖降级处理
# ------------------------------------------------------------------

try:
    import jieba

    _HAS_JIEBA: bool = True
except ImportError:
    _HAS_JIEBA = False
    logger.warning("jieba 未安装，将使用字符级分词降级方案")

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    _HAS_SBERT: bool = True
except ImportError:
    _HAS_SBERT = False
    logger.warning("sentence-transformers 未安装，语义多样性将使用 Jaccard 降级方案")


# ------------------------------------------------------------------
# AI 腔初始禁用词表
# ------------------------------------------------------------------

_AI_ISM_WORDS: list[str] = [
    # 议论文套话 / AI 高频连接词
    "值得注意的是",
    "不由自主地",
    "不禁",
    "仿佛",
    "宛如",
    "似乎",
    "某种程度上",
    "在这个过程中",
    "随着",
    "与此同时",
    "然而",
    "总而言之",
    "综上所述",
    "换言之",
    "不可否认",
    "毋庸置疑",
    "众所周知",
    "如前所述",
    "由此可见",
    "一目了然",
    "深入",
    # 互联网黑话
    "赋能",
    "落地",
    "闭环",
    "生态",
    "矩阵",
    "颗粒度",
    "抓手",
    "对齐",
    "拉通",
    "沉淀",
    "打法",
    "心智",
    "赛道",
    "痛点",
    # 网文专用
    "痒点",
    "爽点",
    "金手指",
    "开挂",
    "逆袭",
]

# ------------------------------------------------------------------
# 不同层级的默认阈值
# ------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "L0": {"repetition_rate": 0.10, "ai_ism_count": 0},
    "L1": {"repetition_rate": 0.10, "ai_ism_count": 0},
    "L2": {"repetition_rate": 0.10, "ai_ism_count": 0},
    "L3": {"repetition_rate": 0.12, "ai_ism_count": 0},
    "L4": {"repetition_rate": 0.15, "ai_ism_count": 0},
}


class QualityMetrics:
    """质量度量器：提供重复率、AI 腔、语义多样性等检测功能。"""

    def __init__(self, config: dict | None = None) -> None:
        """
        初始化质量度量器。

        :param config: 配置字典，可包含 quality.thresholds 和 quality.ai_ism_words
        """
        config = config or {}
        quality_config: dict = config.get("quality", {}) if config else {}
        self.thresholds: dict[str, dict[str, float]] = quality_config.get(
            "thresholds", _DEFAULT_THRESHOLDS
        )

        # 允许通过配置覆盖 AI 腔词表
        custom_words: list[str] | None = quality_config.get("ai_ism_words")
        self.ai_ism_words: list[str] = custom_words if custom_words else _AI_ISM_WORDS

        # 延迟初始化嵌入模型
        self._embedder: Any = None

    # ------------------------------------------------------------------
    # 分词
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        """
        分词：优先使用 jieba，降级为字符级切分。

        :param text: 待分词文本
        :return: token 列表
        """
        if _HAS_JIEBA:
            return list(jieba.cut(text))
        # 降级：按字符切分（去除空白符）
        return [ch for ch in text if not ch.isspace()]

    # ------------------------------------------------------------------
    # n-gram 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
        """生成 n-gram 列表。"""
        if len(tokens) < n:
            return []
        return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

    def _ngram_set(self, text: str, n: int) -> set[tuple[str, ...]]:
        """生成 n-gram 集合。"""
        tokens: list[str] = self._tokenize(text)
        return set(self._ngrams(tokens, n))

    # ------------------------------------------------------------------
    # n-gram 重复率
    # ------------------------------------------------------------------

    def repetition_rate(self, text: str, n: int = 4) -> float:
        """
        n-gram 重复率检测。

        计算方式：1 - (唯一 n-gram 数 / 总 n-gram 数)。
        值越高表示重复越严重。

        :param text: 待检测文本
        :param n: n-gram 的 n 值，默认 4
        :return: 重复率（0.0 ~ 1.0）
        """
        tokens: list[str] = self._tokenize(text)
        ngrams: list[tuple[str, ...]] = self._ngrams(tokens, n)
        if not ngrams:
            return 0.0

        total: int = len(ngrams)
        unique: int = len(set(ngrams))
        return 1.0 - (unique / total)

    # ------------------------------------------------------------------
    # AI 腔检测
    # ------------------------------------------------------------------

    def ai_ism_density(self, text: str) -> int:
        """
        AI 腔禁用词计数。

        :param text: 待检测文本
        :return: 禁用词出现总次数
        """
        count: int = 0
        for word in self.ai_ism_words:
            count += text.count(word)
        return count

    # ------------------------------------------------------------------
    # 全量质量检测
    # ------------------------------------------------------------------

    def check_all(self, text: str, layer: str = "L4") -> dict:
        """
        全量质量检测。

        :param text: 待检测文本
        :param layer: 目标层级，用于选择对应阈值
        :return: {repetition_rate, ai_ism_count, passed, issues}
        """
        rep_rate: float = self.repetition_rate(text)
        ai_count: int = self.ai_ism_density(text)

        # 获取当前层级的阈值
        layer_thresholds: dict[str, float] = self.thresholds.get(
            layer, self.thresholds.get("L4", _DEFAULT_THRESHOLDS["L4"])
        )
        rep_threshold: float = layer_thresholds.get("repetition_rate", 0.15)
        ai_threshold: float = layer_thresholds.get("ai_ism_count", 0)

        issues: list[str] = []
        passed: bool = True

        if rep_rate > rep_threshold:
            issues.append(
                f"重复率 {rep_rate:.4f} 超过阈值 {rep_threshold}"
            )
            passed = False

        if ai_count > ai_threshold:
            issues.append(
                f"AI腔密度 {ai_count} 超过阈值 {ai_threshold}"
            )
            passed = False

        return {
            "repetition_rate": rep_rate,
            "ai_ism_count": ai_count,
            "passed": passed,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # 语义多样性
    # ------------------------------------------------------------------

    def semantic_diversity(self, candidates: list[str]) -> float:
        """
        候选间语义多样性。

        如果 sentence-transformers 可用，用嵌入余弦距离的均值；
        否则用 n-gram Jaccard 距离的均值降级。

        :param candidates: 候选文本列表
        :return: 多样性分数（0.0 ~ 1.0，越高越多样）
        """
        if len(candidates) < 2:
            return 0.0

        if _HAS_SBERT:
            return self._embedding_diversity(candidates)
        else:
            return self._jaccard_diversity(candidates)

    def _embedding_diversity(self, candidates: list[str]) -> float:
        """基于嵌入余弦距离的语义多样性。"""
        embedder = self._get_embedder()
        if embedder is None:
            return self._jaccard_diversity(candidates)

        embeddings = embedder.encode(candidates)
        n: int = len(candidates)
        total_distance: float = 0.0
        pair_count: int = 0

        for i in range(n):
            for j in range(i + 1, n):
                # 余弦距离 = 1 - 余弦相似度
                norm_i: float = float(np.linalg.norm(embeddings[i]))
                norm_j: float = float(np.linalg.norm(embeddings[j]))
                if norm_i < 1e-8 or norm_j < 1e-8:
                    sim: float = 0.0
                else:
                    sim = float(
                        np.dot(embeddings[i], embeddings[j]) / (norm_i * norm_j)
                    )
                total_distance += 1.0 - sim
                pair_count += 1

        return total_distance / pair_count if pair_count > 0 else 0.0

    def _jaccard_diversity(self, candidates: list[str]) -> float:
        """基于 Jaccard 距离的语义多样性降级方案。"""
        n: int = len(candidates)
        if n < 2:
            return 0.0

        # Performance Optimization (⚡ Bolt): Pre-compute 3-gram sets for candidates
        # outside the O(n²) pair loop to avoid repeating jieba tokenization and n-gram set
        # construction O(n²) times. Reduces complexity from O(n²) tokenizations to O(n).
        ngram_sets: list[set[tuple[str, ...]]] = [
            self._ngram_set(c, n=3) for c in candidates
        ]
        total_distance: float = 0.0
        pair_count: int = 0

        for i in range(n):
            set1 = ngram_sets[i]
            for j in range(i + 1, n):
                set2 = ngram_sets[j]
                if not set1 and not set2:
                    jaccard_sim: float = 1.0
                elif not set1 or not set2:
                    jaccard_sim = 0.0
                else:
                    jaccard_sim = len(set1 & set2) / len(set1 | set2)
                total_distance += 1.0 - jaccard_sim
                pair_count += 1

        return total_distance / pair_count if pair_count > 0 else 0.0

    def _get_embedder(self) -> Any:
        """惰性加载嵌入模型。"""
        if self._embedder is None and _HAS_SBERT:
            try:
                self._embedder = SentenceTransformer("BAAI/bge-large-zh-v1.5")
            except Exception as e:
                logger.warning("加载嵌入模型失败: %s，降级为 Jaccard 方案", e)
                self._embedder = None
        return self._embedder

    # ------------------------------------------------------------------
    # 伏笔回收率
    # ------------------------------------------------------------------

    def foreshadow_recovery_rate(self, registry: Any) -> float:
        """
        伏笔回收率。

        注意：本方法为同步方法。如果 registry 的方法为异步（如 ForeshadowRegistry），
        调用方应预先 await 获取伏笔列表后传入，或直接传入伏笔列表。

        :param registry: ForeshadowRegistry 实例（仅支持同步接口）、
                         或伏笔字典列表（预获取的数据）、
                         或包含 recovery_rate() 方法的对象
        :return: 已回收伏笔数 / 总伏笔数（0.0 ~ 1.0）
        """
        if registry is None:
            return 0.0

        # 如果传入的是列表，直接使用
        if isinstance(registry, list):
            foreshadows: list = registry
        else:
            # 尝试不同的同步接口获取伏笔列表
            foreshadows = []

            # 优先尝试 recovery_rate() 方法（部分 registry 直接提供回收率）
            if hasattr(registry, "recovery_rate"):
                try:
                    rate = registry.recovery_rate()
                    if not asyncio.iscoroutine(rate) and isinstance(rate, (int, float)):
                        return float(rate)
                except Exception:
                    pass

            if hasattr(registry, "get_all"):
                try:
                    result = registry.get_all()
                    if not asyncio.iscoroutine(result):
                        foreshadows = result
                except Exception:
                    pass
            elif hasattr(registry, "get_status"):
                try:
                    status = registry.get_status()
                    if not asyncio.iscoroutine(status):
                        if isinstance(status, dict) and "foreshadows" in status:
                            foreshadows = status["foreshadows"]
                        elif isinstance(status, list):
                            foreshadows = status
                except Exception:
                    pass
            elif hasattr(registry, "all"):
                try:
                    result = registry.all()
                    if not asyncio.iscoroutine(result):
                        foreshadows = result
                except Exception:
                    pass

            # 如果所有方法都返回协程（异步接口），提示调用方预获取
            if not foreshadows:
                logger.warning(
                    "registry 可能使用异步接口，请预先获取伏笔列表后传入。"
                    "例如: foreshadows = await registry.get_status(); "
                    "metrics.foreshadow_recovery_rate(foreshadows)"
                )
                return 0.0

        if not foreshadows:
            return 0.0

        total: int = len(foreshadows)
        recovered: int = sum(1 for f in foreshadows if self._is_recovered(f))
        return recovered / total if total > 0 else 0.0

    @staticmethod
    def _is_recovered(foreshadow: Any) -> bool:
        """
        判断单个伏笔是否已回收。

        支持两种字段格式：
        - harvested: 布尔值（ForeshadowRegistry 使用）
        - status: 字符串（其他实现可能使用）
        """
        if isinstance(foreshadow, dict):
            # 优先检查 harvested 布尔字段（ForeshadowRegistry 的格式）
            if "harvested" in foreshadow:
                return bool(foreshadow.get("harvested"))
            # 回退到 status 字符串字段
            status: str = str(foreshadow.get("status", "")).lower()
            return status in ("已回收", "harvested", "recovered", "closed", "resolved")
        return False

    # ------------------------------------------------------------------
    # n-gram Jaccard 相似度
    # ------------------------------------------------------------------

    def ngram_jaccard(self, text1: str, text2: str, n: int = 4) -> float:
        """
        n-gram Jaccard 相似度（用于版权检测）。

        Jaccard = |A ∩ B| / |A ∪ B|

        :param text1: 文本一
        :param text2: 文本二
        :param n: n-gram 的 n 值，默认 4
        :return: Jaccard 相似度（0.0 ~ 1.0，越高越相似）
        """
        set1: set[tuple[str, ...]] = self._ngram_set(text1, n)
        set2: set[tuple[str, ...]] = self._ngram_set(text2, n)

        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection: set[tuple[str, ...]] = set1 & set2
        union: set[tuple[str, ...]] = set1 | set2
        return len(intersection) / len(union)
