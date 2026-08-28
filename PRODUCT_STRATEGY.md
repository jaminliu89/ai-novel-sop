# AI 工业化长篇小说生成流水线产品发展战略规划书 (Product Strategy & Roadmap)

---

## 1. 产品定位与愿景 (Product Vision & Positioning)

### 1.1 产品定义
本产品是一个**基于多 Agent 协作架构与分层收敛 SOP 的工业化长篇小说生成与辅助创作平台**。旨在解决大语言模型（LLM）在长文本创作中普遍存在的“长文崩溃”、“前文遗忘”、“人物立姿坍塌”、“剧情幻觉”以及“泛化 AI 腔”等行业痛点。

### 1.2 核心价值主张 (Core Value Proposition)
* **两次拆解，分而治之**：将小说创作拆解为从宏观世界观（L0）到微观段落/语句（L4/L5）的 6 层递进结构，结合发散（Gardener）、收敛（Pruner）、固化（Distiller/Curator）、审视（Inspector）的四大原子动作。
* **状态持久化与滚动上下文**：通过 SQLite 树状存储（TreeStore）、实体状态机（StoryStateStore）与伏笔注册表（ForeshadowRegistry），实现百万字级别长篇小说的跨章节一致性。
* **人机深度协同（Human-in-the-Loop）**：在关键节点设置 Pause/Resume 断点机制，赋能创作者以“总导演”角色介入与干预，而非被动接受 AI 生成。

---

## 2. 目标用户与痛点分析 (User Personas & Pain Points)

| 用户群体 | 核心需求 | 当前痛点 | 本产品带来的价值 |
| :--- | :--- | :--- | :--- |
| **网文签约作者 / 自由创作者** | 提高日更产出效率，突破创作瓶颈与灵感枯竭 | 手写日更压力大；使用通用 AI 易产生连贯性断裂和强烈 AI 腔 | 辅助构思大纲与场景分解，提供高质量初稿，保留作者独特笔触风格 |
| **网络文学工作室 / MCN** | 批量化、标准化生产高留存小说 IP | 依靠人工编剧成本高、周期长；质量依赖个人，难以标准化 | 提供标准化 SOP 工作流，大幅缩短生成周期，实现大批量高保真内容生产 |
| **影视/动漫/游戏 IP 开发团队** | 快速验证故事大纲、人物网与剧本可行性 | 传统剧本开发评估周期长、试错成本高 | 自动反向拆解标杆作品，快速生成可测试的情节弧线与场景脚本 |

---

## 3. 代码现状评估与差距分析 (Gap Analysis: Code vs SOP)

目前仓库已完成 **Phase 1 核心引擎 MVP 验证**，具备了完整的底层数据结构与 Agent 链路，但在产品化和用户交互层面仍有升级空间。

```
+-------------------------------------------------------------------------+
| 当前现状 (Implementation Status)                                         |
|  - 状态机 Orchestrator (Phase 1 静态固定流程)                            |
|  - 10个 Agent 角色完整实现 (Gardener, Pruner, Inspector, Decoder等)      |
|  - SQLite + Memory 存储 (TreeStore, StoryStateStore, VectorStore)         |
|  - 命令行 CLI 交互与 Mock LLM 验证                                       |
+-------------------------------------------------------------------------+
                                  │
                                  ▼  GAP (能力差距与演进方向)
+-------------------------------------------------------------------------+
| 目标形态 (Target Product Vision)                                        |
|  - Phase 3 元认知 Coordinator (LLM 自主调度与动态重试)                   |
|  - 可视化 Web Studio 创作工作台 (小说之树图形化展示 + 人机节点交互)      |
|  - 多模型适配器与智能路由 (支持 DeepSeek-R1, Claude 3.5 Sonnet, GPT-4o) |
|  - 商业化多租户、Token 成本控制与版权风格指纹微调                        |
+-------------------------------------------------------------------------+
```

---

## 4. 4阶段产品演进路线图 (Strategic 4-Phase Roadmap)

### Phase 1: 核心引擎与工业化 SOP 验证 (Current Baseline - ✅ 已完成/进行中)
* **重点交付**：
  - [x] 分层数据结构（L0-L4）与 SQLite 持久化存储
  - [x] 多 Agent 协作链路与基本发散-收敛动作循环
  - [x] 滚动复盘（Rolling Reviewer）与状态回写（State Writer）
  - [x] 反 AI 腔冷读与声音指纹（Voice Fingerprint）度量体系

### Phase 2: 可视化创作工作台与人机协同 (Visual Studio & Human-in-the-Loop - 0-6个月)
* **重点交付**：
  - [ ] **Novel Tree 可视化浏览器**：基于 Web (React/Next.js + Flow Chart) 呈现 L0-L4 结构树，支持节点拖拽、编辑与分叉分支（A/B test）。
  - [ ] **人机协同断点编辑器 (Human-Gate Studio)**：当 Inspector 审视不通过或进入人机节点时，提供高亮对比、一键重写指令（Regenerate with custom prompt）及手动打标调整。
  - [ ] **统一 LLM 模型路由与适配器**：支持主流大模型（DeepSeek-R1/V3, Claude 3.5 Sonnet, OpenAI GPT-4o, Local Ollama）接入，自动根据发散/收敛动作调度性价比最高的模型。

### Phase 3: 元认知自主调度与图知识记忆增强 (Autonomous Agent & Graph Memory - 6-12个月)
* **重点交付**：
  - [ ] **元认知 Coordinator 调度器**：从 Phase 1 静态状态机升级为由高级 LLM 驱动的 Coordinator Agent，根据 Inspector 质量评估动态决定“回溯（Retrace）”、“局部发散”或“推进到下一阶段”。
  - [ ] **Neo4j / GraphRAG 知识图谱记忆层**：升级现有 VectorStore 为图 Rag 记忆系统，精确追踪复杂小说中的多线人物关系网、物品流转及千章级别的伏笔闭环。
  - [ ] **风格与音律指纹定制引擎**：引入特定名家/作者文本的反向拆解（P0 阶段增强），自动提取声音指纹与 Few-shot 动态注入，实现极致的个性化文风定制。

### Phase 4: 商业化平台与 IP 孵化生态 (Commercial Platform & Ecosystem - 12-18个月)
* **重点交付**：
  - [ ] **多租户 SaaS 架构与团队协作**：支持创作者、主编、制片人多角色协同审阅与审批。
  - [ ] **Token 成本与质量监控仪表盘**：实时可视化每万字生成成本、AI 腔指数、伏笔履行率及剧情流畅度指标。
  - [ ] **多格式导出与出版对接**：支持一键导出 EPUB、标准网文分章格式、影视剧本（Script format）及网文平台 API 直连发布。

---

## 5. 商业化策略与盈利模式 (Commercialization Strategy)

1. **SaaS 订阅制 (B2C)**：
   - **基础版 (Free/Tier 1)**：适合个人爱好者，提供有限 Token 生成与基础 L0-L2 提纲规划能力。
   - **专业版 (Pro)**：面向独立网文作者，提供完整 L0-L4 长篇生成、人机协同工作台、多模型接入与高级反 AI 腔优化。
2. **企业级 / 工作室解决方案 (B2B)**：
   - 面向 MCN、短剧公司、网文工作室，按席位+消耗 Token 计费，提供私有化部署、团队协作、自定义声音指纹模型训练与专有 API 接口。
3. **IP 衍生与微调服务**：
   - 提供名家写作风格定制微调包、标杆小说拆解数据库授权及热门题材模板库（如玄幻系统流、悬疑无限流等）。

---

## 6. 核心成功指标 (PM KPIs & Success Metrics)

1. **文本质量与抗 AI 腔指标**：
   - **人机节点通过率 (Human Pass Rate)**：Inspector 及人类作者在一轮生成的通过率 > 85%。
   - **AI 腔检出率 (AI-Tone Ratio)**：高频 AI 关联词与句式重复率 < 2%。
   - **逻辑矛盾率 (Contradiction Rate)**：10 万字以上长文状态与伏笔冲突次数为 0。
2. **效率与成本指标**：
   - **创作效率提升 (Efficiency Gain)**：万字初稿生成时间由传统 8 小时缩短至 30 分钟以内（含人类审阅时间）。
   - **Token 效益比 (Token Cost Efficiency)**：通过收敛剪枝与精准向量检索，较暴力上下文拼接节省 > 40% Token 消耗。
3. **用户留存与商业转化**：
   - **月度活跃创作者 (MAU)** 及 **完本率 (Completion Rate)**。

---
*本战略规划书由产品经理制定，作为后续系统升级、前端工作台开发及 Agent 智能调度的指导性纲领。*
