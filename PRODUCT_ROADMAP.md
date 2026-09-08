# AI 工业化小说写作平台 · 产品经理分析与发展路线图 (PRODUCT_ROADMAP.md)

## 1. 产品概述与现状评估 (Executive Summary & Product Assessment)

### 1.1 产品定位 (Product Positioning)
本产品旨在通过**“小说之树”纵向分层架构（L0-L4）**与**“6大认知动作循环”（发散、收敛、固化、审视、回溯、蒸馏）**，将传统 AI 写作中“单次 prompt 丢失长篇一致性”、“人物漂移”、“逻辑套路化”等痛点拆解并标准化，打造一个**工业化、高可控、人机共创**的 AI 商业小说创作系统。

### 1.2 现有完成度评估 (Current Capability Assessment)
- **SOP 规范设计 (ai-novel-sop.html)**：已建立极其完整的 14 章工业化 SOP 规范，定义了 Agent 契约、分层模型（L0 世界观 → L1 人物网 → L2 情节弧 → L3 场景 → L4 段落）、度量体系与反 AI 腔三层防御。
- **底层 Python 引擎 (implementation/ai_novel)**：
  - 已实现核心 Agent：Gardener (园丁/发散)、Pruner (剪枝师/收敛)、Curator (记忆/固化)、Inspector (监工/审视)、Distiller (蒸馏者/主题)、Decoder (拆解师/Few-shot)、ParagraphGenerator (段落生成)、SceneDecomposer (场景分解)、RollingReviewer (滚动审视)。
  - 已实现基础存储与度量：基于 SQLite + JSON Snapshot 的状态持久化与回溯机制，以及 Voice Fingerprint (声音指纹) 和 Quality Metrics (质量门禁)。
  - 运行入口：已具备 `run_l0_l2.py`, `run_l3_l4.py`, `run_direct_l0_l2.py` 等 CLI/脚本驱动入口。

### 1.3 核心痛点与差距分析 (Current Gaps & Pain Points)
1. **交互体验断层 (UI/UX Gap)**：
   - 当前完全依赖 CLI 终端与 JSON/Markdown 文件交互，人机节点（Human-in-the-Loop Gate）缺乏直观的可视化审批与修改界面，对非程序员作者（如网文作家、编剧）门槛极高。
2. **长篇工程化与上下文管理 (Context & Memory Limitations)**：
   - 现存实现偏向单本/短篇模拟验证，缺乏对 30万字以上长篇/连载小说、跨卷伏笔网、动态知识图谱的高效支持。
3. **生态与产出多样性 (Ecosystem & Genre Adaptation)**：
   - 目前 Few-shot 拆解库与 Prompt 模板主要集中在科幻/悬疑类型，尚无都市、玄幻、言情等多题材的预置模板库与规则集。
4. **商业交付与集成能力 (Commercial Integration)**：
   - 缺乏一键导出（ePub, Docx, Script 分场剧本）、多端同步、团队协同权限控制以及云端 API 服务。

---

## 2. 核心价值主张与用户画像 (Value Proposition & User Personas)

### 2.1 目标用户群 (Target Users)
1. **商业网文/小说作者**：追求稳定日更、需要克服“卡文/卡梗”以及提高剧情逻辑严密度的创作者。
2. **IP 影视/游戏编剧工作室**：需要快速搭建世界观、人物弧光与分场脚本，进行批量创意发散与结构化审判的专业团队。
3. **AI 独立创作者/出版实验者**：利用 AI 进行人机共创、寻求突破 60-80 分业业余天花板的高质量创作玩家。

### 2.2 核心竞争优势 (Unfair Advantages)
- **分层硬约束与元认知调度**：用结构化分层（L0-L4）彻底替代“大上下文盲目拼接”，指令依从度与剧情连贯性显著提升。
- **高性价比的混合模型架构**：使用 Sonnet/Claude 负责高阶调度，低成本开源/轻量模型（如 DeepSeek V4 Flash）执行发散与固化，单本 10 万字生成成本降至 **$8-10**。
- **自动化反向拆解 (Reverse-Engineering Pipeline)**：能将爆款标杆作品自动拆解为骨架、声音指纹与 Few-shot 库，实现“向经典学习”。

---

## 3. 四阶段产品发展路线图 (4-Phase Strategic Roadmap)

```
Phase 1: 引擎稳固与工程质量 (Engine Consolidation & QA)
  └─ 测试覆盖、依赖与降级优化、自动化 Benchmark 门禁

Phase 2: 可视化人机共创工作台 (Human-in-the-Loop Visual Workbench)
  └─ Web GUI 界面、人机门禁卡口、大纲/人物卡可视比对、交互式修改

Phase 3: 长篇进化与多题材扩展 (Novel Intelligence & Multi-genre Expansion)
  └─ 动态知识图谱、跨卷伏笔追溯、多题材 (玄幻/都市/言情) 模板库

Phase 4: SaaS 商业化与平台生态 (Commercialization & Ecosystem)
  └─ 团队协同、API/Webhook 开放平台、一键多格式出版导出
```

### Phase 1: 引擎稳固与工程质量 (Engine Consolidation & QA)
*目标：提升底层 Python 引擎的鲁棒性、测试覆盖率与降级运行能力，建立自动化质量评估基准。*
- **功能点 1.1：自动化单元测试与集成测试网络**
  - 补充针对各 Agent（Gardener, Pruner, Inspector 等）、State Manager 以及 Quality Metrics 的完整 Unit Tests。
- **功能点 1.2：环境依赖解耦与平滑降级**
  - 增强 `jieba`, `sentence-transformers`, `scikit-learn` 等 NLP 依赖缺失时的 Graceful Degradation (平滑降级)，确保轻量环境与生产环境均可稳定运行。
- **功能点 1.3：质量门禁 Benchmark**
  - 建立自动化 Benchmark 评测集，评估 AI 腔密度、声音漂移度、伏笔回收率等指标的测量准确率。

### Phase 2: 可视化人机共创工作台 (Human-in-the-Loop Visual Workbench)
*目标：打破 CLI 限制，为创作者打造一站式、可视化的“小说之树”人机共创 Web 工作台。*
- **功能点 2.1：可视化人机门禁审批界面 (Gate Approval Dashboard)**
  - 在 P1(世界观)、P2(人物)、P3(大纲) 节点提供可视化卡片审阅，支持人类作者一键“通过/拒绝/编辑分支”。
- **功能点 2.2：“小说之树”树状结构拖拽与对比 (Interactive Novel Tree Editor)**
  - 提供可视化的 L0-L4 树状视图，支持作者直接点击修改某一节点（如修改场景冲突点），并自动触发下游影响范围的重算与回溯提醒。
- **功能点 2.3：场景级四层生成与实时 Diff 编辑器**
  - 提供分层生成（感官 → 内省 → 对话 → 推进）的流式打字机效果与对比模式，支持作者实时修改并保存版本快照。

### Phase 3: 长篇进化与多题材扩展 (Novel Intelligence & Multi-genre Expansion)
*目标：突破单本 15万字上限，打造支持百万字长篇连载与多题材扩展的深度智能引擎。*
- **功能点 3.1：跨卷长程记忆与动态知识图谱 (Long-range Knowledge Graph)**
  - 引入基于图数据库/语义图谱的人物关系与伏笔追踪引擎，精准解决百万字连载中的“跨卷设定冲突”与“伏笔丢失”问题。
- **功能点 3.2：多题材拆解与模板集市 (Multi-genre Preset Bazaar)**
  - 扩展拆解流水线（Decoder），预置“都市爽文”、“东方玄幻”、“硬核科幻”、“悬疑推理”、“言情甜宠”等多题材的骨架与风格模版。
- **功能点 3.3：自适应质量档位调度 (Quality Mode Switching)**
  - 支持“爆款精雕模式”（完全 4 层生成 + 严格审视）与“日更推进模式”（简化动作循环），平衡生成速度与模型调用成本。

### Phase 4: SaaS 商业化与平台生态 (SaaS Commercialization & Ecosystem)
*目标：实现商业变现，面向工作室与创作者提供 SaaS 平台与 API 服务。*
- **功能点 4.1：多端协同与团队权限系统 (Team Collaboration & RBAC)**
  - 支持主创、编剧、校对等多角色协同创作，提供分支版本控制（Branching & Merging）与批注功能。
- **功能点 4.2：多格式出版导出与排版引擎 (Multi-format Publishing Engine)**
  - 一键导出 Epub、Mobi、PDF、Word 以及符合影视/剧本杀标准的“分场剧本格式”。
- **功能点 4.3：开放 API 与生态集成 (Developer API & Platform)**
  - 提供 Webhook 与 RESTful/GraphQL API，支持第三方写作软件（如 Scrivener、Obsidian、墨水屏设备）接入本写作引擎。

---

## 4. 关键指标与成功要素 (KPIs & Key Success Factors)

| 维度 | 指标名称 | 目标值 (Target) | 测量方式 |
| :--- | :--- | :--- | :--- |
| **质量与连贯性** | 伏笔回收率 | ≥ 90% | 监工 Agent 自动审计 + 人工抽样校验 |
| **反 AI 腔指标** | AI 腔词汇密度 / 格式套路 | 0 处 | 禁用词表与模式匹配检测器 |
| **成本效率** | 单本 (10万字) 生成成本 | ≤ $10 USD | 混合模型 API 计费统计 (含 Prompt Cache) |
| **创作效率** | 大纲/分场完成时间 | 降低 70% | 创作者人机门禁通过耗时对比 |
| **用户体验** | 人机门禁一次通过率 (Gate Pass Rate) | ≥ 80% | 统计人机节点中的拒绝/修改比例 |

---

## 5. 总结与近阶段行动建议 (Immediate Next Steps)

1. **短期 (Phase 1 执行)**：编写完整 unit tests，确保 `ai_novel` 模块在 mock 模式与真实 API 下均能通过单元测试；优化依赖缺失时的平滑降级。
2. **中期 (Phase 2 探索)**：基于 FastAPI/Flask + React/Vue 搭建极简的 Web UI 雏形，将 `run_l0_l2.py` 和 `run_l3_l4.py` 的人机节点转化为可视化 Web 审批流程。
