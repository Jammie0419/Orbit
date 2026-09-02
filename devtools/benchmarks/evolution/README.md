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
- **V2 / V3 目前跑不通**：进化层开关（多智能体/技能进化）对应代码尚未实现
  （§2.4），`--arm V2/V3` 会注入 settings 里不生效的键。当前可端到端运行的是 V0。
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