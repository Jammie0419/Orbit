# GAIA Adapter

Maintained adapter for running Ouroboros against GAIA through the official
`inspect_evals/gaia` task and scorer.

Generated runs go under `bench_runs/gaia/` (or `OUROBOROS_BENCH_RUNS_ROOT`), never
inside `repo/` or live runtime `data/`.

```bash
python devtools/benchmarks/gaia/run_gaia.py --dry-run
python devtools/benchmarks/gaia/score_gaia.py --run-dir bench_runs/gaia/<run>
```

## 从已有运行结果提取进化语料（extract_evolution_corpus.py）

把 GAIA 运行结果（每个 run 一个目录，含 `inspect_logs/`、`ouroboros_data/`、
`samples/`）去重、**重建生产级轨迹**、按能力约束抽样，产出规格
`EVOLUTION_EXPERIMENT_SPEC.md` §1.2 的进化语料——轨迹与生产 `llm_trace`
逐字段对齐（完整工具结果的生产视图、真实 reasoning_notes、生产持久化的
trace_summary、usage 快照），可直接喂 `run_evolution_arm.py`：

```bash
python devtools/benchmarks/gaia/extract_evolution_corpus.py --runs-root <runs根目录>
# 输出 bench_runs/evolution_corpus/：
#   gaia_corpus_<date>.jsonl   40 条语料（机器格式，一行一条，含 cost 字段）
#   traces/<safe_id>.json      生产级轨迹（规格 §10.6 形式 b + meta）
#   backups/<safe_id>/         原始数据备份（tools.jsonl/task_result/calls manifests）
#   backups/_shared_blobs/     内容定址 blob 共享池（按 sha256 去重）
#   corpus_stats.md / corpus_pretty.md   统计报告与人工可读排版版
```

轨迹重建使用 per-task `tools.jsonl`（调用序列）+ `observability/` 全量
payload（`blobs/<sha256>.json.gz`：完整工具结果 / result_meta / 每轮 LLM 文本，
仅 secret 脱敏）+ `task_results/<hex>.json`（生产 trace_summary 原文 /
cost / review_evidence）。`meta.reconstruction` 如实记录每条轨迹的重建来源与
降级情况（无 observability 的旧 run 自动降级为 2000 字符视图）。
trace 文件名用安全形式（`2023_level1_30.json`，JSONL id 仍为 `2023_level1:30`
——旧版在 Windows 上生成 NTFS ADS 文件，Linux 不可读）。

参数：`--seed`（抽样种子，同种子跨机可复现）、`--size`、`--failed-count`、
`--quota`（能力标签最低配额）、`--min-calls`（轨迹质量下限）、
`--out`（输出目录，默认 `bench_runs/evolution_corpus/`）、`--date`。

### 移植到另一台机器（Linux 服务器）

`--pack-source` 只拷贝提取需要的文件（`inspect_logs`、`samples/*/result.json`、
各 `tools.jsonl`、`task_results`、`run_manifest.json`），**排除含明文 API key 的
`settings.json`**。生产级轨迹重建还需 observability 全量 payload，默认排除
（体积大头）；`--pack-observability` 时一并复制（calls manifests + blobs，
内容定址按 sha 去重）：

```bash
# 本机：出精简包（无 observability：<500MB vs 原始 3.6GB）
python devtools/benchmarks/gaia/extract_evolution_corpus.py \
    --runs-root E:/2026/ouroboros_v0 --pack-source E:/2026/gaia_runs_pack
# 若要完整保真重建（重建 100% 生产级轨迹）：加 --pack-observability
python devtools/benchmarks/gaia/extract_evolution_corpus.py \
    --runs-root E:/2026/ouroboros_v0 --pack-source E:/2026/gaia_runs_pack_full \
    --pack-observability
rsync -av E:/2026/gaia_runs_pack_full/ server:/home/<user>/gaia_runs/

# 服务器：重新生成语料，哈希应与本机一致（跨机确定性校验）
export OUROBOROS_GAIA_RUNS_ROOT=/home/<user>/gaia_runs
python devtools/benchmarks/gaia/extract_evolution_corpus.py
sha256sum bench_runs/evolution_corpus/gaia_corpus_*.jsonl
```
