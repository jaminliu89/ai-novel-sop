"""
园丁·发散 Agent

职责：给可能性，不给决断。每次发散至少产出 3 个语义差异化的候选，
其中至少 1 个 novelty ≥ 0.8（反共识走向）。

对抗"美颜滤镜"：第一反应想到的走向往往是套路——降级它，
继续找意料之外但情理之中的走向。

质量门禁：
- candidates.length >= 3
- max(novelty) >= 0.8
- 不满足则自动重跑一次（调高 temperature 到 1.0）
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class GardenerAgent(BaseAgent):
    """园丁 Agent —— 发散动作引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__("gardener", llm_client, state_store, tree_store, vector_store)

    async def execute(self, input_data: dict) -> dict:
        """
        执行发散动作。

        :param input_data: 包含以下字段
            - target_layer: 目标层级 (L0-L4)
            - objective: 本轮发散目标
            - constraints: 上层硬约束列表
            - forbid: 禁止使用的套路列表
            - quality_mode: fast | precision
        :return: 包含 candidates 列表和 diversity_note 的字典
        """
        user_message: str = self._build_user_message(input_data)

        # 发散需要高温度（0.9）
        result: dict = await self._call_and_parse(
            user_message, temperature=0.9, max_tokens=4096
        )
        candidates: list[dict] = result.get("candidates", [])

        # 质量门禁检查
        if not self._passes_quality_gate(candidates):
            logger.info(
                "质量门禁未通过（候选数=%d，最高novelty=%.2f），提高温度重跑",
                len(candidates),
                max((c.get("novelty", 0.0) for c in candidates), default=0.0),
            )
            result = await self._call_and_parse(
                user_message, temperature=1.0, max_tokens=4096
            )
            candidates = result.get("candidates", [])

            if not self._passes_quality_gate(candidates):
                logger.warning(
                    "重跑后仍未通过质量门禁（候选数=%d），返回当前候选",
                    len(candidates),
                )

        return {
            "candidates": candidates,
            "diversity_note": result.get("diversity_note", ""),
            "target_layer": input_data.get("target_layer", ""),
        }

    def _passes_quality_gate(self, candidates: list[dict]) -> bool:
        """
        质量门禁检查：
        - 候选数 >= 3
        - max(novelty) >= 0.8（至少一个反共识项）

        :param candidates: 候选列表
        :return: 是否通过
        """
        if len(candidates) < 3:
            return False
        max_novelty: float = max(
            (c.get("novelty", 0.0) for c in candidates), default=0.0
        )
        return max_novelty >= 0.8
