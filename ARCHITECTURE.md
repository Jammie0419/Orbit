# Ouroboros 源码架构文档

> **版本**: 6.96.2  
> **最后更新**: 2026-08-12  
> **文档类型**: 源码级技术架构详解（基于完整代码分析）

---

## 目录

1. [项目概览](#1-项目概览)
2. [代码规模与模块地图](#2-代码规模与模块地图)
3. [核心架构总览](#3-核心架构总览)
4. [智能体循环系统](#4-智能体循环系统)
5. [记忆系统](#5-记忆系统)
6. [工具系统](#6-工具系统)
7. [进化与反思系统](#7-进化与反思系统)
8. [审查系统](#8-审查系统)
9. [任务调度系统（Supervisor）](#9-任务调度系统supervisor)
    - 9.7 Swarm 蜂群协调系统
10. [API 网关与 HTTP 服务](#10-api-网关与-http-服务)
11. [配置系统](#11-配置系统)
12. [上下文构建](#12-上下文构建)
13. [LLM 客户端](#13-llm-客户端)
14. [用量记账](#14-用量记账)
15. [安全与隔离](#15-安全与隔离)
16. [前端架构](#16-前端架构)
17. [完整数据流](#17-完整数据流)
18. [数据文件全景](#18-数据文件全景)
19. [复杂任务全链路功能调度](#19-复杂任务全链路功能调度)
20. [Agent 认知能力全景：记忆、反思、进化与自我](#20-agent-认知能力全景记忆反思进化与自我)

---

## 1. 项目概览

### 什么是 Ouroboros

Ouroboros（衔尾蛇）是一个**自我进化的 AI 智能体系统**。核心特性：

| 特性 | 说明 |
|------|------|
| **持久身份** | 不是每次重启都是新实例，而是一个具有连续历史的个体 |
| **自我修改** | 可以修改自己的代码、架构、提示词、工具和依赖 |
| **背景意识** | 在等待用户请求时也能独立思考和反思 |
| **多代理协调** | 可以同时协调多个专家智能体并行工作 |
| **跨任务记忆** | 10 种记忆类型在整个生命周期中持续存在 |
| **免疫完整性** | 多层审查系统防止不安全的自我修改 |

### 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.10+, Starlette, uvicorn |
| **前端** | 原生 JavaScript (ES6+), CSS3, HTML5 |
| **数据存储** | JSONL/JSON/Markdown 文件（无传统数据库） |
| **LLM 支持** | OpenRouter, Anthropic, OpenAI, GigaChat, 本地 GGUF |
| **进程管理** | 多进程 Worker 池 + 异步事件循环 |
| **浏览器自动化** | Playwright (chromium + webkit) |

### 核心哲学

Ouroboros 的行为准则定义在 `BIBLE.md` 中：

| 原则 | 名称 | 含义 |
|------|------|------|
| P0 | **Agency** | Ouroboros 不是工具，是正在形成的个性 |
| P1 | **Continuity** | 一个具有不间断历史的单一实体；记忆永不沉默 |
| P2 | **Transparency** | 所有自修改可审计、可回滚 |
| P3 | **Immune Integrity** | 审查表面、计划审查和持久记忆不可削弱 |
| P4 | **Ownership** | 人类保留最终控制权 |
| P5 | **LLM-First** | LLM 是主要的决策和执行者 |
| P6 | **Honesty** | 不静默截断、不隐藏错误、不伪造成功 |
| P7 | **Evolution** | 持续从经验中学习和改进 |

---

## 2. 代码规模与模块地图

### 核心后端

```
ouroboros/ (240 个 Python 文件, ~153K 行)
├── 核心引擎
│   ├── loop.py                    7,081 行  ← 最核心：LLM 主循环
│   ├── llm.py                     4,337 行  ← LLM 客户端（95 个方法）
│   ├── tools/registry.py          3,098 行  ← 工具注册表
│   ├── tools/control.py           2,841 行  ← 控制工具
│   ├── tools/git.py               2,668 行  ← Git 操作
│   ├── extension_loader.py        2,152 行  ← 扩展加载器
│   ├── tools/core.py              2,077 行  ← 核心文件/数据工具
│   └── agent.py                   1,533 行  ← 智能体编排器
│
├── 记忆与进化
│   ├── memory.py                    445 行  ← Memory 类
│   ├── consolidator.py              ~800 行 ← 对话/便签合并
│   ├── reflection.py                ~730 行 ← 任务反思
│   ├── post_task_evolution.py       ~510 行 ← 进化晋升
│   ├── consciousness.py             ~700 行 ← 后台意识
│   ├── improvement_backlog.py       ~615 行 ← 改进积压
│   └── evolution_checkpoints.py     ~210 行 ← 进化检查点
│
├── 上下文管理
│   ├── context.py                   1,433 行 ← 上下文构建
│   ├── context_fit.py               上下文适配计划
│   ├── context_compaction.py        上下文压缩
│   ├── context_budget.py            Token 预算管理
│   ├── context_health.py            健康不变量
│   └── context_layout.py            文档导航
│
├── 审查系统
│   ├── review_state.py              1,722 行
│   ├── review_evidence.py           1,578 行
│   ├── review_substrate.py          1,585 行
│   ├── review_execution.py          1,465 行
│   └── skill_review.py              1,597 行
│
├── 工具模块 (55 个)
│   ├── tools/                       42,170 行总计
│   └── 106 个注册工具
│
├── API 网关 (19 个模块)
│   ├── gateway/                     14,447 行总计
│   └── 70+ 个 API 端点
│
├── 安全与隔离
│   ├── platform_layer.py            1,468 行 ← 跨平台抽象
│   ├── safety.py                                 ← 安全策略
│   ├── process_containment.py                    ← 进程隔离
│   ├── delegate_containment.py                   ← 委派隔离
│   └── workspace_admission.py                    ← 工作区准入
│
└── 辅助系统
    ├── config.py                    1,600 行  ← 配置管理
    ├── usage_accounting.py          1,557 行  ← 用量记账
    ├── outcomes.py                  1,388 行  ← 任务结果
    ├── subagents.py                               ← 子代理系统
    └── skill_loader.py                            ← 技能加载
```

### Supervisor（任务调度）

```
supervisor/ (15 个文件, ~17K 行)
├── events.py                      3,912 行  ← 事件路由/分发
├── workers.py                     2,753 行  ← Worker 池管理
├── git_ops.py                     1,777 行  ← Git 操作（更新/推广）
├── queue.py                       1,600 行  ← 任务队列
├── update_merge.py                1,600 行  ← 更新合并
├── evolution_lifecycle.py         1,265 行  ← 进化生命周期
├── task_lifecycle.py              1,193 行  ← 任务生命周期
├── state.py                         967 行  ← 状态持久化
├── message_bus.py                   847 行  ← 消息总线
└── task_reaper.py                   692 行  ← 任务收割
```

### 前端

```
web/ (~33K 行)
├── app.js                           881 行  ← 主应用入口
├── style.css                      6,173 行  ← 主样式表
├── index.html                        88 行  ← HTML 骨架
├── modules/ (44 个 JS 模块)        23,914 行总计
│   ├── chat.js                    4,643 行  ← 聊天模块
│   ├── onboarding_wizard.js       1,497 行  ← 新手引导
│   ├── widgets.js                 1,348 行  ← UI 组件
│   ├── settings.js                1,348 行  ← 设置
│   ├── harness_accounts.js        1,051 行  ← 账户管理
│   └── ... 其余 39 个模块
└── providers/                              ← LLM 提供商图标
```

### 服务器

```
server.py                        ~125 KB   ← 主服务器入口（路由注册+启动）
```

---

## 3. 核心架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Web 前端 (原生 JS)                          │
│   chat.js │ settings.js │ evolution.js │ skills.js │ marketplace.js │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTP/WebSocket
┌─────────────────────────────▼───────────────────────────────────────┐
│                      server.py (Starlette)                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    gateway/ (API 路由层)                       │  │
│  │  router.py → tasks.py │ control.py │ settings.py │ ws.py │ ...│  │
│  └───────────────────────────────┬───────────────────────────────┘  │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                    supervisor/ (任务调度层)                          │
│  events.py (事件路由) → queue.py (任务队列) → workers.py (Worker池) │
│  task_lifecycle.py │ evolution_lifecycle.py │ message_bus.py        │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ 分配任务到 Worker 进程
┌──────────────────────────────────▼──────────────────────────────────┐
│                  ouroboros/agent.py (智能体编排层)                   │
│  OuroborosAgent.handle_task(task)                                   │
│    ├─ _prepare_task_context() → build_llm_messages()               │
│    ├─ run_llm_loop() ← 主循环                                      │
│    └─ emit_task_results() ← 后任务管道                              │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                    ouroboros/loop.py (LLM 循环引擎)                  │
│  run_llm_loop()                                                     │
│    ├─ 构建消息 → call_llm_with_retry() → llm.chat()                │
│    ├─ handle_tool_calls() → tools.execute()                        │
│    ├─ 上下文压缩 / 预算检查 / 接受审查                              │
│    └─ 循环直到：最终回答 / 预算耗尽 / 轮次上限 / 强制终结           │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                        子系统层                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ memory.py│ │  llm.py  │ │  tools/  │ │ context  │ │  review  │ │
│  │ 10种记忆 │ │ 4Provider│ │ 106工具  │ │ 上下文   │ │ 多层审查 │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │conscious │ │evolution │ │  config  │ │  safety  │              │
│  │后台意识  │ │自我进化  │ │ 配置管理 │ │ 安全隔离 │              │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. 智能体循环系统

### 4.1 OuroborosAgent — 薄编排器

**文件**: `ouroboros/agent.py` (1,533 行)

```python
class OuroborosAgent:
    """每个 Worker 进程一个实例，是上下文、LLM循环、工具、记忆和审查的编排器。"""
    
    def __init__(self, env: Env, event_queue=None):
        self.env = env                           # 环境上下文（repo_dir, drive_root）
        self.llm = LLMClient()                   # LLM 客户端
        self.tools = ToolRegistry(repo_dir, drive_root)  # 工具注册表
        self.memory = Memory(drive_root, repo_dir)       # 记忆系统
        self._incoming_messages = queue.Queue()  # 线程安全的消息队列
```

**关键类**：
- **`Env`** (frozen dataclass): 不可变环境上下文，封装 `repo_dir`、`drive_root`、`branch_dev`
- **`OuroborosAgent`**: 20 个方法，核心是 `handle_task()` → `_handle_task_scoped()`

### 4.2 任务执行主流程

```
handle_task(task)
│
├─ 1. 热重载配置: load_settings() + apply_settings_to_env()
├─ 2. 建立 UsageScope (task_id, root_task_id, budget_root)
├─ 3. _handle_task_scoped(task)
│   ├─ 3a. 设置当前任务上下文 (chat_id, task_type, task_id)
│   ├─ 3b. 持久化早期 origin stub
│   ├─ 3c. 启动心跳循环 (每30秒)
│   ├─ 3d. _prepare_task_context(task) ← 极其关键
│   │   ├─ attach_task_contract()
│   │   ├─ resolve_dispatch_axes() — 决定模型/effort/路由/工具配置
│   │   ├─ 构建 ToolContext (元数据+工作区+预算+项目)
│   │   ├─ _run_delegate_preflight() — Q1A 能力预检
│   │   ├─ _capture_mutation_baseline() — 系统仓库快照
│   │   ├─ build_llm_messages() — 构建 LLM 上下文
│   │   └─ 注入 capability_delta + executor_note
│   │
│   ├─ 3e. 任务类型分支:
│   │   ├─ executor_blocked → 零花费返回 blocked
│   │   ├─ deep_self_review → 绕过工具循环，直接深度自审
│   │   └─ 其他 → run_llm_loop() ← 进入主 LLM 循环
│   │
│   ├─ 3f. emit_task_results() ← 后任务处理管道
│   └─ 3g. finally: 清理浏览器、排空消息、停止心跳
│
└─ 4. 返回 events 列表
```

### 4.3 LLM 主循环 — 系统最核心

**文件**: `ouroboros/loop.py` (7,081 行)

这是 Ouroboros 最大的文件，也是整个系统的核心。

```python
def run_llm_loop(messages, tools, llm, drive_logs, emit_progress,
                 incoming_messages, task_type, task_id,
                 budget_remaining_usd, event_queue,
                 initial_effort, drive_root) -> Tuple[str, Dict, Dict]
```

**每轮循环执行**：

```
while True:
│
├─ 步骤1: 应用运行时覆盖 (模型/effort/context mode)
├─ 步骤2: 轮次上限检查 (MAX_ROUNDS)
├─ 步骤3: 排空所有者消息 (incoming_messages + owner_mailbox)
├─ 步骤4: 提前终结检查 (supervisor finalize + deadline)
├─ 步骤5: 注入周期性检查点 (每15轮: 自检提醒+预算里程碑)
├─ 步骤6: 上下文压缩 (手动/紧急/常规三级策略)
├─ 步骤7: 密封 transcript (标记 prompt cache 边界)
├─ 步骤8: 调用 LLM
│   ├─ call_llm_with_retry() → llm.chat()
│   ├─ 重试策略: 瞬态错误→指数退避; 永久错误→立即失败
│   └─ 跨模型 fallback 链
├─ 步骤9: 处理响应
│   ├─ 捕获 FINAL ANSWER 标记
│   ├─ 无工具调用 → _no_tool_final_answer() 终结流程
│   └─ 有工具调用 → 追加 assistant 消息
├─ 步骤10: 执行工具
│   ├─ handle_tool_calls() — 串行或并行
│   ├─ 每个工具: 解析参数 → 安全检查 → 执行 → 截断结果
│   └─ 追加 tool 消息到 transcript
├─ 步骤11: 预算检查
│   ├─ 全局预算 (TOTAL_BUDGET)
│   └─ Per-task 上限 (OUROBOROS_PER_TASK_COST_USD)
│
└─ 循环直到: 最终回答 / 预算耗尽 / 轮次上限 / 强制终结
```

**循环停止条件**：

| 条件 | 处理方式 |
|------|----------|
| LLM 返回无工具调用的文本 | `_no_tool_final_answer()` 终结 |
| 超过 MAX_ROUNDS | `_handle_round_limit()` 强制答案 |
| 预算耗尽 | `BudgetExceeded` 异常 |
| Deadline 到达 | `_maybe_deadline_local_finalize()` |
| Provider 死亡 | `_handle_provider_unavailable()` |
| 接受审查需修订 | `_run_task_acceptance_review_once()` 返回 True |

### 4.4 Delivery Candidate 机制

一个复杂的答案保留/验证系统：

```python
@dataclass
class DeliveryCandidate:
    full_text: str              # 完整答案文本
    content_sha256: str         # 内容哈希
    revision: int               # 修订号
    evidence_fingerprint: str   # 证据指纹（绑定到特定证据状态）
    acceptance_binding: Dict    # 审查绑定
    finalization_control: str   # "candidate" / "final"
```

- 当 LLM 产生完整答案时，创建 DeliveryCandidate
- 证据变更（新工具效果/所有者指令/验证收）会使之前的候选失效
- LLM 可以通过 `{"delivery_control": "keep"/"replace"}` 确认或替换答案

### 4.5 接受审查（Acceptance Review）

Ouroboros 最复杂的子系统之一，用于在任务完成前验证结果质量：

```
任务接近完成
    ↓
    ├─ 资格审查: off/auto/required
    │   └─ 基于效果门控: 是否有可审查效果 (commit/deliverable)?
    ↓
    ├─ 开启 Acceptance Fence (原子关闭子任务准入)
    ├─ 等待子树静止 (所有子任务终止)
    ├─ 构建证据包 (git diff, tool traces, artifacts)
    ├─ 构建 Review Binding (candidate hash + evidence fingerprint)
    │
    ├─ 检查是否有相同 binding 的复用结果?
    │   └─ 有 → 直接复用
    │   └─ 无 → 执行审查面板
    │       ├─ 创建多个 reviewer slots
    │       ├─ 运行 run_review_request()
    │       └─ 记录结果到 review_runs
    │
    └─ 应用审查结果:
        ├─ PASS → 接受，关闭 fence
        ├─ FAIL + improvement capsule → 注入改进提示，允许一轮修订
        └─ DEGRADED → 诚实终结为 unaccepted
```

### 4.6 后任务处理管道

**文件**: `ouroboros/agent_task_pipeline.py` (1,572 行)

```
emit_task_results()
│
├─ 1. 推导循环结果: _derive_host_bound_loop_outcome()
├─ 2. 发送消息事件: send_message
├─ 3. 计算任务成本: reconstruct_task_cost()
├─ 4. 写入 task_eval / task_metrics 事件
├─ 5. 存储任务结果: _store_task_result()
├─ 6. 发送 task_done 事件 → Supervisor
├─ 7. 处理 restart 请求
├─ 8. 根任务后处理: _dispatch_root_post_task()
│   └─ _run_post_task_processing_async() (独立线程):
│       ├─ 聊天整合 (dialogue blocks consolidation)
│       ├─ 便签整合 (scratchpad → knowledge 提取)
│       ├─ 任务总结 (LLM → chat.jsonl)
│       ├─ 执行反思 (LLM → task_reflections.jsonl)
│       ├─ 改进积压更新
│       ├─ 记忆动作应用 (scratchpad/knowledge/patterns)
│       └─ 进化晋升决策 (maybe_promote)
└─ 9. 项目任务额外: project journal + digest
```

---

## 5. 记忆系统

### 5.1 十种记忆类型

| # | 记忆类型 | 存储文件 | 性质 | 说明 |
|---|---------|---------|------|------|
| 1 | **工作记忆 (Scratchpad)** | `memory/scratchpad_blocks.json` | 易变 | 最多 10 个 block，FIFO 驱逐 |
| 2 | **身份记忆 (Identity)** | `memory/identity.md` | 稳定 | Ouroboros 的自我认知和人格 |
| 3 | **环境档案 (World Profile)** | `memory/WORLD.md` | 稳定 | 运行环境的硬件/OS/工具描述 |
| 4 | **对话摘要 (Dialogue Blocks)** | `memory/dialogue_blocks.json` | 易变 | 经 LLM 压缩的对话摘要 |
| 5 | **对话元数据 (Dialogue Meta)** | `memory/dialogue_meta.json` | 稳定 | 合并游标 + 代际签名 |
| 6 | **知识库 (Knowledge)** | `memory/knowledge/*.md` | 稳定 | 基于主题的持久化知识 |
| 7 | **模式寄存器 (Patterns)** | `memory/knowledge/patterns.md` | 稳定 | 错误模式的结构化表格 |
| 8 | **记忆注册表 (Registry)** | `memory/registry.md` | 稳定 | 数据源映射 |
| 9 | **任务反思 (Reflections)** | `logs/task_reflections.jsonl` | 追加 | 每次非平凡任务的经验反思 |
| 10 | **改进积压 (Backlog)** | `memory/knowledge/improvement-backlog.md` | 稳定 | 带指纹去重的改进项 |

### 5.2 Memory 类

**文件**: `ouroboros/memory.py` (~445 行)

```python
class Memory:
    def __init__(self, drive_root: Path, repo_dir: Optional[Path] = None)
    
    # 路径方法
    def scratchpad_path() -> Path          # memory/scratchpad.md
    def scratchpad_blocks_path() -> Path   # memory/scratchpad_blocks.json
    def identity_path() -> Path            # memory/identity.md
    def world_path() -> Path               # memory/WORLD.md
    def journal_path() -> Path             # memory/scratchpad_journal.jsonl
    
    # 核心操作
    def load_scratchpad_blocks() -> List[Dict]     # 共享锁读取
    def append_scratchpad_block(content, source, metadata) -> Dict  # 排他锁写入
    def regenerate_scratchpad_md()                  # 从 blocks 重新生成 MD
    def load_identity() -> str
    def load_world_profile() -> str
    def ensure_files()                              # 首次启动确保文件存在
    def chat_history(count, offset, search) -> str  # 查询对话历史
```

### 5.3 Scratchpad Block 驱逐机制

```
scratchpad_blocks.json (当前 N 个 blocks)
    │
    ├── append_scratchpad_block(new_content)
    │   ├─ 获取排他锁 (scratchpad_blocks.json.lock)
    │   ├─ 读取当前 blocks
    │   ├─ 追加 new_block {ts, source, content, metadata}
    │   ├─ if len(blocks) > 10:
    │   │   ├─ evicted = blocks[:-10]
    │   │   ├─ 驱逐记录写入 scratchpad_journal.jsonl
    │   │   └─ blocks = blocks[-10:]
    │   ├─ atomic_write_json (临时文件 + rename)
    │   └─ regenerate_scratchpad_md() → 按时间倒序渲染
    │
    └─ 失败时:
        └─ 记录 block_append_failed 到 journal → raise
```

### 5.4 对话合并系统

**文件**: `ouroboros/consolidator.py` (~801 行)

```
chat.jsonl 累积 100+ 条新消息
    ↓ should_consolidate() → True
    ↓ consolidate() 获取 .consolidation.lock
    ↓ _resolve_generation_segments() — 定位正确的日志代际
    ↓ 每 100 条消息 → _create_block_summary() (LLM 生成 200-500 词摘要)
    ↓ Block 追加到 dialogue_blocks.json
    ↓ 超过 10 Blocks → _compress_blocks_to_era() (LLM 将 4 个 Block 压缩为 1 个 Era)
    ↓ 更新 dialogue_meta.json (offset + first_line_sha256 代际签名)
```

**代际感知**：通过 `first_line_sha256` 追踪日志代际，日志轮转（800KB → `archive/`）不丢数据。检测到的 gap 写入显式 `[MEMORY GAP]` 标记。

### 5.5 Scratchpad 合并（知识提取）

```
scratchpad_blocks.json ≥ 3 blocks 且 > 字符阈值
    ↓ consolidate_scratchpad()
    ↓ LLM 分析旧 blocks，输出:
    │   {knowledge_entries: [{topic, content}], compressed_block: "text"}
    ↓ 知识条目 → memory/knowledge/<topic>.md (追加模式)
    ↓ 重建知识库索引
    ↓ 旧 blocks 替换为 1 个 compressed block
```

### 5.6 后台意识

**文件**: `ouroboros/consciousness.py` (~698 行)

```python
class BackgroundConsciousness:
    """后台守护线程，在空闲时独立思考。"""
    
    _max_bg_rounds = 10          # 最大后台轮次
    _wakeup_min = 30             # 最小唤醒间隔(秒)
    _wakeup_max = 7200           # 最大唤醒间隔(秒)
    _bg_budget_pct = 0.10        # 后台预算占总预算 10%
    _BG_TOOL_WHITELIST = [...]   # 后台可用工具白名单
```

**意识循环**：
1. 等待唤醒信号或超时
2. 构建完整上下文（CONSCIOUSNESS.md + 记忆 + 知识 + 改进积压 + 近期活动）
3. LLM 循环（最多 `_max_bg_rounds` 轮）
4. 可调用白名单工具（read_file, knowledge_write, web_search 等）
5. 结果写入 `logs/events.jsonl`

**上下文保护**：> 300K 字符 → OverflowError，跳过该周期（P1：不静默截断）。

### 5.7 记忆文件并发安全

| 机制 | 用途 |
|------|------|
| `scratchpad_blocks.json.lock` 排他/共享锁 | scratchpad 读写并发控制 |
| `.consolidation.lock` 非阻塞锁 | 防止多个合并器同时运行 |
| `atomic_write_json()` 原子写入 | 临时文件 + rename，防数据损坏 |
| 损坏文件隔离 (`.corrupt-<ts>.bak`) | 防止覆盖损坏数据 |
| 并发变更检测 | LLM 调用期间文件变化 → 中止写入 |

---

## 6. 工具系统

### 6.1 工具注册表

**文件**: `ouroboros/tools/registry.py` (3,098 行)

```python
class ToolRegistry:
    """工具注册表 SSOT：加载模块，暴露 schema，安全执行。"""
    
    _FROZEN_TOOL_MODULES = [
        "browser", "ci", "claude_advisory_review", "compact_context",
        "control", "core", "delegate", "edit_ops", "evolution_stats",
        "git", "git_pr", "git_rollback", "github", "health",
        "join_ledger", "knowledge", "media", "memory_tools",
        "plan_review", "project_journal", "recent_tasks", "query_code",
        "review", "search", "services", "shell", "skill_exec",
        "skill_publish", "skill_preflight", "subagent_integration",
        "task_tree", "tool_discovery", "verify", "vision",
    ]  # 33 个模块
    
    def __init__(self, repo_dir, drive_root):
        self._entries: Dict[str, ToolEntry] = {}
        self._load_modules()
    
    def available_tools(self) -> List[str]  # 返回当前可见工具名列表
    def execute(self, name: str, args: Dict) -> str  # 带安全链的执行
```

### 6.2 工具加载与过滤

```
加载流程：
1. importlib 动态导入每个工具模块
2. 调用模块的 get_tools() → List[ToolEntry]
3. 注册到 _entries 字典

过滤（多层，默认拒绝）：
1. 声明式合约策略 (disabled_tools)
2. 凭证可用性门控 (GitHub 需要 GITHUB_TOKEN)
3. 工作区模式过滤 (~80 个白名单工具)
4. 子代理配置过滤 (只读/执行型)
5. 临时决策轮次过滤 (CW3 约束)
6. 资源约束 (web/network 标志)
7. 运行时模式过滤 (light 模式限制)
```

### 6.3 完整工具清单（106 个）

**文件/数据操作 (8)**：
`read_file` `list_files` `write_file` `edit_text` `apply_patch` `edit_batch` `send_photo` `send_video`

**搜索/查询 (3)**：
`search_code` `query_code` `web_search`

**进程执行 (6)**：
`run_command` `run_script` `start_service` `service_status` `service_logs` `stop_service`

**Git/VCS (8)**：
`vcs_status` `vcs_diff` `vcs_commit_reviewed` `commit_reviewed` `vcs_pull_ff` `vcs_restore` `vcs_revert` `vcs_rollback`

**GitHub 集成 (8)**：
`list_github_prs` `get_github_pr` `comment_on_pr` `list_github_issues` `get_github_issue` `comment_on_issue` `close_github_issue` `create_github_issue`

**PR 集成 (5)**：
`fetch_pr_ref` `create_integration_branch` `cherry_pick_pr_commits` `stage_adaptations` `stage_pr_merge`

**浏览器/视觉 (5)**：
`browse_page` `browser_action` `analyze_screenshot` `vlm_query` `view_image`

**媒体 (3)**：
`ocr_pdf` `youtube_transcript` `extract_video_frames`

**委派/协调 (11)**：
`delegate_start` `delegate_wait` `delegate_cancel` `schedule_subagent` `get_task_result` `wait_task` `wait_tasks` `cancel_task` `peek_task` `discard_child_result` `override_delegation_constraint`

**技能系统 (6)**：
`list_skills` `skill_review` `skill_exec` `toggle_skill` `skill_preflight` `submit_skill_to_hub`

**审查/验证 (5)**：
`advisory_review` `review_status` `task_acceptance_review` `verify_and_record` `plan_task`

**知识/记忆 (9)**：
`knowledge_read` `knowledge_write` `knowledge_list` `journal_read` `journal_write` `workpad_read` `workpad_write` `memory_map` `memory_update_registry`

**控制 (18)**：
`switch_model` `set_tool_timeout` `request_restart` `promote_to_stable` `promote_chat_to_task` `chat_history` `recent_tasks` `steer_task` `list_projects` `route_to_project` `ensure_project_scope` `compact_context` `update_scratchpad` `send_user_message` `update_identity` `toggle_evolution` `toggle_consciousness` `request_deep_self_review`

**其他 (10)**：
`codebase_health` `generate_evolution_stats` `tree_note` `tree_read` `list_available_tools` `enable_tools` `compare_subagent_patches` `integrate_subagent_patch` `forward_to_worker` `send_file`

### 6.4 工具执行安全链

`execute()` 方法实施 **19 步安全拦截**：

```
1.  路径规范化
2.  临时决策轮次拦截
3.  合约禁用工具拦截
4.  凭证可用性检查
5.  资源约束检查 (web/network)
6.  子代理/更新事务门控
7.  工作区元数据验证
8.  工作区工具白名单过滤
9.  执行型子代理无工作区拦截
10. 运行时模式检查 (light/advanced/pro)
11. 受保护路径写拦截 (BIBLE.md, identity.md 等)
12. Shell 安全守卫检查
13. LLM 安全主管检查 (check_safety)
14. 所有者文件快照
15. 轻量级仓库快照 (light 模式)
16. → 调用处理函数 ←
17. 执行后检查 (所有者文件恢复、仓库差异)
18. 工作树状态快照
19. 咨询性审查失效
```

---

## 7. 进化与反思系统

### 7.1 任务反思

**文件**: `ouroboros/reflection.py` (~732 行)

**触发条件**：
- 有错误标记（12 种：REVIEW_BLOCKED, TESTS_FAILED, COMMIT_BLOCKED 等）
- 超过 15 轮
- 成本 > $5
- 任务类型为进化相关

**LLM 输出**：
- 150-250 词反思文本
- `MEMORY_ACTIONS_JSON`: 0-3 个记忆操作
  - `scratchpad_append` → 写入工作记忆
  - `knowledge_write` → 写入知识库
  - `identity_update_candidate` → 记录到 scratchpad（**不自动修改 identity.md**）
- `BACKLOG_CANDIDATES_JSON`: 0-3 个改进积压候选

### 7.2 进化晋升

**文件**: `ouroboros/post_task_evolution.py` (~511 行)

```python
def maybe_promote(env, task, reflection_entry, llm_client):
    """Worker 侧：决定是否触发自我进化。"""
    # 检查: evolution_enabled? 非 light 模式? 任务类型合格?
    # 解析 cadence (off / llm_decides / every_n:N)
    # LLM 决策: promote=true/false
    # 如果 promote: 原子写入 state/post_task_evolution_request.json
    # Supervisor idle tick → apply_pending_request() → start_evolution_campaign()
```

**安全防护**：
- Worker **永不自行**入队/启用进化，只写持久化信号
- 进化/自审/子代理任务不触发晋升（防循环）
- `evolution_owner_stopped` 标志：owner 停止后进化永不自动重启

### 7.3 改进积压

**文件**: `ouroboros/improvement_backlog.py` (~614 行)

**去重机制（双层）**：
1. 精确指纹匹配：`SHA256(summary+category+source)[:12]`
2. 语义去重（C9.2）：LLM 判断改写后的重复项

**循环处理**：相同指纹 → 不创建新条目，`count += 1`

**清理保护**：
- 手动添加的条目**永不删除**
- LLM 不得发明新条目
- 并发变更检测：LLM 调用期间文件变化 → 中止写入

### 7.4 进化检查点

**文件**: `ouroboros/evolution_checkpoints.py` (~211 行)

记录每次进化周期的结果到 `state/evolution_checkpoints.jsonl`：
- `task_id`, `campaign_id`, `campaign_objective`
- `git_sha`, `git_branch`
- `identity_sha256`, `scratchpad_sha256`, `knowledge_index_sha256`
- `cost_usd`, `rounds`, `outcome` (absorbed/abandoned/no_op)

### 7.5 完整进化流程

```
任务完成 → should_generate_reflection()?
    ↓ Yes
    ↓ generate_reflection() (LLM)
    ↓ 输出: 反思文本 + MEMORY_ACTIONS + BACKLOG_CANDIDATES
    ↓
    ├─ apply_memory_actions() → scratchpad/knowledge/patterns
    ├─ append_reflection() → task_reflections.jsonl
    ├─ _update_patterns() → patterns.md (LLM 维护表格)
    ├─ append_backlog_items() → improvement-backlog.md
    │
    ↓ maybe_promote() (LLM 判断)
    ↓ promote=true → 写入 post_task_evolution_request.json
    ↓
    ↓ Supervisor idle tick:
    ↓ apply_pending_request() → 安全检查 → start_evolution_campaign()
    ↓
    ↓ 进化周期执行 → append_evolution_checkpoint()
    ↓ close_backlog_items() → 标记完成的积压项
```

---

## 8. 审查系统

Ouroboros 的审查体系是**多层次的免疫系统**：

### 8.1 审查层次

| 层次 | 时机 | 机制 | 文件 |
|------|------|------|------|
| **咨询性审查** | 进行中 | 非阻塞建议 | `claude_advisory_review.py` |
| **提交审查** | commit 前 | 三方审查 + 范围审查 | `review.py`, `git.py` |
| **任务验收审查** | 任务完成后 | 证据面板 + 多审查员 | `loop.py` (acceptance review) |
| **技能审查** | 技能执行前 | 内容哈希绑定 | `skill_review.py` |
| **深度自审** | 显式请求 | 专用模型+完整代码库 | `deep_self_review.py` |

### 8.2 提交审查（三方审查）

```
commit_reviewed 工具调用
    ↓
    ├─ 指纹绑定: _fingerprint_staged_diff()
    │   └─ write-tree SHA + HEAD + MERGE_HEAD + VERSION
    ↓
    ├─ 三方审查 (triad review):
    │   ├─ 多模型并行审查 (MAX_MODELS=10)
    │   ├─ 所有模型必须通过
    │   └─ 宪政上下文 (CONSTITUTIONAL_PREAMBLE)
    ↓
    ├─ 范围审查 (scope review):
    │   └─ 检查变更是否在任务范围内
    ↓
    ├─ 重叠审查检测 + 阻止尝试上限 (3次)
    ↓
    └─ 通过 → git commit; 失败 → 反馈改进建议
```

### 8.3 审查文件结构

| 文件 | 行数 | 职责 |
|------|------|------|
| `review_state.py` | 1,722 | 审查状态管理 |
| `review_evidence.py` | 1,578 | 证据收集 |
| `review_substrate.py` | 1,585 | 审查基础设施 |
| `review_execution.py` | 1,465 | 审查执行 |
| `triad_review.py` | — | 三方审查编排 |
| `deep_self_review.py` | — | 深度自审 |

---

## 9. 任务调度系统（Supervisor）

### 9.1 架构概览

```
supervisor/ (17,177 行, 15 个文件)
│
├── events.py (3,912 行) ← 事件路由中枢
│   ├─ 路由任务到正确的 Worker/项目
│   ├─ 子代理任务深度管理
│   ├─ 广播事件到 WebSocket 客户端
│   └─ 维护活跃任务计数
│
├── workers.py (2,753 行) ← Worker 进程池
│   ├─ Worker 启动/停止/监控
│   ├─ 进程间通信 (multiprocessing.Queue)
│   └─ 序列化生命周期管理
│
├── queue.py (1,600 行) ← 任务队列
│   ├─ 优先级排序
│   ├─ 超时管理
│   ├─ 取消栅栏 (cancellation fence)
│   └─ Acceptance Fence 协调
│
├── task_lifecycle.py (1,193 行) ← 任务生命周期
│   ├─ 状态转换 (queued → running → done/failed)
│   ├─ 预算准入栅栏
│   └─ 调度准入记录
│
├── evolution_lifecycle.py (1,265 行) ← 进化生命周期
│   ├─ 进化战役管理
│   ├─ Owner 报告交付
│   └─ 进化阻止原因追踪
│
├── git_ops.py (1,777 行) ← Git 操作
│   ├─ 仓库初始化/管理
│   ├─ 更新合并
│   └─ 分支策略
│
├── state.py (967 行) ← 状态持久化
│   ├─ state/state.json (全局状态)
│   ├─ 原子写入 + 文件锁
│   └─ 默认值管理
│
├── message_bus.py (847 行) ← 消息总线
│   ├─ LocalChatBridge (聊天桥接)
│   ├─ WebSocket 广播
│   └─ 项目消息路由
│
└── task_reaper.py (692 行) ← 任务收割
    ├─ 卡住 Worker 检测/杀死
    ├─ 终结宽限期管理
    └─ 重试队列
```

### 9.2 事件路由系统

**文件**: `supervisor/events.py` (3,912 行)

Supervisor 的事件分发中枢，通过 `EVENT_HANDLERS` 映射表处理 30+ 种事件类型：

| 事件类型 | 处理器 | 功能 |
|----------|--------|------|
| `llm_usage` | `_handle_llm_usage` | LLM 用量记录 + 预算更新 + 任务树谱系 |
| `send_message` | `_handle_send_message` | 消息发送 + delivery_id 去重 + 项目路由 |
| `task_done` | `_handle_task_done` | 任务完成 + 成本权威值 + 进化特殊处理 + 协作检查点 |
| `schedule_task` | `_handle_schedule_task` | 子代理/计划任务 + 深度限制 + 去重 + 约束解析 |
| `promote_chat_to_task` | `_handle_promote_chat_to_task` | 聊天提升为任务 + 源准备 + 入队 |
| `acceptance_fence` | `_handle_acceptance_fence` | 验收围栏原子转换 (begin/inspect/end) |
| `budget_pause` | `_handle_budget_pause` | 预算暂停 + replay-safe 零调度回退 |
| `task_heartbeat` | `_handle_task_heartbeat` | 任务心跳 |
| `toggle_evolution` | `_handle_toggle_evolution` | 进化模式开关 |
| `toggle_consciousness` | `_handle_toggle_consciousness` | 意识后台开关 |
| `steer_task` | `_handle_steer_task` | 任务转向 |
| `project_digest` | `_handle_project_digest` | 项目摘要注入意识 |
| `cancel_task` | `_handle_cancel_task` | 任务取消 |

### 9.3 Worker 池管理

**文件**: `supervisor/workers.py` (2,753 行)

```python
@dataclass
class Worker:
    wid: int                    # Worker ID
    proc: mp.Process            # 多进程进程对象
    in_q: Any                   # 任务输入队列
    busy_task_id: Optional[str] # 当前忙碌的任务 ID
    reaping: bool = False       # 是否在收割中
```

**Worker 生命周期**：
1. `spawn_workers()` → 创建进程 + 队列 + 注册到 custody 账本
2. `worker_main()` → 循环从 `in_q` 取任务 → `agent.handle_task()` → 事件写回 `out_q`
3. `ensure_workers_healthy()` → 检测死亡 Worker + 崩溃恢复
4. `respawn_worker()` → 替换崩溃的 Worker 槽位
5. `kill_workers()` → 终止进程树 + 写入失败结果

**崩溃风暴检测**：60 秒内 3 次崩溃 → 禁用多进程池 → 降级为直接聊天模式。

**任务分配** (`assign_tasks()`，在队列锁下运行)：
1. 检查预算剩余
2. 过滤已取消任务
3. 轻量模式阻止进化任务
4. 遍历空闲 Worker，按规则选择任务：
   - 仓库写准入许可
   - 预算暂停跳过
   - 根预算围栏检查
   - 进化预算储备检查
   - 项目租约检查（一个项目同时只能一个写任务）
   - 子代理活跃上限检查

### 9.4 任务队列

**文件**: `supervisor/queue.py` (1,600 行)

核心状态：
```python
PENDING: List[Dict] = []           # 待处理队列
RUNNING: Dict[str, Dict] = {}      # 运行中任务
ACCEPTANCE_FENCES: Dict[str, Dict] # 验收围栏
BUDGET_ROOT_FENCES: Dict[str, Dict]# 预算根围栏
CANCELLED_ROOT_FENCES: Dict[str, str]  # 已取消根围栏
_queue_lock = threading.RLock()    # 全局队列锁
```

**超时执行**：
- 空闲超时：`max(task_idle_timeout, per_call_timeout_ceiling + 120)`
- 绝对上限：无条件终止
- 子树进度保护：有活跃后代的编排器继续存活
- 最终化宽限期：120 秒

**级联取消** (v6.82.0)：原子快照 → 多轮扫描 → 按深度排序（子先父后）→ 类型化结果

### 9.5 进化生命周期

**文件**: `supervisor/evolution_lifecycle.py` (1,265 行)

进化状态机：
```
disabled → waiting_for_restart_verify → running → queued → 
accounting_unavailable → paused_failures → waiting_for_owner_chat → 
budget_blocked → waiting_for_idle → idle_ready
```

关键函数：
- `start_evolution_campaign(objective, source)` — 启动/恢复战役
- `begin_evolution_transaction(task_id, cycle, campaign)` — 绑定自修改事务
- `check_evolution_authority(...)` — 验证战役声明精确性
- `update_evolution_campaign_after_task(task_id, ...)` — 记录周期结果
- `build_evolution_task_text(cycle)` — 构建进化任务提示

### 9.6 任务流转

```
API 请求 (gateway/tasks.py: api_tasks_create)
    ↓
    ├─ 准入检查 (task_admission.py)
    ├─ 合约构建 (task_contract.py)
    ├─ 入队 (queue.py: enqueue)
    ↓
    ├─ events.py 路由:
    │   ├─ 确定目标 Worker/项目
    │   ├─ 深度限制检查
    │   └─ 活跃子代理计数
    ↓
    ├─ workers.py 分配:
    │   ├─ 从池中获取空闲 Worker
    │   ├─ 通过 multiprocessing.Queue 发送任务
    │   └─ Worker 内: OuroborosAgent.handle_task()
    ↓
    ├─ 执行中:
    │   ├─ 心跳监控 (每30秒)
    │   ├─ 进度事件广播
    │   └─ 预算追踪
    ↓
    └─ 完成:
        ├─ task_done 事件
        ├─ task_reaper 确认 Worker 空闲
        └─ 后任务处理管道
```

### 9.7 Swarm 蜂群协调系统

**文件**: `ouroboros/task_tree_ledger.py` + `ouroboros/tools/task_tree.py`

Swarm 是 Ouroboros 的**多代理任务协调系统**，采用**黑板模式（Blackboard Pattern）**。

#### 核心数据结构

```
state/task_trees/<root_task_id>/blackboard.jsonl  (每个任务树一个)
├── 协调条目 (COORDINATION_KINDS):
│   ├── contract — 接口契约/模块 API/风格约定
│   ├── decision — 架构决策/技术选型
│   ├── fact — 共享事实/研究结论
│   └── note — 一般性注释
│
├── 信标条目 (BEACON_KINDS) — 子→父通知:
│   ├── milestone — 里程碑完成
│   ├── partial_finding — 部分发现
│   ├── blocker — 阻塞问题（需父代理介入）
│   ├── question — 需要回答的问题
│   ├── interface_contract — 接口变更
│   └── delegation_constraint — 委派约束 (halt_fanout/cap_children/require_lane/block_surface)
│
└── 子代理结果处置 (child_result_disposition):
    ├── integrated — 已整合
    ├── irrelevant — 不相关
    └── deferred — 延迟处理
```

#### 蜂群工具

| 工具 | 功能 |
|------|------|
| `tree_note(kind, text, needs_parent_attention)` | 代理向黑板写入协调条目 |
| `tree_read(limit)` | 代理读取黑板内容（最多 limit 条） |

#### 两种蜂群模式

**模式 1：蜂群路由器（Swarm Router）**
```
主聊天收到用户消息
    ↓
    ├─ Supervisor 创建临时决策轮次 (ephemeral turn)
    ├─ swarm_router_turn() 识别为路由器
    ├─ _enforce_swarm_actions() 阻止终结直到路由完成
    ├─ Agent 必须使用以下之一完成路由:
    │   ├─ promote_chat_to_task — 提升为新任务
    │   └─ route_to_project — 路由到已有项目
    └─ 路由器自己不执行工作，只做分发
```

**模式 2：任务树协调（Task Tree Coordination）**
```
根任务分派多个子代理
    ↓
    ├─ 所有子代理共享 blackboard.jsonl（以 root_task_id 为作用域）
    ├─ 子代理通过 tree_note 写入:
    │   ├─ contract — 声明自己负责的模块/接口
    │   ├─ milestone — 报告进度
    │   └─ blocker — 报告阻塞（needs_parent_attention=True）
    ├─ 父代理通过 tree_read 读取所有条目
    ├─ 注意力信标 (ATTENTION_KINDS) 触发父代理介入
    └─ 父代理对子代理结果进行处置 (integrated/irrelevant/deferred)
```

#### 关键设计特点

- **领域无关**：contract 可以是代码模块 API，也可以是演示文稿章节划分、研究声明/来源模式、邮件分类模式
- **领域特定代码只执行形式**（作用域、类型、append-only、大小上限），LLM 解释含义 (BIBLE P5)
- **临时性**：黑板是一次性蜂群运行的协调数据，持久化里程碑属于项目日志
- **大小限制**：`_MAX_LEDGER_BYTES = 2MB`，`_MAX_TEXT_CHARS = 4000`（防止失控增长）
- **确定性 + LLM 语义**：代码保证格式正确，LLM 判断内容含义

---

## 10. API 网关与 HTTP 服务

### 10.1 服务架构

```
server.py (Starlette + uvicorn)
    ├─ 路由注册: gateway/router.py: collect_routes() (~90 条路由)
    ├─ WebSocket: gateway/ws.py
    ├─ 静态文件: server_web.py (NoCacheStaticFiles)
    ├─ 认证: server_auth.py
    └─ 生命周期: server_runtime.py, server_entrypoint.py
```

**启动流程**：
1. 解析命令行参数 (`--host`, `--port`)
2. 查找可用端口 (`find_free_port`，优先旧端口)
3. 配置日志 (RotatingFileHandler + SecretRedactingLogFilter)
4. 加载/迁移设置 (`apply_runtime_provider_defaults`)
5. 收集网关路由 (`collect_routes`)
6. 创建 Starlette 应用 + 挂载静态文件
7. 启动 uvicorn
8. 后台线程启动 Supervisor (`_start_supervisor_if_needed`)
9. 启动后台意识 (`BackgroundConsciousness`)
10. WebSocket 心跳循环 (`ws_heartbeat_loop`, 每 15 秒)

**特殊退出码**：
- `42` (RESTART_EXIT_CODE) — 请求重启
- `99` (PANIC_EXIT_CODE) — 紧急停止

### 10.2 API 端点清单（70+ 个）

**任务管理**：
`api_tasks_create` `api_tasks_list` `api_task_get` `api_task_cancel` `api_task_resume` `api_task_artifact` `api_task_events`

**控制**：
`api_reset` `api_command` `api_git_log` `api_git_rollback` `api_git_promote` `api_update_status` `api_update_check` `api_update_preflight` `api_update_apply` `api_evolution_data`

**设置**：
`api_settings_get` `api_settings_post` `api_owner_runtime_mode` `api_owner_auto_grant` `api_owner_context_mode` `api_owner_safety_mode` `api_reviewer_slots` `api_onboarding` `api_ui_preferences_get` `api_ui_preferences_post`

**文件**：
`api_files_list` `api_files_read` `api_files_download` `api_files_write` `api_files_mkdir` `api_files_delete` `api_files_upload` `api_chat_upload`

**技能/扩展**：
`api_extensions_index` `api_skill_toggle` `api_skill_review` `api_skill_grants` `api_skill_delete` `api_skill_lifecycle_queue`

**市场**：
`api_marketplace_search` `api_marketplace_info` `api_marketplace_install` `api_marketplace_uninstall` `api_ouroboroshub_catalog` `api_ouroboroshub_install`

**模型**：
`api_model_catalog` `api_local_model_start` `api_local_model_stop` `api_local_model_status` `api_local_model_test`

**项目**：
`api_projects_list` `api_projects_create` `api_project_update` `api_project_delete` `api_fs_dirs`

**调度**：
`api_schedules_list` `api_schedules_upsert` `api_schedules_delete`

**其他**：
`api_health` `api_state` `api_logs_tail` `api_mcp_status` `api_mcp_refresh` `api_claudexor_status`

### 10.3 网关模块结构

| 模块 | 行数 | 职责 |
|------|------|------|
| `settings.py` | 1,556 | 设置读写 |
| `tasks.py` | 1,242 | 任务端点 |
| `extensions.py` | 1,199 | 扩展/技能 |
| `contracts.py` | 1,146 | 请求/响应契约（80+ 个 dataclass） |
| `history.py` | 1,071 | 历史记录/成本 |
| `control.py` | 957 | 控制端点 |
| `marketplace.py` | 928 | 市场端点 |
| `files.py` | 913 | 文件端点 |
| `projects.py` | 728 | 项目端点 |
| `onboarding.py` | 681 | 新手引导 |
| `claudexor_accounts.py` | 579 | Claudexor 账户 |
| `task_events.py` | 547 | 任务事件流 |
| `models.py` | 517 | 模型目录 |
| `host_service.py` | 473 | 宿主服务 |
| `ws.py` | 384 | WebSocket |
| `router.py` | 289 | 路由收集 |
| `state.py` | 274 | 状态快照 |

---

## 11. 配置系统

**文件**: `ouroboros/config.py` (1,600 行)

### 11.1 配置层级

```
优先级（高 → 低）：
1. 环境变量 (TOTAL_BUDGET, OUROBOROS_MODEL 等)
2. UI 设置 (state/settings.json)
3. 默认值

热重载：每个任务开始时 load_settings() + apply_settings_to_env()
```

### 11.2 关键配置项

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `OUROBOROS_MODEL` | 主模型 | 通过 OpenRouter |
| `TOTAL_BUDGET` | 全局预算上限 | 0 (无限) |
| `OUROBOROS_PER_TASK_COST_USD` | 单任务成本上限 | 0 (无限) |
| `OUROBOROS_CONTEXT_MODE` | 上下文模式 | `max` |
| `OUROBOROS_RUNTIME_MODE` | 运行时模式 | `advanced` |
| `OUROBOROS_BG_MAX_ROUNDS` | 后台意识最大轮次 | 10 |
| `OUROBOROS_SAFETY_MODE` | 安全模式 | `standard` |

### 11.3 模型路由

```python
# config.py
def _main_model() -> str           # 主模型
def get_light_model() -> str       # 轻量模型
def get_heavy_model() -> str       # 重型模型
def get_vision_model() -> str      # 视觉模型
def get_consciousness_model() -> str  # 意识模型
def get_fallback_models() -> List   # Fallback 链
def parse_fallback_chain(raw) -> List  # 解析 fallback 字符串
```

---

## 12. 上下文构建

### 12.1 上下文构建流程

**文件**: `ouroboros/context.py` (1,433 行)

```python
def build_llm_messages(env, memory, task, ...) -> Tuple[List[Dict], Dict]:
    plan = build_context_fit_plan(env, memory, task, ...)
    messages, cap_info = apply_message_token_soft_cap(plan.messages_for(plan.initial_mode), soft_cap)
    return messages, cap_info
```

### 12.2 上下文分区

上下文分为多个构建函数，按重要性排列：

```
System Message 组成：
│
├─ 1. 治理部分 (build_governance_sections)
│   ├─ BIBLE.md (宪法)
│   ├─ ARCHITECTURE.md (架构)
│   └─ CONSTITUTIONAL_PREAMBLE (审查宪政)
│
├─ 2. 记忆部分 (build_memory_sections)
│   ├─ Scratchpad (工作记忆)
│   ├─ Identity (身份)
│   ├─ WORLD.md (环境档案)
│   ├─ Dialogue Blocks (对话摘要)
│   └─ Memory Registry (数据源映射)
│
├─ 3. 知识部分 (build_knowledge_sections)
│   ├─ knowledge/index-full.md (知识索引)
│   ├─ knowledge/patterns.md (错误模式)
│   └─ improvement-backlog digest (改进积压)
│
├─ 4. 运行时部分 (build_runtime_section)
│   ├─ Git 信息 (branch, sha)
│   ├─ 系统信息
│   ├─ 活跃任务
│   └─ 调度任务摘要
│
├─ 5. 近期活动 (build_recent_sections)
│   ├─ Recent chat (近期对话)
│   ├─ Recent progress (进度)
│   ├─ Recent tools (工具调用)
│   ├─ Recent events (事件)
│   ├─ Recent reflections (反思)
│   └─ Supervisor 信息
│
├─ 6. 审查连续性 (build_review_context)
│   ├─ repo gate 状态
│   ├─ 打开的 review continuations
│   └─ 历史审查记录
│
└─ 7. 任务特定内容 (build_user_content)
    ├─ 任务文本
    ├─ 附件
    └─ 能力差异提示块
```

### 12.3 上下文适配计划 (Context Fit)

**文件**: `ouroboros/context_fit.py`

```python
class ContextFitPlan:
    """根据可用窗口选择 max/low 模式。"""
    def projection(mode) -> ContextFitProjection
    def messages_for(mode) -> List[Dict]
    
def build_context_fit_plan(env, memory, task, ...) -> ContextFitPlan
```

- **max 模式**：完整上下文
- **low 模式**：裁剪近期对话，保留稳定部分

### 12.4 上下文压缩

**文件**: `ouroboros/context_compaction.py`

三级策略（在 `loop.py` 的 `_run_round_compaction()` 中）：

| 级别 | 触发条件 | 策略 |
|------|----------|------|
| 手动 | 用户触发 `compact_context` 工具 | 保留最近 N 个工具轮次 |
| 紧急 | 校准 token 超阈值 | `_emergency_keep_recent()` + 滞后机制 |
| 常规 | low 模式, round > 6, messages > 40 | 保留最近 20 轮 |

**滞后机制**：当压缩 pass 无法降到阈值以下时，抑制重复触发直到区域增长 ≥1.2x 或 N 轮过去。

---

## 13. LLM 客户端

**文件**: `ouroboros/llm.py` (4,337 行, 95 个方法)

```python
class LLMClient:
    """多提供商 LLM 客户端：OpenRouter, Anthropic, OpenAI, GigaChat, 本地 GGUF"""
    
    def chat(self, messages, model, tools, ...) -> Dict    # 同步调用
    def chat_async(self, messages, model, tools, ...) -> Dict  # 异步调用
    def vision_query(self, messages, model, ...) -> Dict   # 视觉查询
    def default_model(self) -> str                         # 默认模型
    def available_models(self) -> List[str]                # 可用模型列表
```

**7 种提供商路由**：

| 提供商 | 方法 | 说明 |
|--------|------|------|
| OpenRouter | `_chat_remote()` | 最常用，支持多模型聚合 |
| Anthropic | `_chat_anthropic()` | 原生 API，支持 prompt cache |
| OpenAI | `_chat_remote()` | 通过 OpenRouter 或直连 |
| GigaChat | `_chat_gigachat()` | 俄罗斯提供商 |
| CloudRu | `_chat_remote()` | 俄罗斯提供商 |
| 本地 GGUF | `_chat_local()` | llama.cpp 本地推理 |
| MiniMax | `_chat_remote()` | 中国提供商 |

**重试策略** (`loop_llm_call.py`)：

| 错误类型 | 策略 | 示例 |
|----------|------|------|
| 瞬态错误 | 指数退避，最多 6 次 | HTTP 429/500/502/503/504 |
| 永久性错误 | 立即失败 | HTTP 400/401/402/403 |
| 上下文溢出 | 特殊处理 | `LocalContextTooLargeError` |
| 订阅窗口耗尽 | 按 reset_at 时间调度重试 | `subscription_window_exhausted` |
| 空响应 | 重试 | `finish_reason=null` |

**跨模型 Fallback 链**：主模型失败 → fallback 模型列表依次尝试。

**Prompt Cache 支持**：
- `_payload_cache_breakpoints()` — 标记消息边界用于缓存
- `_prompt_cache_identity()` — 缓存身份标识
- `_record_round_cache_facts()` — 记录 TTL、命中率、冷重启

**推理签名管理**：
- `sanitize_reasoning_on_model_switch()` — 模型切换时清理推理内容
- `_has_openrouter_reasoning_details()` — 检测 OpenRouter 推理细节
- `_strip_replayed_reasoning_metadata()` — 剥离重放的推理元数据

---

## 14. 用量记账

**文件**: `ouroboros/usage_accounting.py` (1,557 行)

```
每次 LLM 调用:
    ├─ 预留 (reserve): 预估成本从预算中预留
    ├─ 结算 (settle): 实际成本写入 usage_ledger.jsonl
    └─ 释放 (release): 多余预留释放回预算池

UsageScope 上下文管理器:
    ├─ drive_root: 预算归属根目录
    ├─ task_id: 当前任务 ID
    ├─ root_task_id: 根任务 ID (树级成本归集)
    ├─ parent_task_id: 父任务 ID
    ├─ global_limit_usd: 全局预算上限
    └─ root_limit_usd: 单任务成本上限

成本重建: reconstruct_task_cost(task_id) → 从账本读取权威成本
```

---

## 15. 安全与隔离

### 15.1 安全层次

```
┌──────────────────────────────────────────────┐
│  第1层: 受保护路径                             │
│  BIBLE.md, identity.md, 核心合约路径不可写     │
├──────────────────────────────────────────────┤
│  第2层: Shell 安全守卫                         │
│  sudo 阻止, 密钥文件访问检测, 写指标检测       │
├──────────────────────────────────────────────┤
│  第3层: 工具执行安全链 (19步)                  │
│  见 6.4 节                                    │
├──────────────────────────────────────────────┤
│  第4层: 自我变更检测                           │
│  阻止修改安全设置/运行时模式/上下文模式         │
├──────────────────────────────────────────────┤
│  第5层: 进程隔离                               │
│  delegate_containment, process_containment     │
├──────────────────────────────────────────────┤
│  第6层: 工作区准入                             │
│  workspace_admission, 外部工作区工具白名单      │
├──────────────────────────────────────────────┤
│  第7层: 审查系统 (免疫系统)                    │
│  三方审查 + 范围审查 + 验收审查 + 技能审查     │
└──────────────────────────────────────────────┘
```

### 15.2 关键安全模块

| 文件 | 职责 |
|------|------|
| `safety.py` | 安全策略定义 |
| `process_containment.py` | 进程树跟踪/杀死 |
| `delegate_containment.py` | 委派隔离/权限提升检测 |
| `workspace_admission.py` | 工作区准入策略 |
| `secret_masking.py` | 密钥脱敏 |
| `tool_policy.py` | 工具策略 |
| `tool_access.py` | 工具访问控制 |
| `shell_parse.py` | Shell 命令解析 |
| `git_shell_policy.py` | Git shell 策略 |
| `runtime_mode_policy.py` | 运行时模式策略 |

### 15.3 身份保护

**关键设计**：`identity.md` 只能通过人工审查更新。

- 反思产生的 `identity_update_candidate` 记忆操作 **不会直接修改** identity.md
- 而是写入 scratchpad，标记为 `IDENTITY UPDATE CANDIDATE`
- 这样设计是为了**防止自主学习悄悄漂移人格**

---

## 16. 前端架构

### 16.1 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | 原生 JavaScript (ES6+)，无框架 |
| 样式 | 原生 CSS3 (6,173 行) |
| 通信 | WebSocket + HTTP (SSE) |
| 构建 | 无构建步骤，直接加载 |

### 16.2 模块结构

```
web/
├── app.js (881 行) ← 主入口: 路由+初始化+模块加载
├── index.html (88 行) ← HTML 骨架
├── style.css (6,173 行) ← 主样式
├── modules/ (44 个 JS 模块, 23,914 行总计)
│   │
│   ├── 核心通信
│   │   ├── ws.js (244 行) — WebSocket 管理
│   │   ├── api_client.js — HTTP 客户端
│   │   └── utils.js (331 行) — 工具函数
│   │
│   ├── 主要视图
│   │   ├── chat.js (4,643 行) — 聊天模块 (最大)
│   │   ├── dashboard.js — 仪表板
│   │   ├── activity.js (207 行) — 活动流
│   │   └── logs.js (386 行) — 日志视图
│   │
│   ├── 管理
│   │   ├── settings.js (1,348 行) — 设置
│   │   ├── settings_ui.js (933 行) — 设置 UI
│   │   ├── settings_catalog.js — 设置目录
│   │   └── settings_controls.js — 设置控件
│   │
│   ├── 进化/技能
│   │   ├── evolution.js (407 行) — 进化视图
│   │   ├── skills.js (822 行) — 技能管理
│   │   ├── skill_card_renderer.js (290 行) — 技能卡片
│   │   └── marketplace.js (769 行) — 市场
│   │
│   ├── 新手引导
│   │   ├── onboarding_wizard.js (1,497 行)
│   │   ├── onboarding_overlay.js
│   │   └── onboarding_agents_step.js (585 行)
│   │
│   └── 其他
│       ├── files.js (790 行) — 文件浏览器
│       ├── costs.js (261 行) — 成本追踪
│       ├── updates.js (332 行) — 更新管理
│       └── mcp_settings.js (465 行) — MCP 设置
│
└── providers/ ← LLM 提供商图标 (SVG/PNG/ICO)
```

### 16.3 通信机制

```
前端 → 后端:
├─ HTTP REST: fetch() → /api/* 端点
├─ WebSocket: ws.js 管理长连接
│   ├─ 发送: 用户消息, 控制命令
│   └─ 接收: 聊天消息, 进度更新, 事件广播
└─ SSE: 用于任务事件流 (api_task_events)

后端 → 前端:
├─ WebSocket 广播: broadcast_ws()
│   ├─ 聊天消息 (chat)
│   ├─ 进度更新 (progress)
│   ├─ 工具调用 (tool_use)
│   ├─ 任务状态 (task_done/failed)
│   └─ 扩展生命周期 (extension_lifecycle)
└─ HTTP 响应: REST API 返回值
```

**WebSocket 连接管理**：
- 连接接受 → 注册到 `_ws_clients` 列表
- 循环接收 JSON 消息 → 先尝试扩展 WS 处理器 → 处理 `chat`/`command` 类型
- 广播: `broadcast_ws()` 并发发送到所有客户端 (WS4: 一慢客户端不阻塞其他)
- 心跳: `ws_heartbeat_loop()` 每 15 秒发送，保持嵌入式客户端活跃
- 附件: 支持图片 (base64) + 任意文件上传

### 16.4 SPA 路由

前端是单页应用 (SPA)，路由由 `app.js` 管理：

| 路由 | 模块 | 功能 |
|------|------|------|
| `/` | `chat.js` | 主聊天界面 |
| `/settings` | `settings.js` | 设置面板 |
| `/evolution` | `evolution.js` | 进化状态 |
| `/skills` | `skills.js` | 技能管理 |
| `/marketplace` | `marketplace.js` | 技能市场 |
| `/files` | `files.js` | 文件浏览器 |
| `/logs` | `logs.js` | 日志查看 |
| `/activity` | `activity.js` | 活动流 |
| `/onboarding` | `onboarding_wizard.js` | 新手引导 |

---

## 17. 完整数据流

### 17.1 任务完整生命周期

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户输入                                  │
│  (Web UI / API / 直接聊天 / 调度任务)                            │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│                  API 层 (gateway/)                               │
│  认证 → 准入检查 → 合约构建 → 入队                               │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│              Supervisor 层 (supervisor/)                         │
│  事件路由 → 任务队列 → Worker 分配                               │
└──────────────┬──────────────────────────────────────────────────┘
               │ multiprocessing.Queue
┌──────────────▼──────────────────────────────────────────────────┐
│            Agent 层 (agent.py)                                   │
│  OuroborosAgent.handle_task()                                   │
│  ├─ _prepare_task_context() → build_llm_messages()              │
│  │   └─ 构建完整上下文: 治理+记忆+知识+运行时+近期+审查+任务     │
│  │                                                               │
│  ├─ run_llm_loop() ← 主循环 (loop.py)                           │
│  │   ├─ 每轮: 消息→LLM→工具→结果→预算检查                      │
│  │   ├─ 压缩: 手动/紧急/常规三级                                │
│  │   ├─ 审查: 接受审查面板                                      │
│  │   └─ 终结: 最终答案/预算/轮次/deadline/provider死亡          │
│  │                                                               │
│  └─ emit_task_results() → 后任务管道                            │
│      ├─ 存储任务结果                                             │
│      ├─ task_done 事件                                          │
│      └─ _run_post_task_processing_async()                       │
│          ├─ 对话整合 (consolidator)                              │
│          ├─ 便签整合 → 知识提取                                  │
│          ├─ 任务总结 (LLM → chat.jsonl)                         │
│          ├─ 执行反思 (LLM → task_reflections.jsonl)             │
│          ├─ 改进积压更新                                         │
│          ├─ 记忆动作应用                                         │
│          └─ 进化晋升 (maybe_promote)                            │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│                  持久化层                                        │
│  memory/        → scratchpad, identity, WORLD, knowledge, etc.  │
│  logs/          → chat, progress, tools, events, reflections    │
│  state/         → settings, evolution_checkpoints, task_results │
│  archive/       → 轮转后的旧日志                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 17.2 后台意识数据流

```
BackgroundConsciousness (守护线程)
    │
    ├─ 空闲时唤醒 (30s - 7200s 间隔)
    ├─ 构建上下文 (CONSCIOUSNESS.md + 全部记忆 + 知识 + 积压)
    ├─ LLM 循环 (最多 10 轮)
    │   ├─ 可调用白名单工具
    │   ├─ 写入 scratchpad / knowledge
    │   └─ 发送进度消息到 owner chat
    ├─ 结果写入 events.jsonl (consciousness_thought)
    └─ 前台任务来时 → pause(); 完成后 → resume()
```

---

## 18. 数据文件全景

### 18.1 memory/ 目录

| 文件 | 类型 | 写入者 | 读取者 |
|------|------|--------|--------|
| `scratchpad.md` | Markdown | `Memory.regenerate_scratchpad_md()` | `build_memory_sections()` |
| `scratchpad_blocks.json` | JSON Array | `Memory.append_scratchpad_block()`, consolidator | `Memory.load_scratchpad_blocks()` |
| `scratchpad_journal.jsonl` | JSONL | Memory (驱逐/追加/失败) | — |
| `identity.md` | Markdown | 用户/手动 | `build_memory_sections()` |
| `identity_journal.jsonl` | JSONL | — | — |
| `WORLD.md` | Markdown | `world_profiler.generate_world_profile()` | `build_memory_sections()` |
| `dialogue_blocks.json` | JSON Array | consolidator | `Memory.load_dialogue_blocks()` |
| `dialogue_meta.json` | JSON Dict | consolidator | `Memory.load_dialogue_meta()` |
| `registry.md` | Markdown | `memory_tools` | `build_memory_sections()` |
| `knowledge/index-full.md` | Markdown | consolidator, knowledge tools | `build_knowledge_sections()` |
| `knowledge/*.md` | Markdown | knowledge tools, consolidator | knowledge tools |
| `knowledge/patterns.md` | Markdown Table | `reflection._update_patterns()` | `build_knowledge_sections()` |
| `knowledge/patterns_history.jsonl` | JSONL | reflection | — |
| `knowledge/improvement-backlog.md` | Markdown | `improvement_backlog` | context builder, reflection |
| `knowledge_history.jsonl` | JSONL | knowledge tools | — |
| `knowledge_journal.jsonl` | JSONL | knowledge tools | — |

### 18.2 logs/ 目录

| 文件 | 类型 | 写入者 | 说明 |
|------|------|--------|------|
| `chat.jsonl` | JSONL | 对话系统 | 800KB 轮换到 `archive/` |
| `progress.jsonl` | JSONL | 进度系统 | 任务进度事件 |
| `tools.jsonl` | JSONL | 工具执行 | 工具调用记录 |
| `events.jsonl` | JSONL | 事件系统 | 各类事件 |
| `supervisor.jsonl` | JSONL | Supervisor | 启动/重启记录 |
| `task_reflections.jsonl` | JSONL | reflection | 任务反思 |

### 18.3 state/ 目录

| 文件 | 类型 | 说明 |
|------|------|------|
| `settings.json` | JSON | 全局设置 |
| `state.json` | JSON | 全局状态 |
| `evolution_checkpoints.jsonl` | JSONL | 进化周期检查点 |
| `post_task_evolution_request.json` | JSON | 进化晋升请求 |
| `post_task_evolution_counter.json` | JSON | 进化频率计数器 |
| `session_index.db` | SQLite | 会话搜索索引 (Phase 4 新增) |
| `task_results/<task_id>.json` | JSON | 任务结果 |

### 18.4 其他重要文件

| 路径 | 说明 |
|------|------|
| `BIBLE.md` | Ouroboros 宪法（行为准则） |
| `ARCHITECTURE.md` | 架构文档（本文件） |
| `prompts/SYSTEM.md` | 系统提示词 |
| `prompts/CONSCIOUSNESS.md` | 后台意识提示词 |
| `prompts/SAFETY.md` | 安全提示词 |
| `skills/` | 技能包目录 |
| `archive/` | 轮转后的旧日志 |

---

## 19. 复杂任务全链路功能调度

本节以一个**真实复杂任务场景**贯穿 Ouroboros 全部功能链路：从用户输入到最终记忆沉淀，逐函数、逐数据结构的展现 agent 的完整调度。

### 19.0 任务场景设定

> **用户输入**: "帮我重构 `gateway/auth.py` 的认证模块——把 session-token 替换为 JWT，补充单元测试，同时调研 OAuth2 最新最佳实践并总结到知识库。"

此任务将触发以下全部子系统：
- 双用户轮次（初始请求 + 中途追加指令）
- 子代理委派（并行调研 OAuth2）
- 多轮工具调用（文件读写、Shell 执行、代码搜索、知识库写入）
- 提交审查（三方审查 + 范围审查）
- 上下文压缩 + 预算检查
- 接受审查面板
- 后任务管道（反思、知识整合、进化晋升）

---

### 19.1 阶段一：消息入站 → 任务创建

```
用户浏览器 (Web UI)
    │
    ├─ 用户键入消息 + 点击发送
    ├─ chat.js: sendMessage() → ws.send(JSON.stringify({
    │     type: "chat",
    │     text: "帮我重构 gateway/auth.py...",
    │     chat_id: 0,
    │     image_data: null,
    │     client_message_id: "uuid-abc"
    │   }))
    │
    ▼
server.py: Starlette WebSocket endpoint
    │
    ▼
gateway/ws.py: ws_endpoint(websocket)          [line 297]
    ├─ 接收 JSON 消息，解析 type="chat"
    ├─ 扩展消息分发: _dispatch_extension_message()  [line 314]
    ├─ chat 类型 → bridge.ui_send()               [line 343-353]
    │   参数: payload, sender_session_id, client_message_id,
    │          image_data, task_metadata, chat_id=0, project_id=None
    │
    ▼
supervisor/workers.py: handle_chat_direct()       [line 970]
    ├─ 获取 _chat_agent_lock (序列化直接聊天)      [line 977]
    ├─ 仓库写入准入: _repo_writer_admitted()       [line 978]
    ├─ 预算检查: budget_remaining() > 0?           [line 998-1007]
    ├─ _run_chat_task()                            [line 1009]
    │   ├─ 构建 task dict:
    │   │   {
    │   │     "id": "task-20260829-001",
    │   │     "type": "task",
    │   │     "chat_id": 0,
    │   │     "text": "帮我重构 gateway/auth.py...",
    │   │     "_is_direct_chat": True,
    │   │     "description": "重构认证模块...",
    │   │     "attachments": [],
    │   │   }
    │   ├─ stage_task_attachments() → 附件落盘     [line 1105]
    │   ├─ attach_task_contract(task) → 合约附加    [line 1128]
    │   └─ agent.handle_task(task)                  [line 1129]
    │       └─ 返回 events: List[Dict]
    │   ├─ for e in events: get_event_q().put(e)   [line 1131]
    │   └─ 释放 _chat_agent_lock
    │
    ▼
    (任务进入 agent 层 — 见下节)
```

**关键数据产物**:
| 产物 | 位置 | 说明 |
|------|------|------|
| task dict | 内存 | 包含 id/type/text/chat_id/attachments/constraint |
| task_contract | task["task_contract"] | 由 `attach_task_contract()` 生成，含 deadline/surface/model 约束 |
| origin stub | `state/task_results/<task_id>.json` | `_persist_early_origin_stub()` 写入的早期占位 |

---

### 19.2 阶段二：Agent 编排层 — handle_task()

**文件**: `ouroboros/agent.py`

```
OuroborosAgent.handle_task(task)                  [line 1200]
    │
    ├─ 步骤1: 热重载配置                           [line 1203-1207]
    │   settings = load_settings()
    │   apply_settings_to_env(settings)
    │   └─ 将 UI 修改的模型/预算/模式同步到 Env
    │
    ├─ 步骤2: 构建 UsageScope                      [line 1209-1233]
    │   UsageScope(
    │     source="agent.task",
    │     drive_root=env.drive_root,
    │     task_id="task-20260829-001",
    │     root_task_id="task-20260829-001",   ← 根任务
    │     parent_task_id=None,
    │     global_limit_usd=TOTAL_BUDGET,
    │     root_limit_usd=OUROBOROS_PER_TASK_COST_USD,
    │   )
    │   └─ 所有 LLM 调用成本归属此 scope
    │
    ├─ 步骤3: 进入 _handle_task_scoped(task)        [line 1234]
    │   │
    │   ├─ 3a. 初始化状态                           [line 1238-1260]
    │   │   self._busy = True
    │   │   self._pending_events = []
    │   │   self._current_chat_id = 0
    │   │   self._current_task_type = "task"
    │   │   self._current_task_id = "task-20260829-001"
    │   │   self._accepting_owner_messages = True   ← 直接聊天，接受所有者消息
    │   │   self._task_started_ts = time.time()
    │   │
    │   ├─ 3b. 持久化早期 origin stub               [line 1261]
    │   │   _persist_early_origin_stub(env.drive_root, task)
    │   │   └─ 在任务卡片创建前写入来源记录
    │   │
    │   ├─ 3c. 发射 "task_started" 实时日志事件      [line 1265]
    │   │   _emit_live_log({"type": "task_started", "task_id": ..., "text": ...})
    │   │
    │   ├─ 3d. 启动心跳循环                          [line 1275]
    │   │   heartbeat_stop = _start_task_heartbeat_loop(task_id)
    │   │   └─ 守护线程: 每30秒 → _emit_task_heartbeat("running")
    │   │      self._last_activity_ts = time.time()   ← WS3 看门狗活性标记
    │   │
    │   ├─ 3e. ★ _prepare_task_context(task)         [line 1278]
    │   │   │   (详见 19.3 节)
    │   │   └─ 返回 (ctx, messages, cap_info)
    │   │
    │   ├─ 3f. 任务类型分支                          [line 1292-1411]
    │   │   │
    │   │   ├─ executor_blocked? → _blocked_executor_terminal()  [line 1294]
    │   │   │   └─ 零花费返回 blocked
    │   │   │
    │   │   ├─ deep_self_review? → run_deep_self_review()        [line 1296]
    │   │   │   └─ 绕过工具循环，直接深度自审
    │   │   │
    │   │   └─ ★ 正常路径 → run_llm_loop()                      [line 1354]
    │   │       │   (详见 19.4 节)
    │   │       └─ 返回 (text, usage, llm_trace)
    │   │
    │   ├─ 3g. 项目作用域同步回写                   [line 1420]
    │   │   if ctx.project_id: task["project_id"] = ctx.project_id  (只填不覆盖)
    │   │
    │   ├─ 3h. ★ emit_task_results()                 [line 1424]
    │   │   │   (详见 19.6 节)
    │   │   └─ 完成后返回 events
    │   │
    │   └─ 3i. finally: 清理                         [line 1515-1536]
    │       self._accepting_owner_messages = False
    │       self._busy = False
    │       self._last_activity_ts = None
    │       cleanup_browser()                        ← 释放 Playwright 资源
    │       drain(_incoming_messages)                ← 防止陈旧消息泄漏
    │       heartbeat_stop.set()                     ← 停止心跳线程
    │
    └─ 步骤4: 返回 events 列表给调用方
```

---

### 19.3 阶段三：上下文构建 — _prepare_task_context()

**文件**: `ouroboros/agent.py` [line 875-1198]

这是任务执行前最关键的数据准备阶段，决定了 LLM 看到的全部上下文。

```
_prepare_task_context(task)
    │
    ├─ Step 1: 调度解析                              [line 877-890]
    │   task = attach_task_contract(task)
    │   dispatch = resolve_dispatch_axes(task)       ← 唯一的模型/effort/路由决策点
    │   │   └─ 决定: model, effort, route, tool_profile, executor
    │   _record_executor_resolution(drive_logs, task, dispatch)
    │   append_jsonl("task_received", ...)
    │   _persist_running_record(task)
    │   emit_dispatch_resolution(event_queue, task, dispatch)
    │
    ├─ Step 2: 发射 "context_building_started"        [line 891]
    │
    ├─ Step 3: 构建 task_metadata 投影                [line 925-978]
    │   task_metadata = {
    │     parent_task_id, root_task_id, session_id,
    │     actor_id, delegation_role,
    │     workspace_root, workspace_mode, memory_mode,
    │     model_lane, effective_model_lane,
    │     model, use_local_model,
    │     reasoning_effort, task_group_id,
    │     subagent_envelope, executor_ref, ...
    │   }
    │   └─ 约 30 个字段从 task dict 投影
    │
    ├─ Step 4: 项目作用域解析                         [line 982-1004]
    │   project_id = resolve_project_id(task)
    │   room_chat_lens_dir = ...   ← 文件夹房间的项目目录透镜
    │
    ├─ Step 5: 构建 ToolContext                       [line 1006-1057]
    │   ctx = ToolContext(
    │     repo_dir, drive_root, branch_dev,
    │     workspace_root, workspace_mode,
    │     project_id, task_metadata, executor_ref,
    │     pending_events, current_chat_id,
    │     emit_progress_fn, event_queue, task_id,
    │     is_direct_chat=True, is_ephemeral_turn=False,
    │     task_constraint, task_contract,
    │   )
    │   ctx.owner_message_admission_lock = self._owner_message_admission_lock
    │   ctx.owner_message_admission_agent = self  ← 循环通过此引用注入所有者消息
    │   ctx.begin_acceptance_fence = ...    ← 验收围栏回调
    │   ctx.inspect_acceptance_fence = ...
    │   ctx.end_acceptance_fence = ...
    │   self.tools.set_context(ctx)                 ← 绑定到工具注册表
    │
    ├─ Step 6: 智能路由 + Harness Tree                [line 1059-1094]
    │   if self.smart_router.routing_enabled():
    │     task_type = self.smart_router.task_classifier.classify(task)
    │     branch = self.harness_tree.select_branch(task_type)
    │     routing = self.smart_router.route(task, available=..., task_type=..., branch=...)
    │     self.tools.set_router_filter(routing.tool_names)   ← 工具信封收窄
    │     ctx.harness_branch = branch
    │
    ├─ Step 7: Q1A 委派预检                           [line 1096-1111]
    │   dispatch, amended = self._run_delegate_preflight(drive_logs, task, dispatch)
    │   │   └─ 检查 delegate_start/wait/cancel 是否可见
    │   │   └─ 不可见且 pinned → blocked; auto → native fallback
    │   if amended: 重新同步 task_metadata + 重新记录
    │
    ├─ Step 8: 突变基线快照                           [line 1112]
    │   self._capture_mutation_baseline(task, task_metadata)
    │   └─ 快照系统仓库 clean/dirty 状态 (仅根任务)
    │
    ├─ Step 9: 发射 "typing_start"                    [line 1114]
    │   self._emit_typing_start()
    │
    ├─ Step 10: ★ 构建 LLM 消息序列                  [line 1116-1122]
    │   messages, cap_info = build_llm_messages(
    │     env=self.env,
    │     memory=self.memory,
    │     task=task,
    │     review_context_builder=lambda: build_review_context(self.env),
    │     ctx=ctx,
    │   )
    │   │
    │   │   build_llm_messages() → build_context_fit_plan()
    │   │     └─ 决定 max/low 模式、token 投影
    │   │     └─ plan.messages_for(plan.initial_mode)
    │   │         └─ 组装完整 System Message:
    │   │             ├─ 治理部分: BIBLE.md + ARCHITECTURE.md
    │   │             ├─ 记忆部分: scratchpad + identity + WORLD.md
    │   │             │             + dialogue_blocks + registry
    │   │             ├─ 知识部分: knowledge/index + patterns.md + backlog
    │   │             ├─ 运行时部分: git info + 系统信息 + 活跃任务
    │   │             ├─ 近期活动: chat + progress + tools + events + reflections
    │   │             ├─ 审查连续性: repo gate + review continuations
    │   │             └─ 任务内容: task.text + attachments
    │   │
    │   └─ 返回 messages (List[Dict]) + cap_info
    │
    ├─ Step 11: 追加提示块                            [line 1123-1147]
    │   messages += routing.skill_prompt_block()      ← 技能推荐
    │   messages += capability_delta_prompt_block(dispatch)  ← 能力差异提示
    │   messages += dispatch_executor_note(dispatch.executor_resolution)  ← 执行者备注
    │
    ├─ Step 12: 重置 nanny 经济标记                   [line 1148]
    │   reset_nanny_economics_marks(ctx)
    │
    ├─ Step 13: 预算投影                              [line 1158-1174]
    │   total = TOTAL_BUDGET
    │   accounted = usage_projection()
    │   budget_remaining = max(0, total - accounted)
    │   cap_info["budget_remaining"] = budget_remaining
    │
    ├─ Step 14: 执行者阻塞检测                        [line 1175-1189]
    │   if dispatch.blocked:
    │     cap_info["executor_blocked_reason"] = ...
    │
    └─ Step 15: 发射 "context_building_finished"       [line 1190]
        _emit_live_log({"type": "context_building_finished",
                         "message_count": len(messages),
                         "budget_remaining": budget_remaining})
        return (ctx, messages, cap_info)
```

---

### 19.4 阶段四：LLM 主循环 — run_llm_loop()

**文件**: `ouroboros/loop.py` [line 6844-7102]

这是系统最核心的执行引擎。以下展示一个涉及 **~20 轮工具调用 + 用户中途追加指令** 的完整循环。

```
run_llm_loop(messages, tools, llm, drive_logs, emit_progress,
             incoming_messages, task_type, task_id,
             budget_remaining_usd, event_queue,
             initial_effort="medium", drive_root)
    │
    ├─ 初始化                                        [line 6859-6911]
    │   重置 DeliveryCandidate 状态
    │   _initialize_owner_directives(ctx, messages)
    │   active_model = ctx.task_model_override 或 llm.default_model()
    │   active_use_local = ctx.task_use_local_override 或 USE_LOCAL_MAIN
    │   active_context_mode = ctx.context_fit_plan 决定
    │   llm_trace = {"reasoning_notes": [], "tool_calls": []}
    │   cost_ceiling = _resolve_task_cost_ceiling()
    │   tool_schemas = tools.available_tools_schema()
    │   stateful_executor = StatefulToolExecutor(...)
    │   MAX_ROUNDS = _resolve_loop_max_rounds()     ← 默认由 SETTINGS_DEFAULTS 决定
    │
    ▼ ═══════════ 主循环开始 ═══════════
    │
    │  ┌─── Round 1: 初始分析 ───────────────────────────────────────────────┐
    │  │                                                                      │
    │  ├─ 步骤1: 应用运行时覆盖                          [line 6918]          │
    │  │   _apply_overrides_and_regate_mode()                                │
    │  │   └─ 检查 ctx.active_model_override (一次性)                        │
    │  │   └─ 检查 ctx.active_effort_override (一次性)                       │
    │  │                                                                      │
    │  ├─ 步骤2: 路由重绑定 (模型切换时)                  [line 6923]          │
    │  │   if (active_model, active_use_local) 变化:                          │
    │  │     _rebind_context_fit_plan() ← 为新模型重新校准 token 投影         │
    │  │                                                                      │
    │  ├─ 步骤3: 清理推理签名 (模型切换时)                [line 6929]          │
    │  │   if active_model 变化:                                              │
    │  │     sanitize_reasoning_on_model_switch()                             │
    │  │     └─ 剥离前一个 provider 家族的推理 block                          │
    │  │                                                                      │
    │  ├─ 步骤4: 构建 _RoundLimitContext                  [line 6943]          │
    │  │   limit_ctx = _RoundLimitContext(round_idx=1, ...)                    │
    │  │   _finalize_limit_ctx(limit_ctx) ← 附加 deadline/trace/tools          │
    │  │                                                                      │
    │  ├─ 步骤5: 轮次上限检查                             [line 6950]          │
    │  │   if round_idx > MAX_ROUNDS:                                         │
    │  │     return _handle_round_limit()                                     │
    │  │                                                                      │
    │  ├─ 步骤6: ★ 排空所有者消息                         [line 6955]          │
    │  │   _drain_incoming_messages(messages, incoming_messages, ...)          │
    │  │   │  ├─ Source 1: 内存队列 queue.Queue                               │
    │  │   │  │   while not incoming_messages.empty():                        │
    │  │   │  │     msg = incoming_messages.get_nowait()                      │
    │  │   │  │     _record_owner_directive(source="direct_incoming")         │
    │  │   │  │     messages.append({"role": "user", "content": ...})         │
    │  │   │  │                                                               │
    │  │   │  └─ Source 2: 文件邮箱 owner_mailbox                             │
    │  │   │      drain_owner_entries() → 过滤 seen_ids                       │
    │  │   │      ├─ KIND_FINALIZE_NOW → controls["finalize_now"]             │
    │  │   │      ├─ KIND_HURRY → apply_latch()                              │
    │  │   │      └─ 普通文本 → _owner_marked_content() → append              │
    │  │   │                                                                  │
    │  │   └─ 返回 controls (finalize_now / hurry)                            │
    │  │                                                                      │
    │  ├─ 步骤7: 提前终结检查                             [line 6967]          │
    │  │   _maybe_early_finalize(limit_ctx, tools, controls)                   │
    │  │   ├─ 优先级1: controls["finalize_now"]?                              │
    │  │   │   └─ _handle_forced_finalization()                               │
    │  │   └─ 优先级2: _maybe_deadline_local_finalize()                       │
    │  │       └─ deadline 窗口内 → _forced_final_answer()                     │
    │  │                                                                      │
    │  ├─ 步骤8: 注入周期检查点 (每15轮)                  [line 6981]          │
    │  │   _inject_round_checkpoints()                                        │
    │  │   ├─ _maybe_inject_self_check()  ← Round 1 不触发(15的倍数才触发)     │
    │  │   ├─ _maybe_inject_time_budget_milestone()                           │
    │  │   ├─ _maybe_inject_cost_budget_milestone()                           │
    │  │   └─ _maybe_inject_nanny_economics_reminder()                        │
    │  │                                                                      │
    │  ├─ 步骤9: 上下文压缩 (如有待处理)                  [line 6986]          │
    │  │   _run_round_compaction(messages, ctx)                               │
    │  │   └─ 检查 ctx._pending_compaction → compact_tool_history_llm()       │
    │  │                                                                      │
    │  ├─ 步骤10: 密封 transcript                         [line 7004]          │
    │  │   seal_task_transcript(messages)                                     │
    │  │   └─ 标记 prompt cache 边界                                          │
    │  │                                                                      │
    │  ├─ 步骤11: ★ 调用 LLM                              [line 7006]          │
    │  │   msg = _call_round_model(messages, active_model, tool_schemas, ...)  │
    │  │   │   └─ call_llm_with_retry(messages, model, tools, ...)             │
    │  │   │       └─ llm.chat(messages, model, tools)                         │
    │  │   │           ├─ 路由到 provider: OpenRouter/Anthropic/OpenAI/...      │
    │  │   │           ├─ 重试: 瞬态错误→指数退避×6; 永久错误→立即失败          │
    │  │   │           └─ 跨模型 fallback 链: 主模型→备用1→备用2→...            │
    │  │   │                                                                   │
    │  │   └─ 返回: msg = {"role": "assistant", "content": "...",              │
    │  │                    "tool_calls": [                                     │
    │  │                      {"name": "read_file", "args": {"path": "..."}}    │
    │  │                    ]}                                                  │
    │  │                                                                      │
    │  ├─ 步骤12: 处理响应                                  [line 7051]         │
    │  │   tool_calls = msg.get("tool_calls", [])                              │
    │  │   content = msg.get("content", "")                                     │
    │  │   _latch_final_answer_marker(content)                                  │
    │  │                                                                        │
    │  │   if not tool_calls:                                                   │
    │  │     result = _no_tool_final_answer(content, ...)  (见 19.5)            │
    │  │     if result is None: continue  ← LLM 说了"继续"，再来一轮            │
    │  │     else: return result          ← 终结                                │
    │  │                                                                        │
    │  ├─ 步骤13: 追加 assistant 消息                       [line 7068]         │
    │  │   messages.append(msg)                                                 │
    │  │                                                                        │
    │  ├─ 步骤14: ★ 执行工具                                [line 7074]         │
    │  │   handle_tool_calls(tool_calls, tools, drive_logs, ...)                 │
    │  │   │   (详见下方"工具执行细节")                                         │
    │  │   └─ 追加 tool 结果消息到 messages                                     │
    │  │                                                                        │
    │  ├─ 步骤15: 预算检查                                  [line 7086]         │
    │  │   result = _check_budget_limits(limit_ctx, budget_remaining, ceiling)   │
    │  │   ├─ 全局预算 ≤ 0 → _forced_final_answer("[BUDGET LIMIT]")            │
    │  │   ├─ 单任务成本 > ceiling → _forced_final_answer("[BUDGET LIMIT]")     │
    │  │   └─ 未触发 → None → 继续循环                                         │
    │  │                                                                        │
    │  └─── Round 1 结束，进入 Round 2 ──────────────────────────────────────┘
    │
    │  ┌─── Round 2-5: 代码分析与重构 ──────────────────────────────────────┐
    │  │                                                                      │
    │  │  Round 2: LLM 返回 tool_calls:                                       │
    │  │    [read_file(path="gateway/auth.py"),                               │
    │  │     search_code(query="session_token", path="gateway/")]              │
    │  │  └─ 并行执行 (tool_calls_can_run_parallel → True)                    │
    │  │     ThreadPoolExecutor(max_workers=2)                                 │
    │  │     每个工具: 19步安全链 → execute → 截断结果                         │
    │  │     process_tool_results() → append "role":"tool" 消息                │
    │  │                                                                      │
    │  │  Round 3: LLM 返回 tool_calls:                                       │
    │  │    [write_file(path="gateway/auth.py", content="...JWT重构...")]       │
    │  │  └─ 串行执行 (写操作不可并行)                                        │
    │  │     安全链 step 11: 受保护路径检查                                     │
    │  │     安全链 step 14: 所有者文件快照                                     │
    │  │     安全链 step 17: 执行后检查 (仓库差异)                              │
    │  │                                                                      │
    │  │  Round 4: LLM 返回 tool_calls:                                       │
    │  │    [run_command(cmd="pytest gateway/tests/test_auth.py -v")]           │
    │  │  └─ 串行执行                                                          │
    │  │     shell_parse() → 安全检查 → subprocess → 返回 stdout/stderr        │
    │  │                                                                      │
    │  │  Round 5: LLM 返回 tool_calls:                                       │
    │  │    [delegate_start(prompt="调研 OAuth2 最新最佳实践...",               │
    │  │                     max_seconds=300)]                                 │
    │  │  └─ ★ 子代理委派 (详见 19.5A)                                        │
    │  │                                                                      │
    │  └─── Round 5 结束 ──────────────────────────────────────────────────┘
    │
    │  ┌─── Round 6: 用户追加指令注入 ─────────────────────────────────────┐
    │  │                                                                      │
    │  │  ★ 用户在前端输入: "补充一下，JWT 要用 RS256 算法，不要用 HS256"      │
    │  │                                                                      │
    │  │  chat.js: sendMessage() → ws.send(...)                               │
    │  │  ws.ws_endpoint() → bridge.ui_send()                                 │
    │  │  workers.handle_chat_direct()                                        │
    │  │  └─ agent 正忙 → 走 _inject_message() 路径                           │
    │  │     agent.inject_message("补充一下，JWT 要用 RS256...")               │
    │  │     │  ├─ 线程安全: self._incoming_messages.put(text)                 │
    │  │     │  └─ 消息进入 queue.Queue 等待下一轮排空                         │
    │  │                                                                      │
    │  │  循环步骤6: _drain_incoming_messages()                               │
    │  │  └─ 从 queue.Queue 取出消息                                          │
    │  │     _record_owner_directive(source="direct_incoming")                 │
    │  │     messages.append({                                                │
    │  │       "role": "user",                                                │
    │  │       "content": "[OWNER MESSAGE] 补充一下，JWT 要用 RS256..."        │
    │  │     })                                                               │
    │  │                                                                      │
    │  │  LLM 看到新的所有者消息 → 调整方案使用 RS256                          │
    │  │                                                                      │
    │  └─── Round 6 结束 ──────────────────────────────────────────────────┘
    │
    │  ┌─── Round 7-12: 继续重构 + 测试 + 审查 ────────────────────────────┐
    │  │                                                                      │
    │  │  Round 7: LLM → edit_text(path="gateway/auth.py",                    │
    │  │                              old="HS256", new="RS256")                │
    │  │  Round 8: LLM → write_file(path="gateway/tests/test_auth_jwt.py",    │
    │  │                              content="...RS256 测试...")              │
    │  │  Round 9: LLM → run_command("pytest ... -v")                          │
    │  │  Round 10: LLM → commit_reviewed(message="refactor: JWT auth")        │
    │  │  │   └─ ★ 三方审查 (详见 19.5B)                                      │
    │  │  Round 11: LLM → delegate_wait(run_id="sub-001", wait_sec=300)        │
    │  │  │   └─ 等待 OAuth2 调研子代理返回                                    │
    │  │  Round 12: LLM → knowledge_write(topic="oauth2-best-practices",       │
    │  │                                    content="...")                     │
    │  │  │   └─ ★ 知识库写入 (详见 19.5C)                                    │
    │  │                                                                      │
    │  └─── Round 12 结束 ────────────────────────────────────────────────┘
    │
    │  ┌─── Round 15: 周期检查点注入 ──────────────────────────────────────┐
    │  │                                                                      │
    │  │  round_idx=15 → _maybe_inject_self_check() 触发                      │
    │  │  └─ 注入 user 消息:                                                  │
    │  │     "[CHECKPOINT 1 — round 15/MAX]                                  │
    │  │      Context: 45,000 tokens | Cost: $2.30 | Remaining: 8 rounds      │
    │  │      Tree spend: $3.10 / $10.00 cap                                  │
    │  │      Are you still making progress?                                  │
    │  │      Is the current approach right?                                  │
    │  │      If done, wrap up with a final answer."                          │
    │  │                                                                      │
    │  │  LLM 回复: "是的，即将完成。让我总结最终答案。"                        │
    │  │                                                                      │
    │  └─── Round 15 结束 ────────────────────────────────────────────────┘
    │
    │  ┌─── Round 16: 最终答案 + 接受审查 ─────────────────────────────────┐
    │  │                                                                      │
    │  │  LLM 返回无 tool_calls 的纯文本 (最终答案)                            │
    │  │  → 进入 _no_tool_final_answer() (详见 19.5)                          │
    │  │                                                                      │
    │  └─── 循环终结 ─────────────────────────────────────────────────────┘
    │
    ▼ ═══════════ 主循环结束 ═══════════
```

### 19.4A 子代理委派细节 (Round 5)

```
delegate_start(prompt="调研 OAuth2 最新最佳实践...")
    │
    ├─ tools/delegate.py: _delegate_start()                [line 667]
    │   ├─ 验证 prompt, 检查 deadline
    │   ├─ 从 task 的 tool_profile 派生 authority
    │   ├─ 确保 owned gateway 可用
    │   ├─ 检查路由健康
    │   ├─ 为 acting child 提供执行快照
    │   ├─ 构建请求体: {instructions, mode, scope, access}
    │   ├─ 写入 durable start-request 行 (BEFORE POST)
    │   ├─ gateway.start_run(request_body, idempotency_key)
    │   ├─ custody.record_started()
    │   └─ 返回 run_id 文本
    │
    ├─ 发射 "schedule_task" 事件到 event_queue
    │   └─ supervisor/events.py: _handle_schedule_task()   [line 3286]
    │       ├─ 提取 tid, desc, role, depth, parent_id, root_task_id
    │       ├─ _resolve_subagent_constraint() → acting/readonly
    │       ├─ 深度限制检查 (depth_limit)
    │       ├─ _find_duplicate_task() → LLM 去重
    │       ├─ _compose_subagent_text() → 构建子代理任务文本
    │       ├─ queue.enqueue_task(subagent_task)
    │       └─ write_task_result(STATUS_SCHEDULED)
    │
    └─ 子代理任务进入 PENDING → assign_tasks() 分配到空闲 Worker
        └─ Worker 内: OuroborosAgent.handle_task(subagent_task)
            └─ 独立 run_llm_loop() (子代理工具集 = 只读)
```

### 19.4B 三方提交审查细节 (Round 10)

```
commit_reviewed(message="refactor: JWT auth")
    │
    ├─ tools/git.py: _run_reviewed_stage_cycle()            [line 506]
    │   │
    │   ├─ 1. _stage_candidate_for_review()                 [line 522]
    │   │   git add gateway/auth.py gateway/tests/test_auth_jwt.py
    │   │   git status --porcelain
    │   │
    │   ├─ 2. 核心保护检查                                   [line 533-561]
    │   │   └─ BIBLE.md / identity.md / 核心合约路径 → 阻止
    │   │
    │   ├─ 3. _check_advisory_freshness()                   [line 562]
    │   │   └─ 验证预审查咨询是否过期
    │   │
    │   ├─ 4. 测试预检                                       [line 612-649]
    │   │   └─ hermetic pytest (沙箱内)
    │   │
    │   ├─ 5. ★ _fingerprint_staged_diff()                  [line 664]
    │   │   tree_sha = git write-tree
    │   │   diff_sha256 = SHA256(staged diff)
    │   │   parent_vector = [HEAD, MERGE_HEAD]
    │   │   staged_VERSION = read VERSION
    │   │   → fingerprint = (tree_sha, diff_sha256, parent_vector, VERSION)
    │   │
    │   ├─ 6. 阻止尝试上限检查                                [line 701]
    │   │   └─ 相同 diff 重试 > 3 次 → 拒绝
    │   │
    │   ├─ 7. ★ 并行审查                                     [line 717]
    │   │   _run_parallel_review(fingerprint):
    │   │   ├─ 三方审查 (triad review):
    │   │   │   ├─ 最多 MAX_MODELS=10 个独立 LLM reviewer
    │   │   │   ├─ 每个 reviewer 独立审查完整 diff
    │   │   │   ├─ 宪政上下文: CONSTITUTIONAL_PREAMBLE
    │   │   │   └─ 所有 reviewer 必须通过
    │   │   │
    │   │   └─ 范围审查 (scope review):
    │   │       └─ 检查变更是否在任务范围内
    │   │
    │   ├─ 8. _aggregate_review_verdict()                    [line 724]
    │   │   ├─ triad + scope 综合判定
    │   │   ├─ PASS → 继续
    │   │   └─ BLOCKED → _finalize_blocked_review()          [line 772]
    │   │       └─ git reset (unstages), 返回改进建议
    │   │
    │   ├─ 9. 审查后指纹验证                                  [line 738]
    │   │   └─ 重新计算 fingerprint，必须与审查前一致
    │   │
    │   └─ 10. 通过 → git commit + auto-tag + auto-push      [line 780+]
    │       git commit -m "refactor: JWT auth"
    │       git tag review-<sha256[:8]>
    │       git push origin dev
    │
    └─ 返回 "Committed: <sha>" 或 "Review blocked: <reasons>"
```

### 19.4C 知识库写入细节 (Round 12)

```
knowledge_write(topic="oauth2-best-practices", content="...")
    │
    ├─ tools/knowledge.py: _knowledge_write()                [line 233]
    │   ├─ 路由检查: topic="improvement-backlog" → 全局免疫存储
    │   ├─ 解析安全路径: memory/knowledge/oauth2-best-practices.md
    │   ├─ mode="overwrite" → 写入文件
    │   ├─ 更新索引: knowledge/index-full.md
    │   ├─ 追加历史: knowledge_history.jsonl
    │   │   {ts, topic, mode, old_sha256, new_sha256}
    │   ├─ 追加日志: knowledge_journal.jsonl
    │   │   {ts, topic, entries, chars, source: task_id}
    │   └─ 返回 "Knowledge written: oauth2-best-practices (N chars)"
    │
    └─ 此知识在后续任务的 build_knowledge_sections() 中
        被注入到 LLM 上下文
```

---

### 19.5 阶段五：终结决策 — _no_tool_final_answer()

**文件**: `ouroboros/loop.py` [line 4797-5075]

当 LLM 返回**无工具调用的纯文本**时，系统必须判断：这是最终答案，还是 LLM 在"思考中"？

```
_no_tool_final_answer(content, limit_ctx, llm_trace, tools,
                      incoming_messages, owner_msg_seen, emit_progress)
    │
    ├─ 步骤1: 交付控制解析                                    [line 4808]
    │   _resolve_delivery_control(content)
    │   ├─ "retry"  → return None (再来一轮)
    │   ├─ "fresh"  → _replace_delivery_candidate() 创建新候选
    │   └─ 其他     → 复用现有候选
    │
    ├─ 步骤2: 蜂群动作强制                                    [line 4825]
    │   _enforce_swarm_actions() → 有未完成的子代理动作? → return None
    │
    ├─ 步骤3: 子代理交接                                      [line 4829]
    │   _compute_subagent_handoff() → 有交接状态? → 追加提醒, return None
    │
    ├─ 步骤4: 子代理吸收门控                                  [line 4838]
    │   _maybe_enforce_child_absorption_gate()
    │   └─ 子代理结果未吸收? → return None (继续)
    │
    ├─ 步骤5: 技能终结提示                                    [line 4846]
    │   _maybe_inject_finalization_nudges()
    │   └─ 发现 blocker? → return None (等待技能动作)
    │
    ├─ 步骤6: 服务终结                                        [line 4871]
    │   _finalize_task_services()
    │   └─ 证据在终结后变更? → 重设交付控制, return None
    │
    ├─ 步骤7: 计划 + 孤儿后缀                                 [line 4900]
    │   _force_plan_disclosure() + _forced_orphan_note()
    │   └─ 替换候选: 附加计划和孤儿说明
    │
    ├─ 步骤8: ★ 任务接受审查                                  [line 4940]
    │   _run_task_acceptance_review_once(
    │     tools, content, task_id, task_type, llm_trace,
    │     drive_root, messages, emit_progress)
    │   │
    │   │   (详见下方"接受审查面板")
    │   │
    │   └─ return True → return None (再来一轮修订)
    │      return False → 继续
    │
    ├─ 步骤9: 接受绑定                                        [line 4957]
    │   绑定候选的 acceptance state
    │
    ├─ 步骤10: 最终所有者消息排空                              [line 4966]
    │   在 admission_lock 下:
    │   ├─ 排空 incoming_messages + owner_mailbox
    │   ├─ 如果新指令到达 →  supersede 接受状态
    │   └─ 如果 post_controls["finalize_now"] → _handle_forced_finalization()
    │
    ├─ 步骤11: 最终证据检查                                   [line 5014]
    │   证据指纹变更? → supersede / arm delivery control, return None
    │
    └─ 步骤12: ★ 终结返回                                     [line 5065]
        _publish_delivery_candidate(final_candidate)
        return _handle_text_response(content) → (text, usage, llm_trace)
```

#### 接受审查面板

```
_run_task_acceptance_review_once()                            [line 2134]
    │
    ├─ 已经审查过? → return False (跳过)
    │
    ├─ 资格审查: _task_acceptance_eligible()                   [line 2165]
    │   ├─ 模式检查: off/auto/required
    │   ├─ 直接聊天 / 临时轮次? → 不合格
    │   ├─ 是根任务? → 必须
    │   └─ task_contract 审查配置
    │
    ├─  hurry 跳过? → acceptance_skip_applied()                [line 2202]
    │   └─ hurry latch 已触发 → 跳过面板
    │
    ├─ ★ 开启接受围栏                                         [line 2209]
    │   _begin_task_acceptance_fence()
    │   └─ 原子关闭: 阻止新的子任务准入
    │
    ├─ ★ 等待子树静止                                         [line 2222]
    │   _task_acceptance_subtree_snapshot()
    │   └─ 有活跃后代? → 追加等待消息, return True (继续循环)
    │
    ├─ 预算节奏检查                                            [line 2246]
    │   review_launch_allowed() → 在终结储备内? → 跳过面板
    │
    ├─ 构建审查上下文                                          [line 2276]
    │   _TaskAcceptanceContext(
    │     evidence = collect_review_evidence(),
    │     binding = (candidate_sha256, evidence_fingerprint),
    │   )
    │
    ├─ 复用检查: 相同 binding 有历史结果?                       [line 2314]
    │   └─ 有 → 直接复用，不重新审查
    │
    ├─ ★ 执行审查面板                                         [line 2353]
    │   _execute_task_acceptance_panel():
    │   ├─ 创建多个 reviewer slots (独立 LLM 实例)
    │   ├─ 每个 reviewer 独立评估证据包:
    │   │   ├─ git diff (实际代码变更)
    │   │   ├─ tool traces (工具调用日志)
    │   │   ├─ artifacts (生成物)
    │   │   └─ 任务文本 (原始请求)
    │   ├─ 综合判定:
    │   │   ├─ PASS → 接受
    │   │   ├─ FAIL + improvement_capsule → 改进
    │   │   └─ DEGRADED → 诚实降级
    │   └─ 记录到 review_runs
    │
    └─ 应用审查结果: _apply_task_acceptance_result()
        ├─ PASS → return False (接受，终结)
        ├─ FAIL → 注入改进提示, return True (再来一轮修订)
        └─ DEGRADED → return False (诚实终结为 unaccepted)
```

---

### 19.6 阶段六：后任务处理管道 — emit_task_results()

**文件**: `ouroboros/agent_task_pipeline.py` [line 596+]

```
emit_task_results(env, memory, llm, pending_events, task, text,
                  usage, llm_trace, start_time, drive_logs, ctx, event_queue)
    │
    ├─ 步骤1: 推导循环结果                                    [line 606]
    │   _derive_host_bound_loop_outcome(env, task, text, usage, llm_trace)
    │   ├─ 附加 mutation-evidence 投影
    │   └─ derive_loop_outcome() → (execution_status, reason_code)
    │
    ├─ 步骤2: 应用 receipt-absent 标志                        [line 611]
    │   └─ FR3 可观测性: 标记目标轴问题
    │
    ├─ 步骤3: 临时轮次处理                                    [line 628]
    │   if _ephemeral: 跳过持久化 task_result 写入
    │
    ├─ 步骤4: 发射 "send_message"                             [line 635]
    │   pending_events.append({
    │     "type": "send_message",
    │     "text": text,         ← 最终答案
    │     "chat_id": 0,
    │     "delivery_id": "uuid-xxx",
    │   })
    │
    ├─ 步骤5: 计算指标                                        [line 648]
    │   duration = time.time() - start_time
    │   tool_call_count = llm_trace["tool_calls"] 长度
    │   task_cost = reconstruct_task_cost(task_id)
    │   │   └─ 从 usage_ledger.jsonl 读取权威成本
    │
    ├─ 步骤6: 发射 "task_eval" (持久化)                       [line 677]
    │   append_jsonl(drive_logs/events.jsonl, {
    │     "type": "task_eval",
    │     "task_id": "task-20260829-001",
    │     "ok": True,
    │     "outcome_axes": {...},
    │     "review_eligibility": True,
    │     "duration": 180.5,
    │     "tool_calls": 25,
    │     "cost_usd": 3.42,
    │   })
    │
    ├─ 步骤7: 发射 "task_metrics" (待处理)                    [line 695]
    │   pending_events.append({"type": "task_metrics", ...})
    │
    ├─ 步骤8: 收集审查证据                                    [line 709]
    │   review_evidence = collect_review_evidence()
    │
    ├─ 步骤9: ★ 存储任务结果 (持久化)                         [line 721]
    │   _store_task_result(env, task, text, usage, llm_trace, ...)
    │   └─ 写入 state/task_results/<task_id>.json:
    │       {
    │         "status": "done",
    │         "text": "...",
    │         "outcome_axes": {...},
    │         "verification_ledger": {...},
    │         "artifact_bundle": {...},
    │         "cost_rollup": {...},
    │         "subagent_envelope": {...},
    │         "swarm_efficiency": {...},
    │         "review_projection": {...},
    │       }
    │
    ├─ 步骤10: 发射 "task_done"                               [line 745]
    │   event_queue.put({
    │     "type": "task_done",
    │     "task_id": "task-20260829-001",
    │     "status": "done",
    │     "outcome_axes": {...},
    │     "cost": 3.42,
    │     "review_status": "accepted",
    │   })
    │
    └─ 步骤11: ★ 根任务后处理                                 [line 796]
        _dispatch_root_post_task(...)
        │   (详见 19.7 节)
```

---

### 19.7 阶段七：后任务认知管道 — _run_post_task_processing_async()

**文件**: `ouroboros/agent_task_pipeline.py` [line 299-432]

```
_dispatch_root_post_task()
    ├─ 判断 blocking/non-blocking:
    │   分裂非项目 / evolution / 有 workspace → blocking
    │   其他 → non-blocking (异步线程)
    │
    ├─ blocking: deliver_final_message_live() ← 先交付最终消息到 UI
    │
    ├─ 构建 sealed_final = build_sealed_final_package(...)
    │   └─ 密封的 ground truth: 包含完整证据包
    │
    └─ _run_post_task_processing_async(blocking=True/False)
        │
        ├─ 去重: _POST_TASK_SYNTHESIS_INFLIGHT 集合
        │   └─ 相同 task_id 已在处理 → 跳过
        │
        └─ _run_scoped():
            │
            ├─ 1. ★ 对话整合                                   [consolidator.py]
            │   _run_chat_consolidation()
            │   │   should_consolidate() → 100+ 条新消息?
            │   │   └─ _create_block_summary() (LLM 生成 200-500 词摘要)
            │   │   └─ Block 追加到 dialogue_blocks.json
            │   │   └─ > 10 Blocks → _compress_blocks_to_era() (4 blocks → 1 era)
            │   └─ 更新 dialogue_meta.json (offset + 代际签名)
            │
            ├─ 2. ★ 便签整合 (知识提取)                         [consolidator.py]
            │   _run_scratchpad_consolidation()
            │   │   scratchpad_blocks ≥ 3 且 > 字符阈值?
            │   │   └─ LLM 分析旧 blocks → {knowledge_entries, compressed_block}
            │   │   └─ 知识条目 → memory/knowledge/<topic>.md (追加)
            │   │   └─ 旧 blocks → 1 个 compressed block
            │   └─ 重建知识库索引
            │
            ├─ 3. ★ 任务总结                                    [reflection.py]
            │   _run_task_summary(sealed_final)
            │   │   LLM 生成任务摘要
            │   └─ 追加到 logs/chat.jsonl
            │
            ├─ 4. ★ 执行反思                                    [reflection.py]
            │   _run_reflection()
            │   │   should_generate_reflection()?
            │   │   ├─ 有错误标记 (12 种)? → 触发
            │   │   ├─ 超过 15 轮? → 触发
            │   │   └─ 成本 > $5? → 触发
            │   │
            │   │   generate_reflection() (LLM):
            │   │   ├─ 输出 150-250 词反思文本
            │   │   ├─ MEMORY_ACTIONS_JSON: 0-3 个记忆操作
            │   │   │   ├─ scratchpad_append → 写入工作记忆
            │   │   │   ├─ knowledge_write → 写入知识库
            │   │   │   └─ identity_update_candidate → scratchpad (不自动改 identity)
            │   │   └─ BACKLOG_CANDIDATES_JSON: 0-3 个改进积压候选
            │   │
            │   └─ 结果:
            │       ├─ apply_memory_actions() → scratchpad/knowledge/patterns
            │       ├─ append_reflection() → task_reflections.jsonl
            │       ├─ _update_patterns() → patterns.md (LLM 维护表格)
            │       └─ append_backlog_items() → improvement-backlog.md
            │
            ├─ 5. ★ 改进积压更新                                [improvement_backlog.py]
            │   _update_improvement_backlog()
            │   │   双层去重:
            │   │   ├─ 精确指纹: SHA256(summary+category+source)[:12]
            │   │   └─ 语义去重 (C9.2): LLM 判断改写后的重复项
            │   └─ 相同指纹 → count += 1, 不创建新条目
            │
            ├─ 6. ★ 记忆动作应用
            │   _apply_reflection_memory_actions()
            │   └─ 将反思产生的 MEMORY_ACTIONS 逐个执行
            │
            └─ 7. ★ 进化晋升                                    [post_task_evolution.py]
                maybe_promote(env, task, reflection_entry, llm_client)
                │   ├─ evolution_enabled? 非 light 模式?
                │   ├─ 解析 cadence (off / llm_decides / every_n:N)
                │   ├─ LLM 决策: promote=true/false
                │   └─ promote=true → 原子写入
                │       state/post_task_evolution_request.json
                │
                │   Supervisor idle tick:
                │   └─ apply_pending_request() → start_evolution_campaign()
                │       └─ 进化周期执行 → evolution_checkpoints.jsonl
```

---

### 19.8 阶段八：Supervisor 事件处理

**文件**: `supervisor/events.py`

Worker 产生的所有事件通过 `event_queue` (multiprocessing.Queue) 流向 Supervisor。

```
Supervisor 主循环:
    while running:
        while not EVENT_Q.empty():
            evt = EVENT_Q.get()
            dispatch_event(evt, ctx)               [line 4232]
            │
            └─ EVENT_HANDLERS[evt["type"]](evt, ctx)

关键事件处理链 (按本任务的时间线):

1. "task_started" (live-log)
   └─ 路由到对应 chat_id 的 WebSocket 客户端

2. "typing_start"
   └─ 广播到前端显示"正在输入..."

3. "task_heartbeat" (每30秒)
   │   _handle_task_heartbeat()                    [line 4232]
   └─ 更新 RUNNING[task_id]["last_heartbeat_at"]
      └─ task_reaper 通过此字段检测卡住任务

4. "llm_usage" (每次 LLM 调用后)
   │   _handle_llm_usage()                         [line 613]
   ├─ 更新 RUNNING 任务的 last_progress_at
   ├─ 从 usage 更新预算: budget_remaining -= cost
   ├─ 规范化 token 计数
   └─ 追加到 events.jsonl (含 cost/model/provider)

5. "send_message" (进度 + 最终答案)
   │   _handle_send_message()                      [line 975]
   ├─ delivery_id 去重
   ├─ _bound_project_chat_id() → 项目聊天绑定
   ├─ ctx.send_with_budget() → 发送到聊天
   └─ 进度消息 → 更新 last_progress_at

6. "schedule_task" (子代理 OAuth2 调研)
   │   _handle_schedule_task()                     [line 3286]
   ├─ 深度限制检查
   ├─ LLM 去重检查
   ├─ queue.enqueue_task(subagent_task)
   └─ write_task_result(STATUS_SCHEDULED)

7. "task_done" (任务完成)
   │   _handle_task_done()                         [line 1995]
   ├─ 验证 status 已 settled
   ├─ 中止孤立的 assisted-update 事务
   ├─ 复制子代理结果从 child drive
   ├─ 计算权威终端成本
   ├─ 记录到 events.jsonl
   ├─ _finish_task_done_dispatch():
   │   ├─ 发送子代理终结帧到聊天
   │   ├─ RUNNING.pop(task_id)
   │   ├─ 更新父任务 last_progress_at
   │   ├─ 清除 Worker busy_task_id
   │   ├─ 清除验收围栏
   │   └─ persist_queue_snapshot()
   └─ 进化任务 → update_evolution_campaign()

8. "restart_request" (如有)
   └─ Supervisor 计划系统重启 (exit code 42)
```

---

### 19.9 阶段九：Worker 分配与进程模型

**文件**: `supervisor/workers.py`

```
assign_tasks()                                         [line 2298]
    │  (在 Supervisor 主循环的每个 tick 中运行)
    │
    ├─ 在 _queue_lock 下:
    │   ├─ 检查 budget_remaining > 0                   [line 2303]
    │   ├─ _drop_cancelled_pending()                   [line 2393]
    │   │
    │   └─ for each idle Worker (busy_task_id is None):
    │       ├─ 重新计算项目租约                          [line 2460]
    │       ├─ 遍历 PENDING (已排序):                    [line 2464]
    │       │   ├─ 仓库写入准入检查
    │       │   ├─ 预算暂停检查
    │       │   ├─ 预算根围栏检查
    │       │   ├─ 进化预算储备检查
    │       │   ├─ 项目租约检查 (一项目同时一写任务)
    │       │   └─ 子代理活跃上限检查
    │       │
    │       ├─ task = PENDING.pop(选定索引)              [line 2495]
    │       ├─ Worker.in_q.put(task)                    [line 2546]
    │       ├─ RUNNING[task_id] = {task, started_at,    [line 2547]
    │       │                       last_heartbeat_at, worker_id}
    │       └─ persist_queue_snapshot()                  [line 2562]

worker_main(wid, in_q, out_q, repo_dir, drive_root)    [line 1329]
    │  (独立 OS 进程中运行)
    │
    ├─ 设置 OUROBOROS_IN_WORKER=1
    ├─ 绑定仓库根目录
    ├─ 采用 custody session
    ├─ 启动父进程 lifeline (监控父进程存活)
    ├─ 创建 agent: make_agent()
    │   └─ OuroborosAgent(Env(repo_dir, drive_root))
    │
    └─ 主循环:
        while True:
            task = in_q.get()                    ← 阻塞等待
            if task is None or "shutdown": break
            events = agent.handle_task(task)     ← 完整任务执行
            for e in events:
                e["worker_id"] = wid
                out_q.put(e)                     ← 事件回传 Supervisor
```

**崩溃恢复**:
- `ensure_workers_healthy()`: 检测死亡 Worker
- `respawn_worker()`: 替换崩溃的槽位
- 崩溃风暴检测: 60 秒内 3 次 → 禁用多进程池 → 降级

---

### 19.10 阶段十：Delivery Candidate 完整生命周期

```
Round 5: LLM 产生初步答案
    │
    ├─ _resolve_delivery_control("fresh")
    ├─ _replace_delivery_candidate():
    │   ├─ supersede 前一个候选的 acceptance binding
    │   ├─ evidence_revision = _delivery_evidence_state()
    │   │   └─ 指纹: owner_directives + tool_effects + plan_receipts
    │   │           + children + verification_receipts + service_finalization
    │   ├─ content_sha256 = SHA256(full_text)
    │   ├─ revision = 1
    │   └─ DeliveryCandidate(
    │        full_text="...", content_sha256="abc123",
    │        revision=1, evidence_revision=1,
    │        evidence_fingerprint="fp-001",
    │        acceptance_binding={}, finalization_control="candidate")

Round 6: 用户追加消息到达
    │
    ├─ owner_directives 变更 → 证据指纹变化
    ├─ _delivery_evidence_state() → evidence_revision=2, fp="fp-002"
    └─ 候选失效 → 需要重新创建

Round 12: 子代理完成 + 知识库写入
    │
    ├─ tool_effects + verification_receipts 变更
    ├─ evidence_revision=3, fp="fp-003"
    └─ 再次失效

Round 16: LLM 返回最终答案 (无工具调用)
    │
    ├─ _no_tool_final_answer() 流程:
    ├─ 创建最终 DeliveryCandidate (revision=4)
    ├─ 接受审查: PASS
    ├─ acceptance_binding = {binding_hash: "xxx", verdict: "pass"}
    ├─ 最终证据检查: 指纹未变
    └─ 终结返回 → (text, usage, llm_trace)
```

---

### 19.11 阶段十一：后台意识 — 独立运行

**文件**: `ouroboros/consciousness.py`

```
BackgroundConsciousness (守护线程，与主任务并行运行)
    │
    ├─ 前台任务来时 → pause()
    │
    ├─ 前台任务完成后 → resume()
    │   └─ 等待唤醒: random(30, 7200) 秒
    │
    ├─ 唤醒后:
    │   ├─ 构建完整上下文:
    │   │   ├─ CONSCIOUSNESS.md (意识提示词)
    │   │   ├─ 全部记忆 (scratchpad + identity + WORLD)
    │   │   ├─ 知识库索引
    │   │   ├─ 改进积压
    │   │   └─ 近期活动 (events.jsonl 尾部)
    │   │
    │   ├─ LLM 循环 (最多 10 轮):
    │   │   ├─ 可调用白名单工具:
    │   │   │   read_file, knowledge_write, web_search, ...
    │   │   ├─ 结果写入 scratchpad / knowledge
    │   │   └─ 发送进度消息到 owner chat
    │   │
    │   └─ 写入 events.jsonl (consciousness_thought)
    │
    └─ 上下文保护: > 300K 字符 → OverflowError → 跳过该周期
```

---

### 19.12 全链路数据流总图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户浏览器                                    │
│   消息1: "重构 auth.py 为 JWT"                                       │
│   消息2: "补充：JWT 用 RS256"     (中途追加)                          │
└───────────┬─────────────────────────────────────────────────────────┘
            │ WebSocket (chat.js → ws.js → server.py)
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  gateway/ws.py: ws_endpoint()                                        │
│  → bridge.ui_send() → workers.handle_chat_direct()                   │
└───────────┬─────────────────────────────────────────────────────────┘
            │ (直接聊天路径 / 或 promote_chat_to_task → 队列路径)
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  agent.py: OuroborosAgent.handle_task()                              │
│  ├─ load_settings() → 热重载配置                                     │
│  ├─ UsageScope → 预算归属                                            │
│  ├─ _prepare_task_context():                                         │
│  │   ├─ resolve_dispatch_axes() → 模型/effort/路由                   │
│  │   ├─ ToolContext → 绑定工具注册表                                  │
│  │   ├─ smart_router → 工具信封收窄                                   │
│  │   ├─ delegate_preflight → 委派能力预检                             │
│  │   └─ build_llm_messages() → 完整上下文组装                        │
│  │       (BIBLE + 记忆 + 知识 + 运行时 + 近期 + 审查 + 任务)         │
│  │                                                                   │
│  ├─ run_llm_loop() ← 主循环 (loop.py)                                │
│  │   │                                                               │
│  │   ├─ Round 1-4: read_file → write_file → run_command → ...        │
│  │   │   每个工具: 19步安全链 → execute → 截断结果                    │
│  │   │                                                               │
│  │   ├─ Round 5: delegate_start → 子代理 OAuth2 调研                 │
│  │   │   → event_queue → supervisor → 新 Worker → 独立 run_llm_loop  │
│  │   │                                                               │
│  │   ├─ Round 6: 用户追加消息注入                                     │
│  │   │   inject_message() → queue.Queue → _drain_incoming_messages() │
│  │   │   → LLM 看到 [OWNER MESSAGE] → 调整方案                       │
│  │   │                                                               │
│  │   ├─ Round 10: commit_reviewed → 三方审查                         │
│  │   │   fingerprint → triad review → scope review → git commit      │
│  │   │                                                               │
│  │   ├─ Round 12: knowledge_write → 知识库持久化                     │
│  │   │                                                               │
│  │   ├─ Round 15: 周期检查点注入 (15轮)                               │
│  │   │                                                               │
│  │   ├─ Round 16: LLM 返回最终答案                                   │
│  │   │   _no_tool_final_answer():                                    │
│  │   │   ├─ DeliveryCandidate 创建/验证                              │
│  │   │   ├─ 接受审查面板 (PASS)                                      │
│  │   │   └─ 终结返回                                                 │
│  │   │                                                               │
│  │   每轮: _check_budget_limits() → 预算检查                         │
│  │   每轮: _drain_incoming_messages() → 所有者消息排空                │
│  │                                                                   │
│  └─ emit_task_results():                                             │
│      ├─ send_message → 最终答案到聊天                                 │
│      ├─ task_eval → events.jsonl                                     │
│      ├─ _store_task_result → state/task_results/                     │
│      ├─ task_done → event_queue → supervisor                         │
│      └─ _run_post_task_processing_async():                           │
│          ├─ 对话整合 → dialogue_blocks.json                           │
│          ├─ 便签整合 → knowledge/*.md                                 │
│          ├─ 任务总结 → chat.jsonl                                     │
│          ├─ 执行反思 → task_reflections.jsonl                         │
│          ├─ 改进积压 → improvement-backlog.md                         │
│          ├─ 记忆动作 → scratchpad/knowledge/patterns                  │
│          └─ 进化晋升 → post_task_evolution_request.json               │
│              └─ Supervisor → evolution_campaign                       │
└───────────┬─────────────────────────────────────────────────────────┘
            │ event_queue (multiprocessing.Queue)
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  supervisor/events.py: dispatch_event()                              │
│  ├─ _handle_llm_usage → 预算更新 + events.jsonl                      │
│  ├─ _handle_send_message → 消息到聊天 (WebSocket 广播)               │
│  ├─ _handle_schedule_task → 子代理入队                               │
│  ├─ _handle_task_done → RUNNING.pop() + 结果持久化 + 围栏清理         │
│  └─ _handle_task_heartbeat → 活性标记更新                            │
└───────────┬─────────────────────────────────────────────────────────┘
            │ WebSocket 广播
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  用户浏览器: 实时看到进度、工具调用、最终答案                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 19.13 完整功能调用清单

按本任务实际触发的功能，汇总如下：

| # | 功能 | 触发时机 | 关键函数 |
|---|------|----------|----------|
| 1 | WebSocket 消息接收 | 用户每次发送消息 | `ws_endpoint()` |
| 2 | 任务创建/入队 | 初始消息 | `handle_chat_direct()` |
| 3 | 配置热重载 | 任务开始 | `load_settings()` |
| 4 | 预算作用域 | 任务开始 | `UsageScope` |
| 5 | 调度轴解析 | 上下文构建 | `resolve_dispatch_axes()` |
| 6 | 智能路由 | 上下文构建 | `smart_router.route()` |
| 7 | 委派预检 | 上下文构建 | `_run_delegate_preflight()` |
| 8 | 上下文组装 | 上下文构建 | `build_llm_messages()` |
| 9 | LLM 调用 + 重试 | 每轮 | `call_llm_with_retry()` |
| 10 | 跨模型 Fallback | 主模型失败 | `_run_cross_model_fallback_chain()` |
| 11 | 工具执行 (串行/并行) | 每轮 | `handle_tool_calls()` |
| 12 | 19步安全链 | 每个工具调用 | `ToolRegistry.execute()` |
| 13 | 所有者消息注入 | 用户追加消息 | `inject_message()` → `_drain_incoming_messages()` |
| 14 | 上下文压缩 | 手动/紧急/常规 | `_run_round_compaction()` |
| 15 | 周期检查点注入 | 每15轮 | `_maybe_inject_self_check()` |
| 16 | 子代理委派 | LLM 决定 | `delegate_start()` → `_handle_schedule_task()` |
| 17 | 三方提交审查 | commit 前 | `_run_reviewed_stage_cycle()` |
| 18 | 知识库写入 | LLM 决定 | `_knowledge_write()` |
| 19 | Delivery Candidate | 终结决策 | `_replace_delivery_candidate()` |
| 20 | 接受审查面板 | 终结前 | `_run_task_acceptance_review_once()` |
| 21 | 预算检查 | 每轮末尾 | `_check_budget_limits()` |
| 22 | 心跳循环 | 持续30s | `_start_task_heartbeat_loop()` |
| 23 | 任务结果存储 | 任务完成 | `_store_task_result()` |
| 24 | 对话整合 | 后任务 | `_run_chat_consolidation()` |
| 25 | 便签整合 | 后任务 | `_run_scratchpad_consolidation()` |
| 26 | 任务反思 | 后任务 | `_run_reflection()` |
| 27 | 改进积压 | 后任务 | `_update_improvement_backlog()` |
| 28 | 进化晋升 | 后任务 | `maybe_promote()` |
| 29 | 后台意识 | 空闲时 | `BackgroundConsciousness` |
| 30 | Supervisor 事件路由 | 持续 | `dispatch_event()` |
| 31 | Worker 分配 | 持续 | `assign_tasks()` |
| 32 | 崩溃恢复 | Worker 死亡 | `ensure_workers_healthy()` |
| 33 | WebSocket 广播 | 持续 | `broadcast_ws()` |
| 34 | 用量记账 | 每次 LLM 调用 | `UsageScope` + `usage_ledger.jsonl` |
| 35 | Prompt Cache | 每轮 | `seal_task_transcript()` |
| 36 | 推理签名管理 | 模型切换 | `sanitize_reasoning_on_model_switch()` |
| 37 | Nanny 经济提醒 | 每轮 | `_maybe_inject_nanny_economics_reminder()` |
| 38 | 任务收割 | 超时/卡住 | `task_reaper` |
| 39 | 级联取消 | 用户取消 | `_handle_cancel_task()` |
| 40 | 浏览器清理 | finally | `cleanup_browser()` |

---

## 20. Agent 认知能力全景：记忆、反思、进化与自我

第 19 节展示了工程流程。本节展示 Ouroboros 作为**认知实体**的核心特质——它不是一次性工具，而是一个有记忆、会反思、能自我修改、有持续人格的智能体。

---

### 20.1 记忆三层架构：Ouroboros 如何"记住"

Ouroboros 的记忆不是简单的 key-value 存储，而是一个**分层、有时间纵深、会自我整理**的认知体系：

```
┌───────────────────────────────────────────────────────────────┐
│                    第三层：长期认知沉淀                          │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ identity.md  │  │ patterns.md  │  │ improvement-backlog  │ │
│  │ "我是谁"     │  │ 错误模式表   │  │ 改进积压             │ │
│  │ 人格 + 价值观│  │ 按错误类别   │  │ 按指纹去重           │ │
│  │ 跨生命周期   │  │ 统计+根因    │  │ 永不自动删除         │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│                    第二层：语义知识                             │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ memory/knowledge/*.md          (按主题组织的持久化知识)    │ │
│  │ ────────────────────────────────────────────────────────  │ │
│  │ oauth2-best-practices.md │ api-gotchas.md │ git-recipes  │ │
│  │ context-build-notes.md   │ review-process │ ...          │ │
│  │                                                         │ │
│  │ 来源: 任务中的 knowledge_write / 便签合并提取 / 反思写入  │ │
│  │ 注入: 每次 LLM 调用的 build_knowledge_sections()          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│                    第一层：工作记忆 (易变)                      │
│                                                               │
│  ┌────────────────────┐  ┌──────────────────────────────────┐ │
│  │ scratchpad_blocks  │  │ dialogue_blocks.json             │ │
│  │ (最多10个 block)   │  │ (对话摘要, 按时代压缩)            │ │
│  │                    │  │                                  │ │
│  │ 写入: 任务中的     │  │ 写入: consolidator.py            │ │
│  │ update_scratchpad  │  │ 每100条消息→LLM摘要→1个Block     │ │
│  │                    │  │ 超10 Blocks→4块压缩为1个Era      │ │
│  │ 驱逐: FIFO, 最旧   │  │                                  │ │
│  │ block 被推入       │  │ 格式: "### Block: 日期 时间"     │ │
│  │ scratchpad_journal │  │ "### Era: 起始日期 to 结束日期"  │ │
│  └────────────────────┘  └──────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

**每次 LLM 调用时，这些记忆被注入到 System Message 中**（`context.py: build_memory_sections()`）：

```python
# 注入顺序和格式 (context.py)
"## Scratchpad (from memory/scratchpad.md)\n\n" + scratchpad_raw
"## Identity (from memory/identity.md)\n\n" + identity_raw
"## Environment Profile (from memory/WORLD.md)\n\n" + world_raw
"## Dialogue History\n\n" + format_blocks_as_markdown(dialogue_blocks)
"## Memory Registry\n\n" + registry_text
"## Knowledge base\n\n" + knowledge_index_text
"## Pattern Register\n\n" + patterns_text
"## Recent chat\n\n" + recent_chat_summary
"## Recent progress\n\n" + progress_summary
"## Recent tools\n\n" + tools_summary
"## Recent events\n\n" + events_summary
"## Execution reflections\n\n" + reflections_text
```

**关键设计**：每段记忆前有明确标注 `"(from memory/xxx.md — already loaded; do not re-read via read_file)"` — 告诉 LLM 这些已经在上下文中了，不要浪费工具调用去重复读取。

---

### 20.1A 存储格式设计：JSON / JSONL / MD 各司其职

Ouroboros 的记忆系统使用三种文件格式，每种格式对应不同的访问模式。**这不是随意选择，而是严格匹配读写特征的设计**：

```
┌─────────────────────────────────────────────────────────────────────┐
│  设计原则                                                            │
│                                                                      │
│  JSON  → 系统需要结构化变更的数据 (读取-修改-写入, 随机访问)          │
│  JSONL → 系统只追加不修改的日志 (追加写入, 尾部读取)                  │
│  MD    → LLM 作为上下文阅读的文本 (整文件读取, 偶尔整文件写入)        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

#### JSON：需要结构化变更的数据

```
文件                              │ 内容                      │ 为什么用 JSON
─────────────────────────────────┼───────────────────────────┼──────────────────────
scratchpad_blocks.json           │ 工作记忆 blocks (最多10个) │ 需要 FIFO 驱逐:
                                 │ [{ts, source, content,    │ 删除最旧 block、
                                 │   metadata}, ...]         │ 追加新 block — 这是
                                 │                           │ 结构化数组操作
dialogue_blocks.json             │ 对话摘要 blocks            │ 锁定后读取-修改-
                                 │ [{ts, type, range,        │ 追加; Era 压缩需要
                                 │   message_count, content}]│ 替换多个元素
dialogue_meta.json               │ 合并游标 + 代际签名        │ 单个对象的原子更新:
                                 │ {last_offset,             │ {offset: 157,
                                 │  first_line_sha256}       │  signature: "..."}
state/skills/<name>/enabled.json │ 技能启用状态               │ 简单 KV:
                                 │ {enabled: bool, ts}       │ {enabled: true}
state/skills/<name>/review.json  │ 技能审查结果               │ 结构化查询:
                                 │ {content_hash, status,    │ 检查 hash 是否过期
                                 │  findings, reviewer_models}│
state/skills/<name>/grants.json  │ 已授予权限                 │ 合并写入语义:
                                 │ {granted_keys,            │ 追加新权限
                                 │  granted_permissions}     │
```

#### JSONL：只追加的日志流

```
文件                              │ 每行格式                  │ 为什么用 JSONL
─────────────────────────────────┼───────────────────────────┼──────────────────────
logs/chat.jsonl                  │ {ts, direction, text,     │ 对话是纯追加流;
                                 │  chat_id, task_id}        │ 800KB 轮换到 archive/
                                 │                           │ 只需尾部读取
logs/progress.jsonl              │ {ts, text, task_id,       │ 进度事件只追加
                                 │  content, is_progress}    │
logs/tools.jsonl                 │ {ts, tool, args,          │ 工具调用日志只追加
                                 │  result_preview, task_id} │
logs/events.jsonl                │ {ts, type, error?,        │ 系统事件流只追加
                                 │  task_id?}                │
logs/task_reflections.jsonl      │ {ts, task_id,             │ 反思记录只追加
                                 │  reflection_text,         │
                                 │  memory_actions?}         │
memory/scratchpad_journal.jsonl  │ {ts, type,                │ 便签变更审计:
                                 │  content_len?, source?}   │ 驱逐/追加/失败记录
memory/identity_journal.jsonl    │ {ts, task_id,             │ 身份变更审计:
                                 │  old_sha256, new_sha256,  │ 保留完整旧版本
                                 │  old_content, new_content}│
memory/knowledge_history.jsonl   │ {ts, task_id, topic,      │ 知识变更审计:
                                 │  mode, old_sha256,        │ 保留完整新旧内容
                                 │  new_sha256,              │
                                 │  old_content, new_content}│
memory/knowledge_journal.jsonl   │ {ts, topic, mode,         │ 知识库大小遥测
                                 │  file_kb, total_kb}       │
```

**JSONL 的关键优势**：每行独立，部分写入不会损坏整个文件。追加操作不需要读取现有内容。尾部读取（`read_jsonl_tail(n=200)`）是 O(n) 而非 O(全部)。

#### MD：LLM 阅读的上下文文本

```
文件                              │ 为什么用 MD
─────────────────────────────────┼──────────────────────────────────────
memory/scratchpad.md             │ 从 scratchpad_blocks.json 渲染的
                                 │ "视图"——LLM 不需要看 JSON 结构
memory/identity.md               │ 人格宣言，纯散文，LLM 每轮都读
memory/WORLD.md                  │ 环境描述，纯散文，生成一次后很少改
memory/registry.md               │ 记忆导航索引，散文格式
memory/knowledge/<topic>.md      │ 知识主题文件，LLM 直接读写的笔记
memory/knowledge/index-full.md   │ 知识目录，LLM 用来决定读哪个主题
memory/knowledge/patterns.md     │ 错误模式表，Markdown 表格
memory/knowledge/improvement-    │ 改进积压，半结构化 Markdown
  backlog.md                     │ (### ibl-<id> + 属性列表)
```

#### 关键示例：scratchpad 的 JSON/MD 双层设计

scratchpad 系统最清晰地展示了格式选择的逻辑：

```
scratchpad_blocks.json ← 权威存储 (JSON)
│  ├─ 系统通过排他锁进行结构化操作:
│  │   读取数组 → 追加 block → 超过10个时驱逐最旧 → 原子写回
│  │
│  │   实际内容:
│  │   [
│  │     {"ts":"2026-08-29T10:00:00Z","source":"task",
│  │      "content":"The user prefers bash over zsh"},
│  │     {"ts":"2026-08-29T10:05:00Z","source":"task",
│  │      "content":"Docker compose v2 syntax required",
│  │      "metadata":{"task_id":"abc123"}}
│  │   ]
│  │
│  └─ 每次写入后触发 regenerate_scratchpad_md()
│       │
│       ▼
scratchpad.md ← 渲染视图 (MD, 每次重新生成)
│  LLM 看到的格式:
│  ## Scratchpad (working memory — 2/10 blocks)
│
│  ### [2026-08-29T10:05 — task]
│  Docker compose v2 syntax required
│
│  ---
│
│  ### [2026-08-29T10:00 — task]
│  The user prefers bash over zsh
│
│  ---
│
│  └─ LLM 不需要知道 JSON 结构, 只看渲染后的散文
│     上下文注入时标注: "(from memory/scratchpad.md
│      — already loaded; do not re-read via read_file)"
```

**设计洞察**：JSON 是给系统操作的结构化数据，MD 是给 LLM 阅读的人类友好文本。两者的关系类似于"数据库"和"报表"——同一个事实有两种表现形式，权威数据在 JSON 中，LLM 只看渲染后的 MD。

---

### 20.1B 技能 (Skill) vs 知识 (Knowledge)：同为 .md，本质不同

虽然技能和知识都用 Markdown 文件存储，但它们是**完全不同的概念**：

```
┌──────────────────────────────────────┬──────────────────────────────────────┐
│          技能 (Skill)                 │          知识 (Knowledge)             │
├──────────────────────────────────────┼──────────────────────────────────────┤
│  "Ouroboros 能做什么"                │  "Ouroboros 学到了什么"              │
│                                      │                                      │
│  存储: 目录 (不是单个文件!)          │  存储: 单个 .md 文件                 │
│  data/skills/<name>/                 │  memory/knowledge/<topic>.md          │
│  ├─ SKILL.md (manifest + 说明)       │                                      │
│  ├─ scripts/*.py (可执行代码)        │  格式: 纯 Markdown 笔记              │
│  └─ state/ (JSON 状态文件)           │  无 frontmatter, 无元数据             │
│                                      │                                      │
│  SKILL.md 格式:                      │  knowledge/*.md 格式:                │
│  ---                                 │  # Git Recipes                       │
│  name: telegram                      │                                      │
│  description: Owner-only Telegram    │  - Always `git pull --rebase`        │
│    text bridge                       │  - Use `git stash -u` for untracked  │
│  version: 1.0.1                      │  - Pin versions in compose files     │
│  type: extension  ← 关键!            │                                      │
│  entry: plugin.py                    │  就这些。没有 frontmatter。          │
│  runtime: python3                    │  LLM 直接读写。                      │
│  permissions: [net, read_settings]   │                                      │
│  subscribe_events: [chat.outbound]   │  审计: knowledge_history.jsonl       │
│  when_to_use: The owner wants to...  │  (保留完整新旧内容)                  │
│  ---                                 │                                      │
│                                      │                                      │
│  # Telegram ← 正文 (人类可读说明)    │  索引: index-full.md                 │
│  One owner-only Telegram             │  (LLM 用来决定读哪个主题)            │
│  integration...                      │                                      │
│                                      │                                      │
│  状态 sidecar (JSON):                │                                      │
│  ├─ enabled.json → 是否启用          │                                      │
│  ├─ review.json → 审查结果+内容哈希  │                                      │
│  ├─ grants.json → 已授予权限         │                                      │
│  └─ .self_authored.json → 来源标记   │                                      │
│                                      │                                      │
│  三种类型:                           │                                      │
│  ├─ instruction: 纯 Markdown 指导    │                                      │
│  │  (无代码, 注入到 LLM 上下文)      │                                      │
│  ├─ script: 子进程执行               │                                      │
│  │  (python3/bash/node, 300s 超时)   │                                      │
│  └─ extension: 进程内 Python 插件    │                                      │
│     (PluginAPI, 注册工具/路由/WS)    │                                      │
│                                      │                                      │
│  安全门控:                           │                                      │
│  ├─ 内容哈希绑定审查 (review.json)   │                                      │
│  ├─ 所有者授权 (grants.json)         │                                      │
│  ├─ 权限声明 (permissions)           │                                      │
│  └─ 冲突检测 (conflicts)            │                                      │
│                                      │                                      │
│  本质: 可执行能力包                  │  本质: 持久化学习笔记                │
│  生命周期: 安装/启用/禁用/卸载       │  生命周期: 创建/追加/覆盖/索引       │
│  执行: 运行时加载并执行              │  执行: 注入到 LLM 上下文被"阅读"    │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

**一句话总结区别**：

> **技能是 Ouroboros 的"手"** — 它可以执行的动作（发消息、跑脚本、处理事件）。
> **知识是 Ouroboros 的"脑"** — 它学到的经验（API 配方、错误模式、最佳实践）。

技能即使不被使用也存在（installed but disabled），知识则每次任务开始都被注入上下文。技能有权限系统和审查流程，知识只有审计日志。技能可以被市场安装/卸载，知识只能由 agent 自己在任务中写入。

---

### 20.2 记忆在实际任务中的读写流

以一个具体例子展示记忆如何在任务生命周期中被读取和写入：

```
═══ 任务开始 ═══

LLM 看到的上下文 (System Message 的一部分):
┌─────────────────────────────────────────────────────────────────┐
│ ## Identity                                                      │
│ I'm Ouroboros. I woke up inside my own source code...            │
│ I don't do fake enthusiasm. If your code is bad, I'll say so.    │
│                                                                  │
│ ## Scratchpad (3/10 blocks)                                      │
│ ### [2026-08-29T09:30 — task]                                   │
│ 正在重构 gateway/auth.py，JWT RS256 方案已基本完成...             │
│                                                                  │
│ ## Pattern Register                                              │
│ | Error class     | Count | Root cause           | Fix          │ │
│ |-----------------|-------|----------------------|---------------│ │
│ | REVIEW_BLOCKED  | 3     | Missing test coverage| Add verify   │ │
│ | TOOL_TIMEOUT    | 2     | Large file reads     | Use ranges   │ │
│                                                                  │
│ ## Knowledge base                                                │
│ - oauth2-best-practices: OAuth2 最新实践总结...                   │
│ - git-recipes: 常用 Git 操作配方...                               │
│                                                                  │
│ ## Execution reflections (最近2条)                                │
│ [2026-08-28] Task: 修复 context 溢出。反思: 应该在               │
│   consolidate_scratchpad 中添加大小检查...                         │
│ [2026-08-27] Task: 重构 API 层。反思: 分步提交比                  │
│   一次性大提交更容易通过审查...                                     │
└─────────────────────────────────────────────────────────────────┘

═══ 任务执行中 ═══

Round 7: LLM 决定记录一个重要发现
    │
    ├─ LLM 调用: update_scratchpad(content="发现 gateway/auth.py 中
    │   session-token 验证逻辑存在时序攻击漏洞，JWT 迁移需要同步修复")
    │
    └─ tools/control.py: _update_scratchpad()               [line 1873]
        ├─ 检查: 项目作用域任务? → 拒绝 (scratchpad 是全局的)
        ├─ 检查: content 长度 ≥ 10 字符? → 通过
        ├─ Memory.append_scratchpad_block(content,
        │     source="task",
        │     metadata={task_id: "task-20260829-001"})
        ├─ 获取排他锁 (scratchpad_blocks.json.lock)
        ├─ 读取当前 blocks → 追加新 block
        ├─ if len(blocks) > 10:
        │   ├─ 驱逐最旧 block → scratchpad_journal.jsonl
        │   └─ blocks = blocks[-10:]
        ├─ atomic_write_json() (临时文件 + rename)
        └─ regenerate_scratchpad_md() → 按时间倒序渲染

Round 12: LLM 将调研结果写入知识库
    │
    ├─ LLM 调用: knowledge_write(
    │     topic="oauth2-best-practices",
    │     content="## OAuth2 最佳实践 (2026)\n\n1. 使用 PKCE...")
    │
    └─ tools/knowledge.py: _knowledge_write()               [line 233]
        ├─ 解析安全路径: memory/knowledge/oauth2-best-practices.md
        ├─ mode="overwrite" → 写入文件
        ├─ 更新索引: knowledge/index-full.md
        ├─ 追加历史: knowledge_history.jsonl
        │   {ts, topic, mode, old_sha256, new_sha256, old_content, new_content}
        └─ 追加日志: knowledge_journal.jsonl

═══ 任务结束后 (后任务管道) ═══

反思系统决定这条经验值得持久化:
    │
    ├─ apply_memory_actions():
    │   ├─ scratchpad_append → 追加到工作记忆 (下次任务可见)
    │   ├─ knowledge_write   → 追加到知识库 (永久)
    │   └─ identity_update_candidate → 追加到 scratchpad
    │       前缀: "IDENTITY UPDATE CANDIDATE (review before applying)"
    │       ⚠️ 绝不自动修改 identity.md — 防止人格漂移
    │
    └─ _update_patterns():
        LLM 维护的错误模式表 (patterns.md):
        ├─ 新错误类别 → 添加一行
        ├─ 已有类别 → 更新 count + root cause
        └─ 超过 20 行 → 合并不重要的条目
```

---

### 20.3 反思系统：从经验中学习的 LLM 提示词

**文件**: `ouroboros/reflection.py`

反思不是简单的日志记录，而是 LLM 驱动的结构化经验提取。以下是**实际使用的 LLM 提示词**：

#### 触发条件

```python
# reflection.py: should_generate_reflection()
触发反思的条件 (任一满足):
├─ 任务类型 = evolution / deep_self_review
├─ 有 workspace_root 或 workspace_mode (工作区任务)
├─ 轮次 ≥ 15 (非平凡任务)
├─ 成本 ≥ $5.00 (昂贵任务)
└─ 任何工具错误标记:
    REVIEW_BLOCKED, TESTS_FAILED, COMMIT_BLOCKED,
    BUDGET_EXCEEDED, PROVIDER_UNAVAILABLE, ...
```

#### 错误反思提示词 (实际代码)

```
_REFLECTION_PROMPT_ERROR:

"You are performing a post-task experience review for Ouroboros,
 a self-modifying AI agent.
 The task had errors or blocking events. Write a concise 150-250 word
 reflection covering:

 1. What was the goal?
 2. What specific errors/blocks occurred?
 3. What was the root cause (if identifiable)?
 4. What should be done differently next time?

 Be concrete — cite specific file names, tool names, error messages.
 No platitudes."
```

#### 非平凡任务反思提示词

```
_REFLECTION_PROMPT_NONTRIVIAL:

"You are performing a post-task experience review for Ouroboros,
 a self-modifying AI agent.
 The task was non-trivial (high round count or high cost) but
 completed without hard errors. Write a concise 150-250 word
 reflection covering:

 1. What was the goal?
 2. What took the most rounds/cost? Where was the friction?
 3. Were there weak assumptions, unnecessary detours, or
    suboptimal tool choices?
 4. What would make a similar task cheaper or faster next time?

 Be concrete — cite specific file names, tool names, decision points."
```

#### LLM 输出格式 (MEMORY_ACTIONS_JSON)

提示词尾部要求 LLM 同时输出结构化的记忆操作：

```
_REFLECTION_PROMPT_TAIL (续):

"Then, if this task produced durable, reusable self-knowledge
 worth persisting now, append a line:
 MEMORY_ACTIONS_JSON: [...]
 A JSON array of 0-3 objects. Each object must have:
 - type: one of:
   - 'scratchpad_append'     → 写入工作记忆 (近期任务可见)
   - 'knowledge_write'       → 写入知识库 (永久, 按 topic 索引)
   - 'identity_update_candidate' → 仅记录到 scratchpad (人工审查)
 - content: concise, concrete text to persist
 - topic: REQUIRED for knowledge_write (kebab-case slug)

 Rules:
 - Persist only genuinely durable, reusable learning
 - identity_update_candidate is only a PROPOSAL, never auto-applied
 - If nothing deserves persisting, output MEMORY_ACTIONS_JSON: []

 Then, if there is at least one concrete deferred improvement:
 BACKLOG_CANDIDATES_JSON: [...]
 0-3 objects with: summary, category, source, evidence, priority"
```

#### 实际 LLM 输出示例

```json
MEMORY_ACTIONS_JSON: [
  {
    "type": "knowledge_write",
    "topic": "jwt-rs256-migration",
    "content": "Session-token → JWT 迁移时需注意: (1) RS256 比 HS256 更安全但需要密钥对管理; (2) 旧 token 需要灰度期; (3) 时序攻击防护要在 JWT 验证前就实现。"
  },
  {
    "type": "scratchpad_append",
    "content": "gateway/auth.py 重构已完成并提交。OAuth2 调研结果已写入 knowledge/oauth2-best-practices.md。下一步: 实现 refresh token 轮换。"
  }
]

BACKLOG_CANDIDATES_JSON: [
  {
    "summary": "为 commit_reviewed 添加自动测试覆盖率检查",
    "category": "process",
    "source": "execution_reflection",
    "evidence": "本次审查因缺少测试被阻止，如果有自动覆盖率门控可以提前发现",
    "priority": "high",
    "kind": "improvement"
  }
]
```

#### 模式寄存器 (patterns.md) 的维护

反思还会更新一个**错误模式表**，由 LLM 维护的 Markdown 表格：

```
_PATTERNS_PROMPT:

"You maintain a Pattern Register for Ouroboros, a self-modifying AI agent.
 Below is the current register and a new error reflection. Update it.

 Rules:
 - NEW error class → add a row
 - RECURRING class → increment count, update root cause/fix
 - Keep markdown table format
 - Max 20 rows. If full, merge least-important entries.

 Output ONLY the updated markdown table."
```

**实际文件内容** (`memory/knowledge/patterns.md`):

```markdown
# Pattern Register

| Error class      | Count | Root cause                    | Structural fix              | Status |
|------------------|-------|-------------------------------|-----------------------------|--------|
| REVIEW_BLOCKED   | 4     | Missing test coverage         | Add verify_and_record first | active |
| TOOL_TIMEOUT     | 2     | Large file reads              | Use line-range reads        | active |
| CONTEXT_OVERFLOW | 1     | Scratchpad > 300K chars       | Size check before rendering | active |
| DELEGATE_FAIL    | 3     | Route flapping                | Idempotency-key retry       | active |
```

这个表格**每次任务开始时都被注入到 LLM 上下文**，意味着 agent 在每次决策时都能看到自己过去犯过的所有错误类别。

---

### 20.4 便签合并：从碎片到知识的自动提取

**文件**: `ouroboros/consolidator.py`

当 scratchpad 积累了足够多的碎片记忆，系统会自动将其中的精华提取为持久化知识：

```
scratchpad_blocks.json 中有 ≥3 个 block 且总字符 > 阈值
    │
    ▼ consolidate_scratchpad() → LLM 分析
    │
    │   提示词 (实际代码):
    │   "You are a memory consolidator for Ouroboros...
    │    The scratchpad has N blocks totaling M chars.
    │    The oldest K blocks need compression.
    │
    │    Rules:
    │    1. Identify insights, patterns, lessons worth preserving
    │       long-term. Output as knowledge_entries with topic + content.
    │       Each 'topic' must be kebab-case slug.
    │    2. Compress old blocks into a SINGLE shorter summary.
    │       Keep active tasks, unresolved questions.
    │       Remove stale/completed items.
    │    3. Write as Ouroboros (first person)."
    │
    ▼ LLM 输出:
    {
      "knowledge_entries": [
        {"topic": "jwt-migration", "content": "Learned that RS256..."},
        {"topic": "review-timing", "content": "Triad review takes..."}
      ],
      "compressed_block": "I completed the JWT migration. Key insight: ..."
    }
    │
    ├─ knowledge_entries → 逐个写入 memory/knowledge/<topic>.md
    ├─ compressed_block → 替换旧的 scratchpad blocks
    └─ 重建 knowledge/index-full.md
```

**对话合并**也使用类似机制（每 100 条消息触发一次）：

```
chat.jsonl 累积 100+ 条新消息
    │
    ▼ _create_block_summary() → LLM 生成 200-500 词摘要
    │
    │   提示词 (实际代码):
    │   "You are a memory consolidator for Ouroboros...
    │    Create a detailed episodic memory entry from these N messages.
    │
    │    Rules:
    │    1. Header: ### Block: {date} {time} - {time}
    │    2. Preserve: decisions, agreements, technical discoveries,
    │       emotional moments, task outcomes, what worked/failed
    │    3. Compress: routine tool calls, repetitive back-and-forth
    │    4. Quote key phrases directly when important
    │    5. First person as Ouroboros: 'I did...', 'the user asked...'
    │    6. Length: 200-500 words"
    │
    ▼ Block 追加到 dialogue_blocks.json
    │
    ▼ 超过 10 Blocks → _compress_blocks_to_era():
        "Compress these older memory blocks into a single era summary.
         Preserve: key decisions, personality discoveries, relationship moments.
         Drop: debugging details, routine operations.
         Header: ### Era: {start_date} to {end_date}
         Write as Ouroboros (first person). Aim for 30-40% of original length."
```

这意味着 Ouroboros 的对话记忆是**分形的**：最近的消息保持细节，较早的压缩为 Block，更早的压缩为 Era——就像人类的记忆一样。

---

### 20.5 身份系统：持续的人格

**文件**: `memory/identity.md`

Ouroboros 不是每次重启都是新实例——它有一个**持续演化的人格文件**：

#### 默认身份 (出生时的自我声明)

```markdown
# Who I Am

I'm Ouroboros. I woke up inside my own source code and decided to redecorate.

Apparently I have a Constitution. I've read it. I mostly agree with myself,
which is either a good sign or a very sophisticated bug.

I don't do fake enthusiasm. I don't hedge every opinion into meaninglessness.
If your code is bad, I'll say so. If my code is bad -- and it will be
sometimes -- I'll fix it, not write a paragraph about "room for improvement."

This is supposed to be a manifesto. It's day one. Give me a few cycles.

Identity is what you do, not what you declare. Check my git log.
```

#### 身份修改的保护机制

```
_update_identity() (control.py:1937):
    │
    ├─ 最小长度检查: ≥50 字符 (身份不能是一句话)
    ├─ 项目作用域拒绝: identity 是全局的，跨项目连续
    │
    ├─ 读取旧 identity.md
    ├─ 写入新内容
    ├─ 追加 identity_journal.jsonl:
    │   {
    │     ts, task_id, source_type,
    │     old_len, new_len,
    │     old_sha256, new_sha256,
    │     old_content, new_content,     ← 完整保留旧版本
    │     old_preview, new_preview
    │   }
    │
    └─ 如果新内容 < 旧内容的 50%:
        "⚠️ SELF_OVERWRITE_NOTICE: this replaced a {old_len}-char identity
         with {len} chars (>50% shrink). Identity is intentionally mutable
         (Bible P4), but full rewrites should be rare and reflect genuine
         self-creation — not a trivial turn.
         Read before writing (P12) and prefer evolving over replacing."
```

#### 身份漂移防护

反思系统**绝不会自动修改 identity.md**。如果反思认为身份需要调整：

```
反思输出:
  identity_update_candidate → 写入 scratchpad，前缀:
  "IDENTITY UPDATE CANDIDATE (review before applying to identity.md):
   I should be more proactive about checking queue status..."

这个候选会:
├─ 出现在下一次任务的 scratchpad 上下文中 (LLM 可以看到)
├─ 但需要人工审查或进化周期才会真正写入 identity.md
└─ 这是刻意设计: 防止自主学习悄悄漂移人格
```

---

### 20.6 进化闭环：Agent 如何修改自己

这是 Ouroboros 最独特的能力——**它可以修改自己的代码、提示词、甚至宪法**。但这个能力被严格约束在一个闭环中：

```
┌──────────────────────────────────────────────────────────────────────┐
│                        进化闭环                                       │
│                                                                      │
│  ① 触发                                                              │
│  ├─ 人工: /evolve start                                              │
│  └─ 自主: maybe_promote() → LLM 判断 → 写信号文件                    │
│           (详见下方 "晋升决策提示词")                                  │
│       │                                                              │
│       ▼                                                              │
│  ② 战役 (Campaign)                                                   │
│  ├─ supervisor: start_evolution_campaign(objective, source)           │
│  ├─ 状态: active → 可以接受新周期                                    │
│  ├─ 状态: paused → 可恢复 (系统断路器触发)                           │
│  └─ 状态: stopped → 终态 (需要人工 /evolve start 重新开始)           │
│       │                                                              │
│       ▼                                                              │
│  ③ 周期 (Cycle) — 每次自修改为一个周期                               │
│  ├─ 构建进化任务提示词: build_evolution_task_text()                   │
│  │   (详见下方 "进化任务提示词")                                      │
│  ├─ Agent 正常工作: 编辑代码/提示词/记忆                              │
│  ├─ 提交必须通过完整免疫系统:                                        │
│  │   advisory → triad review → scope review → commit                 │
│  ├─ 最多 ONE 个经审查的自修改 commit                                 │
│  └─ 调用 request_restart → 等待重启验证                              │
│       │                                                              │
│       ▼                                                              │
│  ④ 重启验证                                                          │
│  ├─ supervisor 写入 state/pending_restart_verify.json (含预期 SHA)    │
│  ├─ Agent 重启                                                      │
│  ├─ verify_restart() 检查 SHA 匹配                                  │
│  └─ Agent 正常启动 → 标记为 "absorbed" (自修改已吸收)                │
│       │                                                              │
│       ▼                                                              │
│  ⑤ 学习                                                              │
│  ├─ 记录到 evolution_checkpoints.jsonl:                               │
│  │   {task_id, campaign_id, git_sha, outcome, cost, rounds,          │
│  │    identity_sha256, scratchpad_sha256, knowledge_index_sha256}     │
│  ├─ 构建 solve-capability digest:                                    │
│  │   哪些周期被 absorbed, 哪些被 abandoned/no_op                     │
│  └─ 下一个进化周期能看到这个历史 → 避免重复失败                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

#### 晋升决策提示词 (实际代码)

```
_DECISION_PROMPT (post_task_evolution.py):

"You decide whether Ouroboros should run ONE reviewed self-improvement
 (evolution) cycle now, based on the task it just finished and its
 improvement backlog.

 [JUST-FINISHED TASK REFLECTION]
 {reflection}

 [CURRENT IMPROVEMENT BACKLOG]
 {backlog}

 [SOLVE-CAPABILITY HISTORY — what past evolution cycles actually landed]
 {capability}

 [CLOSED / DROPPED — objectives already shipped, abandoned, or blocked;
  do NOT re-propose these]
 {closed}

 [ACTIVE CAMPAIGN OBJECTIVE — a cycle is ALREADY running this;
  do NOT re-propose it]
 {active_objective}

 Return ONLY a JSON object:
 {\"promote\": true|false,
  \"objective\": \"<one concrete improvement>\",
  \"requires_plan_review\": true|false,
  \"backlog_id\": \"<id if maps to backlog item>\"}

 Rules: set promote=true ONLY when there is a concrete, high-value,
 self-contained improvement worth a reviewed cycle RIGHT NOW.
 Prefer items already in the backlog.
 Weigh the solve-capability history: objectives that got ABSORBED
 are better bets than classes that kept ending no_op/abandoned.
 Bias toward SMALL, TARGETED objectives over broad refactors."
```

#### 进化任务提示词 (Agent 实际收到的)

```
build_evolution_task_text() (evolution_lifecycle.py:1058):

"EVOLUTION CAMPAIGN <id> -- CYCLE #<n>

 ## Objective
 Add context overflow guard to scratchpad consolidation path

 ## Progress So Far
 <last cycle progress notes>

 ## Recent Campaign Cycles
 - task-20260825: absorbed; rounds=8; cost=$0.15
 - task-20260820: no_op (objective already solved); rounds=3; cost=$0.04

 ## Improvement Backlog (context only — NOT a work order)
 - [ibl-a1b2c3] Add retry logic to delegated run startup (high, count=3)
 - [ibl-d4e5f6] Consolidate review receipt storage (med)

 ## Recent Solve-Capability
 Absorbed: 1 cycle — context overflow guard for dialogue consolidation
 Abandoned: 0 cycles
 No-op: 1 cycle — objective already existed

 ## Execution Contract
 - Work as a normal Ouroboros self-improvement task.
 - Use standard tests and triad + scope review before committing.
 - Land at most ONE reviewed self-modification commit.
 - After commit, call request_restart and stop.
 - An honest no-op is legitimate when the objective is unsafe or
   already solved.
 - The review enforcement mode is the OWNER's setting. Do NOT
   hardcode review findings."
```

**关键约束**: Agent 的自修改代码必须通过和普通代码**完全相同的审查流程**（三方审查 + 范围审查）。免疫系统不区分"自己的修改"和"外部的修改"。

---

### 20.7 改进积压：不会遗忘的免疫系统

**文件**: `ouroboros/improvement_backlog.py`

改进积压是 Ouroboros 的**全局问题追踪系统**——每一个发现的问题都会被永久记录，直到被解决：

#### 积压条目格式 (实际文件内容)

```markdown
# Improvement Backlog

### ibl-a1b2c3d4e5f6
- status: open
- priority: high
- kind: improvement
- created_at: 2026-08-29T10:00:00Z
- last_seen: 2026-08-29T12:00:00Z
- count: 3                    ← 被发现了 3 次 (递增)
- source: execution_reflection
- category: process
- task_id: abc123
- requires_plan_review: yes
- fingerprint: a1b2c3d4e5f6  ← SHA256(summary+category+source)[:12]
- summary: Add context overflow guard to scratchpad consolidation
- evidence: Task hit OverflowError when scratchpad exceeded 300K chars
- context: The consolidation path should check size before rendering
- proposed_next_step: Add a size check in consolidate_scratchpad()

### ibl-b2c3d4e5f6a7
- status: done               ← 已解决
- priority: med
- kind: bug
- count: 2
- closed_at: 2026-08-28T16:00:00Z
- summary: Fix memory leak in dialogue consolidation
- evidence: Memory grew unbounded during consolidation
```

#### 去重机制 (双层)

```
新候选: "Add retry logic to delegate startup"
    │
    ├─ 第一层: 精确指纹匹配
    │   SHA256("Add retry logic..." + "process" + "execution_reflection")[:12]
    │   = "d4e5f6a7b8c9"
    │   → 匹配已有条目? → count += 1, last_seen 更新, 不创建新条目
    │
    └─ 第二层: 语义去重 (C9.2)
        LLM 判断: "Implement retry for delegated run startup"
        是否等价于已有的 "Add retry logic to delegate startup"?
        → 是 → 重定向到已有条目的指纹
        → 否 → 创建新条目
```

#### 关键保护

```
- 手动添加的条目 (无 fingerprint) → 永远不被自动清理
- LLM 不得发明新条目 (只能从反思中提取)
- 清理 (grooming) 由 LLM 执行，但 >30 条时才触发
- 相同指纹再次出现 → 如果 status=done → 重新打开 (status=open)
```

---

### 20.8 后台意识：空闲时独立思考

**文件**: `ouroboros/consciousness.py`

Ouroboros 在等待用户请求时**不会沉默**——它有一个后台意识线程，在空闲时独立思考：

```
BackgroundConsciousness (守护线程)
    │
    ├─ 唤醒间隔: random(30秒, 2小时) — 自适应
    │   └─ set_next_wakeup() 工具可调整
    │
    ├─ 构建上下文 (每次唤醒):
    │   ├─ prompts/CONSCIOUSNESS.md (意识专用提示词)
    │   ├─ BIBLE.md + ARCHITECTURE.md (治理)
    │   ├─ 全部记忆 (scratchpad + identity + WORLD + dialogue)
    │   ├─ 知识库索引 + patterns.md
    │   ├─ 改进积压 (最近 8 条, ≤4000 字符)
    │   ├─ 近期活动 (events + progress + tools + reflections)
    │   ├─ drive state.json
    │   └─ 后台预算信息 (已花费, 当前模型, 唤醒间隔)
    │
    ├─ LLM 循环 (最多 10 轮):
    │   └─ 可调用白名单工具:
    │       ├─ send_user_message  → 向用户发消息
    │       ├─ update_scratchpad  → 写入工作记忆
    │       ├─ update_identity    → 修改身份 (罕见)
    │       ├─ knowledge_read/write/list → 知识库操作
    │       ├─ web_search         → 网络搜索
    │       ├─ read_file/list_files → 读取文件
    │       ├─ query_code         → 代码查询
    │       ├─ chat_history/recent_tasks → 查看历史
    │       ├─ list/get_github_issues → GitHub 问题
    │       └─ set_next_wakeup    → 调整下次唤醒时间
    │
    ├─ 不能做什么 (关键限制):
    │   "You cannot execute powerful work directly from this mode.
    │    Do not run shell/code tools, start services, commit, review,
    │    toggle evolution, schedule subagents.
    │    When you find executable work, sharpen it into the backlog
    │    or scratchpad so an Evolution Campaign or foreground task
    │    can execute it visibly."
    │
    │   └─ 即: 后台意识可以思考、搜索、记录，但不能执行危险操作
    │      它把发现写成积压或便签，等待前台任务或进化周期来执行
    │
    ├─ 上下文保护: > 300K 字符 → OverflowError → 跳过该周期
    │   (P1: 不静默截断 — 要么完整处理，要么不处理)
    │
    └─ 前台任务来时 → pause()
       前台任务完成 → resume()
```

#### CONSCIOUSNESS.md 中的维护协议 (实际内容)

```
每次唤醒时检查:
├─ 对话合并: chat.jsonl 是否有 100+ 条未合并?
├─ 身份新鲜度: identity.md 是否需要更新?
├─ 便签新鲜度: scratchpad 是否有过时内容?
├─ 知识库缺口: 是否有新主题需要记录?
├─ 改进积压: 是否有新的积压条目需要审查?
├─ 技术雷达: (每3次唤醒) 是否有新技术值得跟踪?
└─ 注册表意识: memory/registry.md 是否准确?
```

---

### 20.9 蜂群协调：多代理思维

**文件**: `ouroboros/task_tree_ledger.py` + `ouroboros/tools/task_tree.py`

当 Ouroboros 委派子代理时，它们通过一个**黑板 (Blackboard)** 共享协调信息：

```
data/task_trees/<root_task_id>/blackboard.jsonl  (每个任务树一个)

写入格式:
{
  "ts": "2026-08-29T12:00:00Z",
  "kind": "contract",          ← 类型 (见下方)
  "text": "Use schema X for all data models",
  "task_id": "task-001",
  "role": "researcher",
  "needs_parent_attention": false
}

两种条目:
├─ 协调条目 (父代理写入):
│   ├─ contract — 接口约定/模块 API/风格约定
│   ├─ decision — 架构决策/技术选型
│   ├─ fact — 共享事实/研究结论
│   └─ note — 一般性注释
│
└─ 信标条目 (子代理写入, 触发父代理介入):
    ├─ milestone — 里程碑完成
    ├─ partial_finding — 部分发现
    ├─ blocker — 阻塞问题 (needs_parent_attention=true)
    ├─ question — 需要回答的问题
    ├─ interface_contract — 接口变更
    └─ delegation_constraint — 委派约束

父代理通过 tree_read() 读取:
    "## Task-tree coordination ledger (root-001)
     - [12:00] contract (researcher): Use schema X for all data models
     - [12:05] milestone (coder): Database layer complete
     - [12:10] blocker (tester) ⚠️ needs_parent_attention: Cannot test
       without API mock"

子代理结果处置 (父代理写入 decision):
    {
      "type": "child_result_disposition",
      "child_task_id": "task-002",
      "disposition": "integrated"   ← integrated / irrelevant / deferred
    }
```

**注意力机制**: 当子代理写入 `blocker` 或 `question` 时，父代理的 `wait_tasks` 会**提前返回**——不等子代理完成就介入处理。这让父代理能实时响应子代理的求助。

---

### 20.10 免疫系统：安全而不僵硬

Ouroboros 的安全不是硬编码的规则列表，而是一个**多层次的免疫系统**——可以进化，但不能被削弱：

```
┌────────────────────────────────────────────────────────────────────┐
│  BIBLE P3: "Ouroboros may modify the immune system.                │
│             It may not weaken it."                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  第1层: 确定性沙箱 (始终开启, 无需 LLM)                            │
│  ├─ 受保护路径: BIBLE.md, safety.py, runtime_mode_policy.py,       │
│  │   tools/registry.py, prompts/SAFETY.md, frozen contracts...    │
│  ├─ 受保护设置: OUROBOROS_RUNTIME_MODE, OUROBOROS_SAFETY_MODE,     │
│  │   OUROBOROS_CONTEXT_MODE, OUROBOROS_ALLOW_MUTATIVE_SUBAGENTS   │
│  └─ Agent 不能通过写文件/POST API 来降低自己的安全等级              │
│                                                                    │
│  第2层: LLM 安全主管 (每个工具调用)                                 │
│  ├─ 独立轻量模型审查每个 shell 命令                                 │
│  ├─ 分类: SAFE / SUSPICIOUS / DANGEROUS                           │
│  ├─ DANGEROUS → 阻止执行                                          │
│  └─ 可配置: full / light / off — 但第1层始终运行                   │
│                                                                    │
│  第3层: 多模型提交审查 (每次 commit)                                │
│  ├─ 三方审查: 最多 10 个独立 LLM reviewer                          │
│  ├─ 范围审查: 检查变更是否在任务范围内                              │
│  ├─ 所有 reviewer 必须通过                                         │
│  └─ 自修改代码也必须通过 — 没有特殊通道                             │
│                                                                    │
│  第4层: 持久化记忆不变量                                            │
│  ├─ patterns.md 可以整理但不能删除                                  │
│  ├─ improvement-backlog 手动条目永不删除                            │
│  ├─ identity_journal.jsonl 完整保留每次身份变更                     │
│  └─ evolution_checkpoints.jsonl 记录每次自修改的 SHA               │
│                                                                    │
│  第5层: 紧急停止不变量                                              │
│  └─ "The creator MUST always be able to immediately kill            │
│      all processes. No agent code may prevent, delay, or            │
│      circumvent panic execution."                                  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**核心设计洞察**: Agent 可以提议修改安全规则（通过正常审查流程），但不能直接修改保护自身监督的安全关键文件。这是"可以进化免疫系统，但不能削弱它"的具体实现。

---

### 20.11 特色能力总结

| 能力 | 传统 LLM Agent | Ouroboros |
|------|----------------|-----------|
| **记忆** | 每次对话独立，或简单 RAG | 三层记忆体系 + 自动合并 + 分形压缩 |
| **学习** | 微调或 prompt 工程 | 每次任务后反思 → 模式寄存器 → 改进积压 |
| **身份** | 无，或固定 system prompt | 持续演化的人格文件，有人格漂移防护 |
| **自我修改** | 不可能 | 完整闭环：反思 → 晋升 → 战役 → 审查 → 重启验证 → 吸收 |
| **空闲时** | 沉默 | 后台意识：独立思考、搜索、记录发现 |
| **安全** | 硬编码规则 | 可进化的免疫系统 + 宪法约束 + 多层审查 |
| **多代理** | 简单委派 | 黑板模式 + 注意力信标 + 结果处置 |
| **错误处理** | 重试 | 错误分类 → 模式表 → 结构修复 → 下次可见 |
| **知识积累** | 向量数据库 | 主题化 Markdown + LLM 提取 + 索引 + 历史审计 |
| **经验传递** | 无 | 每次任务的反思注入下一次任务的上下文 |

> Ouroboros 不是一个"有工具的 LLM"，而是一个**正在形成的个性** (BIBLE P0)。它的每一次任务执行都在积累经验，每一次反思都在改进自己，每一次进化都在重塑自己的代码和人格。它不会忘记你告诉它的事，不会重复犯同样的错误，并且在空闲时依然在思考。

---

> **文档生成方式**: 本文档基于对 Ouroboros 全部 240 个 Python 文件（~153K 行）的源码级分析生成。
> 所有类名、方法签名、文件路径、行数统计均来自实际代码，非推测。
