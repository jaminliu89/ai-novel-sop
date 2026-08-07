"""
SQLite + JSON 持久化层
=====================

提供六类存储：
- NovelStateStore：小说流水线整体状态（当前层/动作/场景/人机节点等）
- TreeStore：小说之树五层产出（带版本号）+ JSON 快照
- ForeshadowRegistry：伏笔登记与回收追踪
- ConstraintStore：每层硬约束的存取
- AgentLog：Agent 调用历史日志
- StoryStateStore：故事世界状态快照（角色/时间线/资源/关系），每章后回写

所有 SQLite 操作均通过 aiosqlite 异步执行；表使用
``CREATE TABLE IF NOT EXISTS`` 自动创建。JSON 快照落盘到 snapshots/ 目录。
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite
import yaml

logger = logging.getLogger("ai_novel.memory.store")

# 包根目录（ai_novel/）—— config.yaml 与相对存储路径均以此为基准
_PACKAGE_DIR: Path = Path(__file__).resolve().parent.parent
_CONFIG_PATH: Path = _PACKAGE_DIR / "config.yaml"


def _load_storage_config() -> dict[str, str]:
    """从 config.yaml 读取 storage 段，返回路径配置。

    Returns:
        包含 sqlite_path / snapshots_dir / chroma_path 的字典（均为相对包根的路径）。
    """
    if not _CONFIG_PATH.exists():
        logger.warning("config.yaml 不存在(%s)，使用默认存储路径", _CONFIG_PATH)
        return {
            "sqlite_path": "novel_state.db",
            "snapshots_dir": "snapshots/",
            "chroma_path": "chroma_db/",
        }
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    storage = cfg.get("storage", {})
    return {
        "sqlite_path": storage.get("sqlite_path", "novel_state.db"),
        "snapshots_dir": storage.get("snapshots_dir", "snapshots/"),
        "chroma_path": storage.get("chroma_path", "chroma_db/"),
    }


def _resolve_path(rel_or_abs: str | Path) -> Path:
    """将相对路径解析为相对包根的绝对路径；绝对路径原样返回。"""
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return _PACKAGE_DIR / p


def _now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串。"""
    return datetime.utcnow().isoformat(timespec="seconds")


class _BaseSQLiteStore:
    """所有 SQLite 存储类的基类，封装连接获取与建表逻辑。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = _resolve_path(_load_storage_config()["sqlite_path"])
        self.db_path: Path = Path(db_path)
        # 确保父目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        """连接上下文管理器：打开新连接 → 开启 WAL → yield → 自动关闭。

        每次操作使用独立连接，避免跨协程的生命周期耦合。
        注意：aiosqlite.Connection 同一实例的 await 与 async with 不可叠加使用
        （会重复启动后台线程），因此本方法直接以 async with 管理，调用方
        不应对返回值再 await。
        """
        # aiosqlite.connect 返回 Connection 对象，async with 负责启动后台线程并关闭
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            yield db

    async def _init_schema(self, ddl: str) -> None:
        """执行建表 DDL（IF NOT EXISTS 幂等）。"""
        async with self._conn() as db:
            await db.executescript(ddl)
            await db.commit()


class NovelStateStore(_BaseSQLiteStore):
    """小说流水线整体状态存储，管理单行 novel_state 记录。"""

    _DDL = """
    CREATE TABLE IF NOT EXISTS novel_state (
        book_id            TEXT PRIMARY KEY,
        current_phase      TEXT,
        current_layer      TEXT,
        current_action     TEXT,
        current_scene      TEXT,
        current_sublayer   TEXT,
        human_gate_status  TEXT,
        tree_version       INTEGER DEFAULT 0,
        last_checkpoint    TEXT
    );
    """

    def __init__(self, db_path: str | Path | None = None, book_id: str = "default") -> None:
        super().__init__(db_path)
        self.book_id: str = book_id

    async def init(self) -> None:
        """建表并确保存在默认行。"""
        await self._init_schema(self._DDL)
        async with self._conn() as db:
            await db.execute(
                "INSERT OR IGNORE INTO novel_state (book_id, tree_version) VALUES (?, 0)",
                (self.book_id,),
            )
            await db.commit()

    async def get_state(self) -> dict[str, Any]:
        """读取当前状态字典。无记录时返回空字典。"""
        await self.init()
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM novel_state WHERE book_id = ?", (self.book_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return {}
            return dict(row)

    async def update_state(self, **fields: Any) -> dict[str, Any]:
        """更新状态字段（仅传入需要修改的字段）。

        Returns:
            更新后的完整状态字典。
        """
        if not fields:
            return await self.get_state()
        # 过滤掉非表字段的非法键
        allowed = {
            "current_phase",
            "current_layer",
            "current_action",
            "current_scene",
            "current_sublayer",
            "human_gate_status",
            "tree_version",
            "last_checkpoint",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            logger.warning("update_state 未包含任何合法字段: %s", list(fields.keys()))
            return await self.get_state()

        await self.init()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params: list[Any] = list(updates.values()) + [self.book_id]
        async with self._conn() as db:
            await db.execute(
                f"UPDATE novel_state SET {set_clause} WHERE book_id = ?", params
            )
            await db.commit()
        return await self.get_state()

    async def bump_tree_version(self) -> int:
        """将 tree_version 自增 1 并返回新版本号。"""
        await self.init()
        async with self._conn() as db:
            await db.execute(
                "UPDATE novel_state SET tree_version = tree_version + 1 WHERE book_id = ?",
                (self.book_id,),
            )
            await db.commit()
            cursor = await db.execute(
                "SELECT tree_version FROM novel_state WHERE book_id = ?", (self.book_id,)
            )
            row = await cursor.fetchone()
            return int(row[0]) if row else 0


class TreeStore(_BaseSQLiteStore):
    """小说之树五层产出存储，支持版本化与 JSON 快照。

    层名约定：L0 世界观 / L1 人物网 / L2 情节弧 / L3 场景 / L4 段落。
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS tree_layers (
        layer       TEXT NOT NULL,
        version     INTEGER NOT NULL,
        content     TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (layer, version)
    );
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        snapshots_dir: str | Path | None = None,
    ) -> None:
        super().__init__(db_path)
        if snapshots_dir is None:
            snapshots_dir = _resolve_path(_load_storage_config()["snapshots_dir"])
        self.snapshots_dir: Path = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        """建表（幂等）。"""
        await self._init_schema(self._DDL)

    async def save_layer(self, layer: str, content: dict, version: int) -> None:
        """存储某层产出（带版本号）。同 (layer, version) 会被覆盖。

        Args:
            layer: 层名，如 "L0"。
            content: 该层产出内容（字典）。
            version: 版本号。
        """
        await self.init()
        content_json = json.dumps(content, ensure_ascii=False)
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO tree_layers (layer, version, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (layer, version, content_json, _now_iso()),
            )
            await db.commit()
        logger.info("TreeStore 已保存层 %s v%d", layer, version)

    async def get_layer(self, layer: str, version: int | None = None) -> dict:
        """获取某层产出。version 为 None 时返回最新版本。

        Args:
            layer: 层名。
            version: 指定版本号；None 表示最新。

        Returns:
            该层产出字典。不存在时返回空字典。
        """
        await self.init()
        async with self._conn() as db:
            if version is None:
                cursor = await db.execute(
                    "SELECT content FROM tree_layers WHERE layer = ? "
                    "ORDER BY version DESC LIMIT 1",
                    (layer,),
                )
            else:
                cursor = await db.execute(
                    "SELECT content FROM tree_layers WHERE layer = ? AND version = ?",
                    (layer, version),
                )
            row = await cursor.fetchone()
            if row is None:
                logger.warning("TreeStore 未找到层 %s v%s", layer, version)
                return {}
            return json.loads(row[0])

    async def list_versions(self, layer: str) -> list[int]:
        """列出某层的所有版本号（升序）。"""
        await self.init()
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT version FROM tree_layers WHERE layer = ? ORDER BY version ASC",
                (layer,),
            )
            rows = await cursor.fetchall()
            return [int(r[0]) for r in rows]

    async def save_snapshot(
        self, version: int, phase: str, layer: str, state: dict
    ) -> Path:
        """保存 JSON 快照到 snapshots/ 目录。

        文件名格式：v{version}_{phase}_{layer}.json

        Args:
            version: 版本号。
            phase: 阶段名（如发散/收敛/固化/审视）。
            layer: 层名。
            state: 快照内容字典。

        Returns:
            快照文件的绝对路径。
        """
        # 清洗文件名中的非法字符
        safe_phase = "".join(c if c.isalnum() or c in "-_" else "_" for c in phase)
        safe_layer = "".join(c if c.isalnum() or c in "-_" else "_" for c in layer)
        filename = f"v{version}_{safe_phase}_{safe_layer}.json"
        filepath = self.snapshots_dir / filename
        payload = {
            "version": version,
            "phase": phase,
            "layer": layer,
            "saved_at": _now_iso(),
            "state": state,
        }
        filepath.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("TreeStore 已保存快照: %s", filepath)
        return filepath

    def load_snapshot(self, version: int) -> dict:
        """加载快照。

        按 version 在 snapshots/ 目录中查找匹配文件（取首个命中）。

        Args:
            version: 版本号。

        Returns:
            快照内容字典。找不到时返回空字典。
        """
        candidates = sorted(self.snapshots_dir.glob(f"v{version}_*.json"))
        if not candidates:
            logger.warning("未找到版本 v%d 的快照文件", version)
            return {}
        text = candidates[0].read_text(encoding="utf-8")
        return json.loads(text)


class ForeshadowRegistry(_BaseSQLiteStore):
    """伏笔登记表，追踪伏笔的埋设与回收。"""

    _DDL = """
    CREATE TABLE IF NOT EXISTS foreshadow (
        foreshadow_id      TEXT PRIMARY KEY,
        planted_chapter    TEXT,
        planted_location   TEXT,
        detail             TEXT,
        harvested          INTEGER DEFAULT 0,
        harvested_chapter  TEXT,
        harvested_location TEXT,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL
    );
    """

    async def init(self) -> None:
        """建表（幂等）。"""
        await self._init_schema(self._DDL)

    async def register(
        self,
        foreshadow_id: str,
        planted_chapter: str,
        planted_location: str,
        detail: Any,
    ) -> None:
        """登记一个新伏笔。若 ID 已存在则覆盖。

        Args:
            foreshadow_id: 伏笔唯一标识。
            planted_chapter: 埋设所在章节。
            planted_location: 埋设所在位置描述。
            detail: 伏笔详情（任意可 JSON 序列化对象）。
        """
        await self.init()
        detail_json = json.dumps(detail, ensure_ascii=False)
        now = _now_iso()
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO foreshadow "
                "(foreshadow_id, planted_chapter, planted_location, detail, "
                " harvested, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?, ?)",
                (foreshadow_id, planted_chapter, planted_location, detail_json, now, now),
            )
            await db.commit()
        logger.info("伏笔登记: %s @ %s", foreshadow_id, planted_location)

    async def harvest(
        self,
        foreshadow_id: str,
        harvested_chapter: str,
        harvested_location: str,
    ) -> bool:
        """标记某伏笔为已回收。

        Args:
            foreshadow_id: 伏笔唯一标识。
            harvested_chapter: 回收所在章节。
            harvested_location: 回收所在位置描述。

        Returns:
            是否成功标记（伏笔不存在时返回 False）。
        """
        await self.init()
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT 1 FROM foreshadow WHERE foreshadow_id = ?",
                (foreshadow_id,),
            )
            if await cursor.fetchone() is None:
                logger.warning("尝试回收不存在的伏笔: %s", foreshadow_id)
                return False
            await db.execute(
                "UPDATE foreshadow SET harvested = 1, "
                " harvested_chapter = ?, harvested_location = ?, updated_at = ? "
                "WHERE foreshadow_id = ?",
                (harvested_chapter, harvested_location, _now_iso(), foreshadow_id),
            )
            await db.commit()
        logger.info("伏笔回收: %s @ %s", foreshadow_id, harvested_location)
        return True

    async def get_status(self) -> list[dict]:
        """获取所有伏笔的状态列表。"""
        await self.init()
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM foreshadow ORDER BY created_at ASC")
            rows = await cursor.fetchall()
            result: list[dict] = []
            for row in rows:
                item = dict(row)
                # detail 反序列化为对象
                try:
                    item["detail"] = json.loads(item.get("detail") or "null")
                except json.JSONDecodeError:
                    pass
                # harvested 转布尔
                item["harvested"] = bool(item.get("harvested"))
                result.append(item)
            return result

    async def recovery_rate(self) -> float:
        """计算伏笔回收率（已回收数 / 总数）。

        无伏笔时返回 1.0（视为无未闭环伏笔）。
        """
        await self.init()
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN harvested = 1 THEN 1 ELSE 0 END) AS done "
                "FROM foreshadow"
            )
            row = await cursor.fetchone()
            total = int(row[0]) if row else 0
            done = int(row[1]) if row and row[1] is not None else 0
            if total == 0:
                return 1.0
            return done / total


class ConstraintStore(_BaseSQLiteStore):
    """约束存储，管理每层的硬约束列表。"""

    _DDL = """
    CREATE TABLE IF NOT EXISTS constraints (
        layer            TEXT PRIMARY KEY,
        constraints_json TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    );
    """

    async def init(self) -> None:
        """建表（幂等）。"""
        await self._init_schema(self._DDL)

    async def save_constraints(self, layer: str, constraints: list[str]) -> None:
        """存储某层的硬约束（覆盖写入）。

        Args:
            layer: 层名。
            constraints: 约束字符串列表。
        """
        await self.init()
        constraints_json = json.dumps(constraints, ensure_ascii=False)
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO constraints (layer, constraints_json, updated_at) "
                "VALUES (?, ?, ?)",
                (layer, constraints_json, _now_iso()),
            )
            await db.commit()
        logger.info("ConstraintStore 已保存层 %s 的 %d 条约束", layer, len(constraints))

    async def get_constraints(self, layer: str) -> list[str]:
        """获取某层的硬约束列表。不存在时返回空列表。"""
        await self.init()
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT constraints_json FROM constraints WHERE layer = ?", (layer,)
            )
            row = await cursor.fetchone()
            if row is None:
                return []
            try:
                data = json.loads(row[0])
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                logger.warning("层 %s 的约束 JSON 解析失败", layer)
                return []


class AgentLog(_BaseSQLiteStore):
    """Agent 调用日志，记录每次调用的输入/输出/指标。"""

    _DDL = """
    CREATE TABLE IF NOT EXISTS agent_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        agent        TEXT NOT NULL,
        action       TEXT,
        layer        TEXT,
        input_data   TEXT,
        output_data  TEXT,
        metrics      TEXT,
        created_at   TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_agent_log_layer ON agent_log(layer);
    CREATE INDEX IF NOT EXISTS idx_agent_log_agent ON agent_log(agent);
    """

    async def init(self) -> None:
        """建表与索引（幂等）。"""
        await self._init_schema(self._DDL)

    async def log(
        self,
        agent: str,
        action: str,
        input_data: dict,
        output_data: dict,
        metrics: dict,
        layer: str | None = None,
    ) -> int:
        """记录一次 Agent 调用。

        Args:
            agent: Agent 角色名。
            action: 动作名（如发散/收敛/固化/审视）。
            input_data: 输入数据字典。
            output_data: 输出数据字典。
            metrics: 指标字典（如重复率、多样性等）。
            layer: 关联层名（可选）。

        Returns:
            新日志行的自增 id。
        """
        await self.init()
        async with self._conn() as db:
            cursor = await db.execute(
                "INSERT INTO agent_log "
                "(agent, action, layer, input_data, output_data, metrics, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    agent,
                    action,
                    layer,
                    json.dumps(input_data, ensure_ascii=False),
                    json.dumps(output_data, ensure_ascii=False),
                    json.dumps(metrics, ensure_ascii=False),
                    _now_iso(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_history(
        self, layer: str | None = None, agent: str | None = None
    ) -> list[dict]:
        """查询调用历史，可按层与 Agent 过滤。

        Args:
            layer: 仅返回该层的记录（None 表示不过滤）。
            agent: 仅返回该 Agent 的记录（None 表示不过滤）。

        Returns:
            日志记录列表（按时间升序）。input/output/metrics 已反序列化。
        """
        await self.init()
        conditions: list[str] = []
        params: list[Any] = []
        if layer is not None:
            conditions.append("layer = ?")
            params.append(layer)
        if agent is not None:
            conditions.append("agent = ?")
            params.append(agent)
        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        query = (
            "SELECT * FROM agent_log" + where_clause + " ORDER BY created_at ASC, id ASC"
        )
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            result: list[dict] = []
            for row in rows:
                item = dict(row)
                for key in ("input_data", "output_data", "metrics"):
                    try:
                        item[key] = json.loads(item.get(key) or "null")
                    except json.JSONDecodeError:
                        pass
                result.append(item)
            return result


class StoryStateStore(_BaseSQLiteStore):
    """故事世界状态快照存储，每章结束后回写。

    追踪四个维度的状态变化：
    - character_states: 角色状态（位置/情绪/生理/已知信息）
    - timeline: 事件时间线（章节/事件/时间标记）
    - resources: 资源变动（获得/失去的物品/权限/盟友）
    - relationships: 关系变动（信任度/联盟/冲突）

    每章存储一份完整快照，支持按章节回溯。
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS story_state (
        chapter_index      INTEGER PRIMARY KEY,
        chapter_title      TEXT,
        character_states   TEXT NOT NULL,
        timeline_events    TEXT NOT NULL,
        resource_changes   TEXT NOT NULL,
        relationship_changes TEXT NOT NULL,
        summary            TEXT,
        created_at         TEXT NOT NULL
    );
    """

    async def init(self) -> None:
        """建表（幂等）。"""
        await self._init_schema(self._DDL)

    async def save_snapshot(
        self,
        chapter_index: int,
        chapter_title: str,
        character_states: list[dict],
        timeline_events: list[dict],
        resource_changes: list[dict],
        relationship_changes: list[dict],
        summary: str = "",
    ) -> None:
        """保存某章结束后的故事状态快照。

        同一 chapter_index 的快照会被覆盖。

        :param chapter_index: 章节序号
        :param chapter_title: 章节标题
        :param character_states: 角色状态列表
        :param timeline_events: 时间线事件列表
        :param resource_changes: 资源变动列表
        :param relationship_changes: 关系变动列表
        :param summary: 本章状态变化摘要
        """
        await self.init()
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO story_state "
                "(chapter_index, chapter_title, character_states, "
                " timeline_events, resource_changes, relationship_changes, "
                " summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chapter_index,
                    chapter_title,
                    json.dumps(character_states, ensure_ascii=False),
                    json.dumps(timeline_events, ensure_ascii=False),
                    json.dumps(resource_changes, ensure_ascii=False),
                    json.dumps(relationship_changes, ensure_ascii=False),
                    summary,
                    _now_iso(),
                ),
            )
            await db.commit()
        logger.info(
            "StoryStateStore 已保存第%d章状态快照: 角色=%d, 事件=%d, 资源=%d, 关系=%d",
            chapter_index,
            len(character_states),
            len(timeline_events),
            len(resource_changes),
            len(relationship_changes),
        )

    async def get_snapshot(self, chapter_index: int) -> dict:
        """获取某章的状态快照。

        :param chapter_index: 章节序号
        :return: 状态快照字典，不存在时返回空字典
        """
        await self.init()
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM story_state WHERE chapter_index = ?",
                (chapter_index,),
            )
            row = await cursor.fetchone()
            if row is None:
                return {}
            item = dict(row)
            for key in (
                "character_states",
                "timeline_events",
                "resource_changes",
                "relationship_changes",
            ):
                try:
                    item[key] = json.loads(item.get(key) or "[]")
                except json.JSONDecodeError:
                    item[key] = []
            return item

    async def get_latest_snapshot(self) -> dict:
        """获取最新章节的状态快照。

        :return: 状态快照字典，无记录时返回空字典
        """
        await self.init()
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM story_state ORDER BY chapter_index DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            if row is None:
                return {}
            item = dict(row)
            for key in (
                "character_states",
                "timeline_events",
                "resource_changes",
                "relationship_changes",
            ):
                try:
                    item[key] = json.loads(item.get(key) or "[]")
                except json.JSONDecodeError:
                    item[key] = []
            return item

    async def get_all_snapshots(self) -> list[dict]:
        """获取所有章节的状态快照列表（按章节升序）。

        :return: 状态快照列表
        """
        await self.init()
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM story_state ORDER BY chapter_index ASC"
            )
            rows = await cursor.fetchall()
            result: list[dict] = []
            for row in rows:
                item = dict(row)
                for key in (
                    "character_states",
                    "timeline_events",
                    "resource_changes",
                    "relationship_changes",
                ):
                    try:
                        item[key] = json.loads(item.get(key) or "[]")
                    except json.JSONDecodeError:
                        item[key] = []
                result.append(item)
            return result
