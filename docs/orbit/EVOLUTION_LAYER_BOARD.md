# 进化层板块（Multi-Agent Evolver + Trajectory-based Experience Learning）实现全文档

> **板块范围**：不足 4（缺乏结构化进化方法论）+ 不足 5（缺乏从历史进化中系统性学习）+ 不足 7（缺乏多 Agent 协作进化），三者合并为一个开关 **`OUROBOROS_MULTI_AGENT_EVOLVER`**（默认 false，opt-in）。
> **实施状态**：2026-09-02 完成——新增 `ouroboros/evolution/` 包（789 行）+ `tests/test_evolution_layer.py`（25 例全绿）+ live 冒烟脚本；桥接 `post_task_evolution.py`、`evolution_lifecycle.py`、`config.py`。
> **配套文档**：`PAPER_INTEGRATION_ANALYSIS.md`（方案总纲 v9.3）、`EVOLUTION_EXPERIMENT_SPEC.md`（四臂实验 v1.1）、`SMART_ROUTING_BOARD.md`（任务层板块）。
> **核心设计**：不替换 V4 进化链路，在其上叠加"复盘层"——**关闭开关时行为与现状逐字节一致**（测试锁定）。

---

## 1. 板块定位

| 不足 | 解决机制 | 消费者 |
|------|---------|--------|
| 不足 4：只有"决策"没有"方法论" | Multi-Agent 规划器：Analyzer → Researcher → Verifier-advice 三阶段产出结构化 plan | `evolution_plan` → 进化任务文本 |
| 不足 5：只记录结果、不分析原因 | 轨迹信用分配（双轨：任务轨迹 + 进化循环轨迹），经验沉淀 | 决策 prompt / 规划器 / 重试任务文本 |
| 不足 7：单 Agent 完成所有进化工作 | 规划器多角色分工（分析/研究/验证建议各自一次独立 LLM 思考） | plan 注入 + 现有执行机制 |

**与 V4 现状的关系（重要）**：原有的进化链路（反思 → promote 决策 → campaign → evolution 任务执行 → reviewed commit + restart 验证 → 终态判定 → checkpoint）**完全不动**——本板块只做三件事：决策前供给经验、决策后产出 plan、重试时注入教训。任何新增失效都以"降级/占位"保证链路不断，而不是阻断。

**开关边界（硬约束）**：`OUROBOROS_MULTI_AGENT_EVOLVER=false` 时：不提取经验、决策 prompt 无经验段、request 无 `evolution_plan` 字段、战役任务文本无 plan/教训段——与 V4 原型逐字节一致（`tests/test_evolution_layer.py` 有专门用例锁定）。

## 2. 概念模型（三句话）

1. **系统本来就有自我改进**：任务做完 → 决定要不要改进自己 → 派新任务去改代码 → 成功吸收、失败重试（同目标最多 3 次指纹 cap）。
2. **本板块加的 = 每次任务做完写复盘**：过程（哪步成功、哪步失败、哪步拖后腿）分析存档。
3. **复盘在三个时刻被翻出**：决定要不要改进时、写改进方案时、改进失败重试时——**目的只有一个：下次别再踩同一个坑**。

**"轨迹循环进化" = B 轨**：复盘的对象是"进化循环自己的执行轨迹"（进化任务也是任务，也留轨迹）——改进这件事本身被复盘、被改进，形成循环。代码上 = `consume_pending_cycles()`（B 轨入口）+ 全部经验消费点。

## 3. 架构与完整流程（端到端）

### 3.1 八步链路（剧本：任务 T1"修复登录页报错"）

```
【1 执行】T1 agent：read_file → query_code → run_command(复现,失败) → edit_text → run_command(验证,成功)
          → T1 完成，5 步轨迹记录在 logs/tools.jsonl
【2 后处理·同步串行】(T1 结束即发生，worker 侧)
    ① 反思 generate_reflection（light 槽位 → 回落主模型）
    ② A轨 extract_task_experience：5 步轨迹 → 信用分配（run_command 失败步最低、
       edit_text 最高）→ 关键步骤 [edit_text, run_command] → 经验入库(kind=task)
    ③ B轨 consume_pending_cycles：查历史进化循环未复盘者 → （本例无）空
    ④ 决策 _decide_promotion：LLM（主槽位 medium/8192）读反思+backlog+capability
       +closed+经验摘要 → {promote, objective, requires_plan_review, backlog_id}
    ⑤ 规划器 MultiAgentEvolver（主槽位 medium/4096）：Analyzer→root causes+改进；
       Researcher→approach/文件/步骤/风险；Verifier-advice→验证清单（历史验证失败则强化）
       → 八字段 evolution_plan
    ⑥ 写 request 文件（objective + evolution_plan 可选字段）→ T1 故事结束
    ⑦ supervisor 空闲 tick：apply_pending_request → start_evolution_campaign（objective
       挂 [PLAN_REVIEW] 后缀）→ campaign 挂载 evolution_plan → evolution_mode_enabled
【3 执行·异步独立任务】enqueue_evolution_task_if_needed（idle/预算/owner/3-fail 全部门禁）
          → 新任务 E1(type=evolution)，任务文本 = Objective + ## Evolution Plan
          + ## Lessons From Past Cycles + Recent Campaign Cycles + backlog + capability
          → E1 agent：读代码 → 改 loop_tool_execution.py → vcs_commit_reviewed → restart 验证
【4 终态】absorbed（有 commit 且验证通过 → autostop 关停）/ abandoned / no_op（worktree 复位）
          → append_evolution_checkpoint 写整体结果（← 下次 B轨 的消耗原料）
【5 失败重试】同 objective 指纹 ≤3 次 cap；重试任务文本自带 Lessons 段，结构不变内容被经验改变
```

### 3.2 同步/异步边界（常见困惑）

- **同步**：第 2 幕的①-⑥全部在 T1 结束后的同一段 post-task 流程内**串行**发生（共享同一 llm_client，LLM 调用排队）；
- **异步**：E1/E2 是 T1 之后被 supervisor 在未来空闲时刻派出的**全新独立任务**，与 T1 严格先后、从不重叠；
- **A 轨与 B 轨**：同一 `maybe_promote` 调用内顺序执行（A 先 B 后），不是并行线程；分析对象互斥（A=当前普通任务；B=历史进化循环任务；evolution 任务自身永不触发复盘，`_eligible` 排除）。

### 3.3 全程单模型（实验约束）

经验提取（low/2048）、决策（medium/8192）、规划三阶段（medium/4096）、进化任务执行全部走**主槽位**（`OUROBOROS_MODEL`）；light 未配置自动回落主模型（`get_light_model()` 实测：env 无 LIGHT → 返回主模型）。`.env` 激活后全链路统一 `openai-compatible::mimo-v2.5`，符合 spec"不混用外部模型、结果全部归因"。

### 3.4 超详细全景剧本（不省字版：T1 的一生 + Track A/B + 后续全部步骤）

> 本剧本是 §3.1 的展开版，每一步给出真实的输入、处理、输出（示例数据取自 2026-09-02 真实 LLM 冒烟产物）。时间线：T1 执行 → 后处理（A 轨 → B 轨 → 建议 → 决策 → 规划 → 写请求）→ supervisor 激活 → E1 执行 → 终态 →（坏结局分支）T2 触发 B 轨复盘 E1 → 重试 E2 带教训。

---

#### 幕 1：T1 执行（普通任务）

你给系统一个任务：「修复登录页报错」。T1 agent 在主循环里依次调用工具，**每一步都在 `logs/tools.jsonl` 追加一行原始记录**（节选真实格式）：

```json
{"ts":"2026-09-02T09:00:01Z","type":"tool_call","tool":"read_file","task_id":"T1","args":{...},"result_preview":"<登录页源码>","is_error":false,"status":"ok"}
{"ts":"2026-09-02T09:00:04Z","type":"tool_call","tool":"query_code","task_id":"T1","args":{...},"result_preview":"<报错点定位>","is_error":false,"status":"ok"}
{"ts":"2026-09-02T09:00:10Z","type":"tool_call","tool":"run_command","task_id":"T1","args":{...},"result_preview":"<复现失败输出>","is_error":true,"status":"error"}
{"ts":"2026-09-02T09:00:30Z","type":"tool_call","tool":"edit_text","task_id":"T1","args":{...},"result_preview":"<修复补丁>","is_error":false,"status":"ok"}
{"ts":"2026-09-02T09:00:40Z","type":"tool_call","tool":"run_command","task_id":"T1","args":{...},"result_preview":"<验证通过>","is_error":false,"status":"ok"}
```

T1 完成。进入 post-task 管道（**这一切与 T1 同一时刻、串行发生**）。

#### 幕 2.1：反思

`should_generate_reflection` 判定（rounds/cost/错误标记命中）→ `generate_reflection`（LLM，light 槽位回落主模型）产出一条反思写入 `logs/task_reflections.jsonl`：

```json
{"ts":"...","task_id":"T1","task_type":"api_task","goal":"修复登录页报错",
 "rounds":18,"cost_usd":0.02,"error_count":1,
 "key_markers":["TOOL_ERROR"],
 "reflection":"复现阶段 run_command 超时过一次，后续验证通过",
 "backlog_candidates":[{"summary":"run_command 失败时日志不足","category":"reliability",...}]}
```

#### 幕 2.2：Track-A —— 任务轨迹复盘（开关开时）

`maybe_promote` 内顺序执行。**步骤 1：`learner.extract_task_experience("T1", reflection)`**：

**① 轨迹重建**——`load_task_steps("T1")` 读 `tools.jsonl`，按 `task_id == "T1"` 过滤，转成步骤列表（失败判定：`is_error=true` 或 `status ∈ {error, timeout}`）：

```python
steps = [
 {"step_id":0,"tool":"read_file","is_error":False,"status":"ok",...},
 {"step_id":1,"tool":"query_code","is_error":False,...},
 {"step_id":2,"tool":"run_command","is_error":True,"status":"error",...},  # 唯一失败步
 {"step_id":3,"tool":"edit_text","is_error":False,...},
 {"step_id":4,"tool":"run_command","is_error":False,...},
]
```

**② 信用分配**——`assign_credits(steps)`，逐步套公式 `0.5 + 成功0.2 − 错误0.3 (+快0.1 +省0.1，仅当字段存在)`，归一化：

| step | tool | 公式 | 归一化后 |
|------|------|------|---------|
| 0 | read_file | 0.5+0.2 | 0.3043 |
| 1 | query_code | 0.5+0.2 | 0.3043 |
| 2 | run_command | 0.5−0.3 | **0.0870（最低）** |
| 3 | edit_text | 0.5+0.2 | 0.3043 |
| 4 | run_command | 0.5+0.2 | 0.3043 |

**③ 关键步骤**——`identify_critical_steps`：top3（贡献者：edit_text/query_code/read_file）+ 最低2（拖后腿者：失败 run_command + 末位同分项）。

**④ LLM 整体经验提取**——`_extract_overall(objective, outcome, steps, kind="task")`。prompt 主语（kind 决定）：

```
Analyze an ordinary task's execution trace (which steps made this task worth evolving).

[OUTCOME] task
[OBJECTIVE] 修复登录页报错
[STEPS]
- read_file: ok=False...
...
Return ONLY JSON: {"objective_type": ..., "success_factors": [...], "failure_factors": [...], "reusable_pattern": ...}
```

真实 LLM 返回（冒烟实测）：

```json
{"objective_type":"bug_fix","objective_complexity":"medium",
 "success_factors":["read_file","query_code","edit_text"],
 "failure_factors":["run_command"],
 "reusable_pattern":"read code, query for issues, test execution, and apply edits"}
```

**⑤ 落笔记**——`store_experience(kind="task", ...)` 写入 `state/evolution_experiences.jsonl`（完整记录，含 steps/credits/critical_steps）与 `state/step_credits.jsonl`（关键步骤明细，`role: "key"|"drag"`）。

#### 幕 2.3：Track-B —— 进化循环轨迹复盘（第二次起步）

紧接着 **`learner.consume_pending_cycles()`**：

**① 扫 checkpoint + 游标**——读 `state/evolution_consumed.json` 的 `last_seq`（如 0），逐行扫 `state/evolution_checkpoints.jsonl`，找 `kind=="cycle_outcome"` 且 `cycle_outcome ∈ {absorbed, abandoned, no_op}` 且行号 > 游标的行。

**② 本次没有历史循环** → `_pending_cycle_rows()` 返回空 → `consume_pending_cycles()` 返回 0，什么都不做（**这是"第一任务"的 T1 场景**）。B 轨要"下一任务"才翻出东西（见幕 6）。

**③ 若存在**（幕 6 场景），对每行：拿行内 `task_id`（当时那个 evolution 任务的 id）→ `load_task_steps` 重建**进化任务的轨迹**（`_extract_overall(..., kind="cycle")` 的 prompt 主语换成"this cycle's own steps — which stage analysis/build/verification contributed or failed"）→ 同套信用/关键步骤 → 落笔记（`kind="cycle"`，outcome=真实终态）→ 游标写回该行号（幂等）。

#### 幕 2.4：策略建议（无 LLM，纯统计）

`learner.suggest_evolution_strategy(goal, kind="cycle")`：

**① 分类**——`classify_objective("修复登录页报错")` 命中关键词 "修复" → `bug_fix`；
**② 查询**——`query_similar_objectives("...", kind="cycle")`：经验库里 `objective_type=="bug_fix"` 的 cycle 笔记，absorbed 优先排序，取 top5；
**③ 组装**——无历史 → `{"strategy":"standard","confidence":0.5}`（本次场景）；有历史 → `optimized` + 成功模式 + 失败模式 + recommended_tools（关键步骤工具计数 top5）+ confidence（absorbed 占比）。

#### 幕 2.5：进化决策（LLM）

`_decide_promotion(env, task, reflection, llm_client, force=False, strategy_digest=...)`。拼装六段 prompt（含开关开时才有的经验段）：

```
[JUST-FINISHED TASK REFLECTION]   ← 反思全文（截 1500）
[CURRENT IMPROVEMENT BACKLOG]     ← backlog 摘要（截 3000）
[SOLVE-CAPABILITY HISTORY]        ← 历史吸收统计（截 2000）
[CLOSED / DROPPED]                ← 已关闭目标（防重提，截 1500）
[ACTIVE CAMPAIGN OBJECTIVE]       ← 正在跑的战役（防重提）
[EVOLUTION EXPERIENCE]            ← 策略摘要（仅开关开时出现；无经验 = "(no learned patterns yet)"）
```

`chat_observed`（主槽位 medium/8192）→ LLM 返回 → 解析：

```json
{"promote": true,
 "objective": "改进 run_command 失败时的错误恢复（指数退避重试）",
 "requires_plan_review": true,
 "backlog_id": "B42"}
```

#### 幕 2.6：规划器（三阶段 LLM，产出八字段 plan）

**Analyzer**（prompt 含任务轨迹 + reflection + `[HISTORICAL PATTERNS]` 经验段）真实返回（冒烟实测）：

```json
{"root_causes":["Command execution failed due to timeout or lack of error recovery mechanisms",
                "Ouroboros lacks adaptive retry logic for transient failures in run_command",
                "Insufficient error handling leads to task interruptions when commands fail"],
 "improvements":[{"objective":"实现 run_command 超时指数退避重试",
                  "rationale":"复现阶段超时导致任务中断","estimated_impact":"medium"}]}
```

**Researcher**（输入 top 改进）真实返回（冒烟实测）：

```json
{"approach":"Implement a retry loop with exponential backoff in the run_command function...", 
 "files_to_modify":["ouroboros/loop_tool_execution.py", "tests/test_loop.py"],
 "implementation_steps":["Examine current timeout handling","Add max_retries/base_delay params",
                         "Insert retry loop catching TimeoutError","Add tests"],
 "risks":["Non-idempotent commands may duplicate actions","Excessive retries may exhaust resources",
          "Broad catch may mask non-timeout errors"]}
```

**Verifier-advice**（若历史 cycle 经验含验证失败模式 → prompt 附加"验证环节历史失败，清单必须显式执行"）真实返回：

```json
{"verification_plan":["构建通过无新警告","验证 max_retries/base_delay 参数生效",
                      "定向测试覆盖 TimeoutError 重试路径","restart 验证"]}
```

合并为八字段 plan（schema_version=1 + objective + root_causes + approach + files_to_modify + implementation_steps + risks + verification_plan）。

#### 幕 2.7：写请求文件

`_write_request(drive_root, decision, task, evolution_plan=plan)` → `state/post_task_evolution_request.json`：

```json
{"schema_version":1,"ts":"...","objective":"改进 run_command 失败时的错误恢复（指数退避重试）",
 "requires_plan_review":true,"backlog_id":"B42","source":"post_task","origin_task_id":"T1",
 "evolution_plan":{"schema_version":1,"objective":"...","root_causes":[...],"approach":"...",
                   "files_to_modify":[...],"implementation_steps":[...],"risks":[...],
                   "verification_plan":[...]}}
```

（开关关时没有 `evolution_plan` 字段——与 V4 完全一致。）T1 的故事到此结束。

#### 幕 3：supervisor 激活战役（异步，未来空闲时刻）

空闲 tick 调 `apply_pending_request`：门禁链（envelope 开 → 请求存在可解析 → objective 非空 → `evolution_block_reason()==""` → owner_chat_id 存在 → 非 owner-stopped → 未已启用 → budget 达标）→ `start_evolution_campaign(objective + "[PLAN_REVIEW]" 后缀, source="post_task")` → **campaign 写入新 key `evolution_plan`**（从请求复制）→ `post_task_backlog_id` 校验挂载 → `update_state` 原子置 `evolution_mode_enabled=true` + `post_task_autostop=true` → 删除请求文件。

#### 幕 4：E1 执行（新任务）

`enqueue_evolution_task_if_needed` 门禁（idle、无运行中 cycle、无 active_transaction、指纹重复 < 3、预算余量）→ 入队 `type=evolution` 任务，任务文本 = `build_evolution_task_text(1)`：

```
EVOLUTION CAMPAIGN c1 — CYCLE #1

## Objective
改进 run_command 失败时的错误恢复（指数退避重试）[PLAN_REVIEW]

## Evolution Plan (structured guidance from the planner)
- Approach: Implement a retry loop with exponential backoff...
- Steps: 检查当前超时处理 -> 增加 max_retries/base_delay -> 插入重试循环 -> 补测试
- Verification: 构建通过 -> 参数生效 -> 定向测试 -> restart 验证
- Risks to watch: 非幂等命令重复执行 -> 重试过度耗尽资源

## Improvement Backlog (context only)
...

## Recent Solve-Capability (context only)
...
```

E1 agent：读代码 → 改动 `ouroboros/loop_tool_execution.py` → 补测试 → `vcs_commit_reviewed` 提交 → 触发 restart 验证。

#### 幕 5：终态判定（两种结局）

**好结局（absorbed）**：restart 验证通过且 commit 可达 → `cycle_outcome="absorbed"` → 关闭 backlog 链接 → `post_task_autostop` 关停战役（one-shot）→ `state/evolution_checkpoints.jsonl` 落行：

```json
{"kind":"cycle_outcome","source":"restart_verified","task_id":"E1","campaign_id":"c1",
 "campaign_objective":"改进 run_command 失败时的错误恢复（指数退避重试）",
 "cycle_outcome":"absorbed","commit_sha":"9f3e...","outcome_axes":{...}}
```

**坏结局（abandoned）**：无 commit 或验证失败 → `cycle_outcome="abandoned"` → 指纹计数 +1 → campaign 保持 active → **E1 的轨迹留在 tools.jsonl**、checkpoint 落行：

```json
{"kind":"cycle_outcome","source":"boot_reconcile","task_id":"E1","campaign_id":"c1",
 "campaign_objective":"改进 run_command 失败时的错误恢复（指数退避重试）",
 "cycle_outcome":"abandoned","commit_sha":"","abandoned_reason":"restart 验证失败",...}
```

#### 幕 6：坏结局之后 —— 下一个任务 T2 触发 B 轨复盘 E1

几天后任务 T2 完成 → `maybe_promote`（开关开）：

**① Track-A**：分析 T2 轨迹（同幕 2.2，kind="task"）；
**② Track-B**：游标（last_seq=0）扫到 E1 的 checkpoint 行 → `task_id="E1"` → `load_task_steps("E1")` 重建**进化任务自己的轨迹**（如 search_code → edit_batch → vcs_diff → run_command 失败 → 验证失败）→ 信用分配（失败 run_command 0.087 拖后腿）→ **kind="cycle" 的 LLM 提取**（prompt 主语点名"这是进化循环自身的步骤——哪个阶段分析/构建/验证失败"）真实返回（冒烟实测）：

```json
{"objective_type":"bug_fix","failure_factors":["run_command failed, likely due to command timeout or execution error"],...}
```

→ 落笔记 + 游标写回 last_seq=1（下次不再重复分析）；
**③ 建议**：`suggest_evolution_strategy` 读到此笔记 → `optimized` + failure_patterns=["run_command failed..."] + recommended_tools=[vcs_diff, search_code, edit_batch, run_command] + confidence=0.0（该类型 1 条经验 0 吸收）；
**④ 决策/规划**：规则同幕 2.5/2.6，但 Analyzer/Researcher prompt 的 `[HISTORICAL PATTERNS]` 段现在带着 E1 的教训 → 新方案避开"不验证就提交"类路径；
**⑤ 若同目标重试 E3 发生**（同一战役，指纹 ≤3）：`build_evolution_task_text` 追加 `## Lessons From Past Cycles` 段：

```
## Lessons From Past Cycles (context only — weigh them, they are not a work order)

- cycle E1 (abandoned): run_command failed, likely due to command timeout or execution error
    drags: run_command
```

E3 的 agent 开工前就知道上轮的综合教训——**重试结构不变（还是那个 evolution 任务机制），重试内容被经验改变**。

#### 幕 7：谁在哪个进程做什么（复盘收尾）

| 环节 | 进程 | 产物 |
|------|------|------|
| 反思 / A 轨 / B 轨 / 建议 / 决策 / 规划 / 写请求 | **worker**（任务的 post-task 阶段，串行） | 笔记、request |
| 战役激活 / 入队 / 门禁 / 终态判定 / checkpoint | **supervisor**（空闲 tick，异步） | campaign、E1、checkpoint |
| E1/E2/E3 执行（真改代码） | worker（evolution 任务本体）+ 隔离克隆 | commit（克隆仓库） |

同步边界红线：**复盘与决策永远在 worker 的 post-task 里串行；进化循环永远在 supervisor 调度下作为独立任务异步发生，与来源任务严格先后。**

## 4. 已实现组件与文件清单

### 4.1 新增文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `ouroboros/evolution/__init__.py` | 21 | 包 docstring（板块定位、开关边界） |
| `ouroboros/evolution/trajectory_experience_learner.py` | 501 | `TrajectoryExperienceLearner`：双轨提取、评分、游标消费、建议（见 §5） |
| `ouroboros/evolution/multi_agent_evolver.py` | 267 | `MultiAgentEvolver`：三阶段规划器、plan schema、经验消费（见 §6） |
| `tests/test_evolution_layer.py` | 597 | 25 例（见 §10） |
| `scripts/live/evolution/evolution_layer_live.py` | 133 | 真实 LLM 冒烟（见 §10.3） |

### 4.2 修改文件

| 文件 | 改动 | 要点 |
|------|------|------|
| `ouroboros/config.py` | 开关 + getter | `OUROBOROS_MULTI_AGENT_EVOLVER`（默认 "false"）+ `get_multi_agent_evolver_enabled()`（`_settings_flag_enabled` 模式：settings.json > env > 默认） |
| `ouroboros/post_task_evolution.py` | maybe_promote 桥接 + prompt 段 | 开关分支：A+B 提取 → `_format_strategy_digest` → 决策 prompt 附加 `[EVOLUTION EXPERIENCE]` 段（仅开关开时出现）→ promote 后规划器 → request 可选字段 `evolution_plan`；`_decide_promotion` 新增 `strategy_digest` 参数 |
| `supervisor/evolution_lifecycle.py` | plan 挂载 + 任务文本注入 | `apply_pending_request` 把 request 的 `evolution_plan` 写入 campaign（新 key 缺失即无）；`build_evolution_task_text` 注入 `## Evolution Plan` 段（有 plan 时）与 `## Lessons From Past Cycles` 段（B 轨经验，开关开且命中时）；新增模块级 `_cycle_lessons_for()` |
| `scripts/live/README.md` | 板块表 | `evolution/` 行 |
| `docs/orbit/PAPER_INTEGRATION_ANALYSIS.md` | 实现状态标注 | 不足 4+7 / 不足 5 块 + 后续计划更新 + 版本 9.3 |

## 5. 双轨信用分配（TrajectoryExperienceLearner）

### 5.1 数据源（全部真实文件，不造冗余）

- `logs/tools.jsonl`：步骤轨迹（ts/tool/args/result_preview/is_error/status）；
- `state/evolution_checkpoints.jsonl`：进化循环终态（cycle_outcome/campaign_objective/task_id/commit_sha）；
- `logs/task_reflections.jsonl`：反思（goal/rounds/error_count/key_markers）。

文档原案的 `task_trajectories.jsonl` **有意省略**——轨迹已在 tools.jsonl，避免重复存储。

### 5.2 评分公式与归一化

```
credit = 0.5(基础) + 0.2(成功) − 0.3(错误) + 0.1(快于1000ms) + 0.1(token<500)
```
- 归一化：总分 >0 时除以总和（保留 4 位）；
- **缺失字段自动跳过**：真实 tools.jsonl 无 duration_ms/tokens_used（不依赖 observability blob），这两个奖励天然不触发——公式完整实现，信号以数据为准；
- `identify_critical_steps`：按信用排序取 top3（贡献者）+ 最低 2（拖后腿者）。

### 5.3 A 轨：`extract_task_experience(task_id, reflection_entry)`

- 触发：每次 `maybe_promote`（开关开）时即时分析当前任务；
- 对象：当前 task_id 在 tools.jsonl 的行（`load_task_steps` 过滤，兼容 root_task_id）；
- 产出：步骤级经验 + LLM 整体提取（成功/失败因素、可复用模式），`kind="task"`；
- 回答的问题：**什么样的任务步骤模式值得进化**（决策参考）。

### 5.4 B 轨：`consume_pending_cycles(limit=5)`（轨迹循环进化）

- 触发：每次 `maybe_promote`（开关开）批次消费，`_limit` 限制单次 LLM 花费；
- 游标幂等：`state/evolution_consumed.json` 记已消费最大行号——重复调用不重复分析（同批 3 行消费后第 2 次调用返回 0）；
- 消费对象：checkpoints 中 `cycle_outcome ∈ {absorbed, abandoned, no_op}` 且未消费的行 → 行内 `task_id` 重建**进化任务的执行轨迹** → 同一套评分 + LLM 提取；
- prompt 明示分析对象（"这是进化循环自身的轨迹——哪个阶段分析/构建/验证贡献或失败"）；
- 回答的问题：**进化循环哪一步导致吸收/失败**（即论文"关键步骤识别"）；evolution 任务不会自我触发 promote，消费始终由普通任务带动。

### 5.5 产物文件

- `state/evolution_experiences.jsonl`：经验记录（ts/kind/task_id/objective/outcome/overall/steps/credits/critical_steps）；
- `state/step_credits.jsonl`：关键步骤明细（step_id/tool/credit/role=key|drag）；
- `state/evolution_consumed.json`：B 轨游标 `{"last_seq": n}`。

### 5.6 查询与建议

- `classify_objective(objective)`：关键词 → bug_fix / performance / capability / refactor / other；
- `query_similar_objectives(objective, kind, top_k)`：按 objective_type + kind 过滤，absorbed 优先排序；
- `suggest_evolution_strategy(objective, kind="cycle")`：无相似历史 → `{strategy:"standard", confidence:0.5}`；有 → `optimized` + success/failure patterns + recommended_tools（关键步骤工具统计）+ confidence（absorbed 比例）。

## 6. 多智能体规划器（MultiAgentEvolver）

### 6.1 三阶段与职责

| 阶段 | 角色 | 输入 | 输出 |
|------|------|------|------|
| `_analyze` | Analyzer | 任务轨迹 + reflection + objective_hint + 经验摘要 | root_causes[] + improvements[]（objective/rationale/impact） |
| `_research` | Researcher | top 改进 + 经验摘要 | approach / files_to_modify[] / implementation_steps[] / risks[] |
| `_verification_advice` | Verifier-advice | plan 草稿 + experience | verification_plan[]（预验清单） |

### 6.2 Plan schema（八字段）

`{schema_version:1, objective, root_causes[], approach, files_to_modify[], implementation_steps[], risks[], verification_plan[]}`

### 6.3 经验消费（失败回环的实现载体）

- `experience_digest`（与决策 prompt 同一份摘要：成功/失败模式 + 关键工具）注入 Analyzer 与 Researcher 的 `[HISTORICAL PATTERNS]` 段——方案生成避开已知失败路径；
- `experience.failure_factors` 含验证类关键词（verif/test/restart/构建/验证…）时，Verifier-advice prompt 附加"历史验证失败"强化提示；
- 无 digest / 无经验 → 段不出现（行为与无经验版本一致，测试断言）。

### 6.4 降级

- LLM 调用失败 → 结构化占位（analyze 空、research 空、verify 空），plan 保留 objective_hint；
- llm_client 为 None → 全占位，plan 可用（objective 仍在）；
- 桥接侧 plan 失败 → `evolution_plan=None` → request 无 plan 字段 → **与 V4 完全一致继续走**。

### 6.5 与文档原案四角色的对照

| 角色 | 原案 | 实现 |
|------|------|------|
| Analyzer / Researcher | 局部类 | ✅ 独立阶段（LLM 调用） |
| Builder | 模块内执行修改 | ⚠️ **现状承接**：既有的 evolution 任务 agent 执行（读 plan 文本自主迭代）——原案直跑会绕开 supervisor 门禁（reviewed commit / restart 验证 / 预算 / 3-fail breaker，100+ 测试保护） |
| Verifier | 模块内验证 | ⚠️ **现状承接**：restart 验证 + commit 门禁；板块新增 Verifier-advice（预验清单） |

## 7. 失败回环：为什么不做递归

### 7.1 原案"revise 递归"的含义

设计稿设想一次进化尝试内部：Analyzer → Researcher → Builder → Verifier → **失败回环**到 Analyzer（带失败信息）→ 新方案 → 再执行 → 再验证，直到成功或放弃——同一轮内"改-测-再改-再测"。

### 7.2 为什么不做（决策记录）

1. **架构**：Builder/Verifier 执行体在 supervisor 侧（门禁体系）；递归 = 把执行搬进 worker 后处理流程 = 绕开门禁，坏形状；
2. **等价物已存在**：跨 cycle 重试（同 objective ≤3 次指纹 cap，`objective_repeat_counts` BUG3 机制）+ 失败历史行；
3. **更强的替代**：经验持久化让教训影响**所有**未来同类型目标，而不是用完即弃。

### 7.3 实际实现的"回环"形态

```
失败 → checkpoint → B轨游标消费 → 步骤诊断入库
   ├─→ 决策侧：suggest → [EVOLUTION EXPERIENCE] 段（下次 promote）
   ├─→ 规划侧：[HISTORICAL PATTERNS]（Analyzer/Researcher）+ 验证强化
   └─→ 重试侧：## Lessons From Past Cycles（同目标 E2/E3 任务文本，
         失败因素 + 拖后腿工具 + 吸收模式）← 2026-09-02 补齐的最后一环
```

## 8. 经验消费点全景

| 消费点 | 触发 | 注入位置 | 回答的问题 |
|--------|------|---------|-----------|
| ① 决策 | 每次 promote（开关开） | 决策 prompt `[EVOLUTION EXPERIENCE]` | 该不该进化、选什么目标 |
| ② 规划-Analyzer | promote 为真 | `[HISTORICAL PATTERNS]` | 不重复已失败的改进方向 |
| ③ 规划-Researcher | 同上 | `[HISTORICAL PATTERNS]` | 方案避开失败路径 |
| ④ 规划-Verifier | 同上 | 验证失败模式 → 清单强化 | 验证多严 |
| ⑤ 重试 | 同目标再排 E2/E3 | 任务文本 `## Lessons From Past Cycles` | 重试避开上次的坑 |
| ⑥ 远期 | 任意未来 promote | 经验库按 objective_type 持久匹配 | 教训永不过期（jsonl 跨会话） |

## 9. 开关与模型

- **开关读取链**：settings.json 显式值 > 环境变量 > 默认 false（`_settings_flag_enabled`，UI 切换免重启）；`.env` 方式已验证；
- **实验对齐**：`run_evolution_arm.py` 的 V2/V3 臂已含 `OUROBOROS_MULTI_AGENT_EVOLVER=true`（spec §10.2 约定名），零改动生效；`SKILL_EVOLUTION` 待 Phase 3（无 getter，环境变量设置无害）；
- **模型**：经验提取/决策/规划器/执行全主槽位；`model=""` 缺陷修复记录——空 model 会解析为 `(openrouter, "")` 真实调用必失败，已改为显式 `_default_main_model()`（env > SETTINGS_DEFAULTS["OUROBOROS_MODEL"]），测试 `test_layer_calls_use_explicit_main_model_slot` 锁定；
- **light 槽位**：未配置自动回落主模型（`get_light_model()` 实证），不需要在 .env 指定。

## 10. 测试与验证

### 10.1 `tests/test_evolution_layer.py`（25 例）

- **开关**：默认关 / env true；
- **评分核心**：成败组合、快/省奖励、critical steps top3+低2、`classify_objective` 关键词；
- **存储与查询**：store/load 往返、step_credits 落盘、query 按类型+kind 过滤、suggest 无历史 standard / 有 cycle 历史 optimized（含 recommended_tools）；
- **双轨**：A 轨（轨迹重建+kind=task+LLM call_type 观测）、空轨迹返回 None；B 轨（3 行消费+游标推进+重复调用 0+skips 非终态）；
- **规划器**：plan 八字段 schema、无 LLM 降级、验证强化（prompt 含 verification-stage failures）、`[HISTORICAL PATTERNS]` 注入有/无两态、主槽位锁定；
- **桥接**：开关关时 request 无 plan + 决策 prompt 段存在（digest 空态）；开关开时 A+B+决策+规划全链（决策 prompt 含 cycle 失败模式、request 含 evolution_plan、游标推进）；
- **campaign/任务文本**：apply_pending_request 挂载 plan；build_evolution_task_text 有/无 plan 两态；`## Lessons From Past Cycles` 注入 + 开关关不注入。

### 10.2 回归范围

`test_post_task_evolution.py`（25 例）、`test_evolution_redesign.py`、`test_evolution_status.py`、`test_smart_router.py`（21）、`test_harness_tree.py`（24）、`test_context.py`——全绿。

### 10.3 真实 LLM 冒烟（`scripts/live/evolution/evolution_layer_live.py`）

- 遵循 scripts/live 惯例：MANUAL 头注、settings 非空才覆盖（.env 激活方式）、开关强制 true、temp drive、LLMClient 真实调用；
- 流程：构造 synthetic tools.jsonl（任务轨迹 + 历史循环轨迹）+ checkpoint + reflection → Track-A 提取（步骤/信用/LLM 整体）→ Track-B 消费（游标推进）→ suggest 策略 → 规划器完整 plan → 逐段打印产物；
- **不做**完整 campaign 闭环（server + restart + commit 属于 `run_evolution_arm.py` 领域，成本高）；
- 运行：`set -a; source .env; set +a && python scripts/live/evolution/evolution_layer_live.py`。

## 11. 决策记录（为什么这样做）

| 决策点 | 选项 | 结论 | 理由 |
|--------|------|------|------|
| 开关粒度 | 2 个 / 1 个 | **1 个**（`OUROBOROS_MULTI_AGENT_EVOLVER`） | 数据流同链（提取→消费）；实验单因子（V2 进化层开关）；spec 已约定名 |
| 执行形态 | 全编排 / **worker 侧规划器** | 规划器 | 尊重 V4 门禁体系；Builder/Verifier 现状承接；最小侵入 |
| 信用分配对象 | 任务轨迹 / 循环轨迹 | **双轨（A+B）** | 文档原案 `cycle_result.trace` 即为循环轨迹（B 为本意）；A 轨补充决策参考；同一评分函数零额外成本 |
| 失败回环 | intra-cycle 递归 / **跨 cycle 经验注入** | 经验注入 | 递归绕门禁；经验持久化影响所有未来同类型目标 |
| 轨迹文件 | 3 个 jsonl / **2 个** | 2 个 | `task_trajectories.jsonl` 冗余（轨迹已在 tools.jsonl） |
| 模型 | 各环节自选 / **全程主槽位** | 主槽位 | 实验单模型归因约束 |

## 12. 与实验的关系与后续

- **V2/V3 臂已可开**：`OUROBOROS_MULTI_AGENT_EVOLVER` 已实现（`SKILL_EVOLUTION` 待 Phase 3）；建议四臂同语料同配置跑（唯一差异=开关组合）→ TB 89 条 pass@5 统一验收；
- **不足 6 搁置**：决策已通过 `[EVOLUTION EXPERIENCE]` 段间接获得历史经验（收益边际）；后续需要时按 PAPER P1 项做（基于 checkpoints 成功率动态重写决策 prompt）；
- **L4 自动调优路线**：经验库（experiences/step_credits）即未来闭环的原料——工具瘦身（recommended_tools 统计）、权重校准（per-kind 吸收率）、分支参数调优（quantified confidence）；
- **观测点**：`state/evolution_experiences.jsonl` 的 kind/outcome 分布、`evolution_consumed.json` 游标、checkpoint 历史——实验报告可量化"经验库增长与吸收率"的相关性。