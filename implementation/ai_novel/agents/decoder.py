"""
拆解师·反向拆解 Agent

职责：把标杆小说喂进来，输出四维结构化样本档案。
拆解不是摘要——提取的是"作者怎么做的"（结构、手法、声音、规则）。

四维并行抽取：
1. 情节骨架：事件链、三幕结构、伏笔映射（埋设-回收对照表）、转折点
2. 声音指纹：句长分布、高频意象、语气词频率、句式偏好、可量化指纹向量
3. 人物图谱：人物关系图、动机链、弧光轨迹、每角色语言指纹
4. 世界规则：显式设定陈述、规则一致性校验、科技水平标定、codex 条目

输出：
- 机器可读的 JSON 四维样本档案
- 写入 config/few_shot/{novel_title}.json
- 样本片段存入 VectorStore (add_few_shot)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)


class DecoderAgent(BaseAgent):
    """拆解师 Agent —— 反向拆解引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        super().__init__("decoder", llm_client, state_store, tree_store, vector_store)

    async def execute(self, input_data: dict) -> dict:
        """
        执行反向拆解。

        :param input_data: 包含以下字段
            - novel_title: 小说标题
            - novel_author: 作者
            - novel_genre: 类型
            - text_source: full_text | chapter_summary | key_passages
            - text_content: 原文/摘要/关键段落
            - existing_analysis: 公开文学分析参考资料列表
        :return: 完整的四维拆解结果字典
        """
        novel_title: str = input_data.get("novel_title", "unknown")

        user_message: str = self._build_user_message(input_data)

        # 拆解需要极低温度（0.2）+ 大 token 上限（8192）
        result: dict = await self._call_and_parse(
            user_message, temperature=0.2, max_tokens=8192
        )

        # 确保基本字段存在
        result.setdefault("novel_title", novel_title)
        result.setdefault("decomposition_version", 1)
        result.setdefault("dimensions", {})
        result.setdefault("narrative_report", "")
        result.setdefault("learnable_models", [])

        # 写入 few_shot 样本文件
        file_path: Path = self._save_few_shot(result, novel_title)

        # 将样本片段存入 VectorStore
        self._store_few_shot_vectors(result)

        logger.info(
            "拆解完成: 小说=%s, 样本文件=%s",
            novel_title,
            file_path.name,
        )

        return result

    # ------------------------------------------------------------------
    # 样本文件持久化
    # ------------------------------------------------------------------

    def _save_few_shot(self, result: dict, novel_title: str) -> Path:
        """
        将拆解结果写入 config/few_shot/{novel_title}.json。

        :param result: 完整拆解结果
        :param novel_title: 小说标题（用于文件名）
        :return: 文件路径
        """
        few_shot_dir: Path = Path(__file__).parent.parent / "config" / "few_shot"
        few_shot_dir.mkdir(parents=True, exist_ok=True)

        # 文件名安全处理：替换非法字符
        safe_title: str = (
            novel_title.replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
            .replace(":", "_")
        )
        file_path: Path = few_shot_dir / f"{safe_title}.json"
        file_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info("拆解结果已写入: %s", file_path)
        return file_path

    # ------------------------------------------------------------------
    # 向量库存储
    # ------------------------------------------------------------------

    def _store_few_shot_vectors(self, result: dict) -> None:
        """
        将样本片段存入 VectorStore (add_few_shot)。

        从四维拆解结果中提取可索引的样本片段：
        - 情节骨架中的事件链条目
        - 伏笔映射条目
        - 声音指纹描述
        - 可学习模型
        - 世界规则条目
        """
        if self.vector is None or not hasattr(self.vector, "add_few_shot"):
            logger.warning("VectorStore 不可用或缺少 add_few_shot 方法，跳过向量存储")
            return

        novel_title: str = result.get("novel_title", "unknown")
        dimensions: dict = result.get("dimensions", {})

        # 收集可索引的样本片段：每项为 (sample_id, content, metadata) 三元组
        fragments: list[tuple[str, str, dict]] = []
        counter: int = 0

        def _make_id(prefix: str) -> str:
            """生成唯一样本 ID。"""
            nonlocal counter
            counter += 1
            safe_title = novel_title.replace(" ", "_")
            return f"{safe_title}_{prefix}_{counter}"

        # 维度一：情节骨架中的事件链
        plot: dict = dimensions.get("plot_skeleton", {})
        for event in plot.get("event_chain", []):
            content_str: str = (
                f"第{event.get('chapter', '?')}章: "
                f"{event.get('event', '')} → {event.get('consequence', '')}"
            )
            fragments.append((
                _make_id("plot"),
                content_str,
                {
                    "novel": novel_title,
                    "dimension": "plot",
                    "scene_type": "情节",
                },
            ))

        # 伏笔映射条目
        for foreshadow in plot.get("foreshadow_map", []):
            content_str = (
                f"伏笔{foreshadow.get('id', '')}: "
                f"埋设[{foreshadow.get('planted_chapter', '')}章]"
                f"{foreshadow.get('planted_detail', '')} → "
                f"回收[{foreshadow.get('harvested_chapter', '')}]"
                f"{foreshadow.get('harvested_location', '')} "
                f"状态:{foreshadow.get('status', '')}"
            )
            fragments.append((
                _make_id("foreshadow"),
                content_str,
                {
                    "novel": novel_title,
                    "dimension": "foreshadow",
                    "scene_type": "伏笔",
                    "fair_play": str(foreshadow.get("fair_play", True)),
                },
            ))

        # 维度二：声音指纹描述
        voice: dict = dimensions.get("voice_fingerprint", {})
        if voice:
            fragments.append((
                _make_id("voice"),
                json.dumps(voice, ensure_ascii=False),
                {
                    "novel": novel_title,
                    "dimension": "voice",
                    "scene_type": "声音",
                },
            ))

        # 维度三：人物图谱中的角色描述
        char_graph: dict = dimensions.get("character_graph", {})
        for character in char_graph.get("characters", []):
            content_str = (
                f"角色:{character.get('name', '')}, "
                f"定位:{character.get('role', '')}, "
                f"弧光:{character.get('arc', '')}, "
                f"语言指纹:{character.get('voice_fingerprint', '')}"
            )
            fragments.append((
                _make_id("character"),
                content_str,
                {
                    "novel": novel_title,
                    "dimension": "character",
                    "scene_type": "人物",
                },
            ))

        # 维度四：世界规则条目
        world: dict = dimensions.get("world_rules", {})
        for rule in world.get("rules", []):
            if isinstance(rule, dict):
                fragments.append((
                    _make_id("world_rule"),
                    f"规则{rule.get('id', '')}: {rule.get('rule', '')}",
                    {
                        "novel": novel_title,
                        "dimension": "world_rule",
                        "scene_type": "世界观",
                    },
                ))

        # 可学习模型
        for model in result.get("learnable_models", []):
            fragments.append((
                _make_id("model"),
                model,
                {
                    "novel": novel_title,
                    "dimension": "model",
                    "scene_type": "技法",
                },
            ))

        # 批量存入向量库
        # VectorStore.add_few_shot(sample_id, content, metadata) 接受三个独立参数
        success_count: int = 0
        for sample_id, content_str, metadata in fragments:
            try:
                self.vector.add_few_shot(sample_id, content_str, metadata)
                success_count += 1
            except Exception as e:
                logger.error("存储样本片段失败 (id=%s): %s", sample_id, e)

        logger.info(
            "样本片段已存入 VectorStore: 成功=%d, 总计=%d",
            success_count,
            len(fragments),
        )
