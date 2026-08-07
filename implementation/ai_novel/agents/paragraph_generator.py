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
- 章节合同（Chapter Contract）：
  * protagonist_goal → 主角行动意图贯穿正文
  * failure_cost → 代价感知渗透到内省层
  * irreversible_change → 章末场景必须呈现该变化
  * read_on_hook → 最后一个场景结尾必须实现该钩子
  * reader_question → 正文应自然引发该疑问

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


# ------------------------------------------------------------------
# 章节合同 → L4 写作指令转换
# ------------------------------------------------------------------

def build_l4_contract_directives(
    contract: dict, is_last_scene: bool
) -> list[str]:
    """将章节合同转换为 L4 段落生成器的写作指令。

    与 L3 的 contract_to_constraints 不同，这里不是硬约束，
    而是指导 LLM「怎么写」的写作方向：

    - protagonist_goal → 让主角的行动和内省被这个目标驱动
    - failure_cost → 在内省层或对话中渗透代价感知
    - reader_question → 正文应自然引发读者的这个疑问（不要直接问出来）
    - irreversible_change（仅最后场景）→ 本场景必须呈现这个不可逆变化
    - read_on_hook（仅最后场景）→ 结尾必须落在这个钩子上

    :param contract: 章节合同
    :param is_last_scene: 是否是本章最后一个场景
    :return: 写作指令列表
    """
    directives: list[str] = []

    # ── 全场景适用的指令 ──
    goal: str = contract.get("protagonist_goal", "")
    if goal:
        directives.append(
            f"【主角驱动】主角的行动和内心活动应被这个目标驱动：{goal}"
            "——不要直接写出目标，让读者通过主角的选择和行为感知到"
        )

    cost: str = contract.get("failure_cost", "")
    if cost:
        directives.append(
            f"【代价感知】在内省层或对话中渗透失败代价：{cost}"
            "——不要说教式地列举代价，让读者通过细节和情绪感受到压力"
        )

    question: str = contract.get("reader_question", "")
    if question:
        directives.append(
            f"【读者疑问】正文应自然引发读者的这个疑问：{question}"
            "——不要在正文中直接提出这个问题，而是通过情节细节让读者自己想到"
        )

    # ── 仅最后一个场景适用的指令 ──
    if is_last_scene:
        change: str = contract.get("irreversible_change", "")
        if change:
            directives.append(
                f"【不可逆变化】本场景结尾必须呈现这个不可逆变化：{change}"
                "——变化应该是已发生的事实，不是'即将发生'的预告"
            )

        hook: str = contract.get("read_on_hook", "")
        if hook:
            directives.append(
                f"【追读钩子】本场景的最后一个段落必须落在这个钩子上：{hook}"
                "——结尾要制造具体悬念或紧迫感，不要用'故事还在继续'式的空泛收尾"
            )

    return directives


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
            - chapter_contract: (可选) 章节合同，提供时将合同写作指令注入 prompt
            - is_last_scene: (可选) 是否本章最后一个场景，默认 False
        :return: 包含以下字段
            - scene_id: 场景 ID
            - content: 生成的正文
            - word_count: 实际字数
            - layers_used: 使用的叠加层
            - foreshadow_planted: 已埋设的伏笔
            - contract_directives_applied: 已应用的合同指令数
        """
        # ── 提取章节合同并生成写作指令 ──
        chapter_contract: dict = input_data.get("chapter_contract", {})
        is_last_scene: bool = input_data.get("is_last_scene", False)

        contract_directives: list[str] = []
        if chapter_contract:
            contract_directives = build_l4_contract_directives(
                chapter_contract, is_last_scene
            )

        # 将写作指令合并到 constraints 中，让 LLM 在生成时感知合同
        enhanced_input: dict = dict(input_data)
        if contract_directives:
            original_constraints: list = input_data.get("constraints", [])
            enhanced_input["constraints"] = (
                list(original_constraints) + contract_directives
            )
            # 同时将合同原文传入，供 LLM 参考
            enhanced_input["chapter_contract"] = chapter_contract
            enhanced_input["is_last_scene"] = is_last_scene

        user_message: str = self._build_user_message(enhanced_input)

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

        scene_id: str = input_data.get("scene", {}).get("scene_id", "?")
        logger.info(
            "段落生成完成: scene=%s, 字数=%d, 层=%s, 合同指令=%d%s",
            scene_id,
            word_count,
            layers_used,
            len(contract_directives),
            ", 末场" if is_last_scene else "",
        )

        return {
            "scene_id": scene_id,
            "chapter_index": input_data.get("chapter_index", 0),
            "scene_index": input_data.get("scene_index", 0),
            "content": content,
            "word_count": word_count,
            "word_target": word_target,
            "layers_used": layers_used,
            "foreshadow_planted": foreshadow_planted,
            "quality_mode": quality_mode,
            "contract_directives_applied": len(contract_directives),
            "is_last_scene": is_last_scene,
        }
