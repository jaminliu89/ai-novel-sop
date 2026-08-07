"""
监工·审视 Agent

职责：找问题不解决问题。只审查不修改——避免"既当运动员又当裁判"。

核心铁律：
- 发现问题后输出审查报告，交回协调者调度重写
- 绝不自己改

审查清单（五维度）：
1. 层间一致性：是否违反上层硬约束、世界观、人物动机、时间线
2. 人物声音：对话是否符合角色语言指纹、性格是否漂移、多角色可区分
3. 叙事质量：重复率、AI 腔密度、廉价和解、未赚到的转折、套路收尾
4. 伏笔系统：伏笔推进、新埋设登记、遗忘伏笔
5. 弧光推进：本场景是否推动人物弧光、弧光覆盖率

判定规则：
- 任一 ✗ → verdict = "fail" → 必须重写
- 有 ⚠️ 但无 ✗ → verdict = "warn" → 可推进但记录
- 全 ✓ → verdict = "pass" → 可推进

同时用代码做客观检测（重复率、AI 腔词表）补充 LLM 主观判断：
- 如果客观检测发现 AI 腔或重复率超标，升级 verdict
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class InspectorAgent(BaseAgent):
    """监工 Agent —— 审视动作引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
        quality_metrics: Any | None = None,
    ) -> None:
        """
        初始化监工。

        :param quality_metrics: QualityMetrics 实例，如未提供则惰性初始化
        """
        super().__init__(
            "inspector", llm_client, state_store, tree_store, vector_store
        )
        self._quality_metrics: Any | None = quality_metrics

    @property
    def quality_metrics(self) -> Any | None:
        """惰性初始化 QualityMetrics 实例。"""
        if self._quality_metrics is None:
            try:
                from ..metrics.quality import QualityMetrics

                self._quality_metrics = QualityMetrics(config={})
            except Exception as e:
                logger.warning("无法初始化 QualityMetrics: %s，客观检测将被跳过", e)
                self._quality_metrics = None
        return self._quality_metrics

    async def execute(self, input_data: dict) -> dict:
        """
        执行审视动作。

        :param input_data: 包含以下字段
            - target_layer: 目标层级
            - content: 待审视的产出文本
            - constraints: 上层硬约束列表
            - foreshadow_registry: 伏笔登记表当前状态
            - quality_mode: fast | precision
                fast 模式只查层间一致性 + AI 腔 + 重复率
                precision 模式全量五维度审查
        :return: 审查报告 {verdict, checks, issues, metrics}
        """
        content: str = input_data.get("content", "")
        target_layer: str = input_data.get("target_layer", "L4")

        user_message: str = self._build_user_message(input_data)

        # 审视需要极低温度（0.1）
        result: dict = await self._call_and_parse(
            user_message, temperature=0.1, max_tokens=4096
        )

        # 确保关键字段存在
        result.setdefault("verdict", "warn")
        result.setdefault("checks", [])
        result.setdefault("issues", [])
        result.setdefault("metrics", {})
        result.setdefault("target_layer", target_layer)

        # 代码客观检测补充 LLM 主观判断
        objective_metrics: dict = self._objective_checks(content, target_layer)

        # 合并 metrics（客观检测结果覆盖 LLM 的同名指标）
        llm_metrics: dict = result.get("metrics", {})
        llm_metrics.update(objective_metrics)
        result["metrics"] = llm_metrics

        # 用客观检测结果补充/修正审查报告
        self._augment_with_objective_findings(result, objective_metrics, target_layer)

        logger.info(
            "审视完成: verdict=%s, 客观检测=%s",
            result.get("verdict"),
            {k: round(v, 4) if isinstance(v, float) else v for k, v in objective_metrics.items()},
        )

        return result

    # ------------------------------------------------------------------
    # 客观检测
    # ------------------------------------------------------------------

    def _objective_checks(self, content: str, layer: str) -> dict:
        """
        代码客观检测：重复率、AI 腔密度。

        L0-L2 为结构化大纲数据（JSON），不适用散文级重复率检测；
        仅 L3（场景）和 L4（段落）做全量客观检测。

        :param content: 待检测文本
        :param layer: 目标层级
        :return: 客观指标字典 {repetition_rate, ai_ism_count}
        """
        metrics: dict[str, Any] = {}

        # L0-L2 为大纲层，跳过重复率检测（结构化数据天然有重复关键词）
        if layer in ("L0", "L1", "L2"):
            metrics["repetition_rate"] = 0.0
            metrics["ai_ism_count"] = 0
            metrics["objective_passed"] = True
            metrics["skipped"] = True
            metrics["skip_reason"] = f"层 {layer} 为结构化大纲，跳过散文级检测"
            return metrics

        qm = self.quality_metrics
        if qm is None:
            logger.warning("QualityMetrics 不可用，跳过客观检测")
            return metrics

        try:
            check_result: dict = qm.check_all(content, layer=layer)
            metrics["repetition_rate"] = check_result.get("repetition_rate", 0.0)
            metrics["ai_ism_count"] = check_result.get("ai_ism_count", 0)
            metrics["objective_passed"] = check_result.get("passed", True)
        except Exception as e:
            logger.error("客观检测失败: %s", e)
            metrics["objective_error"] = str(e)

        return metrics

    # ------------------------------------------------------------------
    # 客观检测补充
    # ------------------------------------------------------------------

    def _augment_with_objective_findings(
        self,
        result: dict,
        metrics: dict,
        target_layer: str,
    ) -> None:
        """
        用客观检测结果补充/修正 LLM 审查报告。

        如果客观检测发现 AI 腔或重复率超标：
        - 在 checks 中追加客观检测项
        - 在 issues 中追加对应问题
        - 必要时升级 verdict 为 "fail"

        :param result: LLM 审查报告（原地修改）
        :param metrics: 客观检测指标
        :param target_layer: 目标层级
        """
        checks: list[dict] = result.get("checks", [])
        issues: list[dict] = result.get("issues", [])

        ai_ism_count: int = metrics.get("ai_ism_count", 0)
        repetition_rate: float = metrics.get("repetition_rate", 0.0)

        # AI 腔检测：任何禁用词出现都标记为不通过
        if ai_ism_count > 0:
            checks.append(
                {
                    "item": "AI腔密度（客观检测）",
                    "status": "\u2717",
                    "note": f"检测到 {ai_ism_count} 个 AI 腔禁用词",
                }
            )
            issues.append(
                {
                    "severity": "fail",
                    "layer": target_layer,
                    "location": "全文",
                    "description": f"AI腔禁用词计数={ai_ism_count}（阈值=0）",
                    "suggested_action": "重写包含禁用词的句子",
                }
            )
            result["verdict"] = "fail"

        # 重复率检测：>0.15 标记为不通过，0.10-0.15 标记为需关注
        if repetition_rate > 0.15:
            checks.append(
                {
                    "item": "重复率（客观检测）",
                    "status": "\u2717",
                    "note": f"n-gram 重复率={repetition_rate:.4f}（阈值=0.15）",
                }
            )
            issues.append(
                {
                    "severity": "fail",
                    "layer": target_layer,
                    "location": "全文",
                    "description": f"重复率超标: {repetition_rate:.4f}（阈值=0.15）",
                    "suggested_action": "重写高重复段落",
                }
            )
            result["verdict"] = "fail"
        elif repetition_rate > 0.10:
            checks.append(
                {
                    "item": "重复率（客观检测）",
                    "status": "\u26a0\ufe0f",
                    "note": f"n-gram 重复率={repetition_rate:.4f}（需关注）",
                }
            )
            # warn 不覆盖已有的 fail
            if result.get("verdict") != "fail":
                result["verdict"] = "warn"
