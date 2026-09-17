# 续跑（resume）与失败归档（failed@1）操作手册

> 本手册把两件事放在一起：**把判定为"不该补"的失败 trial 归档到 `failed@1/`**，以及**在 `pass@1/` 原 job 上原地续跑补回 k=5**。
> 更细的背景（失败三分类、侧车文件、残留清理）见同目录 `README.md` 的「失败分三类」与「⑤ 续跑」。

---

## 0. 目录约定

| 目录 | 放什么 | 谁写 |
|---|---|---|
| `exp/pass@1/<task>/<job>/` | **正在跑的 job**：完整的 k 个 trial + job 级 `result.json`/`config.json`/`lock.json` | harbor |
| `exp/failed@1/<task>/<job>/` | **从 pass@1 移出的失败 trial**（结构完全同构：`<task>/<job>/<trial>`） | 手工移动（本手册流程 A） |
| `exp/smoke/<task>/<job>/` | 单任务冒烟（k=1）产物 | harbor |

关键点：**移动 = 从 pass@1 里消失**。harbor 续跑时把"计划中有、磁盘上没有对应目录"的 trial 视为待跑（`job.py:_init_remaining_trial_configs`），所以移走失败 trial 之后 resume 会把它们补回来，恢复 k=5；归档件在 failed@1 里保留完整证据链。

---

## 1. 流程 A：把失败结果移到 failed@1

**适用**：跑完（或中断后）确认某些 trial 是**不该补的失败**（真实失败 / 超时截断），要把它们从 pass@1 里清出去归档。

```bash
# 变量：JOB=任务 job 目录；TASK/JOBNAME 用于构造 failed@1 的同构路径
JOB=~/bench_runs/terminal_bench/exp/pass@1/cobol-modernization/2026-09-17__22-52-57
DST=~/bench_runs/terminal_bench/exp/failed@1/cobol-modernization/2026-09-17__22-52-57

# ① 建同构目录
mkdir -p "$DST"

# ② 逐个移动失败的 trial（容器写入的文件属 root，必须 sudo）
for tr in cobol-modernization__iw2Rtpp cobol-modernization__JxGbUdc; do
  sudo mv "$JOB/$tr" "$DST/"
done

# ③ 验证
ls "$JOB" | grep __        # 只剩通过的 trial
ls "$DST"                  # 被移出的失败 trial
```

**留一份搬迁记录**（可选但推荐，便于回溯与披露）：

```bash
cat > "$DST/_MOVED.md" <<'EOF'
# 移入说明（failed@1）
- 来源：<原 pass@1 job 路径>
- 移入时间：YYYY-MM-DD HH:MM (+0800)
- 移入的 trial：<名字> —— <异常类型/时长/reward/一句话原因>
- 原因分析：见 exp/capabilities/annotations/<task>.txt 的失败模式条目
- 用途：从 pass@1 移出，供 harbor job resume 补跑回 k=5
- 备注：trial 内文件多为 root 属主，删除本目录请用 sudo rm -rf
EOF
```

**注意**：
- 移动而非复制——留在原地的失败 trial 会被 resume 视为"已完成"，不会重跑；
- 移出前先做失败三分类（见 README）：**只有 infra 才值得补跑**；真实失败/超时截断移走只是归档，续跑补出来的还是同类结果（那种情况请直接跑新的一批，而不是拿归档当"没跑过"）；
- `failed@1` 里是完整 trial（含 trajectory / verifier / artifacts），分析、注释、对外披露都用它。

---

## 2. 流程 B：在 pass@1 原 job 上续跑

**适用**：跑完发现某些 trial 因外部原因没拿到公平机会（infra），或跑到一半必须下线。

```bash
# 所有 harbor 命令都在仓库根、载入环境后执行
cd /mnt/disk2/lzm/ouroboros
source .env.terminal_bench.linux
export PATH="/mnt/disk2/lzm/ouroboros/.venv/bin:$PATH"
export PYTHONPATH=/mnt/disk2/lzm/ouroboros      # 手动跑 harbor 必加，否则 "No module named 'devtools'"

JOB=<job 目录>

# 最短路径：要补哪个就删哪个（整目录、sudo），然后原地续跑
sudo rm -rf "$JOB/<trial 目录名>"
harbor job resume -p "$JOB"
```

**harbor 行为要点**（harbor 0.21 源码核对过）：

| 行为 | 说明 |
|---|---|
| 续跑位置 | 原 job 原地恢复；`job_id`/`started_at`/`lock.json`/`config.json`（并发、超时等**锁定配置**）全部保留 → 评测口径不漂 |
| 待跑判定 | **计划中有、磁盘上没有对应目录的 trial 会被补跑**（`job.py:_init_remaining_trial_configs`） |
| 缺失目录 | 移走整个 trial 目录 = 安全的"待补"信号（不必只删 `result.json`，那样反而会让 harbor 去 rmtree root 文件撞权限） |
| `-f` 过滤器 | 命中的 trial 目录被删后重跑；**默认只有 `CancelledError`**（默认不删任何其他异常） |
| 产物 | 新 trial 用新 7 位后缀、新容器、由 harbor 生成 |
| 收尾 | job 级 `result.json` 按全部 trial 重算（reward 分布 / mean / pass@k） |

**场景速查**：
- **A 断点续跑**：`for d in "$JOB"/*/; do [ -f "$d/result.json" ] || echo "半成品: $d"; done` → `sudo rm -rf` 半成品 → `harbor job resume -p "$JOB"`；可反复"中断→resume"，这就是"k=5 分几次跑"的正规做法。
- **B 定向补跑（推荐）**：只把要补的 trial 移走/删掉，再 resume。
- **C 按异常类型批量**：`harbor job resume -p "$JOB" -f AgentSetupTimeoutError`；⚠️ 不要用 `-f AgentTimeoutError` —— 超时属"截断"不是 infra，且会把你不想动的同类 trial 一起重跑。

**不要用 `run_harbor_smoke.py` 续跑**（无 resume 入口，且会因"0 个新 result.json"判 `harness_failed`）。

---

## 3. 完整实操示例（cobol-modernization，2026-09-17）

背景：整批 k=5 实测 3 过 2 超时（reward mean 0.6，pass@5=1.0）；两个超时均为真实失败（到 deadline 未落盘 `/app/program.py`），按三分类**不该补**，归档；同一 job 之后仍可用 resume 补跑（若判为 infra 的话）或保留 3/5 现状另跑新批。

```bash
# ① 归档两个失败 trial
JOB=~/bench_runs/terminal_bench/exp/pass@1/cobol-modernization/2026-09-17__22-52-57
DST=~/bench_runs/terminal_bench/exp/failed@1/cobol-modernization/2026-09-17__22-52-57
mkdir -p "$DST"
sudo mv "$JOB/cobol-modernization__iw2Rtpp" "$JOB/cobol-modernization__JxGbUdc" "$DST/"
# ② 写 _MOVED.md（内容见流程 A 模板）
# ③ 验证
ls "$JOB"     # cobol-modernization__CFafkEZ / __ELGp2uK / __NyzhQzp（均 reward 1.0）
ls "$DST"     # iw2Rtpp / JxGbUdc + _MOVED.md
# ④ 需要补跑时（本例的失败属真实失败，仅演示命令形态）
export PATH="/mnt/disk2/lzm/ouroboros/.venv/bin:$PATH"; export PYTHONPATH=/mnt/disk2/lzm/ouroboros
source /mnt/disk2/lzm/ouroboros/.env.terminal_bench.linux
harbor job resume -p "$JOB"
```

---

## 4. 跑完的验收清单（30 秒）

```bash
JOB=<job 目录>
ls "$JOB"/                                                     # 新后缀出现 / 该消失的消失
cat "$JOB"/<新 trial>/verifier/reward.txt                      # 与 ctrf.json 一致（不能 reward=1 而 ctrf 记录失败）
python -m json.tool "$JOB"/result.json | head -40              # job 级统计按当前 trial 重算
```

- run-root 侧车（`run_manifest.json` / `result_index.jsonl` / `harbor_command.json`）**不会因 resume 刷新**，以 job 目录里的 `result.json` 为准；
- 若走了 collect/verify 流程，**重新 collect 一次**刷新账本。

---

## 5. 坑清单（速查）

| 坑 | 处理 |
|---|---|
| 容器写入文件属 **root** | 删/移 trial 目录一律 `sudo`；不要只删 `result.json` |
| `run_harbor_smoke.py` 不能续跑 | 续跑只用 `harbor job resume` |
| 侧车文件不刷新 | 真源是 job 级 `result.json` |
| `-f AgentTimeoutError` | 别用：超时属截断，且会重跑全部同类 trial |
| 手工跑 harbor 报 `No module named 'devtools'` | `export PYTHONPATH=/mnt/disk2/lzm/ouroboros` |
| 路径要用裸 `harbor` 找不到 | `export PATH="/mnt/disk2/lzm/ouroboros/.venv/bin:$PATH"` |
| 注册表/API 走代理抖动 | `supabase.co`、`api.xiaomimimo.com` 已在 NO_PROXY 直连；新域名先 curl 对比直连/代理 |
| 记账 | 补了哪些 trial、依据是什么（triage 结论），写进跑记——"补跑"不能变成"刷分" |
