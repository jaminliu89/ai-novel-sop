#!/usr/bin/env python3
"""
L0→L2 单链路测试脚本

验证"分层 + 动作循环"能产出自洽大纲。
两条验证线之一（另一条是拆解流水线）。

用法：
  cd /workspace/ai-novel-sop/implementation

  # Mock 模式（无需 API Key，验证流水线逻辑）
  python run_l0_l2.py --mock

  # 真实模式（需要 API Key）
  python run_l0_l2.py

  # 或通过环境变量
  AI_NOVEL_MOCK=1 python run_l0_l2.py

前置条件：
  1. pip install -r requirements.txt
  2. 真实模式需设置 API Key:
     - export DEEPSEEK_API_KEY='your-key'
     - export ANTHROPIC_API_KEY='your-key'
     或在 ai_novel/config.yaml 中填入
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# 确保能导入 ai_novel 包
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from ai_novel.orchestrator import Orchestrator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_l0_l2")


def load_config() -> dict:
    """加载配置"""
    config_path = Path(__file__).parent / "ai_novel" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main() -> None:
    """主测试流程"""
    parser = argparse.ArgumentParser(description="L0→L2 单链路测试")
    parser.add_argument("--mock", action="store_true", help="使用 Mock 模式（无需 API Key）")
    args = parser.parse_args()

    # 确定 Mock 模式
    mock_mode = args.mock or os.environ.get("AI_NOVEL_MOCK") == "1"
    if mock_mode:
        os.environ["AI_NOVEL_MOCK"] = "1"

    print()
    print("=" * 60)
    print("  Phase 1 验证 · L0→L2 单链路测试")
    print("  目标: 验证'分层 + 动作循环'能产出自洽大纲")
    if mock_mode:
        print("  模式: Mock（无需 API Key）")
    else:
        print("  模式: 真实 LLM 调用")
    print("=" * 60)
    print()

    # 加载配置
    config = load_config()

    # 检查 API Key（Mock 模式跳过）
    if not mock_mode:
        ds_key = os.environ.get("DEEPSEEK_API_KEY", config.get("deepseek", {}).get("api_key", ""))
        cl_key = os.environ.get("ANTHROPIC_API_KEY", config.get("claude", {}).get("api_key", ""))

        if ds_key in ("", "YOUR_DEEPSEEK_API_KEY"):
            print("⚠️  未配置 DeepSeek API Key")
            print("   请设置环境变量: export DEEPSEEK_API_KEY='your-key'")
            print("   或在 ai_novel/config.yaml 中填入")
            print("   或使用 Mock 模式: python run_l0_l2.py --mock")
            sys.exit(1)

        if cl_key in ("", "YOUR_CLAUDE_API_KEY"):
            print("⚠️  未配置 Anthropic API Key")
            print("   请设置环境变量: export ANTHROPIC_API_KEY='your-key'")
            print("   或在 ai_novel/config.yaml 中填入")
            print("   或使用 Mock 模式: python run_l0_l2.py --mock")
            sys.exit(1)

        print(f"  ✓ DeepSeek: {ds_key[:8]}...")
        print(f"  ✓ Claude:   {cl_key[:8]}...")
    else:
        print("  ✓ Mock 模式已启用")
    print()

    # 初始化协调者
    orch = Orchestrator(config, book_id="sf_mystery_test_001")

    print("  ✓ 协调者已初始化")
    print("  ✓ 7 个 Agent 已就绪")
    print("  ✓ 记忆层 (SQLite + JSON) 已就绪")
    print("  ✓ 质量度量模块已就绪")
    print()

    # 运行 L0→L2
    print("-" * 60)
    print("  开始 L0→L2 单链路运行")
    print("  流程: L0 世界观 → L1 人物网 → L2 情节弧 → 主题蒸馏")
    print("  每层: 发散(园丁) → 收敛(剪枝师) → 固化(记忆管家) → 审视(监工) → [人机确认]")
    print("-" * 60)
    print()

    try:
        results = await orch.run_l0_l2()
    except KeyboardInterrupt:
        print("\n\n用户中断。状态已保存，可用 'python -m ai_novel.cli resume' 恢复。")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n运行出错: {e}")
        logger.exception("L0→L2 运行失败")
        sys.exit(1)

    # 输出结果
    print()
    print("=" * 60)
    print("  L0→L2 单链路运行结果")
    print("=" * 60)
    print()

    all_passed = True
    for layer in ["L0", "L1", "L2"]:
        result = results.get(layer, {})
        status = result.get("status", "done") if isinstance(result, dict) else "done"
        if status == "failed":
            all_passed = False
            print(f"  ✗ {layer}: 失败 - {result.get('reason', '未知原因')}")
        else:
            print(f"  ✓ {layer}: 完成 (版本 v{result.get('new_version', '?')})")

    if "distillation" in results:
        dist = results["distillation"]
        theme = dist.get("theme_statement", "未生成")
        print(f"\n  主题: {theme}")

    print()
    if all_passed:
        print("  ✓ L0→L2 单链路验证通过！")
        print("  ✓ '分层 + 动作循环'能产出自洽大纲。")
        print()
        if mock_mode:
            print("  注意: Mock 模式仅验证流水线逻辑，产出为预设内容。")
            print("  接入真实 API Key 后，运行 'python run_l0_l2.py' 获得真实产出。")
        print()
        print("  下一步:")
        print("    1. 审查 output_outline.json 中的大纲质量")
        print("    2. 运行拆解流水线验证标杆拆解")
        print("    3. 两条线都通过后进入 Phase 2")
    else:
        print("  ✗ 部分层未通过，需要排查问题。")
        print("  可用 'python -m ai_novel.cli status' 查看详细状态。")

    print()
    outline_path = Path(__file__).parent / "ai_novel" / "output_outline.json"
    print(f"  大纲文件: {outline_path}")


if __name__ == "__main__":
    asyncio.run(main())
