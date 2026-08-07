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

章节合同（Chapter Contract）—— 写前约束，确保每章有读者驱动力：
- reader_question: 读者这章最想知道的具体问题是什么？
- protagonist_goal: 主角这章主动想完成什么？
- failure_cost: 失败会失去什么？
- irreversible_change: 章尾会形成什么不可逆的新局面？
- read_on_hook: 读者为什么要马上点下一章？
- scene_change_requirement: 每个场景至少改变一项（信息/关系/风险/资源/目标）

工作流程：
1. 接收 L2 章节大纲 + L0 世界规则 + L1 人物指纹
2. 生成章节合同（Chapter Contract）
3. 为每章生成 2-4 个候选场景分解方案（园丁式发散）
4. 选最优方案（剪枝师式收敛）
5. 输出结构化场景列表

不直接生成正文——那是 L4 段落生成器的职责。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 章节合同字段定义与校验规则
# ------------------------------------------------------------------

CHAPTER_CONTRACT_FIELDS: dict[str, str] = {
    "reader_question": (
        "读者这一章最想知道的具体问题是什么？"
        "（不是'剧情会怎样推进'，而是读者层面的好奇心）"
    ),
    "protagonist_goal": (
        "主角这一章主动想完成什么？"
        "（不能是'了解情况'这种被动目标，必须有明确的行动意图）"
    ),
    "failure_cost": (
        "失败会失去什么？"
        "（代价必须具体——不是'事情会变糟'，而是'失去某个关键证据/盟友/时间窗口'）"
    ),
    "irreversible_change": (
        "章尾会形成什么不可逆的新局面？"
        "（不能是'新的任务来了'，必须是读了下一章也回不到本章开头状态的变化）"
    ),
    "read_on_hook": (
        "读者为什么要马上点下一章？"
        "（不是'故事还没讲完'，而是本章结尾制造的具体悬念或紧迫感）"
    ),
    "scene_change_requirement": (
        "每个场景至少改变一项：信息/关系/风险/资源/目标"
        "（如果某个场景读完和开头状态一样，该场景需要重做）"
    ),
}

# 合同字段最小校验长度（避免空泛回答）
_CONTRACT_MIN_LENGTH: dict[str, int] = {
    "reader_question": 8,
    "protagonist_goal": 6,
    "failure_cost": 6,
    "irreversible_change": 8,
    "read_on_hook": 8,
}


def build_contract_prompt_context(input_data: dict) -> dict:
    """从输入数据中提取章节合同所需的上下文。

    将 L2 章节摘要、关键事件、伏笔计划等信息组织成合同生成所需的上下文。

    :param input_data: SceneDecomposerAgent.execute() 的输入
    :return: 合同生成上下文字典
    """
    return {
        "chapter_index": input_data.get("chapter_index", 1),
        "chapter_title": input_data.get("chapter_title", ""),
        "chapter_summary": input_data.get("chapter_summary", ""),
        "key_events": input_data.get("key_events", []),
        "foreshadow_plan": input_data.get("foreshadow_plan", []),
        "constraints": input_data.get("constraints", []),
        "character_fingerprints": input_data.get("character_fingerprints", {}),
    }


def validate_chapter_contract(contract: dict) -> list[str]:
    """校验章节合同的完整性。

    检查每个必填字段是否存在且非空泛回答。

    :param contract: 待校验的章节合同
    :return: 问题列表（空列表表示通过）
    """
    issues: list[str] = []

    for field, min_len in _CONTRACT_MIN_LENGTH.items():
        value: str = contract.get(field, "")
        if not value or not isinstance(value, str):
            issues.append(f"章节合同缺失字段: {field}")
        elif len(value.strip()) < min_len:
            issues.append(
                f"章节合同字段 {field} 回答过于简短"
                f"（'{value.strip()}'，至少需要 {min_len} 字）"
            )

    return issues


def contract_to_constraints(contract: dict) -> list[str]:
    """将章节合同转换为一组硬约束，注入到场景分解的 prompt 中。

    这样 LLM 在生成场景时会自动遵守合同的驱动逻辑。

    :param contract: 已校验的章节合同
    :return: 约束条件列表
    """
    constraints: list[str] = []

    constraints.append(
        f"【读者驱动】本章必须回答的读者问题：{contract.get('reader_question', '未指定')}"
    )
    constraints.append(
        f"【主角目标】本章主角的主动目标：{contract.get('protagonist_goal', '未指定')}"
    )
    constraints.append(
        f"【失败代价】失败代价：{contract.get('failure_cost', '未指定')}"
    )
    constraints.append(
        f"【不可逆变化】章尾必须形成不可逆新局面：{contract.get('irreversible_change', '未指定')}"
    )
    constraints.append(
        f"【追读钩子】章尾追读钩子：{contract.get('read_on_hook', '未指定')}"
    )
    constraints.append(
        "【场景变化】每个场景至少改变一项：信息/关系/风险/资源/目标"
        "——如果某个场景读完和开头状态一样，需要重做"
    )

    return constraints


class SceneDecomposerAgent(BaseAgent):
    """场景分解师 Agent —— L3 场景简报生成引擎。

    在生成场景之前，先生成一份章节合同（Chapter Contract），
    将读者驱动力、主角目标、失败代价、不可逆变化、追读钩子
    作为硬约束注入到场景分解的 prompt 中。
    """

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

    # ------------------------------------------------------------------
    # 章节合同生成
    # ------------------------------------------------------------------

    async def _generate_chapter_contract(
        self, input_data: dict
    ) -> dict:
        """生成章节合同。

        调用 LLM，基于章节摘要、关键事件和约束，
        生成一份结构化的章节合同。

        :param input_data: 场景分解输入数据
        :return: 章节合同字典
        """
        ctx: dict = build_contract_prompt_context(input_data)

        contract_prompt: str = json.dumps(
            {
                "task": "生成章节合同（Chapter Contract）",
                "instructions": (
                    "根据以下章节信息，为这一章生成一份章节合同。"
                    "合同是写正文前的硬约束，确保本章有足够的读者驱动力。"
                    "每个字段必须具体、可操作，不能是空泛的方向性描述。"
                ),
                "chapter_info": ctx,
                "output_format": CHAPTER_CONTRACT_FIELDS,
                "rules": [
                    "reader_question 必须是读者层面的好奇心，不是作者的剧情安排",
                    "protagonist_goal 必须是主动行动意图，不能是'了解情况'等被动目标",
                    "failure_cost 必须是具体代价，不能是'事情会变糟'",
                    "irreversible_change 必须是读了下一章也回不到本章开头的变化",
                    "read_on_hook 必须是本章结尾制造的具体悬念，不是'故事还没讲完'",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

        result: dict = await self._call_and_parse(
            contract_prompt, temperature=0.6, max_tokens=2048
        )

        # 提取合同字段（LLM 可能在嵌套结构中返回）
        contract: dict = {}
        for field in CHAPTER_CONTRACT_FIELDS:
            value = result.get(field, "")
            if not value and "chapter_contract" in result:
                value = result["chapter_contract"].get(field, "")
            contract[field] = value if isinstance(value, str) else str(value)

        # 补充场景变化要求（固定值，不需要 LLM 生成）
        contract.setdefault(
            "scene_change_requirement",
            "每个场景至少改变一项：信息/关系/风险/资源/目标",
        )

        # 校验合同
        issues: list[str] = validate_chapter_contract(contract)
        if issues:
            logger.warning(
                "章节合同校验发现问题（第%d章）: %s",
                ctx.get("chapter_index", 0),
                "; ".join(issues),
            )
            # 不阻断流程，但记录问题；后续场景分解仍可执行
            contract["_validation_issues"] = issues

        logger.info(
            "章节合同生成完成（第%d章「%s」）: 读者问题=%s, 追读钩子=%s",
            ctx.get("chapter_index", 0),
            ctx.get("chapter_title", ""),
            contract.get("reader_question", "未指定")[:50],
            contract.get("read_on_hook", "未指定")[:50],
        )

        return contract

    # ------------------------------------------------------------------
    # 场景分解主流程
    # ------------------------------------------------------------------

    async def execute(self, input_data: dict) -> dict:
        """
        执行场景分解。

        流程：
        1. 生成章节合同（Chapter Contract）
        2. 将合同约束注入场景分解 prompt
        3. 调用 LLM 生成场景列表
        4. 质量门禁检查
        5. 返回结构化场景 + 章节合同

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
            - skip_contract: (可选) 跳过合同生成，用于快速测试
        :return: 包含以下字段
            - chapter_index: 章节序号
            - chapter_title: 章节标题
            - chapter_contract: 章节合同
            - scenes: 场景简报列表
            - total_word_target: 总目标字数
            - scene_count: 场景数
        """
        # ── Step 1: 生成章节合同 ──
        skip_contract: bool = input_data.get("skip_contract", False)
        chapter_contract: dict = {}

        if not skip_contract:
            chapter_contract = await self._generate_chapter_contract(input_data)
        else:
            logger.info(
                "跳过章节合同生成（第%d章）",
                input_data.get("chapter_index", 0),
            )

        # ── Step 2: 将合同约束注入到场景分解的输入中 ──
        contract_constraints: list[str] = contract_to_constraints(
            chapter_contract
        ) if chapter_contract else []

        # 合并原有约束 + 合同约束
        enhanced_input: dict = dict(input_data)
        original_constraints: list = input_data.get("constraints", [])
        enhanced_input["constraints"] = (
            list(original_constraints) + contract_constraints
        )
        # 将合同传递给 LLM，使其在生成场景时参考
        if chapter_contract:
            enhanced_input["chapter_contract"] = chapter_contract

        # ── Step 3: 生成场景列表 ──
        user_message: str = self._build_user_message(enhanced_input)

        # 场景分解用中等温度（0.7），需要结构化但有创意
        result: dict = await self._call_and_parse(
            user_message, temperature=0.7, max_tokens=4096
        )

        scenes: list[dict] = result.get("scenes", [])

        # ── Step 4: 质量门禁 ──
        # 4a. 至少 2 个场景
        if len(scenes) < 2:
            logger.warning(
                "场景分解质量门禁未通过（场景数=%d），重跑", len(scenes)
            )
            result = await self._call_and_parse(
                user_message, temperature=0.9, max_tokens=4096
            )
            scenes = result.get("scenes", [])

        # 4b. 合同约束验证：每个场景是否有变化
        if chapter_contract and scenes:
            scenes = self._verify_scene_changes(scenes, chapter_contract)

        # ── Step 5: 补充元数据 ──
        chapter_index: int = input_data.get("chapter_index", 1)
        for i, scene in enumerate(scenes):
            scene.setdefault("scene_id", f"ch{chapter_index}_s{i + 1}")
            scene.setdefault("narrative_function", "推进情节")
            scene.setdefault("foreshadow_actions", [])
            scene.setdefault("word_target", 1500)
            scene.setdefault("quality_mode", input_data.get("quality_mode", "fast"))

        total_word_target: int = sum(s.get("word_target", 1500) for s in scenes)

        logger.info(
            "场景分解完成: 第%d章, 场景数=%d, 目标字数=%d, 合同校验=%s",
            chapter_index,
            len(scenes),
            total_word_target,
            "通过" if not chapter_contract.get("_validation_issues") else "有警告",
        )

        return {
            "chapter_index": chapter_index,
            "chapter_title": input_data.get("chapter_title", ""),
            "chapter_contract": chapter_contract,
            "scenes": scenes,
            "total_word_target": total_word_target,
            "scene_count": len(scenes),
        }

    # ------------------------------------------------------------------
    # 场景变化验证
    # ------------------------------------------------------------------

    def _verify_scene_changes(
        self, scenes: list[dict], contract: dict
    ) -> list[dict]:
        """验证每个场景是否有实质变化。

        检查场景的 narrative_function 和 conflict，
        如果某个场景看起来没有改变任何状态，标记警告。

        :param scenes: 场景列表
        :param contract: 章节合同
        :return: 可能被标注的场景列表
        """
        change_dimensions: list[str] = ["信息", "关系", "风险", "资源", "目标"]

        for i, scene in enumerate(scenes):
            conflict: str = scene.get("conflict", "")
            function: str = scene.get("narrative_function", "")

            # 简单启发式检查：如果冲突描述太短或功能不明确
            if len(conflict) < 10:
                scene.setdefault("_contract_warnings", []).append(
                    f"场景冲突描述过短（'{conflict}'），"
                    f"可能无法实现合同要求的不可逆变化"
                )
                logger.warning(
                    "场景 %s 冲突描述过短，可能不符合合同要求",
                    scene.get("scene_id", f"s{i+1}"),
                )

            # 检查场景是否有变化标记（可选字段，LLM 可以生成）
            scene_change: str = scene.get("scene_change", "")
            if not scene_change:
                # 自动推断变化维度
                inferred_changes: list[str] = []
                if "信息" in conflict or "发现" in conflict or "揭示" in conflict:
                    inferred_changes.append("信息")
                if "关系" in conflict or "信任" in conflict or "背叛" in conflict:
                    inferred_changes.append("关系")
                if "危险" in conflict or "威胁" in conflict or "暴露" in conflict:
                    inferred_changes.append("风险")
                if "资源" in conflict or "获得" in conflict or "失去" in conflict:
                    inferred_changes.append("资源")
                if "目标" in conflict or "决定" in conflict or "选择" in conflict:
                    inferred_changes.append("目标")

                if not inferred_changes:
                    inferred_changes = ["推进情节"]  # 默认

                scene["scene_change"] = " / ".join(inferred_changes)

        return scenes
