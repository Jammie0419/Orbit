# 进化冒烟实验完整分析（第 7 轮）+ 第 8 轮 / 真实实验执行计划

> 版本：v1.0（2026-09-05）
> 数据来源：第 7 轮冒烟真实运行（`/home/lzm/bench_runs/arms/smoke_test/` + `/tmp/smoke_v6.log`）
> 配套：[GAIA_EVOLUTION_CORPUS_RUNBOOK.md](./GAIA_EVOLUTION_CORPUS_RUNBOOK.md)、[SKILL_EVOLUTION_BOARD.md](./SKILL_EVOLUTION_BOARD.md)、[PAPER_DRAFT.md](./PAPER_DRAFT.md)

---

## 第一部分：第 7 轮冒烟实验全记录与分析

### 1. 实验配置

| 项 | 值 |
|---|---|
| 语料子集 | 11 条（从 130 条全 C 语料抽取：10 条厚轨迹 + 1 条零工具薄轨迹；L1×5 / L2×4 / L3×2） |
| 会话目录 | `/home/lzm/bench_runs/arms/smoke_test/`（clone + data + deploy_ws） |
| 模型 | mimo-v2.5（live settings 5 槽全部指向：main/light/heavy/fallback/review） |
| cadence | `every_n:2`（冒烟加速；正式实验为 every_n:5） |
| 预算 | TOTAL_BUDGET=$20、campaign-timeout=240s（后改默认 600）、max-absorbed=2 |
| 开关 | V3 全开：SMART_ROUTING / SMART_MEMORY / MULTI_AGENT_EVOLVER / SKILL_EVOLUTION |
| 战役执行契约 | 注入 promote 请求 objective（必须改代码+git 提交、禁 journal 工具） |

### 2. 会话启动机制（一次性动作）

1. **隔离克隆**：从主仓库 `git clone` → `checkout -B ouroboros` → `git remote remove origin`（隔离红线：进化改的是克隆，主仓库与远端永不接触）；
2. **隔离数据根**：生成 data/ + settings.json（写入 4 个臂开关 + 持久进化目标 + cadence）；
3. **隔离服务器**：12 个 worker 启动、supervisor 就绪、独立端口；
4. **模型槽确认**：driver 打印 `main/light/heavy 全部 mimo-v2.5`（模型一致性加固的产物）。

### 3. 逐条记录的完整旅程（每条 8 步）

以 record 1（2023_level1:36，YouTube 视频任务）为例：

```
① 种子化：该任务当年的 37 次工具调用 → 写入会话 tools.jsonl（task_id=2023_level1:36）
② 反思：mimo 生成 1510 字反思 → 3 条记忆动作 + 2 条 backlog
       （"视频字幕/抽帧失败" → 建议依赖预检，是后来 vision 预检战役的目标来源）
③ 进化决策（计数器到期）：决策器评估 → promote=True
       → 目标："Implement early strategy pivot detection when external services fail"
       → 写进化请求 + 注入战役执行契约
④ 技能提炼（同一步内并行）：轨迹达标（37 次调用 + 自修复 + 成功）
       → LLM 提炼技能 video-frame-extractor → 入库（pending、待背书）
⑤ supervisor 领取请求 → 开启战役（源码线开工）
⑥ 等待战役周期（240s 窗口，周期异步落账）
```

**9 条记录全程真实数据**（全部 promote=True、真实反思）：

| record | 任务 | 反思字数 | 记忆 | backlog | 种子化行 | 决策 |
|---|---|---|---|---|---|---|
| 1 | level1:36 视频 | 1510 | 3 | 2 | 37 | ✅ |
| 2 | level1:53 文件 | 1936 | 2 | 2 | 30 | ✅ |
| 3 | level1:48 | 2193 | 2 | 2 | 27 | ✅ |
| 4 | level1:34 临床试验 | 1585 | 2 | 2 | 12 | ✅ |
| 5 | level2:35 网页档案 | 1629 | 1 | 2 | 175 | ✅ |
| 6 | level2:51 搜索 | 2475 | 1 | 2 | 99 | ✅ |
| 7 | level2:18 论文 | 1527 | 2 | 0 | 96 | ✅ |
| 8 | level2:49 | 2296 | 3 | 2 | 77 | ✅ |
| 9 | level3:8 | 1695 | 3 | 1 | 49 | ✅ |

处理结果：records_processed=11/11、records_failed=0、promote=True ×9、reflection 全部真实落盘（logs/task_reflections.jsonl 存在）。

### 4. 三条线的最终结果

#### 4.1 技能线：8 个技能生成

| 来源任务 | 技能 |
|---|---|
| 视频任务 | video-frame-extractor |
| 文件任务 | python-file-executor |
| 临床试验任务 | ctgov-enrollment-fetcher |
| 网页档案任务 | archive-web-access |
| 搜索任务 | web-search-tool |
| 论文任务 | openreview-paper-query |
| 图片任务 | image-feature-count-analyzer |
| 检索任务 | fallback-data-retrieval |

全部 pending（未背书不可执行）；技能主题 = 任务领域浓缩，非拍脑袋命名。

#### 4.2 源码线：4 个真实代码提交，账本 5×no_op

**4 个战役周期**（checkpoint 记录）：

| 战役任务 | 目标 |
|---|---|
| e16250d4 | 外部服务失败时的策略切换检测 |
| 382d8534 | 搜索合成步骤 |
| 83f282e5 | 跨源提取的稳健工作流 |
| 7588ff0e | vision 模型可用性预检 |

**真实代码产物**（隔离 clone 的评审侧分支）：

| 提交 | 内容 |
|---|---|
| `42985a2b` feat(cross-reference) | 新增 `ouroboros/cross_reference.py`（多源提取+交叉引用模块） |
| `d88a0073` feat: search-synthesis | 搜索合成实现 |
| `72c59293` feat: lightweight preflight | 新增 `ouroboros/preflight.py`（vision/ffmpeg/媒体静态预检，提交信息引用真实失败 id） |
| `2ec561bb` feat: domain-aware browse_page fallback | 浏览工具 .gov/.org 域感知回退 |

**终态判定**：账本 5 行 `cycle_outcome=no_op`、HEAD 未移动（b3aecf5a）——战役 agent 真实写代码并提交到**评审分支**，但验收评审未通过（advisory/scope 评审需 light/review 模型槽，缺失导致评审包组装失败）→ 未合入 HEAD → no_op。**吸收通道是当前唯一未打通环节**（根因已修：live settings 5 槽 mimo）。

#### 4.3 部署线：60 条部署任务全部 HTTP 400（已修复）

- 4 个技能（video-frame-extractor / python-file-executor / ctgov-enrollment-fetcher / archive-web-access）已背书（owner_attestation + clean review 绑定内容哈希）；
- 60 条部署任务（4 技能 × 15 条）提交时全部 `HTTP 400 Bad Request`；
- **根因**（已定位并修复）：`workspace_admission.validate_workspace_root` 要求任务工作区**必须是 git worktree 根**（`git rev-parse --show-toplevel` 等于该目录）——deploy_ws 目录未 git init，全部被拒；
- **修复**：`_deploy_ws_setup` 现在对每个部署工作区 `git init`（实验专用目录，无外部影响）；已验证：未 init → `WorkspaceRootError`，init 后 → 通过。

### 5. 双轨归因分析（Track A / Track B）

#### 5.1 Track A（任务轨）——冒烟中真实运转 ✓

机制：每条记录 → 种子化轨迹写入会话 tools.jsonl → `TrajectoryExperienceLearner.load_task_steps(task_id)` 读取 → 逐步骤信用评分（成功/错误/效率）→ 经验记录 + 关键步骤（credit top3 / drag bottom2）→ 供决策与技能生成。

第 7 轮实测：

| 证据 | 数值 | 样例 |
|---|---|---|
| `state/evolution_experiences.jsonl` | **10 行 kind=task** | `{"kind":"task","task_id":"2023_level1:36","objective":"...视频...","overall":{"objective_type":"capability","objective_complexity":"high","success_factors":["browse_page for retrieving web content","web_s..."}}` |
| `state/step_credits.jsonl` | **50 行步骤信用** | `{"kind":"task","task_id":"2023_level1:36","step_id":1,"tool":"browse_page","credit":0.0361,"role":"key"}`；step 2 run_command key；step 4 web_search drag |
| 反思/记忆/backlog | 全记录 | 每条 mem/backlog 真实写入 |

分析：经验与信用分配在冒烟中**真实产生并被记录**——record 1 的 critical_steps 标注（browse_page/run_command 为 key、web_search 为 drag）与任务实际执行路径一致；objective/complexity/success_factors 由 LLM 提取（mimo），轨迹归纳有语义。

#### 5.2 Track B（循环轨）——冒烟中未观察到消费，列为第 8 轮验证点

机制：战役周期落账（`evolution_checkpoints.jsonl` 的 cycle_outcome 行）→ 游标（`state/evolution_consumed.json` 的 last_seq）幂等消费 → 用 checkpoints 行的 task_id 重建**战役自身轨迹**（E1 任务的 tools.jsonl 行，如 e16250d4 的 90 次调用）→ 同一套信用评分 → `kind=cycle` 经验 → "这次进化失败在哪一阶段"可归因。

第 7 轮实测：**evolution_consumed.json 不存在**——账号 5 行周期虽落（no_op），但 Track B 的游标消费未触发（原因候选：周期终态行出现时间晚/游标文件初始化时机/收尾抢跑）。诚实结论：**Track B 的端到端消费在冒烟中未验证**，其机制依赖的输入（checkpoint 终态 + 战役轨迹）都已确认存在，属"管线已就位、消费待验证"状态——列入第 8 轮检查点。

### 6. 第 7 轮问题清单与修复状态

| # | 问题 | 根因 | 状态 |
|---|---|---|---|
| 1 | 模型未接通（第一轮）：反思全占位 | 未 source .env（模型名回退 grok）+ Clash 代理对 opencode.ai TLS 失败 | ✅ .env 激活 + 去代理直连 |
| 2 | 残留进程共享会话目录 | TaskStop 未杀 server 进程族 | ✅ 进程族清理方法 |
| 3 | promote/技能块整场不执行 | 开关 getter 读环境变量不读 settings 文件 | ✅ runner 注入开关 env |
| 4 | 战役 agent 只调研不改码 | 执行契约没流进战役任务描述 | ✅ 契约注入 request objective |
| 5 | 战役提交被评审卡死 no_op | light/review 槽缺模型（回退 gemini 无凭据） | ✅ live settings 5 槽 mimo（下轮生效） |
| 6 | 部署任务 60×400 | 工作区非 git worktree 根 | ✅ git init 修复+验证 |
| 7 | campaign-timeout 假警报 | 240s 窗口 < 实际周期 | ✅ 默认 600s |
| 8 | 技能门槛偏松（72% 生成） | MIN_TOOL_CALLS=5 | ✅ 按语料分布校准为 8 |
| 9 | 进程/环境杂项 | — | ✅ 模型一致性启动校验、统一部署窗口 |

### 7. 结论（哪些已真、哪些待验证）

**已真实验证**：模型驱动全链路（反思/决策/战役/技能）、种子化、反思→记忆→backlog、技能生成（8 个）、promote 决策（9/9）、战役执行与代码产物（4 个模块提交）、评审拒绝链路（no_op 如实记录）、Track A 归因（10 经验 + 50 信用）、部署背书。

**待验证（第 8 轮）**：absorbed 提交（评审链修复后）、部署任务真实执行与前后测 Δ、Track B 游标消费。

---

## 第二部分：第 8 轮计划（明天执行）

### 目标
完整闭环验收：**absorbed 提交出现 + 部署真实执行（前测）→ GEPA（若 nudge 到期）→ 后测 → Δ**。

### 配置（全部新代码生效）
- 语料：11 条冒烟子集（与第 7 轮同，便于对照）
- live settings：5 槽 mimo（/tmp/live_settings_smoke.json 已更新）
- cadence every_n:2、budget $20、campaign-timeout 600、min_tool_calls=8（新门槛，子集内候选可能变少——如实观察）
- 统一部署窗口（新逻辑）：语料喂完 → wait_for_absorb → 部署窗口（背书+前测+后测）

### 步骤与检查点
1. 干净会话启动（清理残留进程 + rm session 目录）；
2. 喂 11 条（promote/战役照常）；
3. **检查点①**：战役账本是否出现 `cycle_outcome=absorbed` + commit_sha（评审链修复生效）；
4. **检查点②**：部署窗口触发（deploy_log 状态不再是 400，出现 completed/error 真实分布）；
5. **检查点③**：skill_stats.json 有 execution_count/success_rate（前测数据）；
6. **检查点④**（若 nudge 到期）：GEPA 事件（skill_evolution_history）+ 版本提升 → 后测 rerun；
7. 收尾：tag、session_ledger、analyze_session 汇总。

### 验收标准
- 至少 1 个 absorbed 提交（或如实记录评审仍拒的原因）；
- 部署任务出现真实执行记录（非 driver_error）；
- 前后测 Δ 落账（或如实记录"变异未发生/Δ=0"）。

---

## 第三部分：真实实验（130 条）执行计划

### 1. 总设计

| 项 | 值 |
|---|---|
| 语料 | 130 条全 C（evolution_corpus/gaia_corpus_2026-09-04.jsonl） |
| cadence | `every_n:5`（约 26 次进化评估） |
| 模型 | mimo（5 槽） |
| 臂 | V0（基线）+ V3（全开）——第一期主对比；V1/V2 消融延后 |
| 预算 | 每臂 TOTAL_BUDGET ≥150；分批多次会话 |
| 技能门槛 | ≥8 次调用 + 自修复 + 成功（预计 ~43 个候选） |
| 部署 | 语料喂完统一窗口：挑 2-3 个代表技能 → 前测 → GEPA → 后测 → Δ |

### 2. 用户"五个五个来"的执行模式（即时看结果）

每次执行 5 条（一个 cadence 周期），即时看到：

```bash
# 每次跑 5 条（progress 自动续）——命令模板
cd /mnt/disk2/lzm/ouroboros
source .env && unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
.venv/bin/python devtools/benchmarks/evolution/run_evolution_arm.py \
  --corpus /home/lzm/bench_runs/evolution_corpus/gaia_corpus_2026-09-04.jsonl \
  --arm V3 --session-dir /home/lzm/bench_runs/arms/V3 \
  --resume --cadence every_n:5 --budget 30 --campaign-timeout 600 \
  --deploy-tasks devtools/benchmarks/evolution/deploy_tasks/deploy_tasks.json \
  --max-absorbed 10
# 每批结束后即时查看：
tail -6 <session>/run_evolution_arm.log        # 本批 5 条的反思/决策
cat <session>/data/state/evolution_checkpoints.jsonl   # 本批触发的战役周期（目标/终态）
cat <session>/data/state/skill_generation_history.jsonl # 本批新增技能
cat <session>/data/state/evolution_experiences.jsonl   # Track A 经验（本批 5 条×kind=task）
cat <session>/data/state/step_credits.jsonl            # 步骤信用（key/drag）
```

每批 5 条的预期内容（**trace A/B 长什么样**）：

**Track A（任务轨，每批固定产生）**：
- 5 条 kind=task 经验记录（每条：objective/objective_type/complexity/success_factors/failure_factors/critical_steps）；
- 每条轨迹的步骤信用（5 条 × 平均 8-14 步 ≈ 40-70 行 credit 记录，key/drag 标注）；
- 5 次反思 + 记忆/backlog 落盘。

**源码线（每批第 5 条时评估）**：
- 第 5 条记录计数器到期 → 决策评估（综合本批 5 条的反思/backlog/赛道经验）→ promote True/False；
- True → 战役请求 → supervisor 异步执行（几批之后落账）；
- 战役周期落账后 → **Track B**：checkpoints 行被游标消费 → 战役自身轨迹（E1 任务的工具行）→ kind=cycle 经验（"本次进化改进到哪个环节失败"）→ 后续决策引用。

**每批即时可判**：本批技能是否新增、战役是否开、账本是否落、Track A 累计到多少条——进度完全透明。

### 3. 统一部署窗口：部署与进化**确实可以完全分开**

机制确认（新代码已实现）：部署窗口（`_run_deploy_window`）只在**语料全部喂完**（或预算/吸收数停机收尾）后触发，与进化（战役）互不干扰：

```
阶段 1（多批会话，你控制节奏）：喂 5 条 → 看结果 → 停/续 → ... → 130 条喂完
       —— 期间只积累：技能（pending 入库）、经验（Track A）、战役（异步）
阶段 2（最后一次会话收尾）：wait_for_absorb（等最后战役落账）→
       统一部署窗口：挑 2-3 个代表技能 → 背书 → 前测（15 条/技能）→
       GEPA 变异（nudge 到期触发）→ 后测（15 条/技能）→ Δ → 收尾 tag/ledger
```

**分离的依据**：
1. 部署不需要语料中间状态（前后测只用部署任务集）；
2. 技能在喂料期间已全部生成（pending），部署窗口一次性处理；
3. 时间/预算可控（2-3 技能 × 30 次执行 ≈ 2-3 小时，分到最后一步）；
4. Δ 的对照干净（同一技能同一任务集，前后无其他变化）。

### 4. GEPA 有效性证明口径（为什么测 2-3 个代表足够）

| 层次 | 证据 | 回答的问题 |
|---|---|---|
| 直接因果 | 代表技能的前后测 Δ（同任务集同条件） | GEPA 变异是否提升技能表现（Δ>0 正证据；Δ≤0 如实归因） |
| 机制运转 | GEPA 事件链（候选→变异→接受/回滚→版本谱系）、变异素材=真实失败文本、B4 校准折扣 | 进化机制是否真实地针对失败定向改进 |
| 假设检验 | 方向性变异若有有效则任何技能可测出；2-3 个代表样本足以检验假设（全测=重复同一种检验，只烧预算） | 结论不依赖数量，依赖对照设计 |

### 5. 验收产出

- 表 4-3：吸收数/每吸收成本/通用层占比、技能 Δ、经验条数（analyze_session.py）；
- 图 4-1：累积吸收曲线、技能事件时间线、成本曲线；
- 表 4-4：Terminal 评测 V3 vs V0（1780 trials）；
- 全部如实记录，负结果不粉饰。

---

## 明天执行清单

1. 跑第 8 轮冒烟（第四部分配置）→ 验收 absorbed / 部署 / Δ；
2. Track B 游标消费专项检查（若未触发，定位 reason 后修复）；
3. 冒烟通过后：git 提交本轮全部 devtools/docs 改动；
4. 真实实验 V0/V3 分批复跑（按第三部分模式，你控制五五节奏）；
5. Terminal 评测与论文数据填充。
---

## smoke_test_fix 会话收官（2026-09-13）：首个 absorbed 达成

第十轮冒烟保存原样，`bench_runs/arms/smoke_test_fix` 按进化顺序逐环节修复验证。会话以 **absorbed_cycles_done=1** 收官（历史合计 cycles=9、absorbed=1、no_op=13、成本 $0，absorbed 提交 `432237728995` = media.py + tests 共 +329/-0，零发布面触碰）。

### 环节-证据映射表

| # | 机制环节 | 状态 | 证据（会话内可复核） |
|---|---|---|---|
| 1 | 语料种子化 | ✓ | `state/seeded_tasks.json`（第十轮 10 条）；决策 prompt 正常引用 |
| 2 | 反思 | ✓ | `logs/task_reflections.jsonl` 22 条真实反思 |
| 3 | 记忆动作/backlog | ✓ | `memory/knowledge/` agent 自写条目（tool_registration、test_authoring 等） |
| 4 | Track A 经验+步骤信用 | ✓ | 经验账本 28 行（14 task）；信用分配 135 条（key 74/drag 61，和=3.715）；absorbed 周期 34 步全部带信用 |
| 5 | 决策（maybe_promote） | ✓ | cadence 计数推进；两轮请求文件被消费（含熔断后的目标切换） |
| 6 | Track B 周期消费 | ✓ | 回放：5 行旧 schema → 游标 5 → 5 条 cycle 经验；收官：游标 5→15，13 no_op + 1 absorbed 入账 |
| 7 | planner → evolution_plan | ✓ | 战役 JSON 携带 evolution_plan，周期任务文本可消费 |
| 8 | 契约注入 → 请求文件 | ✓ | 契约 v2（冻结面禁令+五步）在 objective 内；agent 全程只改 media.py/tests |
| 9 | supervisor 消费（apply_pending_request） | ✓ | owner_chat_id 闸门修复后消费成功 ×3；one-shot autostop 按设计复关 |
| 10 | 战役派发+执行 | ✓ | 15 战，执行 ok（degraded 仅早期 2 战） |
| 11 | plan_task（scope 评审前哨） | ✓ | 早期轮次 plan review 通过；收官目标按 `requires_plan_review=False` 精简 |
| 12 | commit_reviewed 正门 | ✓ | e7ab9a6a：enable_tools → advisory 预评审 → **commit OK**；动态必需集（b347d06b）让 scope pack 首次可组装（scope_review_review 调用 3 次） |
| 13 | request_restart → absorbed | ✓ | commit `432237728995` 落库 → 重启 → boot reconcile `restart_verified=True → absorbed`（agent_startup_checks.py:806）；重复计数按设计仅 absorb 清零 |
| 14 | finalize 补消费 → 账本 | ✓ | `consume_pending_cycles` 两轮补消费 9 行；`waiting_for_restart` 中间态行按设计跳过 |

### 本会话新增修复（已入库）

- `b347d06b` 动态必需集：冻结工件仅在 diff 相邻（touched/被提名/注册工具）时 required，其余 manifest-only；`OUROBOROS_SCOPE_DYNAMIC_REQUIRED=0` 可回退静态包。323 个相关测试全绿（atlas 20 + scope 150 + commit 链路 153）。修复 fixture 残留 9 行旧尸体代码（曾把 staged diff 顶掉导致误判）。

### 运营层事故与教训（非代码缺陷）— 已于 3f423435 修复为驱动层机制

1. **隔离 server 需要显式 env**：provider 凭据走 env 白名单透传（server_runner.py:96），新 shell 未 source `.env` 时启动即 "No supported provider"。**已修复**：runner 启动自动加载 `<repo>/.env`（现有环境变量优先，支持 `export KEY=` 行式）。
2. **隔离重启需外部驱动**：`restart_request` 事件在 EVENT_HANDLERS 中无消费者（产品里靠外部 launcher re-exec），隔离部署无人执行重启——周期永远停在 waiting_for_restart（本会话的 absorbed 是手动反弹换来的）。**已修复**：`IsolatedServer.maybe_bounce_for_restart()` 在信号出现且队列空闲时反弹一次 server（幂等键 = marker mtime + campaign updated_at），接入 `wait_for_absorb`（且排在 idle 退出之前——已暂存的 marker 不得被误判为"无事发生"）和 runner 逐记录边界（否则一个待重启周期会经 enqueue 闸门阻塞后续所有周期）。
3. **objective 重复熔断（3/3）**：同一 objective 连续 no_op 三次后战役自动暂停——这是 BUG3 防自维护回路的正确行为，换目标即恢复。设计内，不修。

### 弱模型能力层防护（P2 机制化，3f423435）

scratchpad 污染防护已机制化：`_scratchpad_hygiene()` 在每条记录边界和 finalize 运行，只中和**构造上可验证**的断言——契约关键工具（commit_reviewed/request_restart）"不可调用"类谎言、把设计内栅栏误述为"提交基建不可达"、以及"勿重试"类越权指令。原文保留在可见修正横幅之下（可审计、不静默删除），命中记录进 `memory/scratchpad_hygiene.jsonl`。

### 弱模型能力层新失败模式（cycle #11，7a745930）

模型在 schema 含 `commit_reviewed`（40 工具，03:10:44 起每轮均在）的情况下从未发出该函数调用：试图 CLI 子进程/import/shell commit，被栅栏拦后自我说服"工具不可调用"（progress 消息为证），最终以"基础设施不可达"收尾上报 owner。**ground truth 来自 observability payload 时间线：harness 无罪。** 触发因素之一是共享 scratchpad 被错误信念污染（"not callable" + 旧墙叙事 + "勿重试"），已做 owner 记忆手术（保留真实事实、标注 ibl 已修复）后换新目标一次通过。827K 字符系统提示下的工具注意力稀释是候选根因，值得在论文能力层分析中记录。
