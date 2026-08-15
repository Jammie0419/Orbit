# OuRboros: Self-Evolving Cognitive Architecture for Autonomous Coding Agents
## Methodology (Methods) — 论文方法部分 V2.0

> **编制**: 基于 `ARCHITECTURE.md`(源码基线)、`PAPER_INTEGRATION_ANALYSIS.md`(融合方案 V9.0)、
> `METHODOLOGY.pdf`(方法论草稿)、`Ouroboros_SelfEvolution_Paper.pdf` 与 `evolution_innovation_directions.pdf`(创新方向) 系统整合。
> **用途**: 作为论文 Methods 章节(§3)的正文;第一部分为模块重组决策的中文说明,第二部分为可直接入稿的英文方法正文。

---

# PART 0 模块重组决策摘要(中文说明)

## 0.1 三个合并问题的一一回答

### 问题 1:Unified Smart Router(智能路由)+ Harness Tree 能否统一为"智能路由模块"?

**结论:可以,而且应当统一。** 二者共享同一个逻辑前提——"任务在进入执行前必须被决策",只是粒度不同:

| 维度 | Unified Smart Router | Harness Tree | 统一后的角色 |
|------|---------------------|--------------|-------------|
| 决策对象 | 工具 + 技能(资源级) | 提示词 + 上下文 + 预算(配置级) | 配置级承载资源级 |
| 决策粒度 | 单任务一次路由 | 任务 → 分支 → 子任务树 | 树上的每个节点都做一次路由 |
| 共享依赖 | 任务分类器 | 任务分类器(同一份) | **共享同一个统一任务分类器** |
| 反馈来源 | 路由历史 routing_history.jsonl | 轨迹经验(§3) | 共同消费轨迹反馈,共同反哺 |

统一后的模块命名为 **智能路由模块(Intelligent Routing Module, IRM)**,内部包含四个子引擎:
**(a) 统一任务分类器**(规则优先 + LLM 兜底,只分类一次)→ **(b) 工具-技能联合路由**(统一评分)→ **(c) Harness Tree 配置适配树**(任务特定 harness 分支、级联上下文继承、提前终止剪枝)→ **(d) 执行快照与处置引擎**(委派隔离 + accept/revise/escalate)。这样既消灭了"所有任务暴露全部 35 个工具 + 所有技能"的 token 浪费(降 50–70%),也消灭了"所有任务共用同一 harness 配置"的适应性问题,论文叙事上称为 **统一调度(Unified Dispatch)**——把"路由"从单点决策升级为贯穿任务树的决策骨架。

### 问题 2:Multi-Agent Evolver + Trajectory-based Experience Learning + Prompt Optimization 能否统一?

**结论:可以,建议统一命名为"自进化引擎(Self-Evolution Engine, SEE)"。**

三个子模块不是三个并列的卖点,而是一条经验驱动进化闭环的三个机能,强行拆开会破坏论文的因果叙事:

| 子模块 | 回答的问题 | 在闭环中的机能 |
|--------|-----------|---------------|
| Trajectory-based Experience Learning | 学什么? | **经验源**:把原始轨迹转成带步骤级信用分配的结构化经验(数据层) |
| Multi-Agent Evolver | 怎么做? | **执行体**:Analyzer→Researcher→Builder→Verifier 四阶段方法论(行动层) |
| Prompt Optimization | 用什么改? | **策略层**:把历史成败模式写回决策提示词,让下一次进化更聪明(中介层) |

三者的关系不是 pipeline,而是三角反馈:轨迹经验为进化提供适应度信号 → 进化产生新轨迹 → 提示词优化把轨迹洞察转译成指令约束来引导进化。**缺少任何一环,自进化都退化为源码现有的"决策式"进化**(只有 promote/不 promote 的二元判断)。统一后与源码的治理化自修改管线(观察→规划→修改→评审→提交→重启)自然对接:Multi-Agent Evolver 的四个 Agent 恰好落到该管线的 Modify 阶段。

### 问题 3:Hermes-Style Skill Evolution 单独成模块,Session Index + MemOS + Context Cache(+ Smart Memory)归为记忆模块?

**结论:完全合理,这正是"双轨进化"架构的关键设计。**

- **技能单独成模块(技能自进化引擎,SSE)**:因为技能的进化对象是"能力工件"(skill 资产),而 SEE 的进化对象是"系统实现"(源码/配置/提示词)。两者是**不同基质(genotype)上的两条进化轨道**:SSE 进化出"会什么"(capability),SEE 进化出"怎么运行"(implementation)。技能进化还有独立的生命周期(Seed→Draft→Active→Mature→Archived)、独立的触发机制(Nudge + 轨迹条件)与独立的伦理约束(只进化自编写技能、不碰社区技能)。因此单独成模块。
- **Session Index + MemOS + Context Cache 归为记忆模块(自适应记忆基座,AMS)**,并把 Smart Memory 一并并入:四者分别是记忆的**写入端**(Smart Memory:重要性评估+智能淘汰)、**检索端**(Session Index:FTS5 全文索引 + 分层嵌入)、**外部化端**(MemOS:跨会话语义记忆)与**执行端**(Context Cache:上下文窗口内三级缓存)。它们共同回答"记忆如何被评估、索引、外化、加载"——是同一主题的四个机能,拆开写会散。

## 0.2 模块化后的完整体系(论文视角)

经过重组,整套系统被模块化为 **6 个模块:4 大创新模块 + 2 个支撑模块**:

| # | 模块 | 英文缩写 | 源码基线 | 创新来源 | 论文叙事定位 |
|---|------|---------|---------|---------|-------------|
| 1 | 智能路由模块 | IRM | 静态工具注册表 + 单一 SYSTEM.md | Unified Smart Router + Harness Tree | 决策前端(自适应) |
| 2 | 自进化引擎 | SEE | 二元进化决策(promote) | TEL + MAE + POE | 系统级进化(核心创新) |
| 3 | 技能自进化引擎 | SSE | 技能加载器 + 手动技能 | Hermes-Style Skill Evolution | 能力级进化(双轨之其二) |
| 4 | 自适应记忆基座 | AMS | 10 种扁平文件记忆 + FIFO | Smart Memory + Session Index + MemOS + Context Cache | 认知地基(累积) |
| 5 | 治理与安全层 | GSL | 免疫表面/三方审查/审计/预算/唯一提交者 | 进化安全三层保障 + 七类失败模式缓解 | 横向包络(可信化) |
| 6 | 多智能体编排与后台意识 | MOC | 蜂群黑板 + 任务树 + 后台守护线程 | 演进为进化并行引擎 | 支撑器官(并行) |

## 0.3 框架图构思:为什么不是顺序关系

论文方法部分最忌把模块画成一条流水线。本架构的模块关系是**循环 + 辐射 + 包络**三类拓扑的叠加:

- **循环关系**(核心环):Execute → Reflect → Optimize → Store → Execute,认知循环是心脏,每轮任务同时产生执行输出与进化输入;
- **辐射关系**(四柱环绕):IRM(进)/SEE(系统级进化)/SSE(能力级进化)/AMS(记忆)环绕核心环,彼此之间只有**双向数据流与反馈流**,无单向顺序;
- **包络关系**(治理环):GSL 横向贯穿所有自修改动作(进化、技能更新、提示词改写),MOC 提供并行执行骨架——两者是"横切面"而非"下一级"。

三种连接类型在正文中用显式符号标注:`──▶` 数据流、`─◀─▶` 反馈流、`┄┄▶` 控制依赖(见 §3.2 图 1)。这保证了审稿人能立即看出"模块协同而非模块级联"。

## 0.4 除了这 4+2 模块,还能从源码挖掘哪些论文创新点(建议分级)

| 候选创新点 | 源码依据 | 建议 |
|-----------|---------|------|
| **治理化自修改(Governed Self-Modification)** | 免疫表面(protected paths)、跨厂商三方评审、审计账本、预算免疫、唯一提交者 | **纳入正文为模块 5(GSL)**——这是源码最强、也最容易被审稿人认可的差异化点 |
| **后台意识(Background Consciousness)** | 空闲时 10% 预算独立反思 | 纳入模块 6,作为"主动进化触发器" |
| **蜂群黑板协调(Swarm Blackboard)** | task_tree_ledger + tree_note/tree_read | 纳入模块 6,作为进化并行执行的物理基础 |
| **五层层级记忆(Hierarchical Memory)** | 创新方向 A:工作→情景→长期→存档→遗忘 | 建议作为 AMS 的理论升华写入 §7 展望/消融设计 |
| **成本预算感知进化** | 创新方向 F + usage_accounting | 建议并入 SEE(进化决策的 ROI 元指标),一句话即可提 |
| **用户反馈信号(超越 pass/fail)** | 创新方向 B | 建议并入 TEL(隐式/显式/效率/对比四类信号),作为经验加权来源 |
| **结构化组件类型系统** | 创新方向 D | 建议并入 SSE/IRM(技能=强类型组件),作为表示层面的创新 |
| **跨 session 迁移** | 创新方向 E | 建议并入 AMS(会话级种子模板 + skip_list),作为记忆基座的能力延伸 |

---

# PART 1 Methodology(英文正文,可直接入稿)

## 3. System Overview

### 3.1 Design Philosophy

Traditional coding agents operate in an open-loop paradigm: each task invocation starts from scratch, discarding the rich contextual knowledge accumulated during prior interactions. This architectural limitation manifests as three persistent pathologies: (i) *context amnesia* — the inability to leverage cross-session experience; (ii) *routing rigidity* — static dispatch mechanisms that fail to adapt to task complexity; and (iii) *stagnation* — the absence of self-improvement mechanisms, rendering the agent incapable of learning from its own successes and failures.

OuRboros addresses these limitations through a unified self-evolving cognitive architecture inspired by the Ouroboros symbol — the ancient serpent consuming its own tail — representing the perpetual cycle of execution, reflection, and renewal. The system treats every interaction as a trajectory that simultaneously serves as execution output, training signal, and evolutionary substrate.

Four design principles govern the architecture:

- **Cyclic, not pipeline.** Modules are organized around a central Cognitive Cycle rather than a linear chain; every module both consumes and produces the cycle's trajectory data.
- **Two-track evolution.** The system evolves along two orthogonal substrates: the *system implementation* (configuration, prompts, source) via the Self-Evolution Engine, and the *capability artifacts* (skills) via the Skill Self-Evolution Engine.
- **Governance precedes capability.** Every self-modification action is wrapped by a governance envelope (immune surfaces, cross-vendor review, audit ledger, budget immunity) so that the ability to change oneself and the constraint on that change are two faces of the same architecture.
- **Incremental embedding.** All enhancements are realized as hook-based, minimal-diff extensions over the existing production system (12 new modules, ~4.4K lines, zero changes to core loop semantics), preserving the system's proven safety and continuity properties.

### 3.2 Architectural Overview

Figure 1 presents the high-level architecture. The system comprises six modules organized around a central Cognitive Cycle. The topology is deliberately non-sequential: modules interact through three explicit connection types — **data flow** (`──▶`, artifacts exchanged at runtime), **feedback flow** (`─◀─▶`, learning signals returned to producers), and **control dependency** (`┄┄▶`, governance constraints imposed on actions). The Cognitive Cycle (core ring) is surrounded by four pillar modules — Intelligent Routing Module (input decision), Self-Evolution Engine (system-level evolution), Skill Self-Evolution Engine (capability-level evolution), and Adaptive Memory Substrate (knowledge grounding) — while the Governance & Safety Layer and the Multi-Agent Orchestration layer form a horizontal envelope that constrains and parallelizes all self-modification activity.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             GOVERNANCE & SAFETY LAYER  (GSL, 横向包络 · control)             │
│   免疫表面 protected paths │ 跨厂商三方评审 triad │ 审计账本 audit ledger      │
│   预算免疫 budget immunity │ 唯一提交者 sole committer │ 回滚 rollback         │
└───────┬───────────────────────────┬───────────────────────────┬─────────────┘
        │ ┄┄┄┄ 约束一切自修改动作 ┄┄┄┄│┄┄┄┄ 约束一切自修改动作 ┄┄┄┄│
┌───────▼───────────────────────────▼───────────────────────────▼─────────────┐
│                        MULTI-AGENT ORCHESTRATION  (MOC)                     │
│   Swarm Blackboard (tree_note/tree_read) │ Task Tree │ Background           │
│   Consciousness (主动进化触发器)          │ Disposition Engine              │
└───────┬─────────────────────────────────────────────────────────────────────┘
        │ 任务分配 / 并行执行骨架
┌───────▼─────────────────────────────────────────────────────────────────────┐
│   ┌─────────────────────────┐         ┌──────────────────────────────────┐  │
│   │  IRM 智能路由模块         │ ──▶▶▶  │  认知循环核心 Cognitive Cycle     │  │
│   │  · 统一任务分类器          │ 执行轨迹 │  Execute → Reflect → Optimize   │  │
│   │  · 工具-技能联合路由       │         │  → Store → (循环)               │  │
│   │  · Harness Tree 配置树    │ ◀─◀─◀   │                                │  │
│   │  · 执行快照与处置          │ 路由反馈 │   (唯一自进化主循环)             │  │
│   └───────────┬─────────────┘         └─────┬──────────────┬────────────┘  │
│               │ 路由决策                     │ 轨迹/反思      │ 经验/策略     │
│               ▼                             ▼              ▼               │
│   ┌──────────────────────┐  ┌────────────────────────┐  ┌────────────────┐ │
│   │  SEE 自进化引擎        │  │  SSE 技能自进化引擎      │  │ AMS 记忆基座    │ │
│   │  · 轨迹经验学习(TEL)   │  │  · 技能自动生成          │  │ · SmartMemory  │ │
│   │  · 多智能体进化器(MAE) │  │  · Nudge 引擎           │  │ · SessionIndex │ │
│   │  · 提示词优化(POE)     │  │  · GEPA 技能进化        │  │ · MemOS        │ │
│   │  系统级进化             │  │  · 质量感知路由(↔IRM)   │  │ · ContextCache │ │
│   └──────────────────────┘  └────────────────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
   Legend: ──▶ data flow   ─◀─▶ feedback flow   ┄┄▶ control dependency
```

**Figure 1.** OuRboros architecture overview. The Cognitive Cycle forms the core; IRM, SEE, SSE, and AMS are pillar modules with bidirectional interactions; GSL and MOC form a horizontal envelope.

The architecture is fundamentally non-sequential. For instance, the Memory Substrate informs the Intelligent Routing Module at routing time (historical success-rate priors per task type), while simultaneously receiving new skill artifacts from the Skill Self-Evolution Engine. The Trajectory Experience Learning sub-module provides fitness signals to both the Prompt Optimization Engine and the Multi-Agent Evolver, while itself relying on the Memory Substrate for long-term trajectory storage. Table 1 summarizes the bidirectional dependencies.

| Provider ↓ / Consumer → | IRM | SEE (TEL/MAE/POE) | SSE | AMS |
|---|---|---|---|---|
| **IRM** | — | raw execution traces, delegation logs | routing decisions, tool usage stats | snapshot metadata, routing history |
| **SEE** | updated routing policies (per task-type success priors) | — | fitness signals, skill candidates | experience embeddings, evolution history |
| **SSE** | quality-aware skill scoring (version/success-rate weights) | new strategies (prompt fragments, evolved patterns) | — | skill artifacts, skill stats |
| **AMS** | historical patterns, retrieval results | few-shot examples, retrieved experiences | skill stats (execution_count, success_rate) | — |

**Table 1.** Cross-module interaction matrix. Each cell lists the data artifacts exchanged.

### 3.3 Intelligent Routing Module (IRM)

#### 3.3.1 Motivation and Problem Formulation

Real-world coding tasks exhibit extreme heterogeneity: a single session may involve a trivial typo fix (latency-sensitive, minimal context), a complex multi-file refactoring (context-intensive, parallelizable), and a subtle concurrency bug diagnosis (reasoning-intensive, sequential). The baseline system exposes all 35 tools and all skills to every task without distinction, wasting 7,000–17,500 tokens on tool schemas per request and incurring a ~20% tool-selection error rate; every task also loads an identical system prompt and memory injection regardless of type.

We formulate the dispatch problem as a **contextual bandit with resource constraints**. At each decision point *t*, the system observes a task feature vector *x_t* (complexity estimate, required tools, dependency depth, historical success rate) and selects a dispatch action *a_t* that jointly determines: (i) the execution lane (lightweight delegation vs. full cognitive cycle), (ii) the agent configuration (model, tool set, context budget, prompt branch), and (iii) the isolation level (shared state vs. private snapshot). The routing decision is logged as a tuple *r_t = (x_t, a_t, lane, budget, outcome)* and fed back into the Self-Evolution Engine to improve future routing decisions — closing the Dispatch–Memory feedback loop (see §3.8).

#### 3.3.2 Unified Task Classifier

A single lightweight classifier serves every downstream component (tool routing, skill routing, harness selection), guaranteeing that classification happens exactly once per task. It operates in two tiers:

1. **Rule-based tier.** Deterministic signals (workspace presence → coding; task-type tags → research/knowledge/simple) provide instant classification at zero LLM cost.
2. **LLM tier.** When rules are inconclusive, a compact LLM call classifies the task into one of *K* intent categories (e.g., code generation, bug diagnosis, refactoring, documentation, web research).

The single-classifier design is what makes Unified Dispatch coherent: tool routing, skill routing, and harness selection all consume the same label, and a misclassification is corrected in one place rather than three.

#### 3.3.3 Unified Tool–Skill Router

The router consumes the task label and jointly emits (a) a filtered tool set and (b) a ranked skill set:

- **Tool routing.** Each intent category maps to a curated tool set (10–15 tools vs. the baseline 35). The emitted tool names filter the ToolRegistry's schema exposure to the LLM, reducing schema tokens by 50–70%.
- **Skill routing.** Every skill receives a relevance score combining: tag overlap, name match, description match, and — crucially — **quality terms supplied by the Skill Self-Evolution Engine**: self-authored bonus (+0.1), high success-rate bonus (+0.1 when success_rate > 0.8), and version bonus (+0.05 per evolution version). The top-K (default 10) skills with score > 0.3 are injected into the prompt.

Because both routes share the classifier and scoring philosophy, the router is a single extension point: adding a new intent category or a new quality signal requires touching one file.

#### 3.3.4 Harness Tree Dispatch Engine

The Harness Tree extends routing from individual tasks to execution trees — hierarchical configurations representing task decomposition. Each node of the tree is a dispatch decision; each branch is a task-specific harness:

- **Branch composition.** A branch bundles `system_prompt.md` (task-specific instructions), `tool_set.json`, and `memory_config.json` (which memory sections to inject, with priorities). Branches are organized under a root (`main`) with typed children (`coding`, `research`, `knowledge`, ...), mirroring the classifier's label space.
- **Cascading context inheritance.** Child nodes inherit a compressed summary of their parent's context (relevant code snippets, prior decisions, constraints), avoiding cold starts at each delegation level.
- **Pruning via early termination.** If a parent node's execution produces a result that renders child nodes unnecessary, the remaining subtree is pruned and allocated resources reclaimed.
- **Adaptive budget allocation.** Each branch carries resource budgets (context tokens, tool invocations, execution deadline, delegation depth) proportional to estimated complexity.

#### 3.3.5 Execution Snapshot and Disposition Engine

To keep delegated sub-agent executions both isolated and auditable: (1) the system creates a private snapshot of the current execution state; (2) the sub-agent operates within the snapshot, producing a result and confidence score; (3) the Disposition Engine evaluates the output against correctness, consistency, and efficiency criteria, and emits one of `accept` (merge into parent context), `revise` (re-dispatch with modified instructions), or `escalate` (promote to a higher execution tier). The disposition is recorded into the trajectory, enabling the system to learn which delegation patterns succeed.

**Contribution 1 (Unified Dispatch).** The integration of the Unified Smart Router, Harness Tree, and Execution Snapshot into a single dispatch framework that adapts to task complexity at multiple granularities — a contextual-bandit formulation of routing with closed-loop feedback from execution outcomes.

### 3.4 Self-Evolution Engine (SEE)

#### 3.4.1 The Cognitive Cycle: Unified Logic

The SEE implements the self-referential loop that gives the system its name. Rather than three independent components, the engine is a single cycle with three coordinated subsystems:

```
  Phase 1 Execute   ──►  Phase 2 Reflect   ──►  Phase 3 Optimize   ──►  Phase 4 Store
  (task execution      (Trajectory-based      (Prompt Optimization    (adaptive memory
   produces trajectory   Experience Learning    + Multi-Agent Evolver   substrate persists
   segments)             assigns step credits)   execute improvements)   artifacts)
        ▲                                                                      │
        └──────────────────────  Phase 5: next cycle starts warm  ◀────────────┘
```

**Phase 1 — Execute.** Every action — tool invocation, reasoning step, code modification — is recorded as a trajectory segment *τ_i = (s_i, a_i, o_i, r_i)*, augmented with task description, final outcome, resource consumption, the initiating dispatch decision, and the reflection record.

**Phase 2 — Reflect.** The Trajectory-based Experience Learning sub-module (TEL) transforms raw traces into structured, credit-scored experience (detailed below).

**Phase 3 — Optimize.** Two actions happen: the Prompt Optimization Engine (POE) refines the system's own instructions from accumulated reflection data, and the Multi-Agent Evolver (MAE) executes structured improvement cycles (Analyze → Research → Build → Verify) using trajectory fitness signals.

**Phase 4 — Store.** All trajectory data, reflection records, and optimization artifacts persist to the Adaptive Memory Substrate, ensuring compound learning across cycles.

#### 3.4.2 Sub-module A: Trajectory-based Experience Learning (TEL)

Not all trajectories are equally valuable. TEL implements a four-stage optimization pipeline that selects, compresses, and enriches trajectories before storage:

1. **Deduplication.** Structurally identical trajectories are merged with occurrence counts.
2. **Compression.** Redundant intermediate states (e.g., eventually-succeeded failed tool calls) are removed.
3. **Annotation.** Trajectories are labeled with reflection-extracted patterns.
4. **Scoring.** Each trajectory receives utility *u(T)* from outcome quality, efficiency, generalizability, and novelty.

Its central innovation is **step-level credit assignment**. Whereas the baseline records only the aggregate outcome (absorbed/abandoned/no_op) of an evolution cycle, TEL assigns a normalized credit *c(s) ∈ [0,1]* to every step: base 0.5, +0.2 for success, −0.3 for error, +0.1 for fast completion, +0.1 for token efficiency. The credit distribution identifies **critical steps** — the top-3 highest-credit and bottom-2 lowest-credit steps — yielding: (i) success factors (what worked), (ii) failure factors (what failed), and (iii) **recommended tools** aggregated from the critical-step patterns of similar past objectives. On new tasks, hybrid retrieval (semantic similarity + structural matching + outcome filtering) fetches the top-*k* relevant experiences as few-shot examples and as fitness baselines for evolution. The credit signal can be further enriched by four feedback classes beyond pass/fail — implicit behavioral signals (skill reuse frequency, edit patterns), explicit interaction signals (likes, corrections, skips, manual overrides), efficiency signals (token cost, latency, tool-call counts), and comparative signals (new vs. old harness on the same task).

#### 3.4.3 Sub-module B: Multi-Agent Evolver (MAE)

The baseline evolution loop is a binary decision: a fixed prompt decides whether to promote an improvement cycle; execution is single-agent and unstructured (historical absorbed rate ≈ 40%). MAE replaces the execution phase with a **structured four-stage methodology**, each stage entrusted to a dedicated role:

1. **Analyzer** — performs failure analysis over the task trace and the improvement backlog, extracting root causes and ranking priority improvements with estimated impact.
2. **Researcher** — designs the implementation approach: files to modify, implementation steps, and risks, grounded in codebase context.
3. **Builder** — implements the change by invoking the system's own atomic editing primitives (apply_patch / edit_batch / write_file with validation).
4. **Verifier** — evaluates the change against the original objective: objective achieved, test results, side effects, and a recommendation (`merge` / `revise` / `reject`).

The MAE integrates naturally with the baseline's governed self-modification pipeline (Observe → Plan → Modify → Review → Commit → Restart): the four roles occupy the Modify stage, while the existing cross-vendor triad review, scope review, stale-binding, unique committer, and rollback mechanics remain as hard gates. This is deliberate — evolution capability and evolution constraint must scale together.

#### 3.4.4 Sub-module C: Prompt Optimization Engine (POE)

The system treats its own instructions as optimizable parameters. Given a current prompt *P_t* and a trajectory with outcome quality *q(T)*, POE:

1. **Decomposes** the prompt into *m* semantic segments (tool-use guidelines, error-handling protocol, output-format specification).
2. **Attributes** each segment's contribution counterfactually — "would the outcome have differed if segment *p_i* were absent?" — approximated by comparing against similar past trajectories under different prompt configurations.
3. **Generates** candidate modifications via pattern-based rewriting, reflection-driven revision, and evolutionary mutation.
4. **Evaluates and selects** candidates using a proxy metric (estimated outcome quality from similar past executions).

Prompt variants undergo a conservative lifecycle — Candidate → Probation (tested in *n* sessions) → Promoted (validated across diverse tasks) → Retired (degraded under distribution shift) — ensuring optimization is adaptive but never reckless.

#### 3.4.5 Sub-System Coordination: Three-Way Feedback, Not a Pipeline

TEL, MAE, and POE form a closed triangle rather than a chain:

- TEL provides fitness signals to MAE (without trajectories, evolution would be blind) and attribution data to POE;
- MAE produces strategy variants that generate new trajectories (without evolution, trajectories would stagnate);
- POE mediates between the two, translating trajectory insights into instruction refinements that guide evolution.

**Contribution 2 (Experience-Driven Self-Evolution).** A unified Self-Evolution Engine in which step-level credit-assigned trajectory learning, a four-role structured multi-agent evolution methodology, and attribution-based prompt optimization form a single self-referential loop — replacing binary evolution decisions with a continuously improving, verifiable evolution pipeline.

### 3.5 Skill Self-Evolution Engine (SSE)

#### 3.5.1 Motivation: A Second, Orthogonal Evolution Track

Skills are the most mature form of experience — reusable capability units tested and refined across sessions. In the baseline, skills are static assets: discovered from disk, executed on demand, and never automatically created or improved. The SSE closes this gap by making skills themselves an evolutionary substrate. It is kept separate from the SEE because the two evolve different genotypes: SEE evolves *how the system runs* (implementation), SSE evolves *what the system can do* (capabilities); and because skill evolution carries its own lifecycle, triggers, and ethical constraints (community skills are never modified — only self-authored ones).

A skill is represented as a strongly-typed component: *S = (name, trigger, instructions, parameters, scripts, tags, source, version, fitness)*, where `fitness` is a running estimate updated after each invocation and `source` distinguishes `native`/`community` from `self-authored`.

#### 3.5.2 Auto-Generation from Trajectories

A skill is distilled from a task trace when three conditions hold: (i) more than five tool calls occurred, (ii) the agent performed self-repair (an error followed by a successful retry), and (iii) the task succeeded. An LLM then synthesizes the skill (name, description, parameters, executable scripts, tags) from the extracted key steps; the artifact is stored under `skills/self/` with a `.self_authored.json` origin marker and recorded in the generation history.

#### 3.5.3 Nudge Engine

The Nudge Engine periodically (hourly cadence) prompts the agent to review recent work, detecting (a) reusable patterns worth distilling into new skills and (b) failed `skill_exec` invocations that signal existing skills needing evolution. Nudges are logged and only materialize into generation/evolution actions when the analysis supports them.

#### 3.5.4 GEPA-based Skill Evolution

Eligible skills (self-authored, evolution-enabled, ≥10 executions, success rate < 0.8) undergo genetic-Pareto prompt optimization:

1. **Failure analysis** aggregates common error messages and an LLM generates improvement suggestions;
2. **Population construction** builds a variant set: the original skill + suggestion-guided mutations + random mutations (add error handling / improve description / optimize parameters);
3. **Evaluation** scores each variant's fitness against execution history;
4. **Selection** promotes the best variant only if it strictly exceeds the incumbent's success rate, incrementing the evolution version.

All evolution events are appended to `skill_evolution_history.jsonl`, making every skill change auditable and reversible (the incumbent is never destroyed).

#### 3.5.5 Quality-Aware Routing Interface

Evolved skills feed back into the IRM: routing score gains self-authored (+0.1), high-success (+0.1), and version (+0.05/version) weights. This closes the capability loop — better skills are surfaced more often, get more executions, and receive faster fitness updates.

**Contribution 3 (Capability-Level Self-Evolution).** An orthogonal skill-evolution track with trajectory-driven auto-generation, a nudge-based trigger mechanism, GEPA-based variant evolution with strict fitness gating, and provenance constraints (only self-authored skills evolve), integrated with routing through quality-aware scoring.

### 3.6 Adaptive Memory Substrate (AMS)

#### 3.6.1 Baseline and Design Gap

The baseline already maintains ten memory types (working scratchpad, identity, world profile, dialogue blocks, knowledge, patterns, reflections, checkpoints, backlog, registry) with generation-aware consolidation and atomic concurrent writes. However, it exhibits five weaknesses: flat FIFO eviction with no importance assessment; no semantic search; rotating chat logs (800KB) that are effectively lost after archival; per-task context reconstruction that defeats prompt caching; and no session concept at all. AMS addresses these with four tightly-integrated components.

#### 3.6.2 Smart Memory: Importance-Based Management (Write Side)

The scratchpad's FIFO eviction is replaced by a **hybrid importance model**: a rule tier (source priors: error > reflection > routine; high-value keywords; content-length heuristics) with an LLM fallback when rules are ambiguous. Each block is additionally tagged (LLM-extracted keywords). Eviction now removes the lowest-importance block, and retrieval supports tag-filtered and importance-threshold queries — raising important-memory retention from ~60% to an estimated ~90–95%.

#### 3.6.3 Session Index: Searchable History (Retrieval Side)

A persistent SQLite FTS5 index (`state/session_index.db`) makes the entire session history searchable without altering any existing file: chat summaries, task reflections, and evolution checkpoints are incrementally synchronized (checkpoints via lazy delta-sync with an offset cursor). A cold-call `session_search` tool exposes full-text retrieval at query time, so historical experience — "how did I solve this before?" — becomes a first-class resource. The index is designed as an overlay: existing rotation, archival, and write paths are untouched.

#### 3.6.4 MemOS: External Semantic Memory

An optional external memory provider adds semantic retrieval and cross-project knowledge sharing. Hook-based by design: after each reflection, the reflection content is synchronized to MemOS as a textual memory (source-tagged); during context construction, a prefetch retrieves the top-5 semantically similar memories and injects them as context hints. When MemOS is unavailable, the system degrades gracefully to baseline behavior. Memories transition through lifecycle states (ephemeral → working → archived → forgotten) governed by access frequency, recency, and relevance; similar memories are periodically consolidated; conflicts between new experience and stored memories are resolved by retaining both with context tags and flagging the conflict for reflection analysis.

#### 3.6.5 Context Cache and Resource Lifecycle Manager (Execution Side)

A three-tier cache aligns the memory substrate with the finite context window: L1 session cache (current session, LRU with relevance weighting), L2 working set (cross-session active projects, LFU with recency decay), and L3 archive (unbounded, disk-backed, never evicted). Stable context blocks (identity, world profile, knowledge index) are reused within a session, raising prompt-cache hit rate from ~0% to an estimated 60–80%. The Resource Lifecycle Manager enforces proportional budget allocation (from the IRM's complexity estimate), graceful degradation under budget pressure, reclamation after task completion, and **snapshot-based garbage collection** — execution snapshots are treated as immutable objects and reclaimed when unreferenced, keeping memory growth sub-linear in the number of sessions.

**Contribution 4 (Cognitive Continuity).** A four-sided memory substrate — importance-managed writes, full-text searchable history, external semantic memory, and cache-aware context loading — that eliminates the amnesia pathology while leaving the proven baseline memory semantics (atomicity, generation awareness) intact.

### 3.7 Governance & Safety Layer (GSL)

Self-evolution is unsafe unless its failure modes are structurally bounded. The baseline already embodies a governance architecture: protected paths (immune surface), cross-vendor triad review with scope review, stale-binding (edits invalidate old reviews), attempt caps, an audit ledger, budget immunity, a sole committer, and automatic rescue snapshots. The GSL elevates these into a three-layer evolution-safety guarantee:

1. **Prediction-aware patching.** Every modification carries a self-stated prediction ("this change is expected to raise coding-task pass rate by 5%, no effect on research tasks"). Post-verification comparison computes prediction accuracy as a meta-metric that penalizes inaccurate evolution.
2. **Regression holdout pool.** A holdout task pool (sampled per task type, plus the hardest 10%) is evaluated before and after each evolution; a pass-rate drop exceeding 5% (or a significant statistical test) rejects the change.
3. **Cross-branch conflict detection.** When a modification touches shared components (common prompts, shared skills), validation is forced across all affected branches, not just the current task type.

Together with the baseline's seven failure-mode mitigations (degeneration loops, self-confirmation, stale reviews, infinite retries, budget burning, identity drift, verification bias), this makes the safety argument *structural* rather than behavioral: failures are local (isolated worktrees), reversible (rescue snapshots + undo commits), visible (full audit trail), and expensive (physical attempt ledgers) — and the final authority over self-modification never resides with the modified object itself.

**Contribution 5 (Governed Self-Modification).** A three-layer evolution-safety guarantee — prediction-aware patching, regression holdout validation, and cross-branch conflict detection — layered over immune surfaces, cross-vendor review, audit ledgers, budget immunity, and sole-committer enforcement.

### 3.8 Cross-Module Synergy: A Unified View

The six modules form a unified cognitive architecture through three emergent synergy patterns:

**Synergy 1 — Dispatch–Memory feedback loop.** IRM routing decisions are logged into AMS; the Session Index provides prior success rates for similar tasks under different dispatch configurations; skill fitness informs routing weights; resource availability signals prevent over-commitment. Each routing decision generates data that improves future routing decisions.

**Synergy 2 — Trajectory–Evolution co-adaptation.** TEL provides fitness signals for MAE; MAE produces strategy variants that generate new trajectories; POE mediates by translating trajectory insights into instruction refinements. The system simultaneously optimizes what it knows (trajectories), how it knows it (prompts), and how it acts (strategies).

**Synergy 3 — Skill–Memory consolidation cycle.** Raw trajectories accumulate in the Session Index → TEL extracts skill seeds → SSE validates and refines them into mature skills → quality-aware routing injects them into execution → improved executions generate higher-quality trajectories. This is a knowledge-distillation pipeline that continuously compresses raw experience into reusable expertise.

### 3.9 Theoretical Analysis

**Proposition 1 (Experience Convergence).** Under stationarity of the task distribution within each evaluation window and Lipschitz continuity of the trajectory utility *u*, the expected trajectory utility converges to a local optimum as cycles T→∞ when the optimization steps satisfy the Robbins–Monro conditions (Σα_t = ∞, Σα_t² < ∞). Proof sketch: each optimization step (prompt optimization, strategy evolution, skill refinement) is a stochastic gradient step on the utility landscape; the Cognitive Cycle coordinates steps to prevent oscillation, and AMS provides warm starts that reduce variance.

**Proposition 2 (Evolutionary Stability).** The population-based evolution converges to an evolutionarily stable strategy when the fitness landscape is smooth and the mutation rate satisfies p_m < 1/(2|g|), where |g| is the genotype length. The co-evolutionary dynamics (fitness measured relative to the evolving task distribution) prevent premature convergence to a single strategy.

**Complexity.** Per-cycle overhead: trajectory retrieval O(log N) (ANN); prompt optimization O(m·k) (segments × candidates); evolution O(P·G) (population × generations). Space grows sub-linearly with sessions due to consolidation and snapshot-based GC.

### 3.10 Implementation Mapping: Minimal-Diff Enhancement over the Baseline

All innovations are realized as additive modules with hook-based bridges, preserving the baseline's core loop semantics. New files (≈4.4K lines total): `smart_router.py` (IRM, ~500), `harness_tree.py` + `harness_configs/` (IRM, ~500), `evolution/trajectory_experience_learner.py` (SEE, ~500), `evolution/multi_agent_evolver.py` (SEE, ~400), `evolution/prompt_optimizer.py` (SEE, ~300), `skill_auto_generation.py` + `skill_evolution.py` + `skill_nudge_engine.py` (SSE, ~1,200), `memory_ext/smart_memory.py` (AMS, ~400), `memory_ext/session_index.py` + `tools/session_search.py` (AMS, ~240), `memory_ext/memos_provider.py` (AMS, ~300). Bridge modifications (~100 lines) touch only `agent.py`, `context.py`, `reflection.py`, `agent_task_pipeline.py`, and `post_task_evolution.py` at existing lifecycle hooks — e.g., context construction, post-reflection processing, and evolution promotion decision points.

### 3.11 Summary

OuRboros represents a paradigm shift from static, stateless coding agents to dynamic, self-evolving cognitive systems. Six modules — the Intelligent Routing Module, Self-Evolution Engine, Skill Self-Evolution Engine, Adaptive Memory Substrate, Governance & Safety Layer, and Multi-Agent Orchestration — form a unified feedback architecture in which every execution simultaneously solves the immediate task and improves the system's future capabilities. The key innovations are: **(1) Unified Dispatch** (§3.3), **(2) Experience-Driven Self-Evolution** (§3.4), **(3) Capability-Level Self-Evolution** (§3.5), **(4) Cognitive Continuity** (§3.6), and **(5) Governed Self-Modification** (§3.7) — together enabling a form of machine autonomy in which the system autonomously improves its own capabilities, adapts to changing environments, and accumulates expertise over its operational lifetime.
