"""
协调者状态机 —— 元认知调度核心

Phase 1 简化版：使用 Python 状态机驱动固定序列（发散→收敛→固化→审视→人机节点），
不调用协调者 LLM 做每步调度（Phase 3 再接入）。

状态流转：
  P0 样本拆解 → P1 L0 世界观 → P2 L1 人物网 → P3 L2 情节弧
  每层内部：发散(园丁) → 收敛(剪枝师) → 固化(记忆管家) → 审视(监工) → [人机节点]

断点续写：每次状态变更后写入 SQLite，中断后可从断点恢复。
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from .agents import (
    CuratorAgent,
    DecoderAgent,
    DistillerAgent,
    GardenerAgent,
    InspectorAgent,
    ParagraphGeneratorAgent,
    PrunerAgent,
    SceneDecomposerAgent,
)
from .llm_client import LLMClient
from .memory.store import (
    AgentLog,
    ConstraintStore,
    ForeshadowRegistry,
    NovelStateStore,
    TreeStore,
)
from .memory.vector_store import VectorStore
from .metrics.quality import QualityMetrics

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    """流水线阶段"""
    P0_DECOMPOSE = "P0"
    P1_WORLDVIEW = "P1"
    P2_CHARACTERS = "P2"
    P3_PLOT = "P3"
    P4_SCENES = "P4"
    P5_PARAGRAPHS = "P5"
    P6_UNIFY = "P6"
    SUSPENDED = "SUSPENDED"


class Action(str, Enum):
    """动作循环的各阶段"""
    DIVERGE = "发散"
    CONVERGE = "收敛"
    SOLIDIFY = "固化"
    INSPECT = "审视"
    HUMAN_GATE = "人机节点"
    DISTILL = "蒸馏"
    RETRACE = "回溯"
    DONE = "完成"


# 每个阶段对应的层级
PHASE_LAYER_MAP = {
    Phase.P1_WORLDVIEW: "L0",
    Phase.P2_CHARACTERS: "L1",
    Phase.P3_PLOT: "L2",
    Phase.P4_SCENES: "L3",
    Phase.P5_PARAGRAPHS: "L4",
}

# 人机门禁节点
HUMAN_GATE_PHASES = {Phase.P1_WORLDVIEW, Phase.P2_CHARACTERS, Phase.P3_PLOT}

# 每层的发散目标模板
LAYER_OBJECTIVES = {
    "L0": "构建科幻悬疑小说的世界观：核心科技设定、社会结构、时间线、规则体系",
    "L1": "设计人物网络：主角及核心配角的动机、关系图谱、弧光轨迹、语言特征",
    "L2": "设计情节弧：三幕结构、章节拆解、伏笔埋设计划、关键转折点",
    "L3": "分解场景：每场景的简报、空间图、冲突点、情感目标",
    "L4": "生成段落：按感官→内省→对话→推进四层叠加生成",
}

# 每层禁止的套路
LAYER_FORBID = {
    "L0": [
        "最常见的设定：AI 觉醒/反叛人类",
        "赛博朋克套皮：霓虹灯+大公司+黑客",
        "时间旅行悖论作为核心设定",
    ],
    "L1": [
        "主角是无父无母的天才孤儿",
        "反派是纯粹的邪恶，没有可理解的动机",
        "女主角只是花瓶/恋爱对象",
    ],
    "L2": [
        "第一幕用凶案现场开场",
        "主角直接卷入核心事件",
        "用梦境/闪回作为信息倾倒",
        "高潮是正面对决而非智力博弈",
    ],
}


class Orchestrator:
    """
    协调者状态机

    Phase 1 简化版：固定序列驱动，不做 LLM 元认知调度。
    Phase 3 将接入协调者 LLM 做动态调度。
    """

    def __init__(self, config: dict, book_id: str = "sf_mystery_001") -> None:
        self.config = config
        self.book_id = book_id

        # 初始化所有基础设施
        self._init_infra()

        # 初始化所有 Agent
        self._init_agents()

        # 质量度量
        self.metrics = QualityMetrics(config)

        # 当前状态
        self.current_phase: Phase = Phase.P1_WORLDVIEW
        self.current_action: Action = Action.DIVERGE
        self.tree_version: int = 0
        self.max_retries: int = 3
        self._last_distillation: dict | None = None

    def _init_infra(self) -> None:
        """初始化存储层和 LLM 客户端"""
        # 判断是否使用 Mock 模式
        import os
        mock_mode = (
            self.config.get("llm_mode") == "mock"
            or os.environ.get("AI_NOVEL_MOCK") == "1"
        )
        if mock_mode:
            from .mock_llm_client import MockLLMClient
            self.llm = MockLLMClient(self.config)
            logger.info("使用 MockLLMClient（无需 API Key）")
        else:
            # LLMClient 自行从 config.yaml 加载配置（接受路径或 None）
            self.llm = LLMClient()
        # 将 book_id 传入 NovelStateStore，确保状态查询/更新使用正确的 book_id
        self.state_store = NovelStateStore(book_id=self.book_id)
        self.tree_store = TreeStore()
        self.constraint_store = ConstraintStore()
        self.foreshadow_registry = ForeshadowRegistry()
        self.agent_log = AgentLog()

        storage_cfg = self.config.get("storage", {})
        chroma_path = storage_cfg.get("chroma_path", "chroma_db/")
        self.vector_store = VectorStore(chroma_path)

    def _init_agents(self) -> None:
        """初始化所有 Agent"""
        common_args = {
            "llm_client": self.llm,
            "state_store": self.state_store,
            "tree_store": self.tree_store,
            "vector_store": self.vector_store,
        }
        self.gardener = GardenerAgent(**common_args)
        self.pruner = PrunerAgent(**common_args)
        self.curator = CuratorAgent(
            **common_args,
            constraint_store=self.constraint_store,
            foreshadow_registry=self.foreshadow_registry,
        )
        self.inspector = InspectorAgent(**common_args)
        self.distiller = DistillerAgent(**common_args)
        self.decoder = DecoderAgent(**common_args)
        self.scene_decomposer = SceneDecomposerAgent(**common_args)
        self.paragraph_generator = ParagraphGeneratorAgent(**common_args)

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------

    async def save_state(self) -> None:
        """保存当前状态到 SQLite"""
        await self.state_store.update_state(
            current_phase=self.current_phase.value,
            current_layer=PHASE_LAYER_MAP.get(self.current_phase, ""),
            current_action=self.current_action.value,
            tree_version=self.tree_version,
        )
        logger.info(
            "状态已保存: phase=%s, action=%s, version=%d",
            self.current_phase.value,
            self.current_action.value,
            self.tree_version,
        )

    async def load_state(self) -> None:
        """从 SQLite 恢复状态"""
        state = await self.state_store.get_state()
        if state:
            phase_str = state.get("current_phase") or "P1"
            action_str = state.get("current_action") or "发散"
            self.current_phase = Phase(phase_str)
            self.current_action = Action(action_str)
            self.tree_version = state.get("tree_version", 0) or 0
            logger.info(
                "状态已恢复: phase=%s, action=%s, version=%d",
                self.current_phase.value,
                self.current_action.value,
                self.tree_version,
            )

    # ------------------------------------------------------------------
    # 单层动作循环（核心）
    # ------------------------------------------------------------------

    async def run_layer_cycle(self, layer: str, quality_mode: str = "precision") -> dict:
        """
        执行一层的完整动作循环：发散→收敛→固化→审视→[人机节点]

        :param layer: 目标层级 (L0/L1/L2)
        :param quality_mode: fast | precision
        :return: 该层的最终产出
        """
        retry_count = 0

        while retry_count < self.max_retries:
            logger.info("=== %s 动作循环开始 (尝试 %d/%d) ===", layer, retry_count + 1, self.max_retries)

            # 1. 检索上下文
            context = await self._retrieve_context(layer)

            # 2. 发散（园丁）
            self.current_action = Action.DIVERGE
            await self.save_state()
            diverge_result = await self._do_diverge(layer, context, quality_mode)
            await self.agent_log.log(
                agent="gardener", action="发散", layer=layer,
                input_data={"objective": LAYER_OBJECTIVES.get(layer, "")},
                output_data=diverge_result,
                metrics={},
            )

            # 3. 收敛（剪枝师）
            self.current_action = Action.CONVERGE
            await self.save_state()
            converge_result = await self._do_converge(layer, diverge_result, context)
            await self.agent_log.log(
                agent="pruner", action="收敛", layer=layer,
                input_data={"candidates_count": len(diverge_result.get("candidates", []))},
                output_data=converge_result,
                metrics={},
            )

            # 4. 固化（记忆管家）
            self.current_action = Action.SOLIDIFY
            await self.save_state()
            solidify_result = await self._do_solidify(layer, converge_result)
            self.tree_version = solidify_result.get("new_version", self.tree_version + 1)
            await self.agent_log.log(
                agent="curator", action="固化", layer=layer,
                input_data={"selected": converge_result.get("selected", "")},
                output_data=solidify_result,
                metrics={},
            )

            # 5. 审视（监工）
            self.current_action = Action.INSPECT
            await self.save_state()
            inspect_result = await self._do_inspect(layer, solidify_result, context, quality_mode)
            await self.agent_log.log(
                agent="inspector", action="审视", layer=layer,
                input_data={},
                output_data=inspect_result,
                metrics=inspect_result.get("metrics", {}),
            )

            verdict = inspect_result.get("verdict", "fail")

            if verdict == "pass":
                # 6. 人机节点
                if self.current_phase in HUMAN_GATE_PHASES:
                    self.current_action = Action.HUMAN_GATE
                    await self.save_state()
                    approved, feedback = await self._human_gate(layer, solidify_result)
                    if not approved:
                        logger.info("人机节点未通过，反馈: %s", feedback)
                        retry_count += 1
                        # 将反馈加入下次发散的 forbid
                        continue
                # 通过！返回产出
                self.current_action = Action.DONE
                await self.save_state()
                return solidify_result

            elif verdict == "warn":
                # 有警告但无致命问题，可以推进但记录
                logger.warning("审视有警告但无致命问题: %s", inspect_result.get("issues", []))
                if self.current_phase in HUMAN_GATE_PHASES:
                    self.current_action = Action.HUMAN_GATE
                    await self.save_state()
                    approved, feedback = await self._human_gate(layer, solidify_result)
                    if not approved:
                        retry_count += 1
                        continue
                self.current_action = Action.DONE
                await self.save_state()
                return solidify_result

            else:
                # fail → 重试
                retry_count += 1
                logger.warning(
                    "审视未通过 (尝试 %d/%d)，问题: %s",
                    retry_count, self.max_retries, inspect_result.get("issues", []),
                )

        # 超过最大重试次数
        logger.error("%s 动作循环超过最大重试次数 %d", layer, self.max_retries)
        return {"status": "failed", "layer": layer, "reason": "超过最大重试次数"}

    # ------------------------------------------------------------------
    # 动作执行
    # ------------------------------------------------------------------

    async def _retrieve_context(self, layer: str) -> dict:
        """检索上层约束和相关上下文"""
        # 获取所有上层约束
        constraints = []
        layer_order = ["L0", "L1", "L2", "L3", "L4"]
        current_idx = layer_order.index(layer)
        for i in range(current_idx):
            upper_layer = layer_order[i]
            upper_constraints = await self.constraint_store.get_constraints(upper_layer)
            constraints.extend(upper_constraints or [])

        # 获取上层产出
        upper_outputs = {}
        for i in range(current_idx):
            upper_layer = layer_order[i]
            upper_output = await self.tree_store.get_layer(upper_layer)
            if upper_output:
                upper_outputs[upper_layer] = upper_output

        # 获取伏笔状态（L2 及以上）
        foreshadow_status = []
        if current_idx >= 2:
            foreshadow_status = await self.foreshadow_registry.get_status()

        return {
            "constraints": constraints,
            "upper_outputs": upper_outputs,
            "foreshadow_status": foreshadow_status,
        }

    async def _do_diverge(self, layer: str, context: dict, quality_mode: str) -> dict:
        """执行发散动作"""
        input_data = {
            "target_layer": layer,
            "objective": LAYER_OBJECTIVES.get(layer, ""),
            "constraints": context.get("constraints", []),
            "forbid": LAYER_FORBID.get(layer, []),
            "quality_mode": quality_mode,
        }
        return await self.gardener.execute(input_data)

    async def _do_converge(self, layer: str, diverge_result: dict, context: dict) -> dict:
        """执行收敛动作"""
        input_data = {
            "candidates": diverge_result.get("candidates", []),
            "target_layer": layer,
            "constraints": context.get("constraints", []),
            "evaluation_criteria": f"层级 {layer} 的评分维度及权重",
        }
        return await self.pruner.execute(input_data)

    async def _do_solidify(self, layer: str, converge_result: dict) -> dict:
        """执行固化动作"""
        input_data = {
            "mode": "solidify",
            "target_layer": layer,
            "content": {
                "selected_item": converge_result.get("selected", ""),
                "selection_rationale": converge_result.get("selection_rationale", ""),
                "scores": converge_result.get("scores", []),
            },
            "tree_version": self.tree_version,
        }
        return await self.curator.execute(input_data)

    async def _do_inspect(
        self, layer: str, solidify_result: dict, context: dict, quality_mode: str
    ) -> dict:
        """执行审视动作"""
        # 获取固化后的内容
        content = await self.tree_store.get_layer(layer)
        input_data = {
            "target_layer": layer,
            "content": json.dumps(content, ensure_ascii=False) if content else "",
            "constraints": context.get("constraints", []),
            "foreshadow_registry": context.get("foreshadow_status", []),
            "quality_mode": quality_mode,
        }
        return await self.inspector.execute(input_data)

    # ------------------------------------------------------------------
    # 人机节点（命令行 y/n 交互）
    # ------------------------------------------------------------------

    async def _human_gate(self, layer: str, solidify_result: dict) -> tuple[bool, str]:
        """
        人机门禁节点 —— 命令行交互

        Mock 模式下自动通过。

        :return: (是否通过, 反馈意见)
        """
        # Mock 模式自动通过
        import os
        if os.environ.get("AI_NOVEL_MOCK") == "1" or self.config.get("llm_mode") == "mock":
            logger.info("[MOCK] 人机门禁自动通过: %s", layer)
            return True, ""

        layer_names = {
            "L0": "世界观",
            "L1": "人物网络",
            "L2": "情节弧",
        }
        layer_name = layer_names.get(layer, layer)

        # 获取固化后的完整内容
        content = await self.tree_store.get_layer(layer)

        print("\n" + "=" * 60)
        print(f"  人机门禁节点 · {layer_name} ({layer}) 确认")
        print("=" * 60)

        # 展示产出
        if content:
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
            # 限制显示长度
            if len(content_str) > 3000:
                content_str = content_str[:3000] + "\n... (内容过长，已截断)"
            print(content_str)

        print("\n" + "-" * 60)
        print("选项:")
        print("  y / yes     → 确认通过，进入下一层")
        print("  n / no      → 不通过，重新发散")
        print("  其他文字    → 作为修改意见反馈给园丁重新发散")
        print("-" * 60)

        try:
            user_input = input("请输入: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False, "用户中断"

        if user_input.lower() in ("y", "yes", "通过", "确认"):
            return True, ""
        elif user_input.lower() in ("n", "no", "不通过", "拒绝"):
            return False, "用户拒绝，未给出具体原因"
        else:
            return False, user_input

    # ------------------------------------------------------------------
    # 蒸馏
    # ------------------------------------------------------------------

    async def run_distillation(self) -> dict:
        """执行主题蒸馏（L2 固化后调用）"""
        solidified_layers = {}
        for layer in ["L0", "L1", "L2"]:
            content = await self.tree_store.get_layer(layer)
            if content:
                solidified_layers[layer] = content

        input_data = {
            "solidified_layers": solidified_layers,
            "current_chapters": [],
            "previous_distillation": None,
        }
        result = await self.distiller.execute(input_data)
        await self.agent_log.log(
            agent="distiller", action="蒸馏", layer="L2",
            input_data={}, output_data=result,
            metrics={},
        )
        return result

    # ------------------------------------------------------------------
    # 反向拆解
    # ------------------------------------------------------------------

    async def run_decompose(
        self,
        novel_title: str,
        novel_author: str,
        novel_genre: str,
        text_content: str,
        text_source: str = "chapter_summary",
        existing_analysis: list | None = None,
    ) -> dict:
        """执行反向拆解"""
        input_data = {
            "novel_title": novel_title,
            "novel_author": novel_author,
            "novel_genre": novel_genre,
            "text_source": text_source,
            "text_content": text_content,
            "existing_analysis": existing_analysis or [],
        }
        result = await self.decoder.execute(input_data)
        await self.agent_log.log(
            agent="decoder", action="拆解", layer="P0",
            input_data={"novel_title": novel_title},
            output_data=result,
            metrics={},
        )
        return result

    # ------------------------------------------------------------------
    # L0→L2 单链路运行
    # ------------------------------------------------------------------

    async def run_l0_l2(self) -> dict:
        """
        运行 L0→L2 单链路：
        P1(L0 世界观) → P2(L1 人物网) → P3(L2 情节弧) → 蒸馏

        :return: 完成状态和各层产出
        """
        results = {}

        # L0 世界观
        self.current_phase = Phase.P1_WORLDVIEW
        self.current_action = Action.DIVERGE
        await self.save_state()
        logger.info(">>> P1 L0 世界观建构开始")
        l0_result = await self.run_layer_cycle("L0", quality_mode="precision")
        results["L0"] = l0_result
        if l0_result.get("status") == "failed":
            return results

        # L1 人物网络
        self.current_phase = Phase.P2_CHARACTERS
        self.current_action = Action.DIVERGE
        await self.save_state()
        logger.info(">>> P2 L1 人物网络建构开始")
        l1_result = await self.run_layer_cycle("L1", quality_mode="precision")
        results["L1"] = l1_result
        if l1_result.get("status") == "failed":
            return results

        # L2 情节弧
        self.current_phase = Phase.P3_PLOT
        self.current_action = Action.DIVERGE
        await self.save_state()
        logger.info(">>> P3 L2 情节弧建构开始")
        l2_result = await self.run_layer_cycle("L2", quality_mode="precision")
        results["L2"] = l2_result
        if l2_result.get("status") == "failed":
            return results

        # 蒸馏
        logger.info(">>> 主题蒸馏开始")
        distillation = await self.run_distillation()
        results["distillation"] = distillation
        self._last_distillation = distillation

        # 保存最终大纲
        outline = await self._compile_outline()
        results["outline"] = outline

        return results

    async def _compile_outline(self) -> dict:
        """汇总 L0-L2 产出，生成完整大纲"""
        outline = {}
        for layer in ["L0", "L1", "L2"]:
            content = await self.tree_store.get_layer(layer)
            if content:
                outline[layer] = content

        # 加入蒸馏结果（从最近一次蒸馏产出中提取主题）
        if hasattr(self, "_last_distillation") and self._last_distillation:
            outline["theme"] = self._last_distillation.get("theme_statement", "")
            outline["distillation"] = self._last_distillation
        else:
            outline["theme"] = ""

        # 保存到文件
        import pathlib
        output_path = pathlib.Path(__file__).parent / "output_outline.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(outline, f, ensure_ascii=False, indent=2)
        logger.info("完整大纲已保存到 %s", output_path)

        return outline

    # ------------------------------------------------------------------
    # 生成科幻悬疑候选点子
    # ------------------------------------------------------------------

    async def generate_concept_candidates(self) -> dict:
        """
        基于四部标杆拆解产出的思维模型，生成 3-5 个科幻悬疑核心设定候选。
        由园丁 Agent 执行，但目标层级为"概念生成"（特殊层）。
        """
        input_data = {
            "target_layer": "L0",
            "objective": (
                "基于以下标杆小说的思维模型，生成 3-5 个科幻悬疑核心设定候选。"
                "每个候选必须融合科幻元素（科技设定）和悬疑元素（谜题/诡计），"
                "且有反共识走向。"
            ),
            "constraints": [
                "体裁：科幻悬疑类型融合",
                "语言：中文",
                "目标：网文节奏+标杆文笔",
                "规模：8-15 万字单本",
            ],
            "forbid": [
                "AI 觉醒/反叛人类",
                "赛博朋克套皮",
                "时间旅行悖论",
                "平行宇宙作为核心设定",
                "外星人入侵",
            ],
            "quality_mode": "precision",
        }
        result = await self.gardener.execute(input_data)
        return result

    # ------------------------------------------------------------------
    # L3→L4 场景分解 + 段落生成
    # ------------------------------------------------------------------

    # 第一幕章节元数据（从 L2 大纲提取）
    ACT1_CHAPTERS: list[dict] = [
        {
            "index": 1,
            "title": "死区",
            "summary": "沈语冰在日常使用植入体时发现前同事陈静周围出现死区",
            "key_events": ["沈语冰感知到第一个死区——前同事陈静"],
            "foreshadow_plan": [
                {"id": "fs3", "action": "埋设"},
                {"id": "fs1", "action": "埋设"},
            ],
        },
        {
            "index": 2,
            "title": "信号",
            "summary": "追踪陈静，发现行为异常但本人不自知；苏映首次出场",
            "key_events": ["追踪陈静，发现她近期行为异常但本人不自知"],
            "foreshadow_plan": [
                {"id": "fs1", "action": "推进"},
                {"id": "fs3", "action": "推进"},
            ],
        },
        {
            "index": 3,
            "title": "上门",
            "summary": "姜北辰上门求助，展示女儿的画作",
            "key_events": ["姜北辰上门求助，展示女儿的画作（伏笔fs5）"],
            "foreshadow_plan": [
                {"id": "fs5", "action": "埋设"},
            ],
        },
        {
            "index": 4,
            "title": "扫描",
            "summary": "沈语冰用植入体扫描姜北辰的女儿，确认死区",
            "key_events": [
                "沈语冰用植入体扫描姜北辰的女儿，确认死区",
                "贺明轩出场（伏笔fs2铺垫）",
            ],
            "foreshadow_plan": [
                {"id": "fs2", "action": "埋设"},
            ],
        },
        {
            "index": 5,
            "title": "假说",
            "summary": "苏映提出共振体假说，沈语冰的植入体异常发热",
            "key_events": [
                "苏映提出共振体假说",
                "沈语冰的植入体异常发热（伏笔fs1）",
                "关键转折T1：死区不是'没有情绪'而是'情绪被吃掉了'",
            ],
            "foreshadow_plan": [
                {"id": "fs1", "action": "推进"},
                {"id": "fs3", "action": "推进"},
            ],
        },
    ]

    async def run_l3_l4(self, chapters: list[dict] | None = None) -> dict:
        """
        运行 L3→L4 链路：场景分解 + 段落生成。

        :param chapters: 章节元数据列表，None 时使用第一幕默认值
        :return: 完整产出 {scenes, paragraphs, quality_report}
        """
        if chapters is None:
            chapters = self.ACT1_CHAPTERS

        # 加载 L0/L1/L2 产出作为上下文
        l0 = await self.tree_store.get_layer("L0")
        l1 = await self.tree_store.get_layer("L1")
        l2 = await self.tree_store.get_layer("L2")

        world_rules: list[str] = []
        if l0:
            structured = l0.get("structured", {})
            world_rules = structured.get("world_rules", [])

        character_fingerprints: dict = {}
        if l1:
            structured = l1.get("structured", {})
            for role_key in ("protagonist", "antagonist", "ally", "catalyst"):
                char_data = structured.get(role_key, {})
                if char_data:
                    name = char_data.get("name", "")
                    voice = char_data.get("voice_fingerprint", {})
                    character_fingerprints[name] = voice

        constraints: list[str] = []
        for layer in ("L0", "L1", "L2"):
            layer_constraints = await self.constraint_store.get_constraints(layer)
            constraints.extend(layer_constraints or [])

        all_scenes: list[dict] = []
        all_paragraphs: list[dict] = []
        previous_scenes_text: str = ""

        total_chapters = len(chapters)
        logger.info(">>> L3→L4 链路开始，共 %d 章", total_chapters)

        for ch_meta in chapters:
            ch_idx: int = ch_meta["index"]
            ch_title: str = ch_meta["title"]

            self.current_phase = Phase.P4_SCENES
            self.current_action = Action.DIVERGE
            await self.save_state()
            logger.info(">>> 第 %d 章「%s」场景分解开始", ch_idx, ch_title)

            # ── L3 场景分解 ──
            decompose_input = {
                "chapter_index": ch_idx,
                "chapter_title": ch_title,
                "chapter_summary": ch_meta["summary"],
                "key_events": ch_meta["key_events"],
                "world_rules": world_rules,
                "character_fingerprints": character_fingerprints,
                "constraints": constraints,
                "foreshadow_plan": ch_meta.get("foreshadow_plan", []),
                "quality_mode": "fast",
            }

            decompose_result = await self.scene_decomposer.execute(decompose_input)
            scenes: list[dict] = decompose_result.get("scenes", [])

            await self.agent_log.log(
                agent="scene_decomposer", action="场景分解", layer="L3",
                input_data={"chapter": ch_title},
                output_data=decompose_result,
                metrics={"scene_count": len(scenes)},
            )

            # 存储 L3 场景
            l3_version = self.tree_version + ch_idx
            l3_content = {
                "layer": "L3",
                "chapter_index": ch_idx,
                "chapter_title": ch_title,
                "scenes": scenes,
                "version": l3_version,
            }
            await self.tree_store.save_layer("L3", l3_content, l3_version)

            all_scenes.extend(scenes)
            logger.info(
                "第%d章场景分解完成: %d 个场景, 目标 %d 字",
                ch_idx, len(scenes), decompose_result.get("total_word_target", 0),
            )

            # ── L4 段落生成 ──
            self.current_phase = Phase.P5_PARAGRAPHS
            self.current_action = Action.DIVERGE
            await self.save_state()

            chapter_paragraphs: list[str] = []

            for s_idx, scene in enumerate(scenes):
                scene_id = scene.get("scene_id", f"ch{ch_idx}_s{s_idx+1}")
                logger.info("  生成段落: %s", scene_id)

                gen_input = {
                    "scene": scene,
                    "chapter_index": ch_idx,
                    "scene_index": s_idx + 1,
                    "world_rules": world_rules,
                    "character_fingerprints": character_fingerprints,
                    "constraints": constraints,
                    "previous_scenes_text": previous_scenes_text[-2000:] if previous_scenes_text else "",
                    "foreshadow_plan": scene.get("foreshadow_actions", []),
                    "quality_mode": scene.get("quality_mode", "fast"),
                    "word_target": scene.get("word_target", 1500),
                }

                gen_result = await self.paragraph_generator.execute(gen_input)
                content: str = gen_result.get("content", "")

                # 质量检测
                quality_result = self.metrics.check_all(content, layer="L4")
                gen_result["quality"] = quality_result

                # 伏笔登记
                for fa in scene.get("foreshadow_actions", []):
                    fa_id = fa.get("id", "")
                    fa_action = fa.get("action", "")
                    fa_detail = fa.get("detail", "")
                    if fa_action in ("埋设", "推进") and fa_id:
                        try:
                            await self.foreshadow_registry.register(
                                foreshadow_id=fa_id,
                                planted_chapter=f"第{ch_idx}章",
                                planted_location=f"场景 {scene_id}",
                                detail={
                                    "action": fa_action,
                                    "detail": fa_detail,
                                    "scene_id": scene_id,
                                },
                            )
                        except Exception as e:
                            logger.debug("伏笔登记跳过 %s: %s", fa_id, e)

                await self.agent_log.log(
                    agent="paragraph_generator", action="段落生成", layer="L4",
                    input_data={"scene_id": scene_id},
                    output_data=gen_result,
                    metrics=quality_result,
                )

                all_paragraphs.append(gen_result)
                chapter_paragraphs.append(content)
                previous_scenes_text += "\n\n" + content

            # 存储本章 L4 产出
            l4_version = self.tree_version + ch_idx + 10
            l4_content = {
                "layer": "L4",
                "chapter_index": ch_idx,
                "chapter_title": ch_title,
                "paragraphs": chapter_paragraphs,
                "total_words": sum(len(p) for p in chapter_paragraphs),
                "version": l4_version,
            }
            await self.tree_store.save_layer("L4", l4_content, l4_version)

            logger.info(
                "第%d章段落生成完成: %d 字",
                ch_idx, l4_content["total_words"],
            )

        # ── 汇总 ──
        self.current_phase = Phase.P6_UNIFY
        self.current_action = Action.DONE
        await self.save_state()

        total_words = sum(p.get("word_count", 0) for p in all_paragraphs)
        total_scenes = len(all_scenes)

        # 质量报告
        all_content = "\n\n".join(p.get("content", "") for p in all_paragraphs)
        overall_quality = self.metrics.check_all(all_content, layer="L4")

        # 伏笔状态
        foreshadow_status = await self.foreshadow_registry.get_status()

        result = {
            "status": "completed",
            "chapters_processed": total_chapters,
            "total_scenes": total_scenes,
            "total_words": total_words,
            "scenes": all_scenes,
            "paragraphs": all_paragraphs,
            "quality_report": {
                "overall": overall_quality,
                "per_paragraph": [
                    {
                        "scene_id": p.get("scene_id", ""),
                        "word_count": p.get("word_count", 0),
                        "quality": p.get("quality", {}),
                    }
                    for p in all_paragraphs
                ],
            },
            "foreshadow_status": foreshadow_status,
        }

        # 保存到文件
        import pathlib
        output_path = pathlib.Path(__file__).parent / "output_l3_l4.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("L3→L4 产出已保存到 %s", output_path)

        # 同时保存可读的 Markdown
        md_path = pathlib.Path(__file__).parent / "output_act1.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# 共振体 · 第一幕\n\n")
            current_ch = 0
            for p in all_paragraphs:
                ch = p.get("chapter_index", 0)
                if ch != current_ch:
                    current_ch = ch
                    ch_title = next(
                        (c["title"] for c in chapters if c["index"] == ch),
                        f"第{ch}章",
                    )
                    f.write(f"\n## 第{ch}章 {ch_title}\n\n")
                f.write(p.get("content", ""))
                f.write("\n\n---\n\n")
        logger.info("第一幕 Markdown 已保存到 %s", md_path)

        return result
