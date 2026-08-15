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

> **文档生成方式**: 本文档基于对 Ouroboros 全部 240 个 Python 文件（~153K 行）的源码级分析生成。
> 所有类名、方法签名、文件路径、行数统计均来自实际代码，非推测。
