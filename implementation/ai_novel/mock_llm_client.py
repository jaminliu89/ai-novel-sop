"""
Mock LLM 客户端
===============

无需真实 API Key 即可跑通 L0→L2 全链路。
用于：
1. 验证状态机流转、存储层、Agent 协作逻辑
2. 开发调试时快速迭代
3. CI/CD 冒烟测试

使用方式：
  在 config.yaml 中设置 llm_mode: mock
  或设置环境变量 AI_NOVEL_MOCK=1
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("ai_novel.mock_llm_client")


# ------------------------------------------------------------------
# 各 Agent 角色的 Mock 响应
# ------------------------------------------------------------------

_MOCK_RESPONSES: dict[str, dict] = {
    # 园丁·发散：返回 3 个科幻悬疑候选
    "gardener": {
        "candidates": [
            {
                "id": "c1",
                "title": "记忆裂痕",
                "novelty": 0.85,
                "content": (
                    "近未来，人类可通过神经接口编辑记忆。一名记忆编辑师发现，"
                    "自己的客户正在系统性地删除同一段记忆——某个地下实验室的片段。"
                    "当她试图追查时，发现自己也被编辑过。"
                ),
            },
            {
                "id": "c2",
                "title": "量子囚徒",
                "novelty": 0.78,
                "content": (
                    "量子计算机实现了真正的随机数生成，但研究者发现某些'随机'序列"
                    "在特定条件下呈现规律——仿佛有人在从未来发送信息。"
                ),
            },
            {
                "id": "c3",
                "title": "暗物感知",
                "novelty": 0.90,
                "content": (
                    "一种新型脑机接口让盲人能'看到'暗物质分布。但使用者开始"
                    "看到地球上不应该存在的暗物质结构——某种巨型生命体。"
                ),
            },
        ],
        "diversity_note": "三个候选分别从记忆操控、量子通信、暗物质生命切入，语义差异化充分。",
    },
    # 剪枝师·收敛：选中 c3
    "pruner": {
        "selected": "c3",
        "scores": [
            {"id": "c1", "total": 78, "novelty": 0.85, "eliminated": False, "reason": "记忆编辑题材已有较多同类作品"},
            {"id": "c2", "total": 72, "novelty": 0.78, "eliminated": True, "reason": "量子通信方向科幻硬度高但悬疑元素偏弱"},
            {"id": "c3", "total": 88, "novelty": 0.90, "eliminated": False, "reason": "暗物质感知设定新颖，悬疑元素自然融入，反共识走向"},
        ],
        "selection_rationale": "c3「暗物感知」在创新性（0.90）、科幻悬疑融合度、叙事潜力三维度均领先。",
    },
    # 记忆管家·固化
    "curator": {
        "memory_id": "L0_20260807",
        "new_version": 1,
        "extracted_constraints": [
            "核心设定：暗物质感知型脑机接口",
            "世界规则：暗物质生命体存在且可被特定接口感知",
            "悬疑内核：暗物质结构的异常分布暗示某种智慧生命",
            "禁止：暗物质生命不能是传统的外星人形象",
        ],
        "structured_content": {
            "core_setting": "暗物质感知型脑机接口",
            "tech_premise": "新型脑机接口让盲人能感知暗物质分布",
            "mystery_hook": "使用者看到地球上不该存在的暗物质结构",
            "world_rules": [
                "暗物质生命体存在",
                "只有特定脑机接口能感知",
                "暗物质结构呈现某种智能模式",
            ],
        },
    },
    # 监工·审视
    "inspector": {
        "verdict": "pass",
        "checks": [
            {"item": "层间一致性", "status": "✓", "note": "无上层约束冲突"},
            {"item": "设定创新性", "status": "✓", "note": "novelty=0.90，反共识走向"},
            {"item": "悬疑融合度", "status": "✓", "note": "科幻元素与悬疑自然融合"},
            {"item": "AI腔密度", "status": "✓", "note": "无AI腔禁用词"},
            {"item": "重复率", "status": "✓", "note": "重复率=0.02"},
        ],
        "issues": [],
        "metrics": {
            "repetition_rate": 0.02,
            "ai_ism_count": 0,
        },
    },
    # 蒸馏者·主题蒸馏
    "distiller": {
        "theme_statement": "当人类感知到看不见的世界时，真正的恐惧不是未知本身，而是发现自己一直是那个被观察者。",
        "core_conflict": "感知能力 vs 存在焦虑：看见暗物质的人发现自己也被暗物质中的存在所注视",
        "reader_expectations_challenged": [
            "读者预期暗物质是惰性物质 → 实际上是某种生命形式",
            "读者预期脑机接口是工具 → 实际上是被暗物质生命'植入'的感知器官",
        ],
        "thematic_questions": [
            "感知的边界在哪里？我们看到的'现实'有多少是被筛选过的？",
            "如果暗物质中有智慧生命，它们眼中的我们是什么？",
        ],
    },
    # 拆解师·反向拆解
    "decoder": {
        "novel_title": "样本小说",
        "plot_skeleton": {
            "act1": "设定建立 → 异常出现",
            "act2": "调查深入 → 真相逼近",
            "act3": "反转揭示 → 主题升华",
        },
        "voice_fingerprint": {
            "narrative_voice": "冷静克制的第一人称",
            "dialogue_style": "短句为主，信息密度高",
        },
        "character_graph": {"protagonist": "调查者", "antagonist": "隐藏的真相"},
        "world_rules": ["规则1", "规则2"],
    },
}


# ------------------------------------------------------------------
# L3 场景分解 Mock 数据
# ------------------------------------------------------------------

_L3_SCENES: dict[int, dict] = {
    1: {
        "scenes": [
            {
                "scene_id": "ch1_s1",
                "title": "死区初现",
                "location": "共感科技大厦B座三层·开放办公区·下午",
                "characters": ["沈语冰", "陈静"],
                "conflict": "沈语冰发现陈静的情绪信号完全归零，但陈静本人行为正常",
                "emotional_goal": "不安与困惑——熟悉的日常出现裂缝",
                "sensory_anchor": "植入体反馈的'白纸'感——没有温度、没有压力、没有色彩",
                "narrative_function": "推进情节",
                "foreshadow_actions": [
                    {"id": "fs3", "action": "埋设", "detail": "左手小指发麻"},
                    {"id": "fs1", "action": "埋设", "detail": "植入体温度异常+0.6°C"},
                ],
                "word_target": 1200,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch1_s2",
                "title": "会议中的确认",
                "location": "共感科技·会议室·下午",
                "characters": ["沈语冰", "陈静", "产品总监", "项目经理"],
                "conflict": "在密集情绪信号中确认陈静的零信号持续存在",
                "emotional_goal": "压抑的焦虑——在人群中独自察觉异常",
                "sensory_anchor": "会议室多人情绪叠加如'缓慢沸腾的汤'，陈静的零信号格外刺眼",
                "narrative_function": "推进情节",
                "foreshadow_actions": [],
                "word_target": 800,
                "quality_mode": "fast",
            },
            {
                "scene_id": "ch1_s3",
                "title": "数据库中的线索",
                "location": "沈语冰的工位 → 家中·夜晚",
                "characters": ["沈语冰"],
                "conflict": "系统报告显示一切正常，但沈语冰找到了三条匿名反馈",
                "emotional_goal": "独处的寂静中，疑虑开始发酵",
                "sensory_anchor": "饭团在微波炉里转圈，左手小指的麻木感",
                "narrative_function": "埋设伏笔",
                "foreshadow_actions": [
                    {"id": "fs3", "action": "推进", "detail": "失聪区域扩大至第二指节"},
                ],
                "word_target": 1000,
                "quality_mode": "precision",
            },
        ],
    },
    2: {
        "scenes": [
            {
                "scene_id": "ch2_s1",
                "title": "晨间观察",
                "location": "共感科技·开放办公区·早晨",
                "characters": ["沈语冰", "陈静"],
                "conflict": "确认陈静的零信号在第二天持续",
                "emotional_goal": "冷静的执念——沈语冰开始系统性地追踪",
                "sensory_anchor": "空旷办公区的淡薄情绪光晕，陈静走进时信号依然为零",
                "narrative_function": "推进情节",
                "foreshadow_actions": [],
                "word_target": 600,
                "quality_mode": "fast",
            },
            {
                "scene_id": "ch2_s2",
                "title": "食堂相遇·苏映",
                "location": "共感科技·食堂·中午",
                "characters": ["沈语冰", "苏映"],
                "conflict": "苏映透露在情绪信号中发现了未知频率模式",
                "emotional_goal": "好奇与警觉并存——两条调查线开始交汇",
                "sensory_anchor": "苏映情绪信号中亮黄色底色上的蓝色脉冲，兴奋与恐惧并存",
                "narrative_function": "推进情节",
                "foreshadow_actions": [
                    {"id": "fs1", "action": "推进", "detail": "植入体温度升至37.8°C"},
                ],
                "word_target": 1000,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch2_s3",
                "title": "四十七条记录",
                "location": "沈语冰的工位·下午",
                "characters": ["沈语冰"],
                "conflict": "发现47个用户信号大幅下降，这不是个例",
                "emotional_goal": "从个人疑虑升级为系统性恐惧",
                "sensory_anchor": "屏幕上的数据曲线，左手无名指也开始发麻",
                "narrative_function": "推进情节",
                "foreshadow_actions": [
                    {"id": "fs3", "action": "推进", "detail": "无名指第二指节开始发麻"},
                ],
                "word_target": 800,
                "quality_mode": "fast",
            },
            {
                "scene_id": "ch2_s4",
                "title": "夜公园·线索梳理",
                "location": "张江路·小公园·人工湖边·夜晚",
                "characters": ["沈语冰"],
                "conflict": "四条线索指向一个被压制的真相",
                "emotional_goal": "孤独中的清醒——沈语冰确认有人在掩盖死区现象",
                "sensory_anchor": "湖面碎光，夜鹭缩着脖子一动不动，植入体微烫如嵌在皮下的硬币",
                "narrative_function": "推进情节",
                "foreshadow_actions": [],
                "word_target": 800,
                "quality_mode": "precision",
            },
        ],
    },
    3: {
        "scenes": [
            {
                "scene_id": "ch3_s1",
                "title": "不速之客",
                "location": "共感科技大厦·一楼大厅·上午",
                "characters": ["沈语冰", "姜北辰"],
                "conflict": "姜北辰拦住沈语冰，请求她用植入体确认女儿的状态",
                "emotional_goal": "突兀的侵入感——沈语冰的私人调查被外部力量打断",
                "sensory_anchor": "姜北辰压抑的愤怒情绪信号——暗红色底色上的灰白条纹",
                "narrative_function": "推进情节",
                "foreshadow_actions": [],
                "word_target": 1000,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch3_s2",
                "title": "画作的秘密",
                "location": "姜北辰的车内",
                "characters": ["沈语冰", "姜北辰"],
                "conflict": "姜北辰展示女儿的画作，画中反复出现某种波形图案",
                "emotional_goal": "不安的共鸣——沈语冰意识到死区比她想的更复杂",
                "sensory_anchor": "画作上的重复波形——像心电图，但频率不对",
                "narrative_function": "埋设伏笔",
                "foreshadow_actions": [
                    {"id": "fs5", "action": "埋设", "detail": "女儿画作中的重复波形图案"},
                ],
                "word_target": 1200,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch3_s3",
                "title": "不信任的联盟",
                "location": "咖啡馆",
                "characters": ["沈语冰", "姜北辰"],
                "conflict": "沈语冰和姜北辰在调查方法上产生分歧——技术 vs 直觉",
                "emotional_goal": "张力中的妥协——两个不同世界的人被迫合作",
                "sensory_anchor": "咖啡杯上的水雾，姜北辰的命令式短句",
                "narrative_function": "塑造人物",
                "foreshadow_actions": [],
                "word_target": 800,
                "quality_mode": "fast",
            },
        ],
    },
    4: {
        "scenes": [
            {
                "scene_id": "ch4_s1",
                "title": "姜家",
                "location": "姜北辰家·客厅·下午",
                "characters": ["沈语冰", "姜北辰", "姜北辰的女儿（姜晓）"],
                "conflict": "沈语冰用植入体扫描姜晓，确认她是死区",
                "emotional_goal": "沉重的确认——一个父亲最怕的答案",
                "sensory_anchor": "客厅的整洁与姜晓的空洞眼神，植入体扫描时的绝对静默",
                "narrative_function": "推进情节",
                "foreshadow_actions": [],
                "word_target": 1200,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch4_s2",
                "title": "贺明轩的侧面",
                "location": "共感科技·走廊·傍晚",
                "characters": ["沈语冰", "贺明轩"],
                "conflict": "贺明轩'偶遇'沈语冰，暗示她应停止调查",
                "emotional_goal": "被注视的压迫感——温和外表下的警告",
                "sensory_anchor": "贺明轩恒定温和的情绪信号——过于完美，反而可疑",
                "narrative_function": "埋设伏笔",
                "foreshadow_actions": [
                    {"id": "fs2", "action": "埋设", "detail": "贺明轩从不触碰植入体用户"},
                ],
                "word_target": 800,
                "quality_mode": "precision",
            },
        ],
    },
    5: {
        "scenes": [
            {
                "scene_id": "ch5_s1",
                "title": "共振体假说",
                "location": "苏映的实验室·夜晚",
                "characters": ["沈语冰", "苏映"],
                "conflict": "苏映提出共振体假说——情绪频谱中的非碳基生命体",
                "emotional_goal": "认知震撼——'死区'不是故障，是被捕食",
                "sensory_anchor": "实验室屏幕上的频率波形图，苏映兴奋与恐惧交织的蓝色脉冲",
                "narrative_function": "推进情节",
                "foreshadow_actions": [
                    {"id": "fs1", "action": "推进", "detail": "植入体在实验室中剧烈发热"},
                ],
                "word_target": 1200,
                "quality_mode": "precision",
            },
            {
                "scene_id": "ch5_s2",
                "title": "关键转折T1",
                "location": "苏映的实验室",
                "characters": ["沈语冰", "苏映"],
                "conflict": "沈语冰意识到：死区不是'没有情绪'而是'情绪被吃掉了'",
                "emotional_goal": "存在性恐惧——人类情绪是某种存在的食物",
                "sensory_anchor": "植入体温度飙升至38.5°C，左手从手腕以下完全失去知觉",
                "narrative_function": "推进情节",
                "foreshadow_actions": [
                    {"id": "fs3", "action": "推进", "detail": "失聪区域扩大到左前臂"},
                    {"id": "fs1", "action": "推进", "detail": "植入体温度38.5°C"},
                ],
                "word_target": 1000,
                "quality_mode": "precision",
            },
        ],
    },
}


def _get_l3_scene_mock(input_data: dict) -> str:
    """返回 L3 场景分解 Mock 响应。"""
    chapter_index: int = input_data.get("chapter_index", 1)
    scene_data = _L3_SCENES.get(chapter_index, _L3_SCENES[1])
    return json.dumps(scene_data, ensure_ascii=False)


# ------------------------------------------------------------------
# L4 段落生成 Mock 数据
# ------------------------------------------------------------------

# 每个场景的 Mock 正文（精简版，用于验证管线）
_L4_PARAGRAPHS: dict[str, str] = {
    "ch1_s1": (
        "沈语冰的植入体在周四下午两点十七分报了错。\n\n"
        "不是那种正式的错误弹窗。共感科技的植入体没有界面，"
        "它直接把信号写进你的神经。正常情况下，别人生气时你会觉得"
        "脖子后面发热，别人难过时你会感到一阵轻微的失重。\n\n"
        "两点十七分，她路过陈静的工位。什么都没有。\n\n"
        "不是\"情绪平静\"。陈静的工位是绝对的零。没有温度，没有压力，"
        "没有色彩。沈语冰站在她旁边，植入体反馈的信号是一张白纸。\n\n"
        "她摸了摸耳后的植入体接口。金属微凸，比平时热了一点。"
    ),
    "ch1_s2": (
        "下午的会议开了一个半小时。植入体在密闭空间里更活跃——"
        "十几个人的情绪信号叠加在一起，像一锅缓慢沸腾的汤。\n\n"
        "沈语冰一直观察陈静。陈静坐在长桌左侧第三个位置，"
        "肢体语言没有异常，在合适的时候点头。情绪信号仍然是零。"
    ),
    "ch1_s3": (
        "沈语冰调出共感科技的内部系统，搜索了陈静的植入体状态报告。"
        "报告显示一切正常。\n\n"
        "但报告测的是设备。它测不了陈静。\n\n"
        "她低头看自己的左手。小指和无名指没有知觉。发麻的范围在扩大"
        "——两周前还只是指尖，现在已经蔓延到第二个指节。\n\n"
        "她登录植入体用户健康数据库，搜索\"情绪信号异常\"。零条结果。"
        "换了个搜索词，三条匿名反馈。第三条只有一句话："
        "\"我周围的人好像都不再有情绪了。\"\n\n"
        "提交者的植入体编号对应陈静。"
    ),
    "ch2_s1": (
        "第二天周五，沈语冰提前半小时到公司。九点十二分，陈静来了。"
        "走路姿态正常，步幅稳定。情绪信号：零。\n\n"
        "沈语冰把注意力收回来，打开数据分析平台。脑子分了一半在别处。"
    ),
    "ch2_s2": (
        "中午食堂，苏映端着餐盘坐到她对面。\n\n"
        "\"我在跑一个实验，跟植入体的信号频谱有关。\"苏映用筷子戳着西兰花，"
        "\"我在分析植入体接收到的情绪信号中，是否存在我们还没识别出的频率模式。\"\n\n"
        "沈语冰停下筷子。\"你是说，植入体在接收情绪信号时，可能漏掉了某些频率？\"\n\n"
        "\"不是漏掉，\"苏映摇头，\"是被过滤了。如果那些被切除的不是噪声呢？\"\n\n"
        "沈语冰的植入体发热了。耳后接口处的金属微微发烫，37.8°C，比昨天又高了。"
    ),
    "ch2_s3": (
        "下午，沈语冰调取了共感科技所有植入体用户的匿名健康报告。"
        "她设了一个筛选条件：过去六个月内，月均信号强度下降超过50%的用户。\n\n"
        "四十七条结果。\n\n"
        "排在第一位的用户，信号强度降到了零。完全归零。注册时间和陈静同一批次，"
        "同一个激活地点。\n\n"
        "左手小指的麻木感比早上更明显了，无名指的第二指节也开始发麻。\n\n"
        "这不是设备故障。"
    ),
    "ch2_s4": (
        "下班后沈语冰去了陈静住的小区。五十米外，植入体勉强能工作。"
        "信号模糊，但她能确认——陈静的情绪信号仍然是零。\n\n"
        "她走到一个小公园，坐在长椅上开始理线索。四条线索指向一个被压制的真相："
        "共感科技的官方健康数据库里，\"情绪信号异常\"的搜索结果是零。"
        "不是没有人报告，是有人把报告压下去了。\n\n"
        "她给苏映发了一条消息：\"你说的那个有结构的信号——能给我看看原始数据吗？\"\n\n"
        "苏映回复：\"明天来实验室。别让别人看到。\""
    ),
    "ch3_s1": (
        "周一上午，沈语冰在大厅被一个中年男人拦住了。\n\n"
        "\"你是沈语冰？共感科技的？\"他穿一件旧夹克，眼神锐利但不攻击。"
        "他的情绪信号是压抑的暗红色——愤怒被压在很深的地方。\n\n"
        "\"我叫姜北辰。前刑警。\"他没废话，\"我女儿出事了。我需要你用植入体看看她。\"\n\n"
        "沈语冰看着他。\"你怎么知道我有植入体？\"\n\n"
        "\"我做了调查。\"姜北辰说，\"我不需要机器告诉我别人在想什么。但我需要你。\""
    ),
    "ch3_s2": (
        "姜北辰从车里拿出一叠纸。是画——蜡笔画，色彩鲜艳但线条混乱。\n\n"
        "\"我女儿画的。她今年八岁。\"姜北辰把画递过来，手微微发抖。\n\n"
        "沈语冰翻看着。前几张是普通的儿童画——房子、太阳、花。但从第七张开始，"
        "画面上反复出现一种图案：密集的波浪线，一层叠一层，像心电图，但频率不对。"
        "波浪线覆盖了整张纸，把原来的房子和太阳都挤到了角落。\n\n"
        "\"她反复画这个。每天画。\"姜北辰的声音很平，\"我不知道这是什么。\"\n\n"
        "沈语冰盯着那些波形。她见过类似的图案——在苏映实验室的频率分析图上。"
    ),
    "ch3_s3": (
        "咖啡馆里，两人面对面坐着。姜北辰的咖啡没加糖，沈语冰的茶没碰。\n\n"
        "\"我不信任那东西。\"姜北辰指了指沈语冰的耳后，\"机器读出来的情绪，"
        "和真的情绪不是一回事。\"\n\n"
        "\"但它能发现你发现不了的东西。\"沈语冰说。\n\n"
        "\"比如我女儿没有情绪了？\"姜北辰的暗红色信号闪了一下。"
        "\"我不需要机器告诉我这个。我看得出来。\"\n\n"
        "\"那你来找我能帮你什么？\"\n\n"
        "\"确认。\"姜北辰说，\"然后找出是谁干的。\""
    ),
    "ch4_s1": (
        "姜北辰的家在浦东一个老小区。客厅整洁但冷清，没有孩子的笑声。\n\n"
        "姜晓坐在沙发上看电视。八岁，扎着马尾，表情平静得过分。"
        "屏幕上放着动画片，但她没有在看——眼睛对焦在某个不存在的地方。\n\n"
        "沈语冰站在她三米外，启动了植入体的主动扫描模式。\n\n"
        "零。绝对零。和陈静一样的白纸。\n\n"
        "但更近的距离下，沈语冰注意到了一个细节：在零信号的边缘，"
        "有一圈极微弱的波纹。不是情绪——是某种震动。像有什么东西在水面下呼吸。\n\n"
        "她没说出来。"
    ),
    "ch4_s2": (
        "傍晚，沈语冰走出电梯，在走廊里遇到了贺明轩。\n\n"
        "\"小沈？\"他笑着，温和得体。他的情绪信号是恒定的浅金色——太稳定了，"
        "稳定到不像活人。沈语冰从未见过有人能把自己的情绪控制得如此完美。\n\n"
        "\"听说你最近在做一些……数据调研？\"贺明轩的语气随意，"
        "但他的目光停在她耳后的植入体接口上。\n\n"
        "\"常规分析。\"沈语冰说。\n\n"
        "\"当然。\"贺明轩点头，\"只是提醒你，有些数据涉及用户隐私。"
        "小心点总是好的。\"\n\n"
        "他拍了拍她的肩膀——手指只碰了布料，刻意避开了皮肤。"
    ),
    "ch5_s1": (
        "苏映的实验室在共感科技地下二层。门禁需要特殊权限，苏映帮她刷了卡。\n\n"
        "\"我找到了。\"苏映打开屏幕，上面是一张频率分析图。\"这个频率模式"
        "不在任何已知情绪频段内，但它有结构。有结构的信号不是噪声。\"\n\n"
        "沈语冰看着屏幕上的波形。她和姜晓画上的波浪线几乎一模一样。\n\n"
        "\"我认为，\"苏映压低声音，\"情绪频谱中存在某种自组织模式。"
        "类似电磁波中的驻波。它们以人类情绪为能量源，通过共振吸收信号。\"\n\n"
        "\"你在说——有东西在吃人类的情绪？\"\n\n"
        "苏映没回答。她的蓝色脉冲在加速。"
    ),
    "ch5_s2": (
        "沈语冰的植入体突然剧烈发热。38.5°C。她本能地按住耳后。\n\n"
        "同一瞬间，她明白了。死区不是\"没有情绪\"。死区是\"情绪被吃掉了\"。\n\n"
        "陈静还在笑，还在说话，还在写会议纪要。但她的情绪——那些本该"
        "在植入体上显示为橙黄色和灰白条纹的东西——已经被某种存在吸收殆尽。\n\n"
        "而她自己呢？左手从手腕以下完全失去了知觉。那种麻木不是副作用。"
        "那是被标记的痕迹。\n\n"
        "\"它们不是在破坏情绪，\"沈语冰说，\"它们在吃。\"\n\n"
        "苏映看着她，眼神里有恐惧也有确认。\"对。它们在进食。\""
    ),
}


def _get_l4_paragraph_mock(input_data: dict) -> str:
    """返回 L4 段落生成 Mock 响应。"""
    scene: dict = input_data.get("scene", {})
    scene_id: str = scene.get("scene_id", "")

    # 根据场景 ID 返回预设正文
    content = _L4_PARAGRAPHS.get(scene_id, "")

    # 如果没有预设正文，生成一个通用 Mock
    if not content:
        title = scene.get("title", "未命名场景")
        location = scene.get("location", "未知地点")
        conflict = scene.get("conflict", "")
        content = (
            f"【Mock 正文 · {scene_id}】\n\n"
            f"场景：{title}\n"
            f"地点：{location}\n"
            f"冲突：{conflict}\n\n"
            "（此处为 Mock 模式生成的占位正文，配置 API Key 后将由真实 LLM 生成。）"
        )

    word_target: int = input_data.get("word_target", scene.get("word_target", 1500))

    return json.dumps({
        "content": content,
        "layers_used": ["感官", "内省", "对话", "推进"],
        "foreshadow_planted": [
            fa.get("id", "") for fa in scene.get("foreshadow_actions", [])
            if fa.get("action") in ("埋设", "推进")
        ],
    }, ensure_ascii=False)


def _get_mock_response(agent_role: str, user_message: str) -> str:
    """根据 agent_role 返回 Mock JSON 响应。

    对于园丁（发散），根据 target_layer 调整内容：
    - L0: 世界观候选
    - L1: 人物网络候选
    - L2: 情节弧候选

    L3/L4 检测：通过 input_data 中的字段判断
    - L3 场景分解：input_data 包含 chapter_index + key_events
    - L4 段落生成：input_data 包含 scene（含 scene_id）
    """
    base = _MOCK_RESPONSES.get(agent_role, {})

    # 尝试解析输入
    try:
        input_data = json.loads(user_message)
    except (json.JSONDecodeError, TypeError):
        input_data = {}

    # ── L3 场景分解检测 ──
    if agent_role == "gardener" and "chapter_index" in input_data and "key_events" in input_data:
        return _get_l3_scene_mock(input_data)

    # ── L4 段落生成检测 ──
    if agent_role == "gardener" and "scene" in input_data:
        return _get_l4_paragraph_mock(input_data)

    # 园丁：根据层级返回不同候选
    if agent_role == "gardener":
        layer = input_data.get("target_layer", "L0")

        if layer == "L1":
            return json.dumps({
                "candidates": [
                    {
                        "id": "ch1",
                        "title": "林昭",
                        "novelty": 0.82,
                        "content": (
                            "32岁，神经接口工程师。因童年事故失明，"
                            "成为首批暗物质感知接口的受试者。冷静、偏执，"
                            "对'被观察'有本能的恐惧。口头禅：'我看到的比你们多。'"
                        ),
                    },
                    {
                        "id": "ch2",
                        "title": "方远",
                        "novelty": 0.75,
                        "content": (
                            "45岁，暗物质物理学家。林昭的导师兼合作者。"
                            "理性到冷酷，认为暗物质结构只是自然现象。"
                            "口头禅：'数据不会说谎，但人会。'"
                        ),
                    },
                    {
                        "id": "ch3",
                        "title": "苏野",
                        "novelty": 0.88,
                        "content": (
                            "28岁，前军事情报分析师。也植入了接口，"
                            "但他的感知范围远超林昭。行踪神秘，"
                            "似乎知道暗物质生命的真相。口头禅：'它们一直在。'"
                        ),
                    },
                ],
                "diversity_note": "三个角色分别代表科学理性、技术直觉、情报视角，形成三角张力。",
            }, ensure_ascii=False)

        elif layer == "L2":
            return json.dumps({
                "candidates": [
                    {
                        "id": "p1",
                        "title": "三幕结构A：感知觉醒→结构发现→身份反转",
                        "novelty": 0.83,
                        "content": (
                            "第一幕：林昭获得暗物质感知能力，初见异常结构。"
                            "第二幕：调查发现全球多处暗物质结构呈智慧排列，苏野介入。"
                            "第三幕：林昭发现自己脑中的接口并非人类造物，"
                            "而是暗物质生命的'植入物'。"
                        ),
                    },
                    {
                        "id": "p2",
                        "title": "三幕结构B：失踪→追踪→对峙",
                        "novelty": 0.76,
                        "content": (
                            "以多名接口使用者失踪为起点，林昭追踪线索，"
                            "最终发现失踪者被暗物质生命'回收'。"
                        ),
                    },
                    {
                        "id": "p3",
                        "title": "三幕结构C：日常崩塌→感知扩散→抉择",
                        "novelty": 0.87,
                        "content": (
                            "第一幕：林昭的日常感知开始'泄漏'——她看到暗物质结构在呼吸。"
                            "第二幕：感知能力扩散给非受试者，社会恐慌。"
                            "第三幕：林昭面临抉择——关闭所有接口让人类回到盲目，"
                            "还是接受暗物质生命一直与我们共存的真相。"
                        ),
                    },
                ],
                "diversity_note": "三个走向分别侧重身份悬疑、调查悬疑、社会伦理悬疑。",
            }, ensure_ascii=False)

        # L0 或其他：返回默认世界观候选
        return json.dumps(base, ensure_ascii=False)

    # 剪枝师：根据层级选择不同候选
    if agent_role == "pruner":
        layer = input_data.get("target_layer", "L0")

        if layer == "L1":
            return json.dumps({
                "selected": "ch3",
                "scores": [
                    {"id": "ch1", "total": 80, "novelty": 0.82, "eliminated": False, "reason": "主角候选，工程师视角好"},
                    {"id": "ch2", "total": 75, "novelty": 0.75, "eliminated": True, "reason": "导师角色偏传统"},
                    {"id": "ch3", "total": 89, "novelty": 0.88, "eliminated": False, "reason": "神秘角色，信息不对称，悬疑感最强"},
                ],
                "selection_rationale": "ch3「苏野」在悬疑张力和信息不对称上最优，与主角林昭形成互补。",
            }, ensure_ascii=False)

        elif layer == "L2":
            return json.dumps({
                "selected": "p3",
                "scores": [
                    {"id": "p1", "total": 82, "novelty": 0.83, "eliminated": False, "reason": "身份反转有力但略硬"},
                    {"id": "p2", "total": 74, "novelty": 0.76, "eliminated": True, "reason": "调查线偏传统"},
                    {"id": "p3", "total": 90, "novelty": 0.87, "eliminated": False, "reason": "日常崩塌+伦理抉择，悬疑与科幻融合度最高"},
                ],
                "selection_rationale": "p3「日常崩塌→感知扩散→抉择」在叙事创新性和主题深度上最优。",
            }, ensure_ascii=False)

        return json.dumps(base, ensure_ascii=False)

    # 记忆管家：根据层级返回不同固化内容
    if agent_role == "curator":
        layer = input_data.get("target_layer", "L0")
        tree_version = input_data.get("tree_version", 0)

        new_version = tree_version + 1

        if layer == "L1":
            return json.dumps({
                "memory_id": f"L1_v{new_version}",
                "new_version": new_version,
                "extracted_constraints": [
                    "主角林昭：32岁神经接口工程师，失明受试者，冷静偏执",
                    "关键角色苏野：前情报分析师，知道暗物质生命真相",
                    "配角方远：暗物质物理学家，代表科学理性视角",
                    "人物关系：林昭←导师→方远，林昭←信息差→苏野",
                ],
                "structured_content": {
                    "protagonist": "林昭",
                    "key_characters": ["苏野", "方远"],
                    "character_graph": {
                        "edges": [
                            {"from": "林昭", "to": "方远", "type": "师生"},
                            {"from": "林昭", "to": "苏野", "type": "信息不对称"},
                        ]
                    },
                },
            }, ensure_ascii=False)

        elif layer == "L2":
            return json.dumps({
                "memory_id": f"L2_v{new_version}",
                "new_version": new_version,
                "extracted_constraints": [
                    "三幕结构：日常崩塌→感知扩散→伦理抉择",
                    "第一幕：林昭的感知开始'泄漏'，暗物质结构在呼吸",
                    "第二幕：感知能力扩散给非受试者，社会恐慌",
                    "第三幕：林昭面临抉择——关闭接口 vs 接受真相",
                    "伏笔计划：接口的真正来源（暗物质生命植入物）",
                    "关键转折：苏野揭示自己也是'被植入者'",
                ],
                "structured_content": {
                    "act_structure": "三幕",
                    "act1": "日常崩塌：感知泄漏",
                    "act2": "感知扩散：社会恐慌",
                    "act3": "伦理抉择：盲目 vs 共存",
                    "foreshadows": [
                        {"id": "fs1", "planted": "第一幕", "detail": "接口的异常发热", "harvest": "第三幕"},
                        {"id": "fs2", "planted": "第二幕", "detail": "苏野的接口型号不同", "harvest": "第三幕"},
                    ],
                    "key_turning_points": ["感知泄漏", "苏野揭露真相", "最终抉择"],
                },
            }, ensure_ascii=False)

        # L0
        return json.dumps({
            **base,
            "new_version": new_version,
            "memory_id": f"L0_v{new_version}",
        }, ensure_ascii=False)

    # 其他角色直接返回基础 Mock
    return json.dumps(base, ensure_ascii=False)


class MockLLMClient:
    """Mock LLM 客户端，模拟真实 LLM 调用。

    与 LLMClient 接口完全一致：
    - call(agent_role, system_prompt, user_message, ...) -> str
    - parse_json_response(text) -> dict
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        logger.info("MockLLMClient 初始化完成（无需 API Key）")

    async def call(
        self,
        agent_role: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> str:
        """返回 Mock 响应。"""
        logger.info(
            "[MOCK] agent=%s, temperature=%.2f → 返回预设响应",
            agent_role,
            temperature,
        )
        return _get_mock_response(agent_role, user_message)

    @staticmethod
    def parse_json_response(text: str) -> dict:
        """解析 JSON（Mock 响应已经是合法 JSON）。"""
        try:
            result = json.loads(text)
            return result if isinstance(result, dict) else {"raw": text}
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}
