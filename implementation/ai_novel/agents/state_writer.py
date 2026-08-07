"""
状态回写 Agent

职责：每章 L4 段落生成后，从正文中提取故事世界状态变化，
写入 StoryStateStore 供后续章节参考。

提取四个维度的状态变化：
1. character_states: 角色状态
   - name: 角色名
   - location: 当前位置
   - emotional_state: 情绪状态
   - physical_state: 生理状态（受伤/疲劳/植入体异常等）
   - knowledge_gained: 本章新获得的信息
   - goal_updated: 目标变化

2. timeline_events: 时间线事件
   - event: 事件描述
   - time_marker: 时间标记（如"第一天下午"、"当晚"）
   - chapter: 章节序号

3. resource_changes: 资源变动
   - type: gained / lost
   - item: 资源名称（物品/权限/盟友/信息渠道）
   - detail: 变动详情

4. relationship_changes: 关系变动
   - between: [角色A, 角色B]
   - change_type: trust_up / trust_down / alliance / conflict / neutral
   - detail: 变动详情

工作流程：
1. 接收本章正文 + 章节合同 + 前一章状态快照
2. 调用 LLM 提取状态变化
3. 合并前一章状态（增量更新）
4. 写入 StoryStateStore
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 状态回写字段定义
# ------------------------------------------------------------------

STATE_EXTRACTION_FIELDS: dict[str, str] = {
    "character_states": (
        "本章涉及角色的状态变化列表。每个角色包含："
        "name（角色名）、location（位置变化）、emotional_state（情绪变化）、"
        "physical_state（生理变化，如受伤/植入体异常）、"
        "knowledge_gained（本章新获得的信息）、goal_updated（目标变化）"
    ),
    "timeline_events": (
        "本章发生的关键事件时间线。每个事件包含："
        "event（事件描述）、time_marker（时间标记，如'第一天下午'）"
    ),
    "resource_changes": (
        "本章的资源变动。每项包含："
        "type（gained/lost）、item（资源名称）、detail（变动详情）"
    ),
    "relationship_changes": (
        "本章的关系变动。每项包含："
        "between（[角色A, 角色B]）、"
        "change_type（trust_up/trust_down/alliance/conflict/neutral）、"
        "detail（变动详情）"
    ),
}


def build_state_extraction_prompt(
    chapter_text: str,
    chapter_contract: dict,
    chapter_index: int,
    chapter_title: str,
    prev_state: dict,
) -> str:
    """构造状态提取 prompt。

    :param chapter_text: 本章正文
    :param chapter_contract: 章节合同
    :param chapter_index: 章节序号
    :param chapter_title: 章节标题
    :param prev_state: 前一章状态快照
    :return: JSON 格式的 prompt
    """
    # 简化前一章状态，避免 prompt 过长
    prev_summary: str = prev_state.get("summary", "（首章，无前序状态）")
    prev_chars: list = prev_state.get("character_states", [])

    return json.dumps(
        {
            "task": "提取故事世界状态变化",
            "instructions": (
                "阅读以下章节正文，提取本章结束时故事世界的状态变化。"
                "只提取正文中明确发生的变化，不要推测或虚构。"
                "如果某个维度本章没有变化，返回空列表。"
            ),
            "chapter_info": {
                "chapter_index": chapter_index,
                "chapter_title": chapter_title,
            },
            "chapter_contract": {
                "protagonist_goal": chapter_contract.get("protagonist_goal", ""),
                "irreversible_change": chapter_contract.get(
                    "irreversible_change", ""
                ),
            },
            "prev_state_summary": prev_summary,
            "prev_character_states": [
                {"name": c.get("name", ""), "location": c.get("location", "")}
                for c in prev_chars
                if isinstance(c, dict)
            ],
            "chapter_text": chapter_text[:4000],  # 限制长度
            "output_format": STATE_EXTRACTION_FIELDS,
            "rules": [
                "只记录正文中明确发生的变化，不要推测",
                "character_states 只记录本章有变化的角色",
                "timeline_events 按故事内时间顺序排列",
                "resource_changes 只记录本章获得或失去的资源",
                "relationship_changes 只记录本章发生变动的关系",
                "如果正文信息不足以确定某个字段，留空或返回空列表",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def merge_states(
    prev_state: dict, new_changes: dict
) -> tuple[list, list, list, list, str]:
    """将新变化合并到前一章状态中，生成完整快照。

    :param prev_state: 前一章状态快照
    :param new_changes: 本章提取的状态变化
    :return: (合并后的角色状态, 时间线, 资源变动, 关系变动, 摘要)
    """
    # ── 角色状态：增量合并 ──
    prev_chars: list[dict] = list(prev_state.get("character_states", []))
    new_chars: list[dict] = new_changes.get("character_states", [])

    # 按 name 建索引
    char_map: dict[str, dict] = {
        c.get("name", f"unknown_{i}"): dict(c) for i, c in enumerate(prev_chars)
    }

    for nc in new_chars:
        name: str = nc.get("name", "")
        if not name:
            continue
        if name in char_map:
            # 合并：新值覆盖旧值，knowledge_gained 追加
            existing: dict = char_map[name]
            for key in ("location", "emotional_state", "physical_state", "goal_updated"):
                if nc.get(key):
                    existing[key] = nc[key]
            # 知识追加
            new_knowledge: str = nc.get("knowledge_gained", "")
            if new_knowledge:
                existing_knowledge: str = existing.get("knowledge_gained", "")
                if existing_knowledge:
                    existing["knowledge_gained"] = (
                        existing_knowledge + "；" + new_knowledge
                    )
                else:
                    existing["knowledge_gained"] = new_knowledge
        else:
            char_map[name] = dict(nc)

    merged_chars: list[dict] = list(char_map.values())

    # ── 时间线：追加 ──
    prev_timeline: list = list(prev_state.get("timeline_events", []))
    new_timeline: list = new_changes.get("timeline_events", [])
    merged_timeline: list = prev_timeline + new_timeline

    # ── 资源变动：追加 ──
    prev_resources: list = list(prev_state.get("resource_changes", []))
    new_resources: list = new_changes.get("resource_changes", [])
    merged_resources: list = prev_resources + new_resources

    # ── 关系变动：追加 ──
    prev_rels: list = list(prev_state.get("relationship_changes", []))
    new_rels: list = new_changes.get("relationship_changes", [])
    merged_rels: list = prev_rels + new_rels

    # ── 摘要 ──
    char_names: list[str] = [c.get("name", "?") for c in new_chars]
    summary: str = (
        f"角色变化: {', '.join(char_names) if char_names else '无'}; "
        f"事件: {len(new_timeline)}; "
        f"资源变动: {len(new_resources)}; "
        f"关系变动: {len(new_rels)}"
    )

    return merged_chars, merged_timeline, merged_resources, merged_rels, summary


class StateWriterAgent(BaseAgent):
    """状态回写 Agent —— 从正文提取故事世界状态变化并持久化。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
        story_state_store: Any | None = None,
    ) -> None:
        super().__init__(
            "curator",  # 复用记忆管家的 system prompt
            llm_client,
            state_store,
            tree_store,
            vector_store,
        )
        self._story_state_store: Any | None = story_state_store

    @property
    def story_state_store(self) -> Any:
        """惰性获取 StoryStateStore 实例。"""
        if self._story_state_store is None:
            from ..memory.store import StoryStateStore

            self._story_state_store = StoryStateStore()
        return self._story_state_store

    async def execute(self, input_data: dict) -> dict:
        """执行状态回写。

        :param input_data: 包含以下字段
            - chapter_text: 本章正文
            - chapter_contract: 章节合同
            - chapter_index: 章节序号
            - chapter_title: 章节标题
            - scenes: 本章场景列表（可选，提供额外上下文）
        :return: 包含以下字段
            - chapter_index: 章节序号
            - character_states: 合并后的角色状态
            - timeline_events: 累积时间线
            - resource_changes: 累积资源变动
            - relationship_changes: 累积关系变动
            - summary: 本章状态变化摘要
            - new_changes_count: 本章新提取的变化项数
        """
        chapter_text: str = input_data.get("chapter_text", "")
        chapter_contract: dict = input_data.get("chapter_contract", {})
        chapter_index: int = input_data.get("chapter_index", 0)
        chapter_title: str = input_data.get("chapter_title", "")

        # 获取前一章状态快照
        prev_state: dict = {}
        if chapter_index > 1:
            prev_state = await self.story_state_store.get_snapshot(
                chapter_index - 1
            )

        # 构造 prompt 并调用 LLM
        prompt: str = build_state_extraction_prompt(
            chapter_text, chapter_contract, chapter_index, chapter_title, prev_state
        )

        result: dict = await self._call_and_parse(
            prompt, temperature=0.2, max_tokens=2048
        )

        # 确保四个维度都是列表
        for field in STATE_EXTRACTION_FIELDS:
            value = result.get(field, [])
            if not isinstance(value, list):
                result[field] = []

        # 合并前一章状态
        (
            merged_chars,
            merged_timeline,
            merged_resources,
            merged_rels,
            summary,
        ) = merge_states(prev_state, result)

        # 计算本章新变化项数
        new_count: int = (
            len(result.get("character_states", []))
            + len(result.get("timeline_events", []))
            + len(result.get("resource_changes", []))
            + len(result.get("relationship_changes", []))
        )

        # 持久化
        await self.story_state_store.save_snapshot(
            chapter_index=chapter_index,
            chapter_title=chapter_title,
            character_states=merged_chars,
            timeline_events=merged_timeline,
            resource_changes=merged_resources,
            relationship_changes=merged_rels,
            summary=summary,
        )

        logger.info(
            "状态回写完成（第%d章「%s」）: 角色状态=%d, 时间线=%d, "
            "资源变动=%d, 关系变动=%d, 新变化=%d",
            chapter_index,
            chapter_title,
            len(merged_chars),
            len(merged_timeline),
            len(merged_resources),
            len(merged_rels),
            new_count,
        )

        return {
            "chapter_index": chapter_index,
            "character_states": merged_chars,
            "timeline_events": merged_timeline,
            "resource_changes": merged_resources,
            "relationship_changes": merged_rels,
            "summary": summary,
            "new_changes_count": new_count,
        }
