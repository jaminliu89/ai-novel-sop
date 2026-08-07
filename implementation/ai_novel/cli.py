#!/usr/bin/env python3
"""
AI 小说写作流水线 —— 命令行入口

用法：
  python -m ai_novel.cli run           # 运行 L0→L2 单链路
  python -m ai_novel.cli status        # 查看当前状态
  python -m ai_novel.cli resume        # 从断点恢复
  python -m ai_novel.cli concepts      # 生成科幻悬疑候选点子
  python -m ai_novel.cli decompose     # 拆解标杆小说（需提供文本）
  python -m ai_novel.cli outline       # 查看已生成的大纲

首次运行前：
  1. pip install -r requirements.txt
  2. 在 config.yaml 中填入 API Key，或设置环境变量：
     - DEEPSEEK_API_KEY
     - ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ai_novel.cli")


def load_config() -> dict:
    """加载 config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_api_keys(config: dict) -> bool:
    """检查 API Key 是否已配置"""
    import os

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")

    deepseek_cfg = config.get("deepseek", {})
    claude_cfg = config.get("claude", {})

    ds_configured = (
        deepseek_key
        or deepseek_cfg.get("api_key", "") != "YOUR_DEEPSEEK_API_KEY"
    )
    cl_configured = (
        claude_key
        or claude_cfg.get("api_key", "") != "YOUR_CLAUDE_API_KEY"
    )

    if not ds_configured and not cl_configured:
        print("⚠️  未检测到 API Key！请执行以下操作之一：")
        print("   1. 在 config.yaml 中填入 API Key")
        print("   2. 设置环境变量：")
        print("      export DEEPSEEK_API_KEY='your-key'")
        print("      export ANTHROPIC_API_KEY='your-key'")
        return False

    if not ds_configured:
        print("⚠️  未检测到 DeepSeek API Key（园丁/剪枝师/记忆管家/监工/拆解师需要）")
        print("   设置环境变量: export DEEPSEEK_API_KEY='your-key'")

    if not cl_configured:
        print("⚠️  未检测到 Anthropic API Key（协调者/蒸馏者需要）")
        print("   设置环境变量: export ANTHROPIC_API_KEY='your-key'")

    return True


# ====================================================================
# 命令处理
# ====================================================================

async def cmd_run(args: argparse.Namespace) -> None:
    """运行 L0→L2 单链路"""
    config = load_config()
    if not check_api_keys(config):
        sys.exit(1)

    from .orchestrator import Orchestrator

    orch = Orchestrator(config)

    print("\n" + "=" * 60)
    print("  AI 小说写作流水线 · L0→L2 单链路运行")
    print("  体裁: 科幻悬疑 | 语言: 中文 | 目标: 8-15 万字")
    print("=" * 60)
    print()

    results = await orch.run_l0_l2()

    print("\n" + "=" * 60)
    print("  L0→L2 单链路运行完成")
    print("=" * 60)

    for layer, result in results.items():
        status = result.get("status", "unknown") if isinstance(result, dict) else "done"
        print(f"  {layer}: {status}")

    if "outline" in results:
        print(f"\n  完整大纲已保存到: ai_novel/output_outline.json")
        print(f"  可用 'python -m ai_novel.cli outline' 查看")


async def cmd_status(args: argparse.Namespace) -> None:
    """查看当前状态"""
    from .orchestrator import Orchestrator

    config = load_config()
    orch = Orchestrator(config)
    await orch.load_state()

    print("\n当前状态:")
    print(f"  阶段: {orch.current_phase.value}")
    print(f"  动作: {orch.current_action.value}")
    print(f"  树版本: v{orch.tree_version}")

    # 查看各层是否已固化
    for layer in ["L0", "L1", "L2", "L3", "L4"]:
        content = await orch.tree_store.get_layer(layer)
        if content:
            versions = await orch.tree_store.list_versions(layer)
            print(f"  {layer}: 已固化 (版本: {versions})")
        else:
            print(f"  {layer}: 未开始")


async def cmd_resume(args: argparse.Namespace) -> None:
    """从断点恢复"""
    config = load_config()
    if not check_api_keys(config):
        sys.exit(1)

    from .orchestrator import Orchestrator

    orch = Orchestrator(config)
    await orch.load_state()

    print(f"\n从断点恢复: 阶段={orch.current_phase.value}, 动作={orch.current_action.value}")

    # 继续运行 L0→L2
    results = await orch.run_l0_l2()
    print("\n恢复运行完成。")


async def cmd_concepts(args: argparse.Namespace) -> None:
    """生成科幻悬疑候选点子"""
    config = load_config()
    if not check_api_keys(config):
        sys.exit(1)

    from .orchestrator import Orchestrator

    orch = Orchestrator(config)

    print("\n" + "=" * 60)
    print("  生成科幻悬疑核心设定候选")
    print("=" * 60 + "\n")

    result = await orch.generate_concept_candidates()

    candidates = result.get("candidates", [])
    for i, c in enumerate(candidates, 1):
        novelty = c.get("novelty", 0)
        print(f"  候选 {i} [novelty: {novelty:.2f}]:")
        print(f"    {c.get('content', '')}")
        print(f"    理由: {c.get('rationale', '')}")
        print()

    print(f"共 {len(candidates)} 个候选。选择一个进入 L0 世界观建构。")
    print("提示: 运行 'python -m ai_novel.cli run' 开始完整 L0→L2 流程。")


async def cmd_decompose(args: argparse.Namespace) -> None:
    """拆解标杆小说"""
    config = load_config()
    if not check_api_keys(config):
        sys.exit(1)

    from .orchestrator import Orchestrator

    orch = Orchestrator(config)

    # 获取输入
    title = args.title or input("小说标题: ").strip()
    author = args.author or input("作者: ").strip()
    genre = args.genre or "悬疑"

    # 获取文本来源
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        source = "full_text"
    elif args.summary:
        text = args.summary
        source = "chapter_summary"
    else:
        print("请提供小说文本 (--file) 或章节摘要 (--summary)")
        sys.exit(1)

    print(f"\n开始拆解《{title}》({author})...")

    result = await orch.run_decompose(
        novel_title=title,
        novel_author=author,
        novel_genre=genre,
        text_content=text,
        text_source=source,
    )

    print(f"\n拆解完成！")
    print(f"  伏笔映射: {len(result.get('dimensions', {}).get('plot_skeleton', {}).get('foreshadow_map', []))} 条")
    print(f"  人物: {len(result.get('dimensions', {}).get('character_graph', {}).get('characters', []))} 个")
    print(f"  世界规则: {len(result.get('dimensions', {}).get('world_rules', {}).get('rules', []))} 条")
    print(f"  可学习模型: {len(result.get('learnable_models', []))} 个")

    # 保存拆解结果
    output_path = Path(__file__).parent / f"config/few_shot/{title}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  拆解档案已保存到: {output_path}")


async def cmd_outline(args: argparse.Namespace) -> None:
    """查看已生成的大纲"""
    outline_path = Path(__file__).parent / "output_outline.json"
    if not outline_path.exists():
        print("尚未生成大纲。请先运行 'python -m ai_novel.cli run'")
        return

    with open(outline_path, "r", encoding="utf-8") as f:
        outline = json.load(f)

    print("\n" + "=" * 60)
    print("  已生成的大纲 (L0-L2)")
    print("=" * 60 + "\n")

    for layer, content in outline.items():
        print(f"--- {layer} ---")
        content_str = json.dumps(content, ensure_ascii=False, indent=2)
        if len(content_str) > 2000:
            content_str = content_str[:2000] + "\n... (内容过长，已截断)"
        print(content_str)
        print()


# ====================================================================
# 主入口
# ====================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI 工业化小说写作流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m ai_novel.cli run           # 运行 L0→L2 单链路
  python -m ai_novel.cli concepts      # 生成科幻悬疑候选点子
  python -m ai_novel.cli status        # 查看当前状态
  python -m ai_novel.cli outline       # 查看已生成的大纲
  python -m ai_novel.cli decompose --title 无人生还 --author 克里斯蒂 --summary "..."
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run
    subparsers.add_parser("run", help="运行 L0→L2 单链路")

    # status
    subparsers.add_parser("status", help="查看当前状态")

    # resume
    subparsers.add_parser("resume", help="从断点恢复运行")

    # concepts
    subparsers.add_parser("concepts", help="生成科幻悬疑候选点子")

    # outline
    subparsers.add_parser("outline", help="查看已生成的大纲")

    # decompose
    dec_parser = subparsers.add_parser("decompose", help="拆解标杆小说")
    dec_parser.add_argument("--title", help="小说标题")
    dec_parser.add_argument("--author", help="作者")
    dec_parser.add_argument("--genre", default="悬疑", help="体裁")
    dec_parser.add_argument("--file", help="小说全文文件路径")
    dec_parser.add_argument("--summary", help="章节摘要文本")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 执行对应命令
    cmd_map = {
        "run": cmd_run,
        "status": cmd_status,
        "resume": cmd_resume,
        "concepts": cmd_concepts,
        "outline": cmd_outline,
        "decompose": cmd_decompose,
    }

    cmd_func = cmd_map.get(args.command)
    if cmd_func:
        asyncio.run(cmd_func(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
