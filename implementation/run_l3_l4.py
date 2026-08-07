#!/usr/bin/env python3
"""
L3→L4 全链路运行脚本

流程：
1. 加载已有 L0-L2 大纲（从 output_outline.json 或 TreeStore）
2. 对第一幕 5 章执行 L3 场景分解
3. 对每个场景执行 L4 段落生成
4. 质量检测 + 伏笔登记
5. 输出完整第一幕

使用 Mock 模式无需 API Key。
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 设置 Mock 模式
os.environ["AI_NOVEL_MOCK"] = "1"

IMPL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(IMPL_DIR))

import yaml
from ai_novel.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_l3_l4")


async def main() -> None:
    print("=" * 60)
    print("  L3→L4 全链路运行 · 场景分解 + 段落生成")
    print("  模式: Mock（无需 API Key）")
    print("  目标: 第一幕 5 章 (Ch1-5)")
    print("=" * 60)

    # 加载配置
    config_path = IMPL_DIR / "ai_novel" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["llm_mode"] = "mock"

    # 初始化协调者
    orch = Orchestrator(config)

    # 确认 L0-L2 大纲已存在
    outline_path = IMPL_DIR / "ai_novel" / "output_outline.json"
    if not outline_path.exists():
        print("\n❌ L0-L2 大纲不存在，请先运行 run_direct_l0_l2.py")
        sys.exit(1)

    print(f"\n✓ 已加载 L0-L2 大纲: {outline_path.name}")

    # 检查 TreeStore 中是否已有 L0-L2 数据
    l0 = await orch.tree_store.get_layer("L0")
    l1 = await orch.tree_store.get_layer("L1")
    l2 = await orch.tree_store.get_layer("L2")

    if not l0 or not l1 or not l2:
        # 从 output_outline.json 导入到 TreeStore
        print("\n导入 L0-L2 大纲到 TreeStore...")
        with open(outline_path, "r", encoding="utf-8") as f:
            outline = json.load(f)
        for layer_key in ("L0", "L1", "L2"):
            if layer_key in outline:
                content = outline[layer_key]
                version = content.get("version", 1)
                await orch.tree_store.save_layer(layer_key, content, version)
                # 导入约束
                constraints = content.get("constraints", [])
                if constraints:
                    await orch.constraint_store.save_constraints(layer_key, constraints)
                print(f"  已导入 {layer_key} v{version} ({len(constraints)} 条约束)")

    # 运行 L3→L4
    print("\n>>> 开始 L3→L4 链路 <<<\n")
    result = await orch.run_l3_l4()

    # 输出汇总
    print("\n" + "=" * 60)
    print("  L3→L4 全链路运行完成")
    print("=" * 60)
    print(f"\n  处理章节数:   {result['chapters_processed']}")
    print(f"  总场景数:     {result['total_scenes']}")
    print(f"  总字数:       {result['total_words']}")
    print(f"  伏笔登记数:   {len(result['foreshadow_status'])}")

    # 质量报告
    quality = result["quality_report"]["overall"]
    print(f"\n  全文质量:")
    print(f"    重复率:     {quality['repetition_rate']:.4f}  (阈值 0.15)")
    print(f"    AI腔计数:   {quality['ai_ism_count']}  (阈值 0)")
    print(f"    通过:       {'✓' if quality['passed'] else '✗'}")

    # 逐场景质量
    print(f"\n  逐场景质量:")
    for p in result["quality_report"]["per_paragraph"]:
        q = p["quality"]
        status = "✓" if q.get("passed", True) else "✗"
        rep = q.get("repetition_rate", 0)
        ai = q.get("ai_ism_count", 0)
        print(
            f"    {status} {p['scene_id']}: "
            f"{p['word_count']}字, 重复率={rep:.4f}, AI腔={ai}"
        )

    # 伏笔状态
    print(f"\n  伏笔状态:")
    for fs in result["foreshadow_status"]:
        status = "已回收" if fs.get("harvested") else "待回收"
        print(f"    {fs['foreshadow_id']}: {status} @ {fs.get('planted_location', '?')}")

    # 输出文件
    print(f"\n  产出文件:")
    print(f"    JSON:  ai_novel/output_l3_l4.json")
    print(f"    正文:  ai_novel/output_act1.md")
    print(f"    场景:  TreeStore L3 (v{orch.tree_version + 1}-v{orch.tree_version + 5})")
    print(f"    段落:  TreeStore L4 (v{orch.tree_version + 11}-v{orch.tree_version + 15})")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
