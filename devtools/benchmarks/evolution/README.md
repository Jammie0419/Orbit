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
| `--max-absorbed` | `10` | 吸收周期达到此数提前停止喂料（§3.5 停止条件） |
| `--dry-run` | 关 | 只校验语料→轨迹→摘要加载（零成本） |

## 会话期间监控（每 5 条语料）

```bash
python -c "
import json, collections
p = 'bench_runs/evolution/V0/data/state/evolution_checkpoints.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8')]
print('条数:', len(rows))
print('outcome 分布:', dict(collections.Counter(r.get('cycle_outcome') for r in rows)))
print('总成本 $:', round(sum(r.get('cost_usd', 0) for r in rows), 2))
print('吸收 commit:', [r.get('commit_sha') for r in rows if r.get('cycle_outcome') == 'absorbed'])
"
git -C bench_runs/evolution/V0/clone log --oneline -3
wc -l bench_runs/evolution/V0/data/logs/task_reflections.jsonl
wc -l bench_runs/evolution/V0/data/memory/knowledge/improvement-backlog.md
```

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
