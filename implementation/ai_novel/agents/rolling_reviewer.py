"""
滚动复盘 Agent

职责：每 N 章（默认 3 章）跨章检查叙事模式重复、节奏失衡、伏笔遗忘。
不修改正文，只输出审查报告和修复建议，交回协调者决策。

四个检测维度：
1. 叙事模式重复：跨章场景开头/情感走向/冲突解决方式是否套路化
2. 节奏失衡：字数分布、信息密度、场景-动作比例是否失衡
3. 伏笔遗忘：埋设后超过 N 章未推进的伏笔
4. 状态连续性：角色位置/生理状态/知识积累是否连贯

工作流程：
1. 接收最近 N 章的正文、章节合同、状态快照、伏笔状态
2. 代码启发式检测（节奏、伏笔、状态连续性）
3. LLM 分析叙事模式重复
4. 汇总为审查报告
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


# 滚动复盘默认窗口大小（每 N 章触发一次）
DEFAULT_REVIEW_WINDOW: int = 3

# 伏笔停滞阈值：埋设后超过此章节数未推进，标记为"停滞"
FORESHADOW_STALE_THRESHOLD: int = 3

# 场景开头模式检测：取每章正文前 N 字作为开头指纹
OPENING_FINGERPRINT_LEN: int = 50


def build_rolling_review_prompt(
    chapters_data: list[dict],
    foreshadow_status: list[dict],
    state_snapshots: list[dict],
    window_size: int,
) -> str:
    """构造滚动复盘 LLM prompt。

    :param chapters_data: 最近 N 章的数据列表，每项含
        chapter_index / chapter_title / chapter_text / chapter_contract / scenes
    :param foreshadow_status: 伏笔登记表当前状态
    :param state_snapshots: 最近 N 章的状态快照
    :param window_size: 复盘窗口大小
    :return: JSON 格式的 prompt
    """
    # 精简章节文本（每章取前 2000 字避免 prompt 过长）
    chapters_summary: list[dict] = []
    for ch in chapters_data:
        text: str = ch.get("chapter_text", "")
        chapters_summary.append({
            "chapter_index": ch.get("chapter_index", 0),
            "chapter_title": ch.get("chapter_title", ""),
            "chapter_text_excerpt": text[:2000],
            "word_count": len(text),
            "scene_count": len(ch.get("scenes", [])),
            "contract_reader_question": ch.get("chapter_contract", {}).get(
                "reader_question", ""
            ),
            "contract_irreversible": ch.get("chapter_contract", {}).get(
                "irreversible_change", ""
            ),
        })

    # 精简伏笔状态
    foreshadow_brief: list[dict] = [
        {
            "id": fs.get("foreshadow_id", ""),
            "planted_chapter": fs.get("planted_chapter", ""),
            "harvested": fs.get("harvested", False),
            "detail": fs.get("detail", {}),
        }
        for fs in foreshadow_status
    ]

    # 精简状态快照
    state_brief: list[dict] = []
    for snap in state_snapshots:
        chars: list = snap.get("character_states", [])
        state_brief.append({
            "chapter_index": snap.get("chapter_index", 0),
            "character_names": [c.get("name", "") for c in chars],
            "timeline_count": len(snap.get("timeline_events", [])),
            "resource_count": len(snap.get("resource_changes", [])),
            "relationship_count": len(snap.get("relationship_changes", [])),
            "summary": snap.get("summary", ""),
        })

    return json.dumps(
        {
            "task": "滚动复盘",
            "instructions": (
                f"你正在审阅最近 {window_size} 章的小说正文。"
                "请从跨章视角检查以下维度，只报告问题，不修改正文：\n"
                "1. 叙事模式重复：多章是否使用了相似的场景开头、"
                "情感走向、冲突解决方式？\n"
                "2. 节奏失衡：各章字数分布是否合理？"
                "信息密度是否忽高忽低？\n"
                "3. 伏笔遗忘：是否有伏笔埋设后长时间未推进？\n"
                "4. 状态连续性：角色位置、生理状态、知识积累是否连贯？\n"
                "如果没有问题，对应维度返回 status=pass。"
            ),
            "chapters": chapters_summary,
            "foreshadow_status": foreshadow_brief,
            "state_snapshots": state_brief,
            "output_format": {
                "verdict": "pass / warn / fail",
                "dimensions": [
                    {
                        "name": "叙事模式重复",
                        "status": "pass / warn / fail",
                        "findings": "具体发现描述",
                        "affected_chapters": [1, 2],
                    },
                    {
                        "name": "节奏失衡",
                        "status": "pass / warn / fail",
                        "findings": "具体发现描述",
                        "affected_chapters": [1, 2],
                    },
                    {
                        "name": "伏笔遗忘",
                        "status": "pass / warn / fail",
                        "findings": "具体发现描述",
                        "stale_foreshadows": ["fs1", "fs2"],
                    },
                    {
                        "name": "状态连续性",
                        "status": "pass / warn / fail",
                        "findings": "具体发现描述",
                        "affected_chapters": [1, 2],
                    },
                ],
                "recommendations": [
                    "针对发现的问题给出具体修复建议",
                ],
            },
        },
        ensure_ascii=False,
        indent=2,
    )


class RollingReviewerAgent(BaseAgent):
    """滚动复盘 Agent —— 跨章检查叙事模式、节奏、伏笔、状态连续性。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
        window_size: int = DEFAULT_REVIEW_WINDOW,
    ) -> None:
        super().__init__(
            "inspector",  # 复用监工的 system prompt
            llm_client,
            state_store,
            tree_store,
            vector_store,
        )
        self.window_size: int = window_size

    async def execute(self, input_data: dict) -> dict:
        """执行滚动复盘。

        :param input_data: 包含以下字段
            - chapters_data: 最近 N 章的数据列表
            - foreshadow_status: 伏笔登记表当前状态
            - state_snapshots: 最近 N 章的状态快照
            - window_size: (可选) 复盘窗口大小
            - current_chapter_index: 当前章节序号
        :return: 复审报告 {
            verdict, dimensions, recommendations,
            heuristic_report, review_window
        }
        """
        chapters_data: list[dict] = input_data.get("chapters_data", [])
        foreshadow_status: list[dict] = input_data.get("foreshadow_status", [])
        state_snapshots: list[dict] = input_data.get("state_snapshots", [])
        window_size: int = input_data.get("window_size", self.window_size)
        current_chapter: int = input_data.get("current_chapter_index", 0)

        if not chapters_data:
            logger.warning("滚动复盘无章节数据，跳过")
            return {
                "verdict": "pass",
                "dimensions": [],
                "recommendations": [],
                "heuristic_report": {},
                "review_window": window_size,
                "current_chapter_index": current_chapter,
                "skipped": True,
                "skip_reason": "无章节数据",
            }

        # ── 代码启发式检测 ──
        heuristic_report: dict = self._heuristic_checks(
            chapters_data, foreshadow_status, state_snapshots, current_chapter
        )

        # ── LLM 叙事模式分析 ──
        prompt: str = build_rolling_review_prompt(
            chapters_data, foreshadow_status, state_snapshots, window_size
        )

        llm_result: dict = await self._call_and_parse(
            prompt, temperature=0.15, max_tokens=2048
        )

        # 确保关键字段存在
        llm_result.setdefault("verdict", "warn")
        llm_result.setdefault("dimensions", [])
        llm_result.setdefault("recommendations", [])

        # ── 合并启发式与 LLM 结果 ──
        merged: dict = self._merge_results(llm_result, heuristic_report)

        merged["review_window"] = window_size
        merged["current_chapter_index"] = current_chapter
        merged["heuristic_report"] = heuristic_report

        logger.info(
            "滚动复盘完成（第%d章窗口）: verdict=%s, 启发式发现=%d项, LLM发现=%d项",
            current_chapter,
            merged.get("verdict"),
            len(heuristic_report.get("findings", [])),
            len(merged.get("dimensions", [])),
        )

        return merged

    # ------------------------------------------------------------------
    # 代码启发式检测
    # ------------------------------------------------------------------

    def _heuristic_checks(
        self,
        chapters_data: list[dict],
        foreshadow_status: list[dict],
        state_snapshots: list[dict],
        current_chapter: int,
    ) -> dict:
        """执行代码级启发式检测。

        :return: {
            findings: [检测发现列表],
            pacing_report: 节奏检测报告,
            foreshadow_report: 伏笔检测报告,
            state_report: 状态连续性报告,
        }
        """
        findings: list[dict] = []

        # 1. 节奏失衡检测
        pacing_findings: list[dict] = self._check_pacing(chapters_data)
        findings.extend(pacing_findings)

        # 2. 伏笔遗忘检测
        foreshadow_findings: list[dict] = self._check_foreshadows(
            foreshadow_status, current_chapter
        )
        findings.extend(foreshadow_findings)

        # 3. 状态连续性检测
        state_findings: list[dict] = self._check_state_continuity(state_snapshots)
        findings.extend(state_findings)

        # 4. 场景开头模式重复检测
        opening_findings: list[dict] = self._check_opening_patterns(chapters_data)
        findings.extend(opening_findings)

        return {
            "findings": findings,
            "pacing_report": {
                "findings_count": len(pacing_findings),
                "details": pacing_findings,
            },
            "foreshadow_report": {
                "findings_count": len(foreshadow_findings),
                "details": foreshadow_findings,
            },
            "state_report": {
                "findings_count": len(state_findings),
                "details": state_findings,
            },
            "opening_pattern_report": {
                "findings_count": len(opening_findings),
                "details": opening_findings,
            },
        }

    def _check_pacing(self, chapters_data: list[dict]) -> list[dict]:
        """检测节奏失衡。

        检查项：
        - 各章字数差异超过 2 倍
        - 场景数差异过大
        - 连续多章字数递减或递增
        """
        findings: list[dict] = []
        word_counts: list[tuple[int, str, int]] = []
        scene_counts: list[tuple[int, str, int]] = []

        for ch in chapters_data:
            ch_idx: int = ch.get("chapter_index", 0)
            ch_title: str = ch.get("chapter_title", "")
            text: str = ch.get("chapter_text", "")
            scenes: list = ch.get("scenes", [])
            word_counts.append((ch_idx, ch_title, len(text)))
            scene_counts.append((ch_idx, ch_title, len(scenes)))

        if len(word_counts) < 2:
            return findings

        # 字数差异检测
        wc_values: list[int] = [wc[2] for wc in word_counts]
        max_wc: int = max(wc_values)
        min_wc: int = min(wc_values)

        if min_wc > 0 and max_wc / min_wc > 2.0:
            findings.append({
                "dimension": "节奏失衡",
                "severity": "warn",
                "description": (
                    f"章字数差异过大: 最短={min_wc}字, 最长={max_wc}字, "
                    f"比值={max_wc/min_wc:.1f}x"
                ),
                "affected_chapters": [wc[0] for wc in word_counts],
            })

        # 场景数差异检测
        sc_values: list[int] = [sc[2] for sc in scene_counts]
        max_sc: int = max(sc_values)
        min_sc: int = min(sc_values)

        if min_sc > 0 and max_sc - min_sc >= 3:
            findings.append({
                "dimension": "节奏失衡",
                "severity": "warn",
                "description": (
                    f"场景数差异过大: 最少={min_sc}个, 最多={max_sc}个"
                ),
                "affected_chapters": [sc[0] for sc in scene_counts],
            })

        # 连续递减/递增检测
        if len(wc_values) >= 3:
            all_decreasing: bool = all(
                wc_values[i] > wc_values[i + 1]
                for i in range(len(wc_values) - 1)
            )
            all_increasing: bool = all(
                wc_values[i] < wc_values[i + 1]
                for i in range(len(wc_values) - 1)
            )

            if all_decreasing:
                findings.append({
                    "dimension": "节奏失衡",
                    "severity": "warn",
                    "description": "连续多章字数递减，可能节奏放缓",
                    "affected_chapters": [wc[0] for wc in word_counts],
                })
            elif all_increasing:
                findings.append({
                    "dimension": "节奏失衡",
                    "severity": "warn",
                    "description": "连续多章字数递增，可能信息密度过高",
                    "affected_chapters": [wc[0] for wc in word_counts],
                })

        return findings

    def _check_foreshadows(
        self,
        foreshadow_status: list[dict],
        current_chapter: int,
    ) -> list[dict]:
        """检测伏笔遗忘。

        检查项：
        - 埋设后超过 FORESHADOW_STALE_THRESHOLD 章未回收
        - 回收率过低
        """
        findings: list[dict] = []
        stale_ids: list[str] = []

        for fs in foreshadow_status:
            fs_id: str = fs.get("foreshadow_id", "")
            harvested: bool = fs.get("harvested", False)
            planted_ch: str = fs.get("planted_chapter", "")

            if harvested:
                continue

            # 从 planted_chapter 提取章节数字
            planted_num: int = 0
            for part in planted_ch:
                if part.isdigit():
                    planted_num = planted_num * 10 + int(part)
                    break

            if planted_num > 0 and current_chapter - planted_num >= FORESHADOW_STALE_THRESHOLD:
                stale_ids.append(fs_id)
                findings.append({
                    "dimension": "伏笔遗忘",
                    "severity": "warn",
                    "description": (
                        f"伏笔 {fs_id} 在第{planted_num}章埋设，"
                        f"已 {current_chapter - planted_num} 章未回收"
                    ),
                    "foreshadow_id": fs_id,
                })

        # 回收率检测
        total_fs: int = len(foreshadow_status)
        harvested_fs: int = sum(
            1 for fs in foreshadow_status if fs.get("harvested", False)
        )

        if total_fs > 0:
            recovery_rate: float = harvested_fs / total_fs
            if recovery_rate < 0.2 and total_fs >= 5:
                findings.append({
                    "dimension": "伏笔遗忘",
                    "severity": "warn",
                    "description": (
                        f"伏笔回收率偏低: {harvested_fs}/{total_fs} "
                        f"({recovery_rate:.0%})"
                    ),
                })

        return findings

    def _check_state_continuity(
        self, state_snapshots: list[dict]
    ) -> list[dict]:
        """检测状态连续性。

        检查项：
        - 角色位置突变（跨章位置不一致）
        - 生理状态倒退（已恢复的状态又出现）
        - 新角色突然消失（出现后下一章状态快照中缺失）
        """
        findings: list[dict] = []

        if len(state_snapshots) < 2:
            return findings

        for i in range(1, len(state_snapshots)):
            prev_snap: dict = state_snapshots[i - 1]
            curr_snap: dict = state_snapshots[i]

            prev_chars: list[dict] = prev_snap.get("character_states", [])
            curr_chars: list[dict] = curr_snap.get("character_states", [])

            prev_names: set[str] = {
                c.get("name", "") for c in prev_chars if c.get("name")
            }
            curr_names: set[str] = {
                c.get("name", "") for c in curr_chars if c.get("name")
            }

            # 检测角色消失（上一章有但本章没有）
            disappeared: set[str] = prev_names - curr_names
            if disappeared and prev_names:
                findings.append({
                    "dimension": "状态连续性",
                    "severity": "warn",
                    "description": (
                        f"角色在第{curr_snap.get('chapter_index', 0)}章"
                        f"状态快照中消失: {', '.join(disappeared)}"
                    ),
                    "affected_chapters": [
                        prev_snap.get("chapter_index", 0),
                        curr_snap.get("chapter_index", 0),
                    ],
                })

            # 检测角色位置回退（出现在前一章但当前位置与更早章节相同）
            prev_char_map: dict[str, dict] = {
                c.get("name", ""): c for c in prev_chars if c.get("name")
            }
            curr_char_map: dict[str, dict] = {
                c.get("name", ""): c for c in curr_chars if c.get("name")
            }

            for name in curr_names & prev_names:
                prev_loc: str = prev_char_map[name].get("location", "")
                curr_loc: str = curr_char_map[name].get("location", "")

                # 如果位置相同且非首章，可能角色没有移动（需结合情节判断）
                # 这里不做硬性判定，只在位置完全相同时记录 info 级别
                if prev_loc and curr_loc and prev_loc == curr_loc and i >= 2:
                    findings.append({
                        "dimension": "状态连续性",
                        "severity": "info",
                        "description": (
                            f"角色 {name} 在第"
                            f"{prev_snap.get('chapter_index', 0)}-"
                            f"{curr_snap.get('chapter_index', 0)}章"
                            f"位置未变化: {curr_loc}"
                        ),
                    })

        return findings

    def _check_opening_patterns(
        self, chapters_data: list[dict]
    ) -> list[dict]:
        """检测场景开头模式重复。

        提取每章正文开头的指纹（前 N 字），检测跨章重复。
        """
        findings: list[dict] = []

        if len(chapters_data) < 2:
            return findings

        openings: list[tuple[int, str, str]] = []
        for ch in chapters_data:
            ch_idx: int = ch.get("chapter_index", 0)
            ch_title: str = ch.get("chapter_title", "")
            text: str = ch.get("chapter_text", "")
            opening: str = text[:OPENING_FINGERPRINT_LEN].strip()
            openings.append((ch_idx, ch_title, opening))

        # 检测开头前 10 字是否有重复模式
        opening_prefixes: list[str] = [o[2][:10] for o in openings]
        prefix_counts: Counter = Counter(opening_prefixes)

        for prefix, count in prefix_counts.items():
            if count > 1 and len(prefix) >= 3:
                affected: list[int] = [
                    o[0] for o in openings if o[2][:10] == prefix
                ]
                findings.append({
                    "dimension": "叙事模式重复",
                    "severity": "warn",
                    "description": (
                        f"多章开头模式相似: '{prefix}...' 出现在 {count} 章"
                    ),
                    "affected_chapters": affected,
                })

        return findings

    # ------------------------------------------------------------------
    # 结果合并
    # ------------------------------------------------------------------

    def _merge_results(
        self, llm_result: dict, heuristic_report: dict
    ) -> dict:
        """合并 LLM 分析结果与启发式检测结果。

        :param llm_result: LLM 返回的分析结果
        :param heuristic_report: 启发式检测报告
        :return: 合并后的复审报告
        """
        merged_verdict: str = llm_result.get("verdict", "warn")
        merged_dimensions: list[dict] = list(
            llm_result.get("dimensions", [])
        )
        merged_recommendations: list[str] = list(
            llm_result.get("recommendations", [])
        )

        # 将启发式发现转换为维度报告
        heuristic_findings: list[dict] = heuristic_report.get("findings", [])

        # 按维度分组启发式发现
        dim_groups: dict[str, list[dict]] = {}
        for f in heuristic_findings:
            dim: str = f.get("dimension", "其他")
            dim_groups.setdefault(dim, []).append(f)

        # 合并到 dimensions
        existing_dims: set[str] = {
            d.get("name", "") for d in merged_dimensions
        }

        for dim_name, finds in dim_groups.items():
            # 计算该维度的严重度
            has_fail: bool = any(
                f.get("severity") == "fail" for f in finds
            )
            has_warn: bool = any(
                f.get("severity") == "warn" for f in finds
            )

            if has_fail:
                dim_status: str = "fail"
            elif has_warn:
                dim_status = "warn"
            else:
                dim_status = "pass"

            findings_desc: str = "; ".join(
                f.get("description", "") for f in finds
            )

            if dim_name in existing_dims:
                # 更新已有维度
                for d in merged_dimensions:
                    if d.get("name") == dim_name:
                        # 启发式结果优先（更具体）
                        d["heuristic_status"] = dim_status
                        d["heuristic_findings"] = findings_desc
                        # 如果启发式发现 fail，升级维度状态
                        if dim_status == "fail" and d.get("status") != "fail":
                            d["status"] = "fail"
                        elif dim_status == "warn" and d.get("status") == "pass":
                            d["status"] = "warn"
                        break
            else:
                # 新增维度
                merged_dimensions.append({
                    "name": dim_name,
                    "status": dim_status,
                    "findings": findings_desc,
                    "source": "heuristic",
                })

            # 维度状态影响整体 verdict
            if dim_status == "fail":
                merged_verdict = "fail"
            elif dim_status == "warn" and merged_verdict != "fail":
                merged_verdict = "warn"

        # 追加启发式修复建议
        if heuristic_findings:
            for f in heuristic_findings:
                if f.get("severity") in ("fail", "warn"):
                    merged_recommendations.append(
                        f"[启发式] {f.get('dimension', '')}: "
                        f"{f.get('description', '')}"
                    )

        return {
            "verdict": merged_verdict,
            "dimensions": merged_dimensions,
            "recommendations": merged_recommendations,
        }
