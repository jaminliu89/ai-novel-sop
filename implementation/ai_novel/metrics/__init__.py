"""
度量层模块

导出质量度量和声音指纹相关类。

- QualityMetrics:       质量度量（重复率、AI 腔、语义多样性、伏笔回收率、Jaccard 相似度）
- VoiceProfile:         角色声音指纹（统计特征 + 嵌入质心）
- VoiceDriftMonitor:    声音漂移监测器（三信号确认机制）
"""

from .quality import QualityMetrics
from .voice_fingerprint import VoiceDriftMonitor, VoiceProfile

__all__ = [
    "QualityMetrics",
    "VoiceProfile",
    "VoiceDriftMonitor",
]
