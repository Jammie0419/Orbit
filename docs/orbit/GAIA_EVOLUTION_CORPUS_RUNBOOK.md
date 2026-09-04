# GAIA 进化语料提取与四臂对比实验全流程手册（傻瓜式）

> 版本：v1.0（2026-09-04）
> 配套：[PAPER_DRAFT.md](./PAPER_DRAFT.md)（论文稿，实验设计见其第 4 章）、[EVOLUTION_EXPERIMENT_SPEC.md](./EVOLUTION_EXPERIMENT_SPEC.md)（四臂规格）
> 原则：每一步都给「命令 + 预期输出 + 检查点」，照着跑即可；所有数据操作只读源数据，不删不改。

---

## 0. 这份文档干什么

把**已清洗的 GAIA 数据集**（`ouroboros_v0_merged_mimo/`，165 条：130 C / 35 I）提取成**进化对比实验语料（130 条全成功）**，并打通**四臂实验（V0–V3）**的完整运行链路，产出论文第 4 章所需的全部表格与图表数据。

**最终验收（一句话）**：`gaia_corpus_<date>.jsonl` 恰好 130 条、全部 C、分层 43/70/17、与 `summary.csv` 的 C 集零差集、每条 trace 可加载；四臂 `--dry-run` 全过；真实四臂跑完产生全部观测文件。

---

## 1. 已有资源盘点

| 资源 | 路径 | 角色 |
|---|---|---|
| **提纯后的数据集**（评分/层级/答案权威） | `/home/lzm/bench_runs/gaia_results/valid results/ouroboros_v0_merged_mimo/` | `samples/<uuid>/result.json`（任务记录）、`inspect_logs/*_consolidated.json`（评分 C/I + 层级）、`summary.csv`（uuid/层级/判定/答案）、`merge_provenance.json`（溯源） |
| **原始执行段（trace 库）** | `/home/lzm/bench_runs/gaia_results/2026-08-22__20-23-25_validation_all/` 等 7 段 | 每任务独立 drive：`ouroboros_data/state/headless_tasks/<hex>/data/logs/tools.jsonl` + `task_results/<hex>.json` + observability（全量 payload） |
| **桥接字段** | 每条 `samples/<uuid>/result.json` 的 `task_id`（16hex）+ `child_drive_root`（绝对路径，指向上述源段） | **trace 定位的权威指针**——extractor 据此从 merged 直达源段 per-task trace |
| **extractor 脚本** | `/mnt/disk2/lzm/ouroboros/devtools/benchmarks/gaia/extract_evolution_corpus.py`（1408 行） | 语料抽取（现状：只支持多 run 目录、默认 14 失败/26 成功——**需要 4 处改造**，见 §6） |
| **四臂驱动器** | `/mnt/disk2/lzm/ouroboros/devtools/benchmarks/evolution/run_evolution_arm.py`（516 行） | Mode-P 离线回放：逐条喂语料 → reflection → maybe_promote → 战役（**需要 2 处补丁**，见 §7） |
| **隔离服务器** | `devtools/benchmarks/common/server_runner.py`（IsolatedServer） | 战役/部署任务的真实执行环境 |

**路径关系图（务必记住）**：

```
merged/samples/<uuid>/result.json
   ├── task_id = 16hex（ouroboros 内部 id）
   ├── child_drive_root = /home/lzm/bench_runs/gaia_results/<段>/ouroboros_data/state/headless_tasks/<hex>/data
   └── （评分/层级在 merged 的 consolidated inspect log；uuid 判定在 summary.csv）
                          │
                          ▼
   <child_drive_root>/logs/tools.jsonl        ← 该任务的真实工具轨迹（行式，生产 schema）
   <child_drive_root>/task_results/<hex>.json ← trace_summary / usage / llm_call_refs
```

注意：`child_drive_root` 指向 `gaia_results` **根下**的原始段（不在 `valid results/ouroboros_v0` 拷贝里），一切以该绝对路径为准；`valid results/ouroboros_v0`（7 段拷贝）可作**第二路线对照**（§6.3）。

---

## 2. 各板块的数据通道：语料要为谁供什么

四臂里共 5 个板块 + 基础管线，各自消费的数据通道如下。**语料正确性的本质 = 每个通道需要的字段在提取后仍然在**。

| 消费方 | 数据来源 | 需要的字段 | 离线回放期是否工作 | 语料要保证什么 |
|---|---|---|---|---|
| reflection（四臂都跑） | 语料 trace（`load_trace_from_path`） | tool_calls 的 `is_error`/`result_preview`/`status`、reasoning_notes、trace_summary、usage、review_evidence | ✅ 直接消费语料 | **错误行必须保留**（失败信号全在这）；usage 非空（否则成本语义丢失） |
| maybe_promote 决策（四臂） | reflection_entry + backlog + 账本摘要 | `id`、`task`（文本） | ✅ | id/task 文本完整；反思由 trace 派生 |
| 战役（四臂基础机制；V2/V3 增强） | 隔离服务器内真实执行 | 无语料字段 | ✅（真实运行） | 不需要语料字段 |
| 经验学习 Track A（V2/V3） | **会话 drive 的 `logs/tools.jsonl`**（按 task_id） | `task_id`/`tool`/`is_error`/`status`/`result_preview`/`args` | ⚠️ 需种子化补丁（§7.1） | trace 行必须以生产 schema 可写回 tools.jsonl（字段齐全） |
| 技能自动生成（V2/V3） | 同上 + 任务成功/自修复标记 | ≥5 步、error→recovery、成功 | ⚠️ 同上 | **trace 必须含 is_error 行与 args**（自修复模式=错误后接成功，被清洗掉就永远不达标） |
| skill_stats 账本（V2/V3） | `skill_exec` 行 | tool=="skill_exec" | ⚠️ 需部署期（§7.2） | GAIA 轨迹无 skill_exec（历史事实），账本需部署任务补 |
| GEPA 变异（V2/V3） | 技能真实失败执行 | 失败文本 | ⚠️ 需部署期 | 同上 |
| 智能路由 / 智能记忆（V1/V3） | 任务**执行时**的上下文 | 任务文本等 | ❌ 回放期无任务执行，不工作 | 不需要语料字段；其证据在 Terminal 评测期（§9.5） |

**三个由此得出的硬结论**（决定提取设计的依据）：

1. **语料的核心价值 = 轨迹内容**（错误行、args、恢复模式），不是 outcome 标签——outcome 只是 `passed` 显示用；
2. **Track A 与技能生成读的是会话 tools.jsonl**——驱动器必须把 trace 行种子化进会话（§7.1 补丁），否则 V2/V3 的技能板块在离线臂里是死代码；
3. **路由/记忆不消费语料**——数据集提取不需要为它们准备任何字段，它们的成败在 Terminal 消融实验里判定。

---

## 3. 数据集字段契约（提取后每条记录必须长这样）

`gaia_corpus_<date>.jsonl` 每行（与 spec §1.2 / extractor 现有输出一致）：

| 字段 | 来源 | 必须性 |
|---|---|---|
| `id` | `2023_level<L>:<序号>` | ✅ 驱动器按此定位 task_id |
| `level` | 1/2/3 | ✅ |
| `task` | 问题文本（文本附件并入，≤3000 字符） | ✅ |
| `file_name` | 首附件名或 None | 建议 |
| `outcome` | `{passed: true, final_answer, reason_code}` | ✅（passed 恒 true） |
| `cost` | 任务记录成本（total_rounds/cost_usd/tokens） | ✅（喂 usage_dict） |
| `trace_ref` | `traces/<safe_id>.json`（相对语料目录） | ✅ |
| `uuid` | GAIA sample uuid | ✅（交叉校验键） |
| `target` | 参考答案 | ✅ |
| `started_at` | ISO（种子化时合成 ts 用） | ✅ |

`traces/<safe_id>.json`（form b）必须包含：

- `tool_calls[]`：每项含 `tool`、`tool_call_id`、`args`、`result`（截断视图）、`is_error`、`status`/`exit_code`、`result_meta`、`trace_ref`——**`is_error` 与 `args` 绝不可丢**；
- `reasoning_notes[]`：LLM 轮次文本（无则标注）；
- `trace_summary`：非空；
- `meta.usage`：rounds/cost/tokens；`meta.reconstruction.tool_calls_source`：如实标注（`child_drive_tools` / observability 全量 等）。

---

## 4. 提取设计：成功-only 130

### 4.1 为什么只要 130 条成功任务

1. **技能生成门槛**要求任务成功 + 自我修复（`task_succeeded` gate）——失败任务无法生成技能，不构成进化信号；
2. **失败信号不丢**：成功轨迹内部普遍含"出错—修复"模式，错误行经 trace 保留，是 GEPA 变异与决策的失败素材；
3. **错误任务（35 I）另有问题**：其反思/backlog 内容噪声大，且 165→130 已保证分层充分（43/70/17）。

### 4.2 主路线（A）：以 merged 为权威源，trace 走 child_drive 链

```
merged（评分/层级/答案权威）
  → 解析 consolidated inspect log：取 165 条 sample（uuid/level/score/started_at）
  → 全量保留（不作 14 失败约束）：score==C 的 130 条入选（passed 恒 true）
  → 每条 trace：
      samples/<uuid>/result.json → task_id(hex) + child_drive_root
      → <child_drive_root>/logs/tools.jsonl 按 task_id 过滤
      → <child_drive_root>/task_results/<hex>.json（summary/usage）
      → （可选）源段的 observability blobs 恢复全量 payload
  → 分层：level 桶内按 uuid 排序编号 id；能力配额 + recovery-rich + min_calls≥3 评分排序
      （130 全量时分层自动 43/70/17，配额仅影响顺序不影响入选）
  → 交叉校验：产出 uuid 集 == summary.csv 中 verdict=="C" 的 task_id 集
```

### 4.3 备选路线（B）：7 段拷贝（对照用）

`--runs-root` 指向 `valid results/ouroboros_v0`（7 段），走现有 per-task/global tools.jsonl 链。**A、B 两路线产出的 130 条 uuid 必须完全一致**（一致性证明提纯正确）。

---

## 5. 环境准备

```bash
# 一次性的环境变量（每次新终端先执行）
export REPO=/mnt/disk2/lzm/ouroboros
export MERGED="/home/lzm/bench_runs/gaia_results/valid results/ouroboros_v0_merged_mimo"
export SEGS="/home/lzm/bench_runs/gaia_results/valid results/ouroboros_v0"
export RAWROOT=/home/lzm/bench_runs/gaia_results
export CORPUS_OUT=/home/lzm/bench_runs/evolution_corpus
export PYTHONPATH=$REPO

cd $REPO
python3 -c "import ouroboros, devtools"        # 依赖可用性检查（报错则先装依赖）
git status --porcelain                          # 期望：干净（或仅已知改动）
```

---

## 6. 第 1 步：改造 extractor（4 处，共约 60 行）

文件：`devtools/benchmarks/gaia/extract_evolution_corpus.py`

1. **`scan_runs`（:150-159）单 run 模式**：`runs_root` 自身含 `inspect_logs/` 时，直接解析其下 `*.json`（`rec["run_dir"]=runs_root`），否则走原多 run 逻辑；
2. **`resolve_trace`（:558-582）child_drive 链**：当 run_dir 无 `ouroboros_data/` 时启用——`result_json_data(uuid)` → `task_id`+`child_drive_root` → 读 `<child_drive_root>/logs/tools.jsonl`（按 task_id 过滤）与 `task_results/<hex>.json`；`source="child_drive_tools"`；`_obs_index` 支持额外的 `--obs-roots`（多个目录）合并索引 blobs；
3. **`--outcome-filter {all,passed}`（默认 passed）**：passed 时强制 `failed_count=0`；`select_corpus`（:783-850）删除 failed 分支的 `min(n_errors,5)*0.1` 加分；`validate_corpus`（:1197-1263）的 `n_failed` 硬校验目标变 0；
4. **`--verify-csv <path>` + stats 重写**：完成后比对产出 uuid 集与 CSV 中 `verdict==C` 的 task_id 集（差集报错退出 1）；`build_stats`（:1156-1164）删除"35 个 best-I"段，新增 C-only 分层表、recovery-rich 数量、n_calls 分布、trace_source 分布；docstring/header 同步。

改完自检：

```bash
python3 -m py_compile devtools/benchmarks/gaia/extract_evolution_corpus.py && echo OK
```

---

## 7. 第 2 步：运行提取 + 交叉校验

**路线 A（主，merged 为权威源）**：

```bash
cd $REPO
python3 devtools/benchmarks/gaia/extract_evolution_corpus.py \
  --runs-root "$MERGED" \
  --size 130 \
  --outcome-filter passed \
  --verify-csv "$MERGED/summary.csv" \
  --out "$CORPUS_OUT" \
  --seed 20260829
```

**路线 B（对照，7 段拷贝）**：

```bash
cd $REPO
python3 devtools/benchmarks/gaia/extract_evolution_corpus.py \
  --runs-root "$SEGS" \
  --size 130 \
  --outcome-filter passed \
  --verify-csv "$MERGED/summary.csv" \
  --out "$CORPUS_OUT" \
  --seed 20260829
```

**预期输出（两路线都应出现）**：

```
[1/6] scanning ...（A：1 个 run（merged）；B：7 个 run）
[2/6] deduplicating by uuid ... 165 unique tasks (130 passed / 35 failed)
[3/6] resolving traces ... trace sources: {child_drive_tools: 130}（或 headless_tools 等，应无 inspect_messages）
[4/6] selecting 130 records (0 failed, min_calls=3, quota=4, seed=20260829)
[5/6][6/6] ... 校验通过：n_failed=0；verify-csv 零差集
```

**对照一致性**：A、B 两轮产出的 uuid 集应完全一致（`diff` 两轮输出清单，或比对 `corpus_stats.md` 的 uuid 列表）。

---

## 8. 第 3 步：产出检查清单（6 项，全过才继续）

```bash
cd $CORPUS_OUT
ls gaia_corpus_*.jsonl traces/ corpus_stats.md        # 1) 三件套存在
grep -c '"passed": true' gaia_corpus_*.jsonl          # 2) == 130
grep -o '"level": [123]' gaia_corpus_*.jsonl | sort | uniq -c   # 3) 43 / 70 / 17
python3 - <<'EOF'                                      # 4) 逐条 load_trace_from_path 语义校验
import json, pathlib
for line in open([p for p in pathlib.Path('.').glob('gaia_corpus_*.jsonl')][0]):
    rec = json.loads(line)
    t = json.loads((pathlib.Path('.') / pathlib.Path(rec['trace_ref'])).read_text())
    assert isinstance(t.get('tool_calls'), list) and t['tool_calls'], rec['id']
    assert all(c.get('is_error') is not None for c in t['tool_calls'][:20]), rec['id']
print('all traces loadable, is_error present')
EOF
# 5) 抽查 3 条 trace：确认存在 error→recovery 模式（is_error 后接非错误行）
# 6) corpus_stats.md：trace_source 分布无 inspect_messages；分层/去重报告达标
```

> 若 5) 抽查发现某条 trace 的 is_error 全为 false：说明该 route 的 tools.jsonl 解析丢了错误标记——回查 `_reconstruct_call` 的 `is_error/status` 推导（含 `⚠️ TOOL_TIMEOUT` 文本兜底 :61）。

---

## 9. 第 4 步：补丁 run_evolution_arm.py（2 处，~60 行）

文件：`devtools/benchmarks/evolution/run_evolution_arm.py`

1. **种子化 `_seed_trace_rows(data_root, rec, trace)`**（main 循环 `:437` 之前调用，按 `rec["id"]` 幂等）：
   把 trace 的 `tool_calls` 以生产行 schema 追加入会话 drive `<data_root>/logs/tools.jsonl`：
   `ts=started_at+秒偏移`、`type="tool_call"`、`tool`、`task_id=rec["id"]`、`round_id=序号`、`args`（原样）、`result_preview`（>2000 再截断）、`is_error`、`status`（result_meta 推导）、`result_ref`（trace_ref 原样）、`tool_call_id`；
   效果：Track A 经验学习 + 技能生成门槛（≥5 步 + 自修复 + 成功）在 V2/V3 臂复活。
2. **部署期两段编排 `_run_deploy_phase(...)`**（V2/V3 会话内；V0/V1 无技能自动跳过）：
   ① 扫描 `skills/self/` 新生成 pending 技能 → 写 `state/skills/<name>/owner_attestation.json` + owner_attested 审查态（复用 `skill_loader` 背书路径）；
   ② 固定清单 `devtools/benchmarks/evolution/deploy_tasks/deploy_tasks.json`（12 条通用轻量任务 + 每技能 2-3 刁钻变体，V2/V3 同集同序）逐条 `server.submit()` 真实执行 → 真实 `skill_exec` 行落会话 tools.jsonl；
   ③ 技能执行 ≥10 次且成功率 <0.8 → GEPA 候选（失败文本来自部署真实行）→ 变异/评估/接受；
   ④ 变异接受后同一清单 rerun → 后测成功率；
   ⑤ 记录进 `session_ledger.json` 的 `skills` 段：`{skill, generated_ts, baseline{n, success_rate}, gepa{accepted, version_from, version_to, rolled_back}, post{n, success_rate}, delta}`；未触发如实记 `reason`。
3. **dry-run 扩展**：打印每记录 `seed N rows` + 部署计划预检（技能名/任务数/触发条件）；不启动服务器不调 LLM。

`deploy_tasks.json` 模板（新建）：

```json
{
  "shared": [
    {"id": "deploy-01", "text": "用你已启用的技能 <name> 把目录里所有 .txt 文件的空行去掉并统计行数", "skill_hint": "<name>", "difficulty": "easy"},
    {"id": "deploy-02", "text": "……共 12 条通用任务……", "skill_hint": "<name>", "difficulty": "medium"},
    {"id": "deploy-hard-01", "text": "清空输入（无文件）时调用 <name>，预期给出明确错误而不是崩溃", "skill_hint": "<name>", "difficulty": "hard"},
    {"id": "deploy-hard-02", "text": "构造超长输入（>20MB）调用 <name>，验证截断与性能", "skill_hint": "<name>", "difficulty": "hard"}
  ]
}
```

**工作区输入资产（中等复杂度档）**：任务配套的真实风格输入（含脏数据/缺失/边界用例，
与 GAIA/TB 题面零重叠）由确定性生成器产出，先跑一次（幂等，可重复）：

```bash
.venv/bin/python devtools/benchmarks/evolution/deploy_tasks/make_assets.py
# 产出 devtools/benchmarks/evolution/deploy_tasks/assets/<task_id>/ + manifest.json（69 文件）
```

运行部署期时，工作区优先从该资产目录拷贝（hard 变体在资产上做空/超长/坏编码变换），
资产缺失时降级为极简示例输入；dry-run 的部署预检会显示 `assets=True（N 文件）`。

自检：`python3 -m py_compile devtools/benchmarks/evolution/run_evolution_arm.py && echo OK`

---

## 10. 第 5 步：四臂 dry-run（不烧预算）

```bash
cd $REPO
for arm in V0 V1 V2 V3; do
  echo "===== $arm ====="
  python3 devtools/benchmarks/evolution/run_evolution_arm.py \
    --dry-run \
    --corpus "$CORPUS_OUT/gaia_corpus_$(ls $CORPUS_OUT | grep -oP 'gaia_corpus_\K[0-9-]+' | tail -1).jsonl" \
    --arm "$arm"
done
```

**每臂预期输出（130 行逐条）**：

```
dry-run  1/130 2023_level1:1: tool_calls=12 notes=5 rounds=8 summary=642 失败=False ✓ （seed 12 rows）
...
coverage: reasoning_notes 覆盖 X/130，usage(rounds) 覆盖 Y/130
未启动服务器、未调用 LLM；退出码 0
```

**检查点**：① 130 行全 ✓——其中 11 条零工具任务标注 `✓ zero-tool`（直接作答，合法，非失败）；② `失败=False` 全部为 False（全成功语料）；③ 每行 `seed=N` 与 tool_calls 一致，合计 1788 行（种子化补丁生效）；④ 部署期预检 `loadable=True`、tasks=15（hard=5）；⑤ 四臂全部退出码 0。

---

## 11. 第 6 步：真实四臂（烧预算，4 会话）

> **当前范围（2026-09-04 决策）**：进化期第一期**只跑 V0 与 V3**（主对比），V1/V2 消融臂的进化期会话延后（其 Terminal 消融快照待后续补跑）。此前的 dry-run 已验证 V0–V3 四臂接线一致，补跑时直接复用本命令。

**前置**：`.env` 或 `--live-settings` 提供模型凭证；评测环境 `Terminal-Bench` 就绪（`devtools/benchmarks/terminal_bench/run_tb.py`）。统一使用 `.venv/bin/python`（conda 默认 3.8 缺 `functools.cache`，runner 无法导入 ouroboros）。

```bash
cd $REPO
CORPUS=$CORPUS_OUT/gaia_corpus_$(ls $CORPUS_OUT | grep -oP 'gaia_corpus_\K[0-9-]+' | tail -1).jsonl

for arm in V0 V1 V2 V3; do
  python3 devtools/benchmarks/evolution/run_evolution_arm.py \
    --corpus "$CORPUS" \
    --arm "$arm" \
    --session-dir /home/lzm/bench_runs/arms/$arm \
    --cadence every_n:5 \
    --budget 200.0 \
    --max-absorbed 10 \
    --campaign-timeout 300
done
```

**每臂会话内自动发生的事**（顺序固定，不要中断）：
1. 130 条语料逐条：种子化 → reflection → backlog → maybe_promote（每 5 条 1 次决策）；
2. V2/V3 额外：经验提取 → 规划器产出 evolution_plan → supervisor 战役（隔离服务器真实执行）→ 审查 → checkpoint（absorbed/abandoned/no_op）；
3. V2/V3 额外：技能生成 → owner 背书 → 部署期两段（baseline 15 条 → GEPA → 后测 15 条）；
4. 会话结束：tag `<arm>-evolved`、吸收提交清单、`session_ledger.json`。

**运行中监控点**（每臂）：

```bash
# 战役进度（应为 absorbed 累积）
grep -c '"cycle_outcome": "absorbed"' <arm-session>/ouroboros_data/state/evolution_checkpoints.jsonl
# 技能事件
cat <arm-session>/ouroboros_data/state/skill_generation_history.jsonl
cat <arm-session>/ouroboros_data/state/skill_evolution_history.jsonl
# 预算
cat <arm-session>/ouroboros_data/state/post_task_evolution_counter.json
```

**停机规则**（任一触发即停）：130 条喂完 / absorbed ≥10 / 预算耗尽。若 absorbed <3（V2/V3），按 spec §3.5 考虑 cadence 改 `every_n:3` 重跑一次确认管线。

**随后 Terminal 评测**（每臂快照，进化 OFF、干净种子）：

```bash
cd $REPO
for arm in V0 V1 V2 V3; do
  python3 devtools/benchmarks/terminal_bench/run_tb.py \
    --snapshot /home/lzm/bench_runs/arms/$arm/<tag>-evolved \
    --pass-k 5 --max-workers 4
done   # 每臂 89×5=445 trials，共 1780
```

评测后必查 `run_manifest.json` 核验点：source commit、dirty=0、模型槽位、渲染后设置差异仅臂开关。

---

## 12. 第 7 步：数据收集（论文表/图 → 文件映射）

| 论文位置 | 指标 | 数据文件（<arm>-session 的 ouroboros_data/ 下） |
|---|---|---|
| 表 4-3 进化期（V3 vs V0） | 吸收率/吸收数 | `state/evolution_checkpoints.jsonl`（cycle_outcome） |
| 表 4-3 | 每吸收提交成本 | 同上 cost_usd + `session_ledger.json` |
| 表 4-3 | 通用层变更占比 | 吸收提交 git diff 分类（对 `<arm>-evolved` tag 与起点 commit） |
| 表 4-3 | 技能生成/启用 | `state/skill_generation_history.jsonl` |
| 表 4-3 | 技能前后测 Δ | `state/skill_stats.json` + `session_ledger.json` skills 段 |
| 表 4-3 | 经验注入率 | 决策 prompt 记录（`state/evolution_experiences.jsonl` 与决策日志） |
| 图 4-1 (a)(b)(c) | 累积曲线/技能时间线/成本 | 同上文件逐记录切分 |
| 表 4-4 Terminal 主验收 | pass@1/5、成本、token、工具 | `run_tb.py` 结果 + `run_manifest.json` |
| 图 4-2 消融 | 四臂对比 + 主效应/交互项 | 四臂终端结果汇总 |
| 图 4-2 (c) | 分支行为/信封/记忆保留率 | `state/routing_history.jsonl` + 轨迹 + 记忆存储（V1/V3） |

---

## 13. 全流程时序（预计）

| 天 | 事项 | 产物 |
|---|---|---|
| D1 | extractor 4 处改造 + 单元测试 | 脚本可用 |
| D1 | 双路线提取 + 6 项检查 + 交叉校验 | `evolution_corpus/` 三件套 |
| D2 | arm 驱动器补丁（种子化/部署期）+ dry-run 四臂全过 | 管线就绪 |
| D3–D5 | 真实四臂（4 会话，并行度自定） | 4 个 `<arm>-evolved` 快照 + 观测文件 |
| D6–D8 | Terminal 评测 1780 trials | 终端结果 + run_manifest |
| D9 | 数据收集 → 表 4-2/4-3/4-4、图 4-1/4-2 | 论文实验章节实数据 |

---

## 14. 风险与兜底

| 风险 | 症状 | 兜底 |
|---|---|---|
| child_drive_root 指向的段目录被移动/改名 | trace 全部落 `inspect_messages` 降级 | 用 `--obs-roots "$RAWROOT"` + 检查 corpus_stats 的 trace_source；路径以 result.json 为准重建软链 |
| 某任务 tools.jsonl 缺 is_error/status（旧日志） | 恢复模式统计偏低 | extractor 已有 `⚠️ TOOL_TIMEOUT` 文本兜底（:61）；仍缺则标注 reconstruction |
| 源段 observability 缺失 | trace 降级 2000 字符 | 可接受（is_error/args 仍在）；论文如实标注 tool_calls_source |
| 130 条中某条 trace <3 次调用 | min_calls 过滤掉 → 入选 <130 | 接受（语料数略小于 130）；或调 `--min-calls 1` 并记录 |
| verify-csv 差集非空 | 提取与提纯不一致 | 打印差集 uuid → 查 provenance（`merge_provenance.json` 判定逻辑）后人工裁定 |
| 吸收率过低（V2/V3 <3） | 进化产物不足 | cadence 改 every_n:3 重跑；或扩语料（加入 35 I 的反思价值另行评估） |
| 技能无候选（成功率 ≥0.8） | GEPA 不触发 | 如实记录 reason；部署任务集加难用例 |
| 预算超限 | 会话中断 | `--budget` 上限、`--max-absorbed 10` 停机；V3 增量主要在部署期（V2/V3 各 60-90 次轻量执行） |

---

## 15. 最终验收清单（逐项打勾）

- [ ] `gaia_corpus_<date>.jsonl`：130 条、全部 `passed=true`、分层 43/70/17
- [ ] `--verify-csv` 零差集；路线 A/B uuid 集一致
- [ ] 所有 trace `load_trace_from_path` 可加载；抽查含 error→recovery 模式
- [ ] `corpus_stats.md`：trace_source 无 `inspect_messages`（或已标注）、无失败记录
- [ ] 四臂 dry-run：130 行全 ✓、0 空轨迹、seed 计数正确、退出码 0
- [ ] 真实四臂：absorbed 提交清单、`session_ledger.json` skills 段、checkpoint 落盘
- [ ] Terminal 评测 1780 trials 完成、run_manifest 核验点全过
- [ ] 表 4-2/4-3/4-4、图 4-1/4-2 实数据填充完毕