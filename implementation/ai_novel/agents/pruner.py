"""
剪枝师·收敛 Agent

职责：从候选中选一个，并给出可追溯的理由。

核心原则：
- 选择必有理由，不允许"凭感觉"
- 多维评分，用分数说话
- 约束一票否决：与上层硬约束冲突的候选直接淘汰
- 反共识加权：分数接近时，novelty 更高的候选优先
- 淘汰同样重要：被淘汰的候选及其淘汰理由是未来回溯的依据
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class PrunerAgent(BaseAgent):
    """剪枝师 Agent —— 收敛动作引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__("pruner", llm_client, state_store, tree_store, vector_store)

    async def execute(self, input_data: dict) -> dict:
        """
        执行收敛动作。

        :param input_data: 包含以下字段
            - candidates: 候选列表 [{id, content, novelty, ...}]
            - target_layer: 目标层级 (L0-L4)
            - constraints: 上层硬约束列表
            - evaluation_criteria: 本层评分维度及权重
        :return: 包含以下字段的字典
            - selected: 选中的候选 ID
            - scores: 各候选的评分记录列表
            - selection_rationale: 选择理由
            - target_layer: 目标层级
        """
        user_message: str = self._build_user_message(input_data)

        # 收敛需要低温度（0.3）
        result: dict = await self._call_and_parse(
            user_message, temperature=0.3, max_tokens=4096
        )

        selected: str = result.get("selected", "")
        scores: list[dict] = result.get("scores", [])
        selection_rationale: str = result.get("selection_rationale", "")

        # 日志记录淘汰与选中信息
        eliminated = [s for s in scores if s.get("eliminated")]
        logger.info(
            "剪枝完成: 选中=%s, 淘汰数=%d, 候选总数=%d",
            selected,
            len(eliminated),
            len(scores),
        )

        return {
            "selected": selected,
            "scores": scores,
            "selection_rationale": selection_rationale,
            "target_layer": input_data.get("target_layer", ""),
        }
