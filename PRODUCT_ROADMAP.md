# AI 工业化小说写作平台 - 产品分析与演进路线图 (Product Roadmap & Strategy)

> 本文档针对 `ai-novel-sop` 仓库的理论规范 (`ai-novel-sop.html`) 与代码实现 (`implementation/`) 进行深度产品分析，并制定完整的产品演进路线与商业化落地策略。

---

## 一、 产品定位与核心价值主张 (Product Positioning & Value Proposition)

### 1. 行业痛点分析
当前生成式 AI 在小说与长篇文学创作领域面临三大瓶颈：
1. **单一 Prompt / 长上下文崩溃**：传统 AI 工具依赖单次 Prompt 一键生成长篇，随着字数增加，必然出现前文遗忘、故事结构失控、逻辑矛盾与人设漂移（Voice Deviation）。
2. **“AI 腔”同质化严重 (AI-ism)**：缺乏对语言风格与特定语料的精细化控制，生成内容充满套路化词汇（如“眼眸”、“深邃”、“仿佛”）、缺乏文学张力与情绪起伏。
3. **创作者缺乏控制力 (Lack of HITL Control)**：用户只能黑盒式等待生成结果，无法在世界观构建、人物关系设计、情节弧发展等不同认知层级上实施有效的人工干预（Human-in-the-Loop）。

### 2. 本产品的核心解法 (SOP 核心创新)
本平台基于 **“分而治之，两次拆解”** 的工业化流水线思想：
* **认知层级拆解（L0 ~ L4 认知金字塔）**：
  - `L0 世界观` → `L1 人物网` → `L2 情节弧` → `L3 分场大纲` → `L4 正文生成`。
* **动作单元拆解（6 大原子 Agent 角色）**：
  - **园丁 (Gardener)**：高 T 值发散生成多样化候选。
  - **剪枝师 (Pruner)**：低 T 值收敛挑选最佳方案。
  - **记忆管家 (Curator)**：固化状态至 SQLite / 快照 JSON。
  - **监工 (Inspector)**：实时审视反 AI 腔、重复率与人设漂移。
  - **解码器 (Decoder)**：跨层解耦与详细展开。
  - **蒸馏师 (Distiller)**：主题提炼与偏航纠正。
* **正反双向流水线闭环**：
  - **正向生成流水线**：自顶向下完成小说从无到有的创作。
  - **反向拆解流水线**：将经典名著/爆款小说逆向拆解为四维标杆单元，注入 Few-shot 知识库，作为正向生成的“基因指导”。

---

## 二、 代码库成熟度诊断 (Current Codebase Audit)

通过对 `implementation/` 源码的深入审计，产品现状诊断如下：

| 维度 | SOP 规范定义 | 现阶段代码实现 (`implementation/`) | 产品化短板与差距 |
|---|---|---|---|
| **认知分层架构** | L0-L4 完整层级与状态树 | 已实现 L0-L2 基础大纲流水线与 L3-L4 框架 | L2 到 L3/L4 的自动化关联调度仍待完善；长篇连贯性未形成自动闭环。 |
| **Agent 角色契约** | 6 大原子角色 + 专用 System Prompt | 已建立 Agent 角色，支持 DeepSeek/Claude 路由 | 提示词为静态模板，缺乏根据题材/语境的动态 Prompt 调优。 |
| **记忆与持久化** | SQLite (状态树/约束) + VectorStore (语义/Few-shot) | 实现 SQLite (`store.py`) 与 VectorStore (`vector_store.py`) | 缺失第三方向量依赖时降级为 TF-IDF/Jaccard；缺乏生产级向量数据库支持 (如 Qdrant/Milvus)。 |
| **质量度量与反AI腔** | 重复率、声音指纹、伏笔回收率等防御 | 已实现 `quality.py` 与 `voice_fingerprint.py` | 缺少真实的评测基准数据集（Evaluation Benchmark）；拦截后自动重写循环有待增强。 |
| **人机交互 (HITL)** | 门禁确认、分支决策、手动修改回传 | 仅支持 CLI 命令行与 Mock 自动化 | 缺乏可视化 Web UI，创作者无法直观进行节点拖拽、编辑与人设调优。 |
| **反向拆解流水线** | 标杆拆解、四维抽取 | `scene_decomposer.py` 框架初步构建 | 尚未形成爆款文本解析到 Few-shot 知识库的自动化管道。 |

---

## 三、 目标用户画像与使用场景 (User Personas & Scenarios)

1. **网络文学工作室与签约作者 (Web Novel Studios & Professional Writers)**
   - **痛点**：日更压力大、长篇容易崩盘、创作卡文。
   - **场景**：使用平台自动搭建自洽的世界观与情节弧，通过 HITL 门禁把控故事方向，利用 AI 批量生成草稿并人工精修。
2. **IP 开发与编剧团队 (IP & Screenwriting Teams)**
   - **痛点**：故事构架周期长、多人协作风格冲突、爆款规律难以复现。
   - **场景**：导入标杆爆款作品进行反向拆解，快速生成符合市场喜好的新剧情框架。
3. **独立 AI 创作者与网文爱好者 (Independent AI Creators)**
   - **痛点**：写作门槛高、逻辑推演能力不足。
   - **场景**：通过卡牌化界面选择世界观与人物设定，以低门槛一键协同创作长篇故事。

---

## 四、 产品演进路线图 (Product Roadmap)

```
[Phase 0: 基础巩固] ──► [Phase 1: 视觉化工作室] ──► [Phase 2: 标杆基因库] ──► [Phase 3: 百万字规模产线]
 (工程与测试底座)        (Web UI & HITL 工作台)      (自动化反拆与Few-shot)     (跨章节长效记忆/多端生态)
```

### 1. Phase 0: 基础巩固与工程质量提升 (Engineering & Quality Foundation) - *短期*
* **目标**：全面提升代码库的稳定性、可测试性与环境适应能力。
* **关键交付项**：
  1. **单元测试与 CI 覆盖**：为 Agent、Memory Store、Metrics 模块编写完整的 PyTest / Unittest 单元测试。
  2. **轻量降级与环境兼容**：优化 ChromaDB、jieba、sentence-transformers 的条件加载，确保无深度依赖时平滑降级。
  3. **质量评测基准库 (Evaluation Benchmark Set)**：构建包含 50+ 典型 AI 腔段落与偏航场景的标准测试集。

### 2. Phase 1: 视觉化交互升级 (Visual HITL Workbench) - *中期（核心 MVP）*
* **目标**：从 CLI 命令行工具升级为可视化的“AI 工业化小说创作工作台 (Novel Studio)”。
* **关键交付项**：
  1. **大纲树可视化编辑器 (Visual Tree Navigator)**：
     - 提供 L0-L4 节点的树状图/脑图展示，支持节点新建、编辑、分支（Branching）与快照对比。
  2. **人机协同门禁控制台 (HITL Control Room)**：
     - **剪枝决策对比面板**：在剪枝师 (Pruner) 产生多个选项时，可视化对比优缺点供创作者一键选择或手动融合。
     - **监工警示与重写高亮**：高亮 AI 腔词汇、重复句式及人设偏离点，提供一键替换与重写建议。
  3. **模型路由与 API 配置中心**：
     - 支持 DeepSeek (V3/R1)、Claude (Sonnet/Opus)、OpenAI (o3-mini/GPT-4o) 以及本地 Ollama 模型的动态分配与 Token 成本实时统计。

### 3. Phase 2: 标杆反拆与领域知识生态 (Reverse Pipeline & Knowledge Base) - *中长期*
* **目标**：打造“爆款小说基因库”，赋予 AI 顶级作家的叙事节奏与风格能力。
* **关键交付项**：
  1. **自动化标杆拆解引擎 (Automated Reverse Pipeline)**：
     - 一键导入经典小说/爆款网文，自动抽取四维标杆单元（世界观规则、人物卡牌、情绪高潮弧度、叙事节奏）。
  2. **动态 Few-shot 检索中心**：
     - 按题材（科幻/悬疑/修仙/都市）建立场景语料库，在正文生成时精准检索注入黄金开篇、战斗描写、悬疑留白等范例。
  3. **声音指纹（Voice Fingerprint）定制引擎**：
     - 基于小样本分析作家语言风格（句长分布、修辞偏好、对话占比），生成专属的 Style Prompt 约束。

### 4. Phase 3: 百万字长篇一致性与工业化产线 (Enterprise Scale & Ecosystem) - *长期*
* **目标**：解决百万字超长篇一致性痛点，实现商业化规模产线与多端生态。
* **关键交付项**：
  1. **跨章节长效记忆调度引擎 (Infinite Context Engine)**：
     - 分层摘要树与动态伏笔追踪图谱（Foreshadow Recovery Graph）。
     - 自动检测未回收伏笔并在后续章节的 L2/L3 生成中主动提示回收。
  2. **多角色多人协作 Studio (Collaborative Novel Studio)**：
     - 支持团队分工（主编定大纲，编剧定场景，AI 辅助填充正文，校验员审核）。
  3. **出版与网文平台对接导出 (Publishing & Export Ecosystem)**：
     - 支持导出 EPUB, DOCX, Standard Markdown, 剧本 Standard 格式。
     - 集成主流网文平台格式校验与查重/AI 率合规检测报告。

---

## 五、 商业化与技术架构建议 (Commercial & Architectural Strategy)

### 1. 商业化模式：开源 Engine + 商业化 SaaS / Desktop
* **开源 Core (Community Edition)**：保持 `ai-novel` 核心流水线与 SOP 规范开源，吸引开发者社区共同贡献 Agent 插件与提示词工程。
* **商业 Enterprise/Pro (SaaS / Studio Edition)**：
  - 提供开箱即用的 Visual Web UI / 桌面客户端。
  - 增值服务：云端高并发向量库、商业级爆款小说基因库订阅、定制化声音指纹训练。

### 2. 数据飞轮与模型微调 (Data Flywheel & DPO/RLHF)
* **人机协作数据回流**：搜集创作者在 HITL 门禁节点上的选择、修改与人工剪枝偏好。
* **小模型领域微调**：构建创作偏好 DPO (Direct Preference Optimization) 数据集，微调 7B/14B 开源模型（如 Qwen2.5 / Llama-3），用低成本小模型接管高频的“剪枝”与“监工”任务，显著降低使用成本并提升响应速度。

---
*设计制定人：产品经理 (Product Manager)*
