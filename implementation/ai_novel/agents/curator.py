"""
记忆管家·固化/检索 Agent

职责：把选定的产出写入记忆库，并在需要时检索相关上下文。

两种工作模式：
1. solidify（固化模式）：
   - 调用 LLM 提取结构化内容 + 约束
   - 写入 TreeStore (save_layer) —— 版本不覆盖，每次新增版本号
   - 写入 ConstraintStore (save_constraints) —— 下层必须遵守的硬约束
   - 保存 JSON 快照到 snapshots/ 目录

2. retrieve（检索模式）：
   - 从 ConstraintStore 获取约束
   - 从 VectorStore 检索相关前文
   - 从 ForeshadowRegistry 获取伏笔状态
   - 组装返回完整上下文

存储接口说明：
- TreeStore / ConstraintStore / ForeshadowRegistry 的方法为异步（async）
- VectorStore 的方法为同步
- 本模块统一使用 await 调用异步方法，同步方法直接调用
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import BaseAgent

logger = logging.getLogger(__name__)

# 所有层级名称，用于检索模式下遍历获取约束
_ALL_LAYERS: list[str] = ["L0", "L1", "L2", "L3", "L4"]


class CuratorAgent(BaseAgent):
    """记忆管家 Agent —— 固化与检索引擎。"""

    def __init__(
        self,
        llm_client: Any,
        state_store: Any,
        tree_store: Any,
        vector_store: Any,
        constraint_store: Any | None = None,
        foreshadow_registry: Any | None = None,
    ) -> None:
        """
        初始化记忆管家。

        :param constraint_store: ConstraintStore 实例，如未提供则尝试从 state_store 获取
        :param foreshadow_registry: ForeshadowRegistry 实例，如未提供则尝试从 state_store 获取
        """
        super().__init__(
            "curator", llm_client, state_store, tree_store, vector_store
        )
        # 约束库：优先使用传入参数，其次从 state_store 获取
        self.constraint_store: Any | None = (
            constraint_store
            or getattr(state_store, "constraints", None)
            or getattr(state_store, "constraint_store", None)
        )
        # 伏笔注册表：优先使用传入参数，其次从 state_store 获取
        self.foreshadow_registry: Any | None = (
            foreshadow_registry
            or getattr(state_store, "foreshadow_registry", None)
            or getattr(state_store, "foreshadow", None)
        )

    async def execute(self, input_data: dict) -> dict:
        """
        根据 mode 分流执行固化或检索。

        :param input_data: 必须包含 mode 字段 ("solidify" 或 "retrieve")
        :return: 固化结果或检索结果
        """
        mode: str = input_data.get("mode", "solidify")

        if mode == "solidify":
            return await self._solidify(input_data)
        elif mode == "retrieve":
            return await self._retrieve(input_data)
        else:
            raise ValueError(f"不支持的模式: {mode}，仅支持 'solidify' 或 'retrieve'")

    # ------------------------------------------------------------------
    # 固化模式
    # ------------------------------------------------------------------

    async def _solidify(self, input_data: dict) -> dict:
        """
        固化模式：提取结构化内容 + 约束 → 写入存储 → 保存快照。

        :param input_data: 包含 target_layer, content, tree_version
        :return: {status, memory_id, new_version, extracted_constraints, snapshot_path}
        """
        target_layer: str = input_data.get("target_layer", "")
        content: dict = input_data.get("content", {})
        tree_version: int = input_data.get("tree_version", 0)

        # 构造 LLM 输入，让 LLM 提取结构化内容和下层硬约束
        llm_input: dict = {
            "mode": "solidify",
            "target_layer": target_layer,
            "content": content,
            "tree_version": tree_version,
        }
        user_message: str = self._build_user_message(llm_input)

        # 固化用低温度确保结构化输出稳定
        result: dict = await self._call_and_parse(
            user_message, temperature=0.2, max_tokens=4096
        )

        # 提取关键字段
        memory_id: str = result.get(
            "memory_id",
            f"{target_layer}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        )
        new_version: int = result.get("new_version", tree_version + 1)
        extracted_constraints: list[str] = result.get("extracted_constraints", [])
        structured_content: dict = result.get("structured_content", {})

        # 合并输入内容和 LLM 结构化输出，作为该层的完整产出
        layer_content: dict = {
            "layer": target_layer,
            "version": new_version,
            "input": content,
            "structured": structured_content,
            "constraints": extracted_constraints,
        }

        # 写入 TreeStore（版本不覆盖，新增版本号）
        # TreeStore.save_layer(layer, content, version) 为异步方法
        if self.tree is not None and hasattr(self.tree, "save_layer"):
            try:
                await self.tree.save_layer(target_layer, layer_content, new_version)
                logger.info(
                    "已写入 TreeStore: layer=%s, version=%d", target_layer, new_version
                )
            except Exception as e:
                logger.error("写入 TreeStore 失败: %s", e)

        # 写入 ConstraintStore（下层必须遵守的硬约束）
        # ConstraintStore.save_constraints(layer, constraints) 为异步方法
        if self.constraint_store is not None and hasattr(
            self.constraint_store, "save_constraints"
        ):
            try:
                await self.constraint_store.save_constraints(
                    target_layer, extracted_constraints
                )
                logger.info(
                    "已写入 ConstraintStore: layer=%s, 约束数=%d",
                    target_layer,
                    len(extracted_constraints),
                )
            except Exception as e:
                logger.error("写入 ConstraintStore 失败: %s", e)

        # 保存 JSON 快照
        snapshot_path: Path = self._save_snapshot(
            result, target_layer, new_version
        )

        return {
            "status": "solidified",
            "memory_id": memory_id,
            "new_version": new_version,
            "extracted_constraints": extracted_constraints,
            "snapshot_path": str(snapshot_path),
        }

    # ------------------------------------------------------------------
    # 检索模式
    # ------------------------------------------------------------------

    async def _retrieve(self, input_data: dict) -> dict:
        """
        检索模式：组装约束 + 前文 + 伏笔状态。

        :param input_data: 包含 query, scene_type, need, top_k
        :return: {status, results: {world_rules, character_fingerprints, recent_context, foreshadow_status, few_shot_refs}}
        """
        query: str = input_data.get("query", "")
        scene_type: str = input_data.get("scene_type", "")
        need: list[str] = input_data.get(
            "need",
            ["world_rules", "character_fingerprints", "recent_context", "foreshadow_status"],
        )
        top_k: int = input_data.get("top_k", 5)

        results: dict[str, Any] = {}

        # 从 ConstraintStore 获取约束（世界规则）
        # ConstraintStore.get_constraints(layer) 为异步方法，按层级遍历获取
        if "world_rules" in need and self.constraint_store is not None:
            results["world_rules"] = await self._get_all_constraints()

        # 从 VectorStore 检索相关前文
        # VectorStore.retrieve_context(query, top_k) 为同步方法
        if "recent_context" in need and self.vector is not None:
            results["recent_context"] = self._sync_call(
                self.vector, "retrieve_context",
                fallback_method="search",
                query=query, top_k=top_k, default=[],
            )

        # 从 ForeshadowRegistry 获取伏笔状态
        # ForeshadowRegistry.get_status() 为异步方法
        if "foreshadow_status" in need and self.foreshadow_registry is not None:
            results["foreshadow_status"] = await self._async_call(
                self.foreshadow_registry,
                "get_status",
                fallback_method="get_all",
                default={},
            )

        # few-shot 样本检索（按场景类型）
        # VectorStore.retrieve_few_shot(scene_type, query, top_k) 为同步方法
        if "few_shot_refs" in need and self.vector is not None:
            results["few_shot_refs"] = self._sync_call(
                self.vector,
                "retrieve_few_shot",
                fallback_method="search_few_shot",
                scene_type=scene_type,
                query=query,
                top_k=top_k,
                default=[],
            )

        # 角色语言指纹引用
        if "character_fingerprints" in need and self.tree is not None:
            results["character_fingerprints"] = await self._async_call(
                self.tree, "get_character_fingerprints", default=[]
            )

        return {
            "status": "retrieved",
            "results": results,
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    async def _get_all_constraints(self) -> list[str]:
        """从 ConstraintStore 获取所有层级的约束，合并返回。"""
        all_constraints: list[str] = []
        if self.constraint_store is None:
            return all_constraints

        for layer in _ALL_LAYERS:
            try:
                constraints = await self.constraint_store.get_constraints(layer)
                if constraints:
                    all_constraints.extend(constraints)
            except Exception as e:
                logger.debug("获取层 %s 约束失败: %s", layer, e)

        return all_constraints

    def _save_snapshot(self, data: dict, layer: str, version: int) -> Path:
        """保存 JSON 快照到 snapshots/ 目录。"""
        snapshot_dir: Path = Path(__file__).parent.parent / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path: Path = snapshot_dir / f"v{version}_{layer}.json"
        snapshot_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("快照已保存: %s", snapshot_path)
        return snapshot_path

    @staticmethod
    def _sync_call(
        obj: Any,
        method_name: str,
        fallback_method: str | None = None,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        """
        安全调用同步方法，失败时尝试备选方法，再失败返回默认值。

        :param obj: 目标对象
        :param method_name: 首选方法名
        :param fallback_method: 备选方法名
        :param default: 默认返回值
        :param kwargs: 传递给方法的参数
        :return: 方法调用结果或默认值
        """
        for name in [method_name, fallback_method]:
            if name and hasattr(obj, name):
                try:
                    method = getattr(obj, name)
                    return method(**kwargs) if kwargs else method()
                except Exception as e:
                    logger.warning("调用 %s.%s 失败: %s", type(obj).__name__, name, e)
        return default

    @staticmethod
    async def _async_call(
        obj: Any,
        method_name: str,
        fallback_method: str | None = None,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        """
        安全调用异步方法，失败时尝试备选方法，再失败返回默认值。
        同时兼容同步方法（自动检测是否为协程）。

        :param obj: 目标对象
        :param method_name: 首选方法名
        :param fallback_method: 备选方法名
        :param default: 默认返回值
        :param kwargs: 传递给方法的参数
        :return: 方法调用结果或默认值
        """
        for name in [method_name, fallback_method]:
            if name and hasattr(obj, name):
                try:
                    method = getattr(obj, name)
                    result = method(**kwargs) if kwargs else method()
                    # 如果返回协程，则 await
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                except Exception as e:
                    logger.warning("调用 %s.%s 失败: %s", type(obj).__name__, name, e)
        return default
