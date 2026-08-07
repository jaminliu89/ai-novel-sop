"""
段落生成器·L4 Agent

职责：根据 L3 场景简报生成正文段落。

四层叠加生成法（SOP 核心方法论）：
1. 感官层（Sensory）：外部感知——视觉/听觉/触觉/嗅觉/味觉
2. 内省层（Introspection）：角色内心活动、情绪反应
3. 对话层（Dialogue）：角色对话，体现声纹指纹
4. 推进层（Progression）：动作、情节推进、转折

生成策略：
- fast 模式：2-3 层叠加，快节奏推进
- precision 模式：4 层全叠加，精雕细琢关键场景

约束遵守：
- L0 世界规则：植入体技术设定、死区定义
- L1 角色声纹：每个角色的语言风格、口头禅
- L2 伏笔计划：本场景需要埋设/推进/回收的伏笔
- L3 场景简报：空间图、冲突点、情感目标、感官锚点

反 AI 腔机制：
- 禁用词表实时检测
- 短句为主，控制句长方差
- 避免"仿佛""似乎""不由自主"等 AI 高频词
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class ParagraphGeneratorAgent(BaseAgent):
    """段落生成器 Agent —— L4 正文生成引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__(
            "gardener",  # 复用园丁 system prompt
            llm_client,
            state_store,
            tree_store,
            vector_store,
        )

    async def execute(self, input_data: dict) -> dict:
        """
        根据场景简报生成正文。

        :param input_data: 包含以下字段
            - scene: L3 场景简报 dict
            - chapter_index: 章节序号
            - scene_index: 场景序号
            - world_rules: L0 世界规则
            - character_fingerprints: L1 角色声纹
            - constraints: 上层硬约束
            - previous_scenes_text: 前序场景正文（保持连贯性）
            - foreshadow_plan: 本场景伏笔操作
            - quality_mode: fast | precision
            - word_target: 目标字数
        :return: 包含以下字段
            - scene_id: 场景 ID
            - content: 生成的正文
            - word_count: 实际字数
            - layers_used: 使用的叠加层
            - foreshadow_planted: 已埋设的伏笔
        """
        user_message: str = self._build_user_message(input_data)

        quality_mode: str = input_data.get("quality_mode", "fast")
        word_target: int = input_data.get("word_target", 1500)

        # fast 模式用较高温度（0.85），precision 模式用中低温度（0.6）
        temperature: float = 0.85 if quality_mode == "fast" else 0.6

        # 根据目标字数调整 max_tokens（中文约 1.5 字/token）
        max_tokens: int = max(2048, int(word_target * 1.8))

        result: dict = await self._call_and_parse(
            user_message, temperature=temperature, max_tokens=max_tokens
        )

        content: str = result.get("content", "")
        word_count: int = len(content)

        # 如果生成内容过短（低于目标的 50%），重跑一次提高温度
        if word_target > 0 and word_count < word_target * 0.5:
            logger.warning(
                "生成内容过短 (%d/%d)，重跑",
                word_count,
                word_target,
            )
            result = await self._call_and_parse(
                user_message, temperature=temperature + 0.1, max_tokens=max_tokens
            )
            content = result.get("content", "")
            word_count = len(content)

        layers_used: list[str] = result.get("layers_used", ["感官", "推进"])
        foreshadow_planted: list[str] = result.get("foreshadow_planted", [])

        logger.info(
            "段落生成完成: scene=%s, 字数=%d, 层=%s",
            input_data.get("scene", {}).get("scene_id", "?"),
            word_count,
            layers_used,
        )

        return {
            "scene_id": input_data.get("scene", {}).get("scene_id", ""),
            "chapter_index": input_data.get("chapter_index", 0),
            "scene_index": input_data.get("scene_index", 0),
            "content": content,
            "word_count": word_count,
            "word_target": word_target,
            "layers_used": layers_used,
            "foreshadow_planted": foreshadow_planted,
            "quality_mode": quality_mode,
        }
