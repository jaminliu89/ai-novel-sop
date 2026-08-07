"""
蒸馏者·主题抽象 Agent

职责：从已固化的层中提炼主题主线、精神内核，并挑战预期。

核心原则：
- 主题不是标语：不是"爱与勇气"，而是"当爱需要以牺牲正义为代价时，人如何选择"
- 弧光覆盖：检查每个主要人物的弧光是否承载了主题的某个切面
- 挑战预期：主动提出"读者最可能的预期是什么？这个预期是否太安全？"
- 跨层一致性：主题应从 L0 世界观到 L4 段落都能找到呼应

蒸馏时机：
- L2 情节弧固化后：首次蒸馏，确立主题主线
- 每 5 个场景完成后：校准，检查是否偏航
- 全稿统一时：终审，确认主题贯穿始终
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class DistillerAgent(BaseAgent):
    """蒸馏者 Agent —— 主题抽象引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__("distiller", llm_client, state_store, tree_store, vector_store)

    async def execute(self, input_data: dict) -> dict:
        """
        执行主题蒸馏。

        :param input_data: 包含以下字段
            - solidified_layers: {L0, L1, L2} 已固化层摘要
            - current_chapters: 已完成章节摘要列表
            - previous_distillation: 上一次蒸馏结果（如有）
        :return: 蒸馏结果，包含以下字段
            - theme_statement: 主题陈述
            - theme_dimensions: 主题维度列表
            - arc_alignment: 弧光对齐情况
            - expectation_challenge: 预期挑战
            - drift_detected: 是否检测到偏航
            - drift_notes: 偏航说明
            - cross_layer_consistency: 跨层一致性
        """
        user_message: str = self._build_user_message(input_data)

        # 蒸馏用中等温度（0.5）
        result: dict = await self._call_and_parse(
            user_message, temperature=0.5, max_tokens=4096
        )

        # 确保关键字段存在，提供合理默认值
        result.setdefault("theme_statement", "")
        result.setdefault("theme_dimensions", [])
        result.setdefault("arc_alignment", [])
        result.setdefault("expectation_challenge", {})
        result.setdefault("drift_detected", False)
        result.setdefault("drift_notes", "")
        result.setdefault("cross_layer_consistency", [])

        # 日志记录蒸馏结果摘要
        logger.info(
            "蒸馏完成: 主题=%s, 偏航=%s, 维度数=%d",
            result.get("theme_statement", "")[:50],
            result.get("drift_detected", False),
            len(result.get("theme_dimensions", [])),
        )

        return result
