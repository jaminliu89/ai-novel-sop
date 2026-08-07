"""
监工·审视 Agent

职责：找问题不解决问题。只审查不修改——避免"既当运动员又当裁判"。

核心铁律：
- 发现问题后输出审查报告，交回协调者调度重写
- 绝不自己改

审查清单（五维度 + 读者视角冷读）：
1. 层间一致性：是否违反上层硬约束、世界观、人物动机、时间线
2. 人物声音：对话是否符合角色语言指纹、性格是否漂移、多角色可区分
3. 叙事质量：重复率、AI 腔密度、廉价和解、未赚到的转折、套路收尾
4. 伏笔系统：伏笔推进、新埋设登记、遗忘伏笔
5. 弧光推进：本场景是否推动人物弧光、弧光覆盖率
6. 读者视角冷读（L4 专属，需 chapter_contract）：
   - 读者理解度：首次读者能否跟上？有无未解释的专有名词堆砌？
   - 信息缺口：是否存在打断沉浸感的认知断层？
   - 读者驱动力：正文结尾是否让读者想立刻看下一章？
   - 合同履行：章节合同的 reader_question / read_on_hook / irreversible_change
     是否在正文中被实际回应（而非仅出现在大纲里）？

判定规则：
- 任一 ✗ → verdict = "fail" → 必须重写
- 有 ⚠️ 但无 ✗ → verdict = "warn" → 可推进但记录
- 全 ✓ → verdict = "pass" → 可推进

同时用代码做客观检测（重复率、AI 腔词表、冷读启发式）补充 LLM 主观判断：
- 如果客观检测发现 AI 腔或重复率超标，升级 verdict
- 冷读启发式检测合同字段是否在正文中有语义呼应
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 读者视角冷读 —— 合同字段与正文的最小语义呼应检测
# ------------------------------------------------------------------

# 合同字段 → 正文关键词映射（用于启发式检测合同是否被履行）
# 每个合同字段对应一组关键词，只要正文包含其中任意一个，即认为该字段被"触及"
_CONTRACT_KEYWORD_MAP: dict[str, list[str]] = {
    "reader_question": [
        "为什么", "什么", "怎么", "为何", "是否", "到底", "究竟",
        "归零", "消失", "异常", "秘密", "真相", "隐藏",
    ],
    "protagonist_goal": [
        "想要", "需要", "必须", "决定", "打算", "目标", "任务",
        "确认", "查清", "找到", "获取", "调查", "追查",
    ],
    "failure_cost": [
        "失去", "错过", "代价", "后果", "无法", "再也不能",
        "危险", "风险", "暴露", "警告",
    ],
    "irreversible_change": [
        "不再", "已经", "无法回头", "不可逆", "彻底", "永远",
        "变成了", "确认了", "暴露了", "消失了",
    ],
    "read_on_hook": [
        " ?", "？", "……", "——", "第二天", "明天", "下一",
        "还没", "仍未", "继续", "等待", "未知",
    ],
}

# 冷读各子项的判定阈值
_COLD_READ_MIN_CONTENT_LEN: int = 200  # 正文低于此字数时跳过冷读（信息量不足）


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
            - chapter_contract: (可选) 章节合同，提供时触发读者视角冷读
            - chapter_index: (可选) 章节序号，用于日志
            - chapter_title: (可选) 章节标题，用于日志
        :return: 审查报告 {verdict, checks, issues, metrics, cold_read_report}
        """
        content: str = input_data.get("content", "")
        target_layer: str = input_data.get("target_layer", "L4")
        chapter_contract: dict = input_data.get("chapter_contract", {})

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

        # 读者视角冷读（仅 L4 且有章节合同时触发）
        if chapter_contract and target_layer == "L4":
            cold_read_report: dict = self._cold_read_checks(
                content, chapter_contract
            )
            result["cold_read_report"] = cold_read_report
            self._augment_with_cold_read(result, cold_read_report, target_layer)

        logger.info(
            "审视完成: verdict=%s, 客观检测=%s, 冷读=%s",
            result.get("verdict"),
            {k: round(v, 4) if isinstance(v, float) else v
             for k, v in objective_metrics.items()},
            "已执行" if "cold_read_report" in result else "未触发",
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

    # ------------------------------------------------------------------
    # 读者视角冷读
    # ------------------------------------------------------------------

    def _cold_read_checks(
        self, content: str, contract: dict
    ) -> dict:
        """读者视角冷读评估（启发式）。

        从读者视角检查正文是否履行了章节合同，包含四个子维度：
        1. 合同履行：reader_question / irreversible_change / read_on_hook
           等关键字段是否在正文中被语义触及
        2. 读者理解度：专有名词密度是否过高（首次读者可能困惑）
        3. 读者驱动力：结尾段落是否包含悬念/问题标记
        4. 信息缺口：正文是否过短（可能信息量不足）

        :param content: L4 正文文本
        :param contract: 章节合同
        :return: 冷读报告 {
            overall, contract_fulfillment, reader_comprehension,
            reader_drive, info_gap, details
        }
        """
        content_len: int = len(content)
        details: list[dict] = []

        # ── 1. 合同履行检测 ──
        contract_fields_checked: list[dict] = []
        unfulfilled_fields: list[str] = []

        for field, keywords in _CONTRACT_KEYWORD_MAP.items():
            contract_value: str = str(contract.get(field, ""))
            if not contract_value:
                continue

            # 检测正文是否触及该合同字段
            touched: bool = any(kw in content for kw in keywords)

            # 如果合同值中的关键名词也出现在正文中，也算触及
            if not touched:
                # 提取合同值中的名词片段（2字以上的中文词组）
                for i in range(len(contract_value) - 1):
                    fragment: str = contract_value[i:i + 2]
                    if fragment in content and not fragment.isspace():
                        touched = True
                        break

            contract_fields_checked.append({
                "field": field,
                "touched": touched,
                "contract_value": contract_value[:80],
            })
            if not touched:
                unfulfilled_fields.append(field)

        fulfillment_rate: float = 1.0
        total_fields: int = len(contract_fields_checked)
        if total_fields > 0:
            fulfillment_rate = (
                (total_fields - len(unfulfilled_fields)) / total_fields
            )

        if unfulfilled_fields:
            details.append({
                "dimension": "合同履行",
                "status": "⚠️" if fulfillment_rate >= 0.5 else "✗",
                "note": (
                    f"合同字段未被正文触及: {', '.join(unfulfilled_fields)}"
                    f"（履行率 {fulfillment_rate:.0%}）"
                ),
            })
        else:
            details.append({
                "dimension": "合同履行",
                "status": "✓",
                "note": f"全部合同字段在正文中被触及（履行率 100%）",
            })

        # ── 2. 读者理解度（专有名词密度启发式）──
        # 检测连续出现的专有名词（2字以上中文字符串，非常见词）
        common_words: set[str] = {
            "沈语冰", "陈静", "苏映", "姜北辰", "贺明轩",
            "共感科技", "植入体", "死区", "共振体",
        }
        proper_noun_count: int = sum(
            1 for name in common_words if name in content
        )
        # 名词密度 = 不同专有名词数 / 千字
        noun_density: float = (
            proper_noun_count / max(content_len, 1) * 1000
        )

        if content_len > 300 and noun_density > 15:
            details.append({
                "dimension": "读者理解度",
                "status": "⚠️",
                "note": (
                    f"专有名词密度偏高（{noun_density:.1f}/千字），"
                    f"首次读者可能困惑"
                ),
            })
        else:
            details.append({
                "dimension": "读者理解度",
                "status": "✓",
                "note": f"专有名词密度合理（{noun_density:.1f}/千字）",
            })

        # ── 3. 读者驱动力（结尾悬念检测）──
        # 取正文最后 200 字作为结尾段落
        ending: str = content[-200:] if content_len > 200 else content
        hook_markers: list[str] = ["？", "?", "……", "——", "未完", "继续"]
        has_hook: bool = any(marker in ending for marker in hook_markers)

        if has_hook:
            details.append({
                "dimension": "读者驱动力",
                "status": "✓",
                "note": "结尾包含悬念/疑问标记，有追读驱动力",
            })
        else:
            details.append({
                "dimension": "读者驱动力",
                "status": "⚠️",
                "note": "结尾未检测到悬念标记，追读驱动力可能不足",
            })

        # ── 4. 信息缺口（正文长度检测）──
        if content_len < _COLD_READ_MIN_CONTENT_LEN:
            details.append({
                "dimension": "信息缺口",
                "status": "✗",
                "note": (
                    f"正文过短（{content_len} 字 < {_COLD_READ_MIN_CONTENT_LEN}），"
                    f"可能存在严重信息缺口"
                ),
            })
        elif content_len < 500:
            details.append({
                "dimension": "信息缺口",
                "status": "⚠️",
                "note": f"正文偏短（{content_len} 字），信息量可能不足",
            })
        else:
            details.append({
                "dimension": "信息缺口",
                "status": "✓",
                "note": f"正文字数充足（{content_len} 字）",
            })

        # ── 汇总 ──
        has_fail: bool = any(d["status"] == "✗" for d in details)
        has_warn: bool = any(d["status"] == "⚠️" for d in details)

        if has_fail:
            overall: str = "fail"
        elif has_warn:
            overall = "warn"
        else:
            overall = "pass"

        return {
            "overall": overall,
            "contract_fulfillment": {
                "rate": fulfillment_rate,
                "unfulfilled_fields": unfulfilled_fields,
                "fields_checked": contract_fields_checked,
            },
            "reader_comprehension": {
                "noun_density": round(noun_density, 2),
                "proper_noun_count": proper_noun_count,
            },
            "reader_drive": {
                "has_ending_hook": has_hook,
            },
            "info_gap": {
                "content_length": content_len,
                "min_threshold": _COLD_READ_MIN_CONTENT_LEN,
            },
            "details": details,
        }

    # ------------------------------------------------------------------
    # 冷读结果补充审查报告
    # ------------------------------------------------------------------

    def _augment_with_cold_read(
        self,
        result: dict,
        cold_read: dict,
        target_layer: str,
    ) -> None:
        """将冷读结果补充到审查报告中。

        根据冷读 overall 判定调整 verdict：
        - cold_read overall == "fail" → 升级 verdict 为 fail
        - cold_read overall == "warn" → 不覆盖已有 fail，但降级 pass 为 warn

        :param result: 审查报告（原地修改）
        :param cold_read: 冷读报告
        :param target_layer: 目标层级
        """
        checks: list[dict] = result.get("checks", [])
        issues: list[dict] = result.get("issues", [])

        for detail in cold_read.get("details", []):
            dimension: str = detail.get("dimension", "")
            status: str = detail.get("status", "✓")
            note: str = detail.get("note", "")

            checks.append({
                "item": f"读者冷读·{dimension}",
                "status": status,
                "note": note,
            })

            if status == "✗":
                issues.append({
                    "severity": "fail",
                    "layer": target_layer,
                    "location": "全文",
                    "description": f"冷读·{dimension}: {note}",
                    "suggested_action": (
                        "根据章节合同补充正文内容，"
                        "确保合同字段在正文中被回应"
                    ),
                })
                result["verdict"] = "fail"
            elif status == "⚠️":
                issues.append({
                    "severity": "warn",
                    "layer": target_layer,
                    "location": "全文",
                    "description": f"冷读·{dimension}: {note}",
                    "suggested_action": "检查并优化该维度",
                })
                if result.get("verdict") != "fail":
                    result["verdict"] = "warn"
