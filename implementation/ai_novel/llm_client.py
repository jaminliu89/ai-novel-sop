"""
统一 LLM 客户端
===============

支持两类后端：
- DeepSeek：通过 OpenAI 兼容协议调用（openai.AsyncOpenAI，base_url 指向 deepseek）
- Claude：通过 Anthropic 官方 SDK 调用（anthropic.AsyncAnthropic）

设计要点：
1. 根据 agent_role 自动路由到对应模型（路由表来自 config.yaml 的 agent_model_mapping）。
2. API Key 优先从环境变量读取，回退到 config.yaml 中的配置。
3. 失败自动重试 3 次，指数退避。
4. 每次调用记录 agent_role / model / tokens / latency 日志。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml

# 第三方 SDK：延迟到运行时校验，便于在缺包时给出清晰提示
try:
    import openai
except ImportError:  # pragma: no cover - 仅在依赖缺失时触发
    openai = None  # type: ignore[assignment]

try:
    import anthropic
except ImportError:  # pragma: no cover - 仅在依赖缺失时触发
    anthropic = None  # type: ignore[assignment]

logger = logging.getLogger("ai_novel.llm_client")

# 包根目录（config.yaml 与 config/system_prompts/ 均相对此处解析）
_PACKAGE_DIR: Path = Path(__file__).resolve().parent
_CONFIG_PATH: Path = _PACKAGE_DIR / "config.yaml"
_SYSTEM_PROMPT_DIR: Path = _PACKAGE_DIR / "config" / "system_prompts"

# DeepSeek 路由前缀 → config.yaml 中 models 字段的键名
_DEEPSEEK_MODEL_KEY_MAP: dict[str, str] = {
    "deepseek_flash": "flash",
    "deepseek_pro": "pro",
}

# 环境变量名
_ENV_DEEPSEEK_KEY = "DEEPSEEK_API_KEY"
_ENV_ANTHROPIC_KEY = "ANTHROPIC_API_KEY"


def load_system_prompt(agent_role: str) -> str:
    """加载指定 Agent 角色的 system prompt。

    从 config/system_prompts/{role}.md 读取文本内容。
    文件不存在时抛出 FileNotFoundError。

    Args:
        agent_role: Agent 角色名，如 "coordinator" / "gardener"。

    Returns:
        system prompt 原文（字符串）。
    """
    prompt_path = _SYSTEM_PROMPT_DIR / f"{agent_role}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"未找到 system prompt 文件: {prompt_path}（角色: {agent_role}）"
        )
    return prompt_path.read_text(encoding="utf-8")


def parse_json_response(text: str) -> dict:
    """从 LLM 输出中提取 JSON 字典。

    依次尝试以下策略：
    1. 去除 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）后整体解析；
    2. 用正则定位首个 ```...``` 代码块内容解析；
    3. 用正则定位首个 {...} 花括号片段解析。

    Args:
        text: LLM 原始输出文本。

    Returns:
        解析得到的字典。若全部失败，返回 {"raw": text} 以保留原文便于排查。
    """
    if not text or not text.strip():
        return {}

    cleaned = text.strip()

    # 策略 1：整体可能是被代码块包裹的 JSON
    fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
    fence_match = fence_pattern.match(cleaned)
    candidates: list[str] = []
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    candidates.append(cleaned)

    for candidate in candidates:
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    # 策略 2：从文本中提取首个代码块
    block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL | re.IGNORECASE)
    if block_match:
        try:
            result = json.loads(block_match.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 策略 3：提取首个 {...} 片段（贪婪到匹配的闭合括号，取最外层）
    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        try:
            result = json.loads(brace_match.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    logger.warning("JSON 解析失败，返回原文。文本前 200 字: %s", cleaned[:200])
    return {"raw": text}


class LLMClient:
    """统一 LLM 客户端，封装 DeepSeek 与 Claude 两条调用链路。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        """初始化客户端，读取 config.yaml 并按需构造两条子链路。

        Args:
            config_path: 可选的自定义 config.yaml 路径。默认使用包内 config.yaml。
        """
        path = Path(config_path) if config_path else _CONFIG_PATH
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with path.open("r", encoding="utf-8") as f:
            self.config: dict[str, Any] = yaml.safe_load(f)

        # 解析路由表
        self.agent_model_mapping: dict[str, str] = self.config.get("agent_model_mapping", {})

        # 解析 DeepSeek 配置
        deepseek_cfg = self.config.get("deepseek", {})
        self._deepseek_base_url: str = deepseek_cfg.get("base_url", "https://api.deepseek.com/v1")
        self._deepseek_models: dict[str, str] = deepseek_cfg.get("models", {})
        # API Key：环境变量优先，回退到配置文件
        self._deepseek_api_key: str | None = os.environ.get(
            _ENV_DEEPSEEK_KEY
        ) or deepseek_cfg.get("api_key")

        # 解析 Claude 配置
        claude_cfg = self.config.get("claude", {})
        self._claude_model: str = claude_cfg.get("model", "claude-sonnet-4-20250514")
        self._claude_api_key: str | None = os.environ.get(
            _ENV_ANTHROPIC_KEY
        ) or claude_cfg.get("api_key")

        # 懒构造客户端实例（避免在缺 key 时立即报错，延迟到实际调用时）
        self._openai_client: Any = None
        self._anthropic_client: Any = None

        logger.info("LLMClient 初始化完成，路由表: %s", self.agent_model_mapping)

    # ------------------------------------------------------------------
    # 客户端懒加载
    # ------------------------------------------------------------------
    def _get_openai_client(self) -> Any:
        """获取（或构造）DeepSeek 使用的 OpenAI 兼容客户端。"""
        if self._openai_client is None:
            if openai is None:
                raise ImportError("缺少 openai 依赖，请执行 pip install openai>=1.0")
            if not self._deepseek_api_key or self._deepseek_api_key.startswith("YOUR_"):
                raise ValueError(
                    "DeepSeek API Key 未配置：请设置环境变量 DEEPSEEK_API_KEY "
                    "或在 config.yaml 中填写 deepseek.api_key"
                )
            self._openai_client = openai.AsyncOpenAI(
                api_key=self._deepseek_api_key,
                base_url=self._deepseek_base_url,
            )
        return self._openai_client

    def _get_anthropic_client(self) -> Any:
        """获取（或构造）Claude 使用的 Anthropic 客户端。"""
        if self._anthropic_client is None:
            if anthropic is None:
                raise ImportError("缺少 anthropic 依赖，请执行 pip install anthropic>=0.20")
            if not self._claude_api_key or self._claude_api_key.startswith("YOUR_"):
                raise ValueError(
                    "Claude API Key 未配置：请设置环境变量 ANTHROPIC_API_KEY "
                    "或在 config.yaml 中填写 claude.api_key"
                )
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=self._claude_api_key)
        return self._anthropic_client

    # ------------------------------------------------------------------
    # 路由解析
    # ------------------------------------------------------------------
    def _resolve_backend(self, agent_role: str) -> tuple[str, str]:
        """根据 agent_role 解析出后端类型与模型名。

        Args:
            agent_role: Agent 角色名。

        Returns:
            (backend, model) 二元组。backend 取值 "claude" 或 "deepseek"。
        """
        route = self.agent_model_mapping.get(agent_role)
        if route is None:
            raise ValueError(
                f"agent_role '{agent_role}' 未在 agent_model_mapping 中配置。"
                f"已知角色: {list(self.agent_model_mapping.keys())}"
            )

        if route == "claude":
            return "claude", self._claude_model

        if route in _DEEPSEEK_MODEL_KEY_MAP:
            model_key = _DEEPSEEK_MODEL_KEY_MAP[route]
            model_name = self._deepseek_models.get(model_key)
            if not model_name:
                raise ValueError(f"config.yaml 中未配置 deepseek.models.{model_key}")
            return "deepseek", model_name

        raise ValueError(f"无法识别的路由标识 '{route}'（角色: {agent_role}）")

    # ------------------------------------------------------------------
    # 核心调用
    # ------------------------------------------------------------------
    async def call(
        self,
        agent_role: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> str:
        """调用 LLM，根据 agent_role 自动路由到对应模型。

        失败时重试 3 次，指数退避（1s / 2s / 4s）。

        Args:
            agent_role: Agent 角色名，用于路由与日志。
            system_prompt: 系统提示词。
            user_message: 用户消息（本轮输入）。
            temperature: 采样温度，默认 0.8。
            max_tokens: 最大生成 token 数，默认 4096。

        Returns:
            LLM 生成的文本内容。
        """
        backend, model = self._resolve_backend(agent_role)
        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            start_ts = time.perf_counter()
            try:
                if backend == "claude":
                    content, usage = await self._call_claude(
                        model, system_prompt, user_message, temperature, max_tokens
                    )
                else:
                    content, usage = await self._call_deepseek(
                        model, system_prompt, user_message, temperature, max_tokens
                    )
                latency_ms = (time.perf_counter() - start_ts) * 1000
                logger.info(
                    "LLM 调用成功 | role=%s backend=%s model=%s "
                    "in_tokens=%s out_tokens=%s latency=%.0fms",
                    agent_role,
                    backend,
                    model,
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    latency_ms,
                )
                return content
            except Exception as exc:  # noqa: BLE001 - 统一捕获并重试
                last_error = exc
                latency_ms = (time.perf_counter() - start_ts) * 1000
                logger.warning(
                    "LLM 调用失败(第 %d/%d 次) | role=%s model=%s "
                    "latency=%.0fms error=%s",
                    attempt,
                    max_retries,
                    agent_role,
                    model,
                    latency_ms,
                    exc,
                )
                if attempt < max_retries:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    await asyncio.sleep(backoff)

        # 全部重试失败
        assert last_error is not None
        logger.error(
            "LLM 调用最终失败 | role=%s model=%s error=%s",
            agent_role,
            model,
            last_error,
        )
        raise last_error

    async def _call_deepseek(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int]]:
        """通过 OpenAI 兼容协议调用 DeepSeek。

        Returns:
            (内容文本, usage 字典)。
        """
        client = self._get_openai_client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0),
            "output_tokens": getattr(response.usage, "completion_tokens", 0),
        }
        return content, usage

    async def _call_claude(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int]]:
        """通过 Anthropic SDK 调用 Claude。

        Returns:
            (内容文本, usage 字典)。
        """
        client = self._get_anthropic_client()
        response = await client.messages.create(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Claude 的 content 是一个块列表，取首个文本块
        content = ""
        if response.content:
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    content += getattr(block, "text", "")
        usage = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }
        return content, usage
