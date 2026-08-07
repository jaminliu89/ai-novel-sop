"""
Agent 层模块

导出所有 Agent 类，供协调者调度使用。

七种 Agent 各精通一种动作：
- BaseAgent:       基类，提供 LLM 调用和 JSON 解析的公共逻辑
- GardenerAgent:   园丁·发散 —— 给可能性，不给决断
- PrunerAgent:     剪枝师·收敛 —— 从候选中选一个，给出可追溯理由
- CuratorAgent:    记忆管家·固化/检索 —— 写入记忆库 + 检索上下文
- InspectorAgent:  监工·审视 —— 找问题不解决问题
- DistillerAgent:  蒸馏者·主题抽象 —— 提炼主题主线，挑战预期
- DecoderAgent:    拆解师·反向拆解 —— 标杆小说四维样本档案
"""

from .base import BaseAgent
from .gardener import GardenerAgent
from .pruner import PrunerAgent
from .curator import CuratorAgent
from .decoder import DecoderAgent
from .inspector import InspectorAgent
from .distiller import DistillerAgent
from .scene_decomposer import SceneDecomposerAgent
from .paragraph_generator import ParagraphGeneratorAgent

__all__ = [
    "BaseAgent",
    "GardenerAgent",
    "PrunerAgent",
    "CuratorAgent",
    "DecoderAgent",
    "InspectorAgent",
    "DistillerAgent",
    "SceneDecomposerAgent",
    "ParagraphGeneratorAgent",
]
