"""
场景分解师·L3 Agent

职责：将 L2 情节弧中的章节拆解为可执行的场景简报。

每个场景简报包含：
- scene_id: 场景唯一标识
- title: 场景标题
- location: 空间设定（物理空间 + 感官氛围）
- characters: 在场角色列表
- conflict: 核心冲突（一句话）
- emotional_goal: 情感目标（读者应感受到什么）
- sensory_anchor: 感官锚点（视觉/听觉/触觉/嗅觉/味觉的具体意象）
- narrative_function: 叙事功能（推进情节/塑造人物/营造氛围/埋设伏笔/回收伏笔）
- foreshadow_actions: 本场景的伏笔操作（埋设/推进/回收）
- word_target: 目标字数
- quality_mode: fast | precision

工作流程：
1. 接收 L2 章节大纲 + L0 世界规则 + L1 人物指纹
2. 为每章生成 2-4 个候选场景分解方案（园丁式发散）
3. 选最优方案（剪枝师式收敛）
4. 输出结构化场景列表

不直接生成正文——那是 L4 段落生成器的职责。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class SceneDecomposerAgent(BaseAgent):
    """场景分解师 Agent —— L3 场景简报生成引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__(
            "gardener",  # 复用园丁的 system prompt（发散式生成）
            llm_client,
            state_store,
            tree_store,
            vector_store,
        )

    async def execute(self, input_data: dict) -> dict:
        """
        执行场景分解。

        :param input_data: 包含以下字段
            - chapter_index: 章节序号
            - chapter_title: 章节标题
            - chapter_summary: L2 大纲中的章节摘要
            - key_events: L2 大纲中的关键事件列表
            - world_rules: L0 世界规则
            - character_fingerprints: L1 角色声纹
            - constraints: 上层硬约束
            - foreshadow_plan: 本章应操作的伏笔
            - quality_mode: fast | precision
        :return: 包含以下字段
            - chapter_index: 章节序号
            - scenes: 场景简报列表
            - total_word_target: 总目标字数
            - scene_count: 场景数
        """
        user_message: str = self._build_user_message(input_data)

        # 场景分解用中等温度（0.7），需要结构化但有创意
        result: dict = await self._call_and_parse(
            user_message, temperature=0.7, max_tokens=4096
        )

        scenes: list[dict] = result.get("scenes", [])

        # 质量门禁：至少 2 个场景
        if len(scenes) < 2:
            logger.warning(
                "场景分解质量门禁未通过（场景数=%d），重跑", len(scenes)
            )
            result = await self._call_and_parse(
                user_message, temperature=0.9, max_tokens=4096
            )
            scenes = result.get("scenes", [])

        # 为每个场景补充元数据
        chapter_index: int = input_data.get("chapter_index", 1)
        for i, scene in enumerate(scenes):
            scene.setdefault("scene_id", f"ch{chapter_index}_s{i + 1}")
            scene.setdefault("narrative_function", "推进情节")
            scene.setdefault("foreshadow_actions", [])
            scene.setdefault("word_target", 1500)
            scene.setdefault("quality_mode", input_data.get("quality_mode", "fast"))

        total_word_target: int = sum(s.get("word_target", 1500) for s in scenes)

        logger.info(
            "场景分解完成: 第%d章, 场景数=%d, 目标字数=%d",
            chapter_index,
            len(scenes),
            total_word_target,
        )

        return {
            "chapter_index": chapter_index,
            "chapter_title": input_data.get("chapter_title", ""),
            "scenes": scenes,
            "total_word_target": total_word_target,
            "scene_count": len(scenes),
        }
