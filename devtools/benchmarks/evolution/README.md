# run_evolution_arm.py — GAIA 进化语料离线回放驱动（模式 P）

对应 `EVOLUTION_EXPERIMENT_SPEC.md` §10.4 的**模式 P（离线回放，推荐）**：
不重新执行 GAIA 任务，直接把 `extract_evolution_corpus.py` 产出的语料逐条喂进
post-task 进化管道（反思 → 记忆/积压 → promote → 进化战役），战役由隔离会话的
supervisor 执行。代码与规格 §10.4 的伪代码一一对应。

## 前提

1. 语料已生成（`devtools/benchmarks/gaia/extract_evolution_corpus.py`，见
   `bench_runs/evolution_corpus/gaia_corpus_*.jsonl` + `traces/`）。新版语料的
   trace 是**生产级轨迹**（完整工具结果的生产视图 + 真实 reasoning_notes +
   生产 trace_summary + `meta.usage`/`meta.review_evidence`），驱动直接使用：
   `usage_dict` 从 `meta.usage` 组装（反思条目 round/cost 不再恒为 0/None）、
   `review_evidence` 原样传入；旧版语料（无 meta）自动降级兼容。
2. 本机有可用的 provider 配置：驱动按 `$OUROBOROS_DATA_DIR/settings.json` →
   `$OUROBOROS_SETTINGS_PATH` → `~/Ouroboros/data/settings.json` →
   `~/.ouroboros/settings.json` 的顺序找 live settings 拷贝
   provider/model/budget 键（不拷任何密钥），也可用 `--live-settings` 显式指定。
3. 预算：真实运行会调用模型（每条语料一次反思 + 每 5 条一次 promote 决策 +
   进化战役），请先 `--dry-run` 免费验证，再正式跑。

## 最小运行步骤

```bash
# 0) （可选）免费验证语料与管道的衔接：不启动服务器、不调用 LLM
#    （输出每条记录的 tool_calls/notes/rounds 覆盖统计 —— 语料质量一目了然）
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus bench_runs/evolution_corpus/gaia_corpus_2026-09-02.jsonl --dry-run

# 1) 正式跑 V0 会话（单臂；持久目录 bench_runs/evolution/V0/，自动建 clone + data）
#    （Linux 服务器建议 nohup 后台跑；所有输出同时落在 bench_runs/evolution/V0/run_evolution_arm.log）
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus bench_runs/evolution_corpus/gaia_corpus_2026-09-02.jsonl \
    --arm V0 --budget 200.0 --cadence every_n:5 --campaign-timeout 300

# 2) 中途断了（服务器重启/掉电）：同一会话目录加 --resume 续跑，只喂未处理的记录
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --session-dir bench_runs/evolution/V0 --resume

# 3) 会话结束的产物
#    bench_runs/evolution/V0/session_ledger.json      ← 周期计数/吸收 commit/成本/失败记录汇总
#    bench_runs/evolution/V0/data/state/evolution_checkpoints.jsonl  ← 每周期一条记录
#    bench_runs/evolution/V0/feed_progress.json       ← 喂料进度（--resume 的依据）
#    bench_runs/evolution/V0/clone/                   ← 会话后代码（含吸收 commit，tag: V0-evolved）
```

## 分批运行与 API 限流处理

如果你的 API 有速率限制或需要分批运行，使用 `--max-absorbed` 参数控制每批的战役数量：

```bash
# 批次 1：跑 10 个战役后自动停止（约 50 条语料）
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus bench_runs/evolution_corpus/gaia_corpus_2026-09-04.jsonl \
    --arm V3 --session-dir /home/lzm/bench_runs/arms/real_run \
    --cadence every_n:5 --max-absorbed 10

# 休息一会，让 API 恢复（5-10 分钟）

# 批次 2：resume 继续，再跑 10 个战役（总计 20 个）
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus bench_runs/evolution_corpus/gaia_corpus_2026-09-04.jsonl \
    --arm V3 --session-dir /home/lzm/bench_runs/arms/real_run \
    --cadence every_n:5 --max-absorbed 20 --resume

# 批次 3：继续跑完所有 26 个战役
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus bench_runs/evolution_corpus/gaia_corpus_2026-09-04.jsonl \
    --arm V3 --session-dir /home/lzm/bench_runs/arms/real_run \
    --cadence every_n:5 --max-absorbed 26 --resume
```

**工作原理**：
- `--max-absorbed N`：吸收的战役数达到 N 后，程序优雅退出
- 检查发生在每条记录处理之前，所以不会有"半处理的记录"
- 退出时进度已更新，`--resume` 会从下一条记录继续
- 安全：不会出现重复处理或状态不一致

**时间估算**（基于 smoke_test_14 实测）：
- 每个战役平均 30 分钟（23-44 分钟不等）
- 每条非晋升记录约 1.6 分钟（反思 + 记忆 + backlog）
- 130 条语料 × every_n:5 = 26 个战役
- 总计约 16-17 小时（可分批完成）

## 参数说明

| 参数 | 默认 | 说明 |
|---|---|---|
| `--corpus` | 最新 `gaia_corpus_*.jsonl` | 语料文件 |
| `--session-dir` | `bench_runs/evolution/V0` | 会话目录（`clone/` + `data/`）；目录已存在会拒绝并提示 |
| `--arm` | `V0` | 臂标签：V0（全关）/ V1（任务层）/ V2（进化层）/ V3（全开），按 §10.2 开关表注入 settings |
| `--source-repo` | 当前仓库 | throwaway 克隆的来源 |
| `--live-settings` | 自动回退链 | provider/model/budget 拷贝源（不拷密钥）；回退顺序见"前提"2 |
| `--resume` | 关 | 会话目录已存在时续跑（按 `feed_progress.json` 跳过后已处理记录） |
| `--cadence` | `every_n:5` | promote 决策节奏（§10.8-4：吸收少可先 `every_n:3` 验证管线） |
| `--budget` | `200.0`（USD） | 每会话独立总预算（§10.8-7 建议 ≥150） |
| `--campaign-timeout` | `300`（秒） | 每次 promote 后等待战役周期落账的轮询上限 |
| `--max-absorbed` | `10` | **分批运行关键参数**：吸收周期达到此数提前停止喂料。支持分批运行：第一次设为 10，resume 后设为 20，再 resume 设为 26。每次检查在记录处理前，不会有"半处理的记录"，resume 安全。 |
| `--dry-run` | 关 | 只校验语料→轨迹→摘要加载（零成本） |

**Arms 说明**：
- **V0**：基线（无特殊开关）
- **V1**：SMART_ROUTING + SMART_MEMORY（智能路由 + 智能记忆）
- **V2**：MULTI_AGENT_EVOLVER + SKILL_EVOLVER（多智能体进化 + 技能进化）
- **V3**：全部开启（推荐用于真实实验）

## 会话期间监控

### 快速状态检查

```bash
# 查看战役状态和成本
python -c "
import json, collections
p = 'bench_runs/evolution/V0/data/state/evolution_checkpoints.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8')]
print('条数:', len(rows))
print('outcome 分布:', dict(collections.Counter(r.get('cycle_outcome') for r in rows)))
print('总成本 $:', round(sum(r.get('cost_usd', 0) for r in rows), 2))
print('吸收 commit:', [r.get('commit_sha') for r in rows if r.get('cycle_outcome') == 'absorbed'])
"

# 查看最近的 git 提交
git -C bench_runs/evolution/V0/clone log --oneline -3

# 查看反思和 backlog 数量
wc -l bench_runs/evolution/V0/data/logs/task_reflections.jsonl
wc -l bench_runs/evolution/V0/data/memory/knowledge/improvement-backlog.md
```

### 详细日志分析

```bash
# 查看最新日志（实时跟踪）
tail -f bench_runs/evolution/V0/run_evolution_arm.log

# 查看每条记录的处理情况
grep "^\[run_evolution_arm\] ── \[记录" bench_runs/evolution/V0/run_evolution_arm.log

# 查看战役启动和完成
grep -E "\[战役#|campaign: 新周期|checkpoints:" bench_runs/evolution/V0/run_evolution_arm.log

# 查看技能生成
grep "\[技能\]" bench_runs/evolution/V0/run_evolution_arm.log

# 查看决策情况
grep "\[决策\]" bench_runs/evolution/V0/run_evolution_arm.log
```

### 使用 analyze_session.py 生成报告

```bash
# 生成完整的会话分析报告
python devtools/benchmarks/evolution/analyze_session.py \
    --session-dir /home/lzm/bench_runs/arms/real_run

# 报告包含：
# - 战役统计（周期数、吸收数、成本）
# - 代码改动统计（提交数、文件数、行数）
# - 技能生成统计（生成数、失败数）
# - 反思和 backlog 统计
```

## 日志输出格式

日志按论文 LEAP 的**算法 1 算子**组织（不再按数据来源打标签）。格式化代码在
`leap_report.py`（纯渲染：无 IO、不产生指标），驱动收集数值后按**三段时刻**发出，避免慢
provider 让运行看起来像卡死：

| 时刻 | 输出 |
|---|---|
| 记录开始（播种后） | 块头 + `②执行 轨迹播种 N 行` |
| 反思返回后（promote 前） | `②执行` 目标/轮次/摘要 + `④记忆`（记忆落库、backlog、技能资格） |
| promote 决策返回后 | `③归因` → `④记忆 +经验` → `⑤触发` → `⑥规划` → `⑨遗传(行为级技能)` → `[战役] …` → `⑦变异 开` |
| 战役终态被轮询到 | `⑨遗传 ⤷ absorbed/abandoned/no_op/infra_failed` → `⑪沉淀 checkpoints: …` |

```
━━ 记录  5/11 · 2023_level2:35 (L2) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 175 行
        ↓（静默数分钟＝反思 LLM 调用中）
 ②执行  τ  目标: … | 轮次 155 | 错误 16 | 标记 SHELL_EXIT_ERROR,TOOL_ERROR | 反思 1757 字
          摘要: …
 ④记忆  M  knowledge_write「task_planning」: … | scratchpad_append: … | 落库 2/2
          backlog 候选 2 | 新增 2（high 1 | med 1） | 技能资格 ✅ (ok)
 ③归因  E  信用 +5 步计分: 最高 browse_page 0.0061 | 最低 run_command 0.0023
          Track-A task=2023_level2:35 | 结果=task | 类型=capability(h) | 关键=browse_page(0.01)
 ④记忆  M  +1 经验（账本累计 5）
 ⑤触发  W  cadence 0/5 | LLM: promote ✅ 理由: …
 ⑥规划  P  目标: Add automatic capability pre-check… | backlog: ibl-e6e0f878cbe9
 ⑨遗传  H  技能生成: web-archive-text-extractor (task 2023_level2:35)
[战役]    第 1/1 个战役已提交请求
[战役]    达到战役上限 1，停止喂料（剩余 6 条记录未处理）
 ⑦变异  Δ  战役#1 开: "Add automatic capability pre-check…" (task 675e1043)
 ⑧选择  ✓  战役#1 ⤷ commit ✅ b2f0c13f40
 ⑨遗传  H  战役#1 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=2 周期=1 吸收=1 分布={'absorbed': 1, 'waiting_for_restart': 1} 成本=$0
━━ 里程碑 @记录5 ━━ 周期1 (吸收1, no_op0) | 技能4 | 经验5 | backlog开放7
 等待  ·  等待最后一个战役完成…
 等待  ·  300s · 战役进行中 · 调用 30 · 编辑 4 · shell 3 · 提交 3 · 参数错 2 · 闸门拦 2 · 最近 advisory_review
[isolated-server] restart signal: server busy — will retry (silenced until it changes)   ← 仅终端
━━ 会话收尾 · 臂 V3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ⑪沉淀  M  记录 5/11 | 失败 0
          吸收 1 | 放弃 0 | no_op 0 | 成本 $0
          账本分布 absorbed=1, waiting_for_restart=1
          吸收提交:
            b2f0c13f404c  feat: add tool preflight checks …
          clone b2f0c13f | tag V3-evolved
          ledger: <session>/session_ledger.json
```

**算子标（＝算法 1 步号）**：`②执行 τ` / `③归因 E` / `④记忆 M`（含 `+1 经验` 这一次写入）/
`⑤触发 W` / `⑥规划 P` / `⑦变异 Δ`（**代码侧**补丁，隔离克隆）/ `⑧选择 ✓` / `⑨遗传 H`
（代码级＝吸收提交；行为级＝技能生成）/ `⑪沉淀 M`（第 12 步：**结果已知之后**的账本写入——
所以它跟在战役终态行后面，而不是"发起战役的那条记录"末尾）。`①表达` 永不出现：隔离
runner 观察不到 agent 的路由，不做占位。

**四类行**：算子标行；`[战役]` / `[战役#N]` 战役命名空间；`等待 ·` / `运行 ·` 运行态行
（等待、心跳、收尾动作，**不带**算子标）；`[isolated-server] …` 是驱动的 server 助手裸
`print`——**只在终端，不进 `run_evolution_arm.log`**（同一段 busy 只报一次；实测日志文件
命中 0）。

**两套编号**（都对，含义不同）：
- `[战役] 第 N/M 个战役已提交请求` = **本 session 内**计数 / 本 session 的 `--max-absorbed`
  预算（resume 后按新的基线重新计数）；
- `⑧选择 战役#K`、`⑨遗传 战役#K` = **campaign 的 cycle 号**，跨 session 连续（同一 campaign
  文档承载连续的 cycle）。

**心跳**：状态没变就不重复输出，每 5 分钟补一条存活线；字段为 调用/编辑/shell/提交/参数错/
闸门拦/最近。

三个版本的完整预期输出（`--max-absorbed 1` / `--max-absorbed 2` / 先 `max=1` 再
`--resume --max-absorbed 2`）见
[`docs/orbit/EXPECTED_RUN_OUTPUT.md`](../../../docs/orbit/EXPECTED_RUN_OUTPUT.md)，
由真实渲染器生成，可逐行核对。

## 评审强度：两个开关（默认关闭，跑语料时保持默认）

语料跑**刻意保持默认**：让循环转起来、持续产出吸收，不被选择层打断。两个开关会改变方法
本身，若要启用必须四臂一致并重跑基线：

1. **`OUROBOROS_REVIEW_ENFORCEMENT=blocking`** —— 让"选择"算子**真的拦**。默认 `advisory`
   （`config.py`），所有阻断信号被降级为警告 + 一条 owner 可见的 `review_advisory_override`
   审计。实测证据：`PREFLIGHT_BLOCKED: New files added in ouroboros/ or supervisor/ but
   docs/ARCHITECTURE.md is not staged` 被降级后，提交在**未改该文档**的情况下落地。开启后
   提交失败率会上升——那正是 selection pressure，不是回归。
2. **`OUROBOROS_ADVISORY_REVIEW_ROUTE=agent_session`** —— 让 advisory 预评审**真的跑**。默认
   路由 `api` 需要 `ANTHROPIC_API_KEY`；在 BYO `openai-compatible` 环境下每次
   `advisory_review` 会自动 bypass，并记录
   `status=bypassed, reason="ANTHROPIC_API_KEY not set — auto-bypassed (advisory route=api)"`。
   `agent_session` 是 keyless 的 delegated 路由，**尚未在本机 xiaomi/openai-compatible 环境
   验证**，启用前先用单周期试跑。

**默认口径下，一次落地提交实际过了什么**：triad + scope 两道 LLM 评审（给出意见、不阻断）、
attribution / evolution authority / 重启收据校验（硬性），以及一次**被审计的** advisory
bypass。这些都有持久痕迹（`state/advisory_review.json` 的 attempts：`no_advisory` →
`advisory_review_required` → `succeeded`；`logs/events.jsonl` 的 `advisory_review_bypassed`、
`review_advisory_override`），所以写论文时可以如实报告评审强度，而不是笼统写"已评审"。

驱动另外会向隔离 server 注入三个 benchmark 专用开关：
`OUROBOROS_PRE_PUSH_TESTS=0`（语料提交不被本仓库自身的尺寸债普查挡住）、
`OUROBOROS_REQUIRE_ADVISORY_REVIEW=1`（拒绝 `skip_advisory_review=True` 这条调用级捷径；
advisory 工具必须被调用，其 bypass 会被审计）、
`OUROBOROS_DIE_WITH_PARENT=1`（隔离 server 树随 harness 生命周期结束，避免被硬杀的 launcher
留下孤儿进程继续写同一 drive root）。

## 本轮改动（2026-09-15）

**驱动/循环**
- `--max-absorbed` 真正生效：战役是异步创建的，计数改为"等战役出现后再数"
  （`account_promoted_campaign`），且上限判定对**每条记录**复查（原先只在 promote 决策分支
  里判，`promote=False` 的记录不会复查 → `第 0/1 个战役` 那种日志）。
- 一个战役独占执行：下一块的反思先等 commit 落定，再与**吸收**并行
  （`wait_for_campaign_execution`），记录头标注 `· 并行 战役#K 吸收中`。
- 停喂料会说明原因（撞上限 vs 语料喂完）；`_budget_reached` 在 `try` 之前绑定，避免启动阶段
  失败时把收尾文案变成 `NameError`。
- 日志按算子组织、三段发射、收尾块汇总；心跳仅变化时输出；bounce 的 busy 提示一段只报一次。

**演进账本（产品侧）**
- 被基础设施打死的无提交周期记为 `infra_failed`（附 `infra:<原因>`），**不再**计入目标重复
  计数、也不进 `dropped_objective_fps`（原先与"主动判断无需改动"的 `no_op` 无法区分）。
- replay 终态会回填该周期的 rounds/cost（boot 对账可能先于终态到达）；摘要现在能读到失败的
  原因。
- 反思输出能容忍单个非法 JSON 转义或裸控制字符（原先整块 memory actions 被丢弃）；仍不可
  解析时标 `memory_actions_parse_failed`，不再看起来像"模型主动留空"。

**进程/可观测**
- 隔离 server 及其 worker 的 stdout/stderr 落盘到会话目录旁（原为 `DEVNULL`：worker 的
  traceback 无痕消失）。
- 无价格目录的模型不再把 `$0.00` 当"available"记进 campaign（账本全局状态不动——它同时是
  重放安全闸门）。
- 孤儿防护：server 有优雅 SIGTERM/SIGINT 收尾路径（收掉整棵 worker 树）、fork 出的 worker
  重置继承的信号处理器、bench 启动的 server 武装 `PR_SET_PDEATHSIG`（双向实测：父被
  SIGKILL 时子随之死亡；不武装则存活留下孤儿）。
- 原先无人处理的 review 事件（`review_wave_budget_partial_unknown`）现在落成类型化行。

## 注意（规格 §10.8 常见坑）

- 会话 clone 的 origin 已被移除，self-mod 的 push 不可能污染 live 仓库（勿手滑加回）。
- `checkout -B ouroboros` 已由驱动完成；`safe_restart` 依赖该分支存在。
- **单条记录失败不会中断整轮**：驱动逐条 try/except，失败计入
  `feed_progress.json` 的 `failures` 与 ledger 的 `records_failed`（续跑时跳过失败记录）。
- **V2 / V3 进化层已实现并实测**（多智能体战役 / 技能进化，开关由 arm 注入）。
  注意：mimo 级模型的战役 agent 常见失败模式见 `EVOLUTION_SMOKE_ANALYSIS.md`。
- `server.stop()` 只在全部语料喂完且战役结束后调用（驱动已处理）。
- 会话目录是持久的（供溯源）：重跑请清理目录或换 `--session-dir`；
  断点续跑用 `--resume`（进度文件 `feed_progress.json`）。

## 常见问题与故障排查

### Q: 程序运行很慢，是不是卡住了？

**A**: 检查日志输出。正常流程：
- 每条记录处理约 1-2 分钟（反思 + 记忆 + backlog）
- 每个战役约 20-40 分钟（agent 探索 + 实施 + 测试 + 提交）
- 战役完成后，重启信号检测约 5 秒（已优化）

如果长时间无输出，检查：
```bash
# 查看最新日志
tail -20 bench_runs/evolution/V0/run_evolution_arm.log

# 检查 server 进程
ps aux | grep server.py

# 检查 checkpoint 状态
python -c "
import json
rows = [json.loads(l) for l in open('bench_runs/evolution/V0/data/state/evolution_checkpoints.jsonl')]
print('最新 checkpoint:', rows[-1] if rows else '无')
"
```

### Q: API 限流或失败怎么办？

**A**: 使用 `--max-absorbed` 分批运行：
1. 第一批：`--max-absorbed 10`（约 5 小时）
2. 休息 5-10 分钟
3. 第二批：`--max-absorbed 20 --resume`（再约 5 小时）
4. 第三批：`--max-absorbed 26 --resume`（最后约 2 小时）

每次 resume 都从上次停止的地方继续，不会有重复或冲突。

### Q: Resume 后会重复处理已完成的记录吗？

**A**: 不会。`--resume` 机制：
- 检查在每条记录处理**之前**
- 已处理的记录（无论成功或失败）都会跳过
- 进度文件 `feed_progress.json` 记录 `last_index`
- Resume 从 `corpus[last_index:]` 开始

**安全场景**：
- ✅ 正常终止后 resume：从下一条记录继续
- ✅ 战役中途强制终止：进度未更新，会重试当前记录（但之前的部分工作保留）
- ❌ 不要手动修改 `feed_progress.json`，会导致状态不一致

### Q: 如何查看进化产生了什么代码改动？

**A**: 查看 clone 目录的 git 历史：
```bash
cd bench_runs/evolution/V0/clone

# 查看所有进化提交
git log --oneline --grep="feat" --grep="fix"

# 查看具体某个提交的改动
git show <commit-sha>

# 对比起点和当前状态
git diff V0-evolved~10..V0-evolved --stat
```

### Q: 如何评估进化效果？

**A**: 使用多维度评估：
```bash
# 1. 查看 session_ledger.json
python -c "
import json
ledger = json.load(open('bench_runs/evolution/V0/session_ledger.json'))
print('总周期:', ledger.get('cycle_outcome_counts', {}).get('total', 0))
print('吸收数:', ledger.get('absorbed_count', 0))
print('吸收率:', f\"{ledger.get('absorbed_count', 0) / max(1, ledger.get('cycle_outcome_counts', {}).get('total', 1)) * 100:.1f}%\")
print('总成本: $', ledger.get('total_cost_usd', 0))
"

# 2. 查看代码改动统计
git -C bench_runs/evolution/V0/clone log --oneline V0..V0-evolved | wc -l
git -C bench_runs/evolution/V0/clone diff --stat V0..V0-evolved | tail -1

# 3. 查看技能生成统计
python -c "
import json
rows = [json.loads(l) for l in open('bench_runs/evolution/V0/data/state/skill_generation_history.jsonl')]
print('技能生成数:', len(rows))
print('成功:', sum(1 for r in rows if r.get('status') == 'success'))
print('失败:', sum(1 for r in rows if r.get('status') == 'failed'))
"
```

### Q: 如何清理失败的会话重新开始？

**A**: 
```bash
# 方法 1：删除整个会话目录
rm -rf bench_runs/evolution/V0

# 方法 2：保留数据，只重置进度
rm bench_runs/evolution/V0/feed_progress.json

# 方法 3：新建会话目录
python -m devtools.benchmarks.evolution.run_evolution_arm \
    --corpus ... --session-dir bench_runs/evolution/V0_new
```

**注意**：删除会话目录会丢失所有进化成果（代码改动、技能、经验）。建议先备份：
```bash
tar -czf backup_V0.tar.gz bench_runs/evolution/V0
```

## 移植到 Linux 服务器

```bash
# 1. 在服务器上准备语料（runs 源可用精简包，排除密钥；要 100% 生产级轨迹重建
#    需带 observability：--pack-observability，体积大头。不带则服务器上重建
#    自动降级为 tools.jsonl 视图，语料可用但保真度低）
python devtools/benchmarks/gaia/extract_evolution_corpus.py \
    --runs-root <runs根目录> --pack-source <runs精简包目录> --pack-observability  # 本机执行一次
rsync -av <runs精简包目录> server:/home/<user>/gaia_runs/

# 2. 服务器上重新生成语料并校验跨机确定性（哈希应与本机一致）
export OUROBOROS_GAIA_RUNS_ROOT=/home/<user>/gaia_runs
python devtools/benchmarks/gaia/extract_evolution_corpus.py   # 默认输出 bench_runs/evolution_corpus/
sha256sum bench_runs/evolution_corpus/gaia_corpus_*.jsonl     # 对比本机哈希

# 3. 后台跑会话（live settings 找不到时用 --live-settings 显式指定）
nohup python -m devtools.benchmarks.evolution.run_evolution_arm \
    --arm V0 --live-settings /home/<user>/<live>/settings.json \
    > bench_runs/evolution/V0/nohup.out 2>&1 &

# 4. 断线恢复
python -m devtools.benchmarks.evolution.run_evolution_arm --session-dir bench_runs/evolution/V0 --resume
```
## 技能部署（run_skill_deploy.py，与 arm 解耦）

arm 跑完语料后的收尾流程：`wait_for_absorb`（等在途战役，最长 30 分钟）→ 打
`<arm>-evolved` 标签 → 写 `session_ledger.json` → 退出。**默认不跑部署窗口**；
要顺带部署需显式加 `--deploy`（V2/V3）。技能部署的正常入口是独立脚本：

```bash
# 前测：修 frontmatter + 重背书 + 跑固定任务集（建议先挑 2 个技能，约 1 小时/技能）
python devtools/benchmarks/evolution/run_skill_deploy.py \
    --session-dir /home/lzm/bench_runs/arms/smoke_test_10 \
    --skills clinical-trial-enrollment-finder,openreview-neurips-query --re-attest

# 后测：GEPA 变异（管线 nudge 触发，evolution_version 提升）后重跑同一任务集出 Δ
python devtools/benchmarks/evolution/run_skill_deploy.py \
    --session-dir <session> --skills <同前> --phase post
```

流程：`--fix-frontmatter`（自动补 `runtime:` 字段，默认 python3）→ `--re-attest`
（重背书，刷新内容哈希绑定，解除 edited-since-review 拦截）→ 启动隔离 server
（cadence=off，部署会话零战役干扰）→ 每技能 × 15 条固定任务（`deploy_tasks.json`，
与 GAIA/TB 零重叠）→ 写 `deploy_log.jsonl` 与 `skill_stats.json`。

产出：`skill_stats.json`（执行数/成功率/版本）+ `deploy_log.jsonl`（前后测分布）
+ 部署状态机 `deploy_state.json`（none → baseline → post）。

### 部署任务集（2026-09-12 修订）

每技能 13 条运行，三类口径（deploy_log 的 kind 字段区分；其中 edge+domain=10 条强制执行技能，正好满足 GEPA 变异门槛 >=10 executions）：

- **edge ×3**（技能强制）：空输入/超长/非法编码，测技能自身鲁棒性；
- **domain ×7**（技能强制）：按技能 SKILL.md 由 LLM 生成的领域任务
  （`run_skill_deploy.py --gen-domain-tasks`，存 `<skill>/deploy_tasks.json`）——
  测技能真实价值，是 GEPA 前后测 Δ 的主口径；
- **regression ×3**（中性措辞，不强制用技能）：通用任务回归，测技能不拖累基线。

已修复的历史问题：① 通用任务原措辞强制"使用技能 <name>"，领域技能做不了
CSV 清洗类任务、agent 改用普通工具后成功却被归因到技能（归因噪声）——已改
中性措辞；② 生成端 `render_skill_manifest` 漏渲染 `runtime` 字段导致全部技能
exec 被拦——已补（存量技能由 `--fix-frontmatter` 补齐）。
