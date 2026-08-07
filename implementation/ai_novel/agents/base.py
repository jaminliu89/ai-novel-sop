"""
Agent 基类模块

所有 Agent 的公共基类，负责：
- 加载 system prompt（从 config/system_prompts/{role}.md）
- 构造 user message（JSON 序列化）
- 调用 LLM 并解析 JSON 响应
- 记录执行日志

子类只需实现 execute 方法，完成"构造输入 → 调用 LLM → 解析 → 返回"的流程。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseAgent:
    """所有 Agent 的基类。"""

    def __init__(
        self,
        role: str,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
    ) -> None:
        """
        初始化 Agent。

        :param role: Agent 角色名（gardener / pruner / curator / inspector / distiller / decoder）
        :param llm_client: LLMClient 实例，提供 call() 和 parse_json_response() 方法
        :param state_store: NovelStateStore 实例，全局状态存储
        :param tree_store: TreeStore 实例，小说之树存储
        :param vector_store: VectorStore 实例，向量检索存储
        """
        self.role: str = role
        self.llm: Any = llm_client
        self.state: Any = state_store
        self.tree: Any = tree_store
        self.vector: Any = vector_store
        self.system_prompt: str = self._load_prompt()

    # ------------------------------------------------------------------
    # Prompt 加载
    # ------------------------------------------------------------------

    def _load_prompt(self) -> str:
        """从 config/system_prompts/{role}.md 加载系统提示词。"""
        path: Path = (
            Path(__file__).parent.parent
            / "config"
            / "system_prompts"
            / f"{self.role}.md"
        )
        if not path.exists():
            logger.warning("系统提示词文件不存在: %s，使用空提示词", path)
            return ""
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # 消息构造与 LLM 调用
    # ------------------------------------------------------------------

    def _build_user_message(self, input_data: dict) -> str:
        """将输入字典序列化为 JSON 格式的 user message。"""
        return json.dumps(input_data, ensure_ascii=False, indent=2)

    async def _call_llm(
        self,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        调用 LLM 并返回原始文本响应。

        :param user_message: 构造好的用户消息
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :return: LLM 原始文本输出
        """
        logger.debug(
            "[%s] 调用 LLM: temperature=%.2f, max_tokens=%d",
            self.role,
            temperature,
            max_tokens,
        )
        raw: str = await self.llm.call(
            agent_role=self.role,
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return raw

    async def _call_and_parse(
        self,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        """
        调用 LLM 并解析 JSON 响应，返回字典。

        :param user_message: 构造好的用户消息
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :return: 解析后的字典
        """
        raw: str = await self._call_llm(user_message, temperature, max_tokens)
        return self._parse_json(raw)

    def _parse_json(self, raw: str) -> dict:
        """
        解析 LLM 输出的 JSON。

        依次尝试以下策略：
        1. 如果 llm_client 实例有 parse_json_response 方法，调用它；
        2. 尝试从 llm_client 模块导入模块级 parse_json_response 函数；
        3. 最终降级为 json.loads。

        :param raw: LLM 原始输出文本
        :return: 解析后的字典
        """
        # 策略 1：llm_client 实例方法
        if hasattr(self.llm, "parse_json_response"):
            return self.llm.parse_json_response(raw)

        # 策略 2：模块级函数
        try:
            from ..llm_client import parse_json_response

            return parse_json_response(raw)
        except (ImportError, TypeError):
            pass

        # 策略 3：最终降级
        try:
            import json

            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("JSON 解析失败，返回原文。文本前 200 字: %s", str(raw)[:200])
            return {"raw": raw}

    # ------------------------------------------------------------------
    # 子类实现
    # ------------------------------------------------------------------

    async def execute(self, input_data: dict) -> dict:
        """
        子类实现：构造 user_message → 调用 LLM → 解析 JSON → 返回。

        :param input_data: 输入数据字典
        :return: 输出数据字典
        """
        raise NotImplementedError
