"""
声音指纹模块（两层融合方案）

角色声音指纹 = 统计特征质心 + 嵌入质心
- 统计层：句长分布、功能词频率、标点比率、TTR
- 嵌入层：sentence-transformers 嵌入向量的质心（降级为 hash 向量）

偏离度计算：deviation = alpha * 统计距离 + (1 - alpha) * 嵌入距离
- 统计距离：StandardScaler 标准化后 + PCA 降维后的欧几里得距离
- 嵌入距离：1 - 余弦相似度

阈值计算：基于参考语料的基线偏离距离
- warn_threshold = μ + 2σ
- critical_threshold = μ + 3σ

VoiceDriftMonitor 监测角色生成轨迹的声音漂移，
三信号确认机制：偏离 > 阈值 且 slope > 0.0015 且 max_late > 阈值

外部依赖降级策略：
- jieba 不可用 → 字符级分词
- sentence-transformers 不可用 → hash 向量降级
- scikit-learn 不可用 → 手动标准化，跳过 PCA
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
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
    logger.warning("jieba 未安装，声音指纹将使用字符级分词降级方案")

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    _HAS_SBERT: bool = True
except ImportError:
    _HAS_SBERT = False
    logger.warning("sentence-transformers 未安装，声音指纹嵌入层将降级为 hash 向量")

try:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    _HAS_SKLEARN: bool = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning("scikit-learn 未安装，声音指纹将降级为纯统计特征（不做标准化/降维）")


# ------------------------------------------------------------------
# 常量定义
# ------------------------------------------------------------------

# 功能词列表（10 个）
_FUNCTION_WORDS: list[str] = ["的", "了", "是", "也", "却", "便", "乃", "之", "而", "则"]

# 标点符号全集（用于统计总标点数）
_PUNCTUATION_ALL: str = "，。！？……——；：、""''（）()【】[]《》<>「」『』"

# 各类标点（用于提取标点比率特征，8 类）
_PUNCT_TYPES: list[str] = ["，", "。", "！", "？", "……", "——", "；", "："]

# hash 向量维度（嵌入降级方案）
_HASH_DIM: int = 256


class VoiceProfile:
    """
    角色声音指纹：统计特征 + 嵌入质心。

    两层融合方案：
    1. 统计层：句长(均值/方差/最大值/长句占比) + 功能词频率(10维) + 标点比率(8维) + TTR
    2. 嵌入层：sentence-transformers 嵌入质心（降级为 hash 向量质心）
    """

    def __init__(self) -> None:
        # sklearn 组件（降级时为 None）
        if _HAS_SKLEARN:
            self.scaler: Any = StandardScaler()
            self.pca: Any = PCA(n_components=64)
        else:
            self.scaler = None
            self.pca = None

        # 统计特征质心
        self.centroid_stat: list[float] | None = None
        # 嵌入质心
        self.centroid_emb: list[float] | None = None
        # 参考语料基线偏离距离（用于计算阈值）
        self.baseline_distances: list[float] = []

        # 嵌入模型（惰性加载）
        self._embedder: Any = None
        # 统计特征维度
        self._stat_dim: int = 0
        # 标记是否已 fit
        self._fitted: bool = False

    # ------------------------------------------------------------------
    # 训练
    # ------------------------------------------------------------------

    def fit(self, reference_texts: list[str]) -> None:
        """
        用角色参考语料建质心。

        :param reference_texts: 角色参考语料列表
        """
        if not reference_texts:
            logger.warning("参考语料为空，无法建质心")
            return

        # 提取统计特征
        stat_features: list[list[float]] = [
            self._extract_stat_features(text) for text in reference_texts
        ]
        self._stat_dim = len(stat_features[0]) if stat_features else 0

        if _HAS_SKLEARN and len(stat_features) > 1:
            self._fit_with_sklearn(stat_features)
        else:
            self._fit_without_sklearn(stat_features)

        # 嵌入质心
        if _HAS_SBERT:
            embedder = self._get_embedder()
            if embedder is not None:
                try:
                    embeddings = embedder.encode(reference_texts)
                    self.centroid_emb = (
                        np.array(embeddings).mean(axis=0).tolist()
                    )
                except Exception as e:
                    logger.warning("嵌入质心计算失败: %s，降级为 hash 向量", e)
                    self._fit_hash_centroid(reference_texts)
            else:
                self._fit_hash_centroid(reference_texts)
        else:
            self._fit_hash_centroid(reference_texts)

        self._fitted = True
        logger.info(
            "声音指纹训练完成: 参考语料数=%d, 统计维度=%d, 基线距离数=%d",
            len(reference_texts),
            self._stat_dim,
            len(self.baseline_distances),
        )

    def _fit_with_sklearn(self, stat_features: list[list[float]]) -> None:
        """使用 sklearn 进行标准化、降维、质心计算。"""
        stat_array = np.array(stat_features)

        # 标准化
        scaled = self.scaler.fit_transform(stat_array)

        # PCA 降维（仅当特征维度 > n_components 时）
        if scaled.shape[1] > 64:
            scaled = self.pca.fit_transform(scaled)

        # 质心 = 均值
        self.centroid_stat = scaled.mean(axis=0).tolist()

        # 计算基线偏离距离
        for row in scaled:
            dist: float = self._euclidean_distance(row.tolist(), self.centroid_stat)
            self.baseline_distances.append(dist)

    def _fit_without_sklearn(self, stat_features: list[list[float]]) -> None:
        """不使用 sklearn 的降级方案：手动标准化，跳过 PCA。"""
        n: int = len(stat_features)
        dim: int = self._stat_dim

        # 手动计算均值和标准差
        means: list[float] = [0.0] * dim
        for features in stat_features:
            for i in range(dim):
                means[i] += features[i]
        means = [m / n for m in means]

        stds: list[float] = [0.0] * dim
        for features in stat_features:
            for i in range(dim):
                stds[i] += (features[i] - means[i]) ** 2
        stds = [math.sqrt(s / n) for s in stds]

        # 存储标准化参数供 deviation 使用
        self._manual_means = means
        self._manual_stds = stds

        # 手动标准化
        scaled_features: list[list[float]] = []
        for features in stat_features:
            scaled = [
                (features[i] - means[i]) / (stds[i] + 1e-8)
                for i in range(dim)
            ]
            scaled_features.append(scaled)

        # 质心 = 标准化后的均值
        self.centroid_stat = [0.0] * dim
        for scaled in scaled_features:
            for i in range(dim):
                self.centroid_stat[i] += scaled[i]
        self.centroid_stat = [v / n for v in self.centroid_stat]

        # 基线偏离距离
        for scaled in scaled_features:
            dist = self._euclidean_distance(scaled, self.centroid_stat)
            self.baseline_distances.append(dist)

    def _fit_hash_centroid(self, reference_texts: list[str]) -> None:
        """hash 向量降级方案：计算 hash 向量质心。"""
        hash_vectors: list[list[float]] = [
            self._hash_vector(text) for text in reference_texts
        ]
        if not hash_vectors:
            return

        dim: int = len(hash_vectors[0])
        centroid: list[float] = [0.0] * dim
        for vec in hash_vectors:
            for i in range(dim):
                centroid[i] += vec[i]
        self.centroid_emb = [v / len(hash_vectors) for v in centroid]

    # ------------------------------------------------------------------
    # 偏离度
    # ------------------------------------------------------------------

    def deviation(self, text: str, alpha: float = 0.5) -> float:
        """
        计算偏离度：alpha * 统计距离 + (1 - alpha) * 嵌入距离。

        :param text: 待检测文本
        :param alpha: 统计距离权重（0.0 ~ 1.0），默认 0.5
        :return: 偏离度（0 表示完全一致，越大越偏离）
        """
        if not self._fitted or self.centroid_stat is None:
            logger.warning("声音指纹未训练，返回 0 偏离度")
            return 0.0

        # 统计距离
        stat_features: list[float] = self._extract_stat_features(text)
        stat_dist: float = self._compute_stat_distance(stat_features)

        # 嵌入距离
        emb_dist: float = self._compute_emb_distance(text)

        return alpha * stat_dist + (1.0 - alpha) * emb_dist

    def _compute_stat_distance(self, stat_features: list[float]) -> float:
        """计算统计特征距离。"""
        if _HAS_SKLEARN and self.scaler is not None:
            stat_array = np.array([stat_features])
            scaled = self.scaler.transform(stat_array)
            if (
                self.pca is not None
                and hasattr(self.pca, "components_")
                and self.pca.components_ is not None
                and scaled.shape[1] > self.pca.n_components_
            ):
                scaled = self.pca.transform(scaled)
            return self._euclidean_distance(scaled[0].tolist(), self.centroid_stat)
        else:
            # 手动标准化
            dim: int = min(len(stat_features), len(self._manual_means))
            scaled: list[float] = [
                (stat_features[i] - self._manual_means[i])
                / (self._manual_stds[i] + 1e-8)
                for i in range(dim)
            ]
            return self._euclidean_distance(scaled, self.centroid_stat)

    def _compute_emb_distance(self, text: str) -> float:
        """计算嵌入距离（余弦距离）。"""
        if self.centroid_emb is None:
            return 0.0

        if _HAS_SBERT:
            embedder = self._get_embedder()
            if embedder is not None:
                try:
                    emb = embedder.encode([text])[0]
                    return self._cosine_distance(emb.tolist(), self.centroid_emb)
                except Exception as e:
                    logger.warning("嵌入计算失败: %s，降级为 hash 向量", e)

        # hash 向量降级
        hash_vec: list[float] = self._hash_vector(text)
        return self._cosine_distance(hash_vec, self.centroid_emb)

    # ------------------------------------------------------------------
    # 阈值
    # ------------------------------------------------------------------

    def thresholds(self) -> tuple[float, float]:
        """
        返回 (warn_threshold, critical_threshold) = (μ+2σ, μ+3σ)。

        基于参考语料的基线偏离距离计算。

        :return: (警告阈值, 严重阈值)
        """
        if not self.baseline_distances:
            # 默认阈值
            return (1.0, 2.0)

        n: int = len(self.baseline_distances)
        mean: float = sum(self.baseline_distances) / n
        variance: float = sum((d - mean) ** 2 for d in self.baseline_distances) / n
        std: float = math.sqrt(variance)

        warn: float = mean + 2 * std
        critical: float = mean + 3 * std
        return (warn, critical)

    # ------------------------------------------------------------------
    # 统计特征提取
    # ------------------------------------------------------------------

    def _extract_stat_features(self, text: str) -> list[float]:
        """
        提取统计特征向量。

        特征列表（共 23 维）：
        - 句长：均值、方差、最大值、长句占比（4 维）
        - 功能词频率：的/了/是/也/却/便/乃/之/而/则（10 维）
        - 标点比率：，。！？……——；：（8 维，各类占总标点的比例）
        - TTR（类型-令牌比）（1 维）
        """
        features: list[float] = []

        # --- 句长统计 ---
        sentences: list[str] = self._split_sentences(text)
        if sentences:
            sent_lengths: list[int] = [len(s) for s in sentences]
            mean_len: float = sum(sent_lengths) / len(sent_lengths)
            variance: float = sum((l - mean_len) ** 2 for l in sent_lengths) / len(sent_lengths)
            std_len: float = math.sqrt(variance)
            max_len: float = float(max(sent_lengths))
            # 长句占比：长度超过 (均值 + 标准差) 的句子比例
            threshold: float = mean_len + std_len
            long_ratio: float = sum(1 for l in sent_lengths if l > threshold) / len(sent_lengths)
        else:
            mean_len = variance = max_len = long_ratio = 0.0

        features.extend([mean_len, variance, max_len, long_ratio])

        # --- 功能词频率 ---
        total_chars: int = max(len(text), 1)
        for word in _FUNCTION_WORDS:
            features.append(text.count(word) / total_chars)

        # --- 标点比率 ---
        total_punct: int = sum(text.count(p) for p in _PUNCTUATION_ALL)
        for p in _PUNCT_TYPES:
            features.append(text.count(p) / max(total_punct, 1))

        # --- TTR（类型-令牌比）---
        tokens: list[str] = self._tokenize(text)
        if tokens:
            ttr: float = len(set(tokens)) / len(tokens)
        else:
            ttr = 0.0
        features.append(ttr)

        return features

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按句末标点切分句子。"""
        pattern: str = r"[。！？；…]+"
        sentences: list[str] = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """分词：优先 jieba，降级为字符级。"""
        if _HAS_JIEBA:
            return [t for t in jieba.cut(text) if t.strip()]
        return [ch for ch in text if not ch.isspace()]

    def _get_embedder(self) -> Any:
        """惰性加载嵌入模型。"""
        if self._embedder is None and _HAS_SBERT:
            try:
                self._embedder = SentenceTransformer("BAAI/bge-large-zh-v1.5")
            except Exception as e:
                logger.warning("加载嵌入模型失败: %s，降级为 hash 向量", e)
                self._embedder = None
        return self._embedder

    @staticmethod
    def _hash_vector(text: str, dim: int = _HASH_DIM) -> list[float]:
        """
        hash 向量降级方案：将文本映射为固定维度的向量。

        使用 hash trick：对每个 token 取 hash 值映射到维度，
        累加计数后 L2 归一化。

        :param text: 输入文本
        :param dim: 向量维度
        :return: 归一化后的 hash 向量
        """
        vec: list[float] = [0.0] * dim
        tokens: list[str] = (
            [t for t in jieba.cut(text) if t.strip()]
            if _HAS_JIEBA
            else [ch for ch in text if not ch.isspace()]
        )

        for token in tokens:
            # 使用 MD5 hash 取模确定维度索引
            h: int = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx: int = h % dim
            vec[idx] += 1.0

        # L2 归一化
        norm: float = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-8:
            vec = [v / norm for v in vec]

        return vec

    @staticmethod
    def _euclidean_distance(vec1: list[float], vec2: list[float]) -> float:
        """计算欧几里得距离（自动对齐维度）。"""
        min_dim: int = min(len(vec1), len(vec2))
        return math.sqrt(sum((vec1[i] - vec2[i]) ** 2 for i in range(min_dim)))

    @staticmethod
    def _cosine_distance(vec1: list[float], vec2: list[float]) -> float:
        """计算余弦距离（1 - 余弦相似度）。"""
        min_dim: int = min(len(vec1), len(vec2))
        dot: float = sum(vec1[i] * vec2[i] for i in range(min_dim))
        norm1: float = math.sqrt(sum(v * v for v in vec1[:min_dim]))
        norm2: float = math.sqrt(sum(v * v for v in vec2[:min_dim]))

        if norm1 < 1e-8 or norm2 < 1e-8:
            return 1.0

        sim: float = dot / (norm1 * norm2)
        # 限制相似度在 [0, 1] 范围内（避免数值误差）
        sim = max(0.0, min(1.0, sim))
        return 1.0 - sim


class VoiceDriftMonitor:
    """
    监测角色生成轨迹的声音漂移。

    三信号确认机制：
    1. 偏离度 > warn 阈值
    2. slope（偏离度趋势斜率）> 0.0015
    3. max_late（近期窗口最大偏离）> warn 阈值

    三个信号同时满足才确认漂移（drift_confirmed = True），
    避免单次波动导致误报。
    """

    # 偏离度趋势斜率阈值
    SLOPE_THRESHOLD: float = 0.0015

    # 近期窗口大小（最近 N 次检测）
    RECENT_WINDOW: int = 5

    def __init__(self, profile: VoiceProfile) -> None:
        """
        初始化漂移监测器。

        :param profile: 已训练的 VoiceProfile 实例
        """
        self.profile: VoiceProfile = profile
        self.warn: float
        self.crit: float
        self.warn, self.crit = profile.thresholds()
        self.history: list[float] = []

    def check(self, text: str) -> dict:
        """
        检测声音漂移。

        :param text: 待检测文本
        :return: 检测结果字典
            - deviation: 当前偏离度
            - slope: 偏离度趋势斜率
            - max_late: 近期窗口最大偏离
            - level: "normal" | "warn" | "critical"
            - drift_confirmed: 是否确认漂移（三信号）
            - warn_threshold: 警告阈值
            - critical_threshold: 严重阈值
        """
        deviation: float = self.profile.deviation(text)
        self.history.append(deviation)

        # 计算趋势斜率（简单线性回归）
        slope: float = self._compute_slope()

        # 近期窗口最大偏离
        recent: list[float] = self.history[-self.RECENT_WINDOW :]
        max_late: float = max(recent) if recent else 0.0

        # 确定级别
        if deviation >= self.crit:
            level: str = "critical"
        elif deviation >= self.warn:
            level = "warn"
        else:
            level = "normal"

        # 三信号确认漂移
        drift_confirmed: bool = (
            deviation > self.warn
            and slope > self.SLOPE_THRESHOLD
            and max_late > self.warn
        )

        return {
            "deviation": deviation,
            "slope": slope,
            "max_late": max_late,
            "level": level,
            "drift_confirmed": drift_confirmed,
            "warn_threshold": self.warn,
            "critical_threshold": self.crit,
        }

    def _compute_slope(self) -> float:
        """计算偏离度历史的趋势斜率（简单线性回归）。"""
        n: int = len(self.history)
        if n < 2:
            return 0.0

        x: list[float] = [float(i) for i in range(n)]
        y: list[float] = self.history

        x_mean: float = sum(x) / n
        y_mean: float = sum(y) / n

        numerator: float = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator: float = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator < 1e-12:
            return 0.0

        return numerator / denominator
