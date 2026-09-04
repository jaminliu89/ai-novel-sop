# AI 工业化小说创作平台 · 产品分析与演进路线图 (PRODUCT_ROADMAP.md)

---

## 一、 执行摘要与产品定位 (Executive Summary & Positioning)

### 1.1 产品定位
本产品旨在打造 **AI 驱动的长篇小说/网文工业化创作平台 (AI Novel Industrial Production Suite)**。
区别于市场上现有的“单一 Prompt 一次性生成/拼接 (Chunking)”的生成工具，本系统立足于 **“分而治之、两次拆解”** 的核心设计哲学：
- **纵向五层硬依赖 (L0 ~ L4)**：世界观 (L0) → 人物网 (L1) → 情节弧 (L2) → 场景简报 (L3) → 段落细节 (L4)，自上而下施加结构性约束。
- **横向层无关动作引擎**：发散 (Gardener) → 收敛 (Pruner) → 固化 (Curator) → 审视 (Inspector) → 回溯 (Coordinator) → 蒸馏 (Distiller) 的通用认知动作引擎。

该平台既可作为**专业作家与网文工作室的人机共创 Copilot 桌面/Web 工作台**，也可作为**网文厂牌与 IP 开发机构的批量自动化内容生产线 (Automated Novel Factory)**。

### 1.2 核心价值主张 (Value Proposition)
1. **彻底解决长篇智商滑坡与逻辑矛盾**：通过硬约束契约与结构化记忆库 (StoryStateStore)，保证百万字连载的人物性格不崩坏、时间线不紊乱、伏笔回收率达 90%+。
2. **三层防御消除 AI 腔 (Zero AI-Isms)**：基于模式匹配、动态提示词防护及冷读监工重写，确保文本具有极高读感与文学张力。
3. **混合分层调度降本增效**：通过 Claude Sonnet 4.6 (元认知调度) + DeepSeek V4 (发散/收敛/推理) 的三层分层调度与前缀缓存 (Prefix Caching)，将 10 万字单本生成成本控制在最低水平。

---

## 二、 现状诊断与技术/产品成熟度 (Current Maturity Audit)

### 2.1 已完成的核心能力 (Phase 1 ~ Phase 3 阶段成果)
1. **Agent 体系全面落地**：
   - 7 大核心 Agent（Gardener, Pruner, Curator, Inspector, Coordinator, Distiller, Decoder）及 L3-L4 专项 Agent（SceneDecomposer, ParagraphGenerator, RollingReviewer, StateWriter）全部完成编码与闭环。
2. **全链路 SOP 流水线通畅**：
   - `run_direct_l0_l2.py`：跑通从世界观发散到 3 幕 22 章完整大纲与伏笔登记的单链路。
   - `run_l3_l4.py`：跑通场景分解、合同校验、段落生成、冷读评估、滚动复盘与状态回写全过程。
3. **记忆与度量体系**：
   - 基于 SQLite 的持久化存储（`TreeStore`, `ConstraintStore`, `StoryStateStore`）。
   - 实现余弦指纹（声音偏离度）、4-gram 重复率检测、AI 腔密度判定等量化指标。

### 2.2 核心瓶颈与差距 (Gap Analysis & Pain Points)

| 维度 | 当前现状 | 目标终局 | 差距与瓶颈 |
| :--- | :--- | :--- | :--- |
| **产品形态** | CLI 命令行脚本 / Python API | 现代可视化 Web UI / Electron 桌面应用 | 缺乏图形化交互，人类作者无法直观在 P1-P5 节点干预 |
| **人机协作** | 全自动脚本驱动或静态 JSON 配置 | 人机共创 (Human-in-the-Loop) 画板与节点编辑 | 缺少可视化大纲树、剧情分支干预、实时冷读意见反馈 |
| **性能与并发** | 单线程同步执行 | 异步事件驱动 (Async Task Queue + WebSocket) | 多候选发散时阻塞时间较长，高并发生成效率有限 |
| **题材与样本** | 仅含通用 Prompt 与 4 部标杆拆解 | 涵盖玄幻、都市、科幻、悬疑等多题材 Few-shot 库 | 缺失动态 RAGFew-shot 检索与题材特色模板包 (Genre Kits) |
| **连载能力** | 单本 (8-15万字) 第一幕验证 | 百万字长篇跨卷一致性管理 | 缺少跨卷“超长程记忆压缩”与多线伏笔关联图谱 |

---

## 三、 战略发展路线图 (Strategic Product Roadmap)

我们将产品演进划分为四个递进阶段：

```
Phase 1: 引擎完善与基准测试 (Engine Hardening) ──► Phase 2: 交互式 Copilot 工作台 (Novel Studio GUI)
                                                                 │
Phase 4: IP 多模态与创作者生态 (Multi-modal IP) ◄── Phase 3: 商业化 SaaS 与百万字连载 (Commercial SaaS)
```

### 3.1 Phase 1：工业化引擎完善与基准建设 (Engine Hardening & NovelBench)
- **目标**：巩固底层 Agent 框架，提升生成稳定性与多样性。
- **核心功能**：
  1. **完备的人机节点干预契约 (P1-P5 Human-in-the-Loop)**：定义标准的 JSON/YAML 人工覆盖协议，支持作者在 P1(世界观)、P2(人物)、P3(大纲)、P4(场景简报)、P5(段落) 随时暂停、修改并恢复执行。
  2. **题材模板库 (Genre Kits)**：推出科幻悬疑、都市异能、玄幻修仙、古代权谋等 4 大热门网文题材的专属系统提示词与 Few-shot 样本集。
  3. **自动化基准测试套件 (NovelBench)**：构建长文本逻辑一致性、伏笔回收率、AI 腔控制率的自动化基准评测。

### 3.2 Phase 2：产品化 GUI/UX 体验升级 (Interactive Copilot Studio)
- **目标**：从“开发者工具”转变为“专业作家生产力软件”。
- **核心功能**：
  1. **小说之树可视化画布 (Novel Tree Canvas)**：
     - 展示 L0-L4 树状导图，支持节点展开、折叠、拖拽调整情节顺序。
     - 支持在节点上标记“回溯路径”与“硬约束关联”。
  2. **实时冷读与质量仪表盘 (Real-time Quality Dashboard)**：
     - 边写边测：实时显示重复率、AI 腔密度、声音指纹偏离度雷达图。
     - 监工意见卡片：针对未通过段落提供“一键重写/修改建议”。
  3. **故事状态灵感协同面板 (Story State Portal)**：
     - 实时查看角色状态快照（位置、生理、情绪、装备）。
     - 伏笔追踪清单：亮红显示“久未回收”或“即将过期”的伏笔。

### 3.3 Phase 3：商业化 SaaS 与百万字长篇连载 (Commercial SaaS & Long-form Engine)
- **目标**：支持工作室与网文厂牌的商业化批量连载。
- **核心功能**：
  1. **跨卷超长程记忆管理 (Multi-Volume Long-term Memory)**：
     - 基于向量数据库 (ChromaDB/Milvus) + 图数据库 (Neo4j) 实现百万字人物关系与设定高精度检索。
     - 滚动蒸馏：每 10 万字自动生成卷末摘要与设定更新，防止上下文溢出。
  2. **混合云端调度与成本优化引擎 (Dynamic Hybrid Scheduler)**：
     - 支持 DeepSeek V4 Pro / Claude Sonnet 4.6 / Qwen 等多模型动态降级与前缀缓存命中率（目标 Cache Hit Rate > 85%）。
  3. **工作室多租户 SaaS 架构 (Multi-Tenant SaaS)**：
     - 支持团队分工（如大纲师、场景师、文字润色师协作）。
     - 权限隔离、版本控制 (Git-like Story Branching) 与资产导出。

### 3.4 Phase 4：IP 多模态衍生与创作者生态 (IP Multi-modal & Creator Ecosystem)
- **目标**：打通网文到短剧、漫画、播客的 IP 全产业链。
- **核心功能**：
  1. **文本到分镜/剧本自动转换 (Text-to-Storyboard / Script Engine)**：
     - 将 L3/L4 段落一键转化为短剧剧本、漫改分镜脚本或广播剧配音提示词。
  2. **创作者拆解骨架社区 (Prompt & Skeleton Marketplace)**：
     - 允许顶尖作家/编辑上传经典名著或爆款网文的拆解骨架 (Skeletons) 与 Few-shot 模式，实现变现与共享。

---

## 四、 商业模式与 Go-To-Market (GTM) 策略

### 4.1 目标客户画像 (Target Audience)
1. **网文独立创作者 / 独立作家**：提升写作效率（从月更 10 万字提升至 30 万字），辅助构思大纲与伏笔。
2. **网文工作室 & 批量生产厂牌**：降低工业化产出成本，实现多品类、多频道爆款内容的标准化流水线生产。
3. **IP 影视/游戏/短剧公司**：快速根据市场热点生成详细世界观、人物设定与全本故事梗概，用于项目立项评估。

### 4.2 商业化变现路径 (Monetization Models)
- **Freemium 订阅制 (针对个人作者)**：
  - 免费版：支持 L0-L2 大纲生成与基础 Copilot 功能。
  - Pro 版（月/年费）：开放全套 7 Agent 闭环、高阶冷读监工、AI 腔消除及高级模型 Token 额度。
- **Team / Enterprise 版 (针对工作室/厂牌)**：
  - 按席位 + 消耗 Token 计费，提供私有化部署、专属题材 Few-shot 拆解服务与 7x24 技术支持。
- **生态抽成 (Marketplace Revenue Share)**：
  - 创作者在社区售卖题材模板包、拆解骨架，平台按 20%-30% 抽成。

---

## 五、 近期行动计划与里程碑 (Near-Term Action Plan)

| 里程碑 | 时间周期 | 关键交付物 | 衡量指标 |
| :--- | :--- | :--- | :--- |
| **M1: 引擎强化** | Month 1 | P1-P5 人机契约规范、4 大题材模板包、NovelBench 基准测试 | 测试覆盖率>85%，AI腔归零，重复率<5% |
| **M2: UI 原型** | Month 2 | Electron / Next.js 可视化工作台原型 (Novel Tree Canvas + 监工面板) | 人类作者干预响应时间<1s，完成单章端到端体验 |
| **M3: SaaS 试点** | Month 3-4 | 多租户云端部署、DeepSeek/Claude 混合调度优化、跨卷记忆系统 | 10万字生成成本<$5，伏笔回收率>90% |

---
*本 Roadmap 由产品管理团队制定，作为本仓库后续版本迭代与架构演进的基础指导文档。*
