# Terminal-Bench 实验目录

逐任务跑冒烟、最后收集成**榜单官方排版**的工作流。目标是让 pass@5 的结果既反映模型能力，又能以官方形态交付。

## 工作流总览

```
① 跑前预检   →  ② 逐任务冒烟（k=5）  →  ③ 收集成官方排版  →  ④ 校验
preflight.sh     run_harbor_smoke.py     collect_smoke.py     verify_output.py
```

## ① 跑前预检

```bash
source .venv/bin/activate
source .env.terminal_bench.linux

./devtools/benchmarks/terminal_bench/exp/preflight.sh \
  --tasks-file devtools/benchmarks/terminal_bench/exp/all_tasks.txt
```

检查凭证 / docker / API 探活 / 缓存挂载 / 磁盘 / 任务镜像。任一不过就拒绝启动——把外部故障挡在花钱之前。

## ② 逐任务冒烟

一次一个任务，每个任务一个独立的 run root（保证每次的 `run_manifest.json` 和 `result_index.jsonl` 都干净）：

```bash
python devtools/benchmarks/terminal_bench/run_harbor_smoke.py \
  --task terminal-bench/regex-log \
  --model "$TERMINAL_BENCH_MODEL" \
  --k 5 \
  --run-root ~/bench_runs/terminal_bench/exp/smoke/regex-log \
  --allow-dirty-seed \
  --execute
```

> **镜像默认复用**。`--force-build` 现在是显式开关、默认关闭——只有确实要重建镜像时才加它。

> **冷缓存需要放大安装超时。** harbor 的 agent 安装默认只给 360 秒，而容器内要装约 200MB 的大包（claude-agent-sdk 87MB、playwright 45MB…）。实测：缓存冷时会撞 `AgentSetupTimeoutError: Agent setup timed out after 360.0 seconds`；把 `uv`/`pip` 缓存预热后（挂载目录 `/mnt/disk2/lzm/ouro-pip-cache`，本次预热后 9.0G）同一任务就能在窗口内装完。两种处理：
>
> - **本地实验**：带上 `$TERMINAL_BENCH_LOCAL_GUARD`（内含 setup×3 / build×2），但产物失去榜单资格；
> - **要提交**：先跑一次预热缓存，用默认超时重跑——官方认可的替代做法是预构建镜像，而不是放大超时。

## ③ 收集成官方排版

把散落的逐任务产物合并成**一个**官方形态的 submission 树：

```bash
python devtools/benchmarks/terminal_bench/exp/collect_smoke.py \
  --model "$TERMINAL_BENCH_MODEL" \
  --out ~/bench_runs/terminal_bench/exp/campaign \
  --scan ~/bench_runs/terminal_bench/exp/smoke \
  --k 5
```

产物：

```
campaign/
├── assembly_manifest.json     # 记录来源 run root、合并方式、短 k 的任务
│                              # 注意：**不是**经准入的 run_manifest（没有干净种子闸门/
│                              # 源码溯源/凭证披露）——组装本身没有跑任何东西，
│                              # 所以用独立 schema 名，避免被误读为一次真实运行
├── disclosure_ledger.json     # 与 run_tb 同一套 reason_code 分类
└── submission/submissions/terminal-bench/2.1/ouroboros__<model>/
    ├── metadata.yaml
    └── job/
        ├── agent_job_config.json      # 带 agents[].name（冒烟模式缺的那项）
        └── <timestamp>/
            ├── config.json  lock.json  job.log
            ├── result.json            # 合并后全部 trial 的聚合
            └── {task}__{hash}/        # 全部任务的全部 trial 平铺于此
```

**收集器修掉的三件事**（冒烟产物直接拿去提交是不合格的）：

1. 冒烟用裸 `--agent-import-path`，job config 里 `agents[0].name = null`，官方 CI「no matching agent in job config」永远匹配不上 → 收集器生成命名 job config
2. 每次调用各自一个 job 目录，89 个任务就是 89 个 job → 收集器合并成一个
3. 冒烟不写 `metadata.yaml` 和 `disclosure_ledger.json` → 收集器补齐（复用 `run_tb.py` 自己的函数，口径不会漂）

> ⚠️ **收集时必须 `source .env.terminal_bench.linux`**。`metadata.yaml` 声明的评审模型取自环境变量；不设就会写成代码里的**出厂默认值**，与实际运行的评审模型不符。收集器会在这种情况下打印警告。

## ④ 校验

```bash
python devtools/benchmarks/terminal_bench/exp/verify_output.py \
  --submission ~/bench_runs/terminal_bench/exp/campaign/submission \
  --k 5
```

按官方规则逐项检查并**如实打印缺口**（阻塞项 exit≠0）：

| 检查 | 级别 |
|---|---|
| slot 目录 / `metadata.yaml` | 阻塞 |
| job config 命名了每个 agent，且含 `--agent-name` | 阻塞 |
| 每任务 trial 数 ≥ k | 阻塞 |
| 每个 trial 有 `result.json` | 阻塞 |
| **每个 rewarded trial 有 ATIF trajectory** | 阻塞 |
| `verifier/reward.txt` + `agent/instruction.txt` | 提示 |
| `task_id.ref`（内容哈希） | 提示 |

> ATIF trajectory 必须在**首次上传前**存在：README 记载重复上传会跳过已存在的 trial，而 trajectory PUT 失败会静默降级为仅归档，客户端无法修复。缺失用 `build_atif_trajectories.py --job-dir <job> --validate` 补齐。

## 缓存预热：只需要 2 次，不是 89 次

任务镜像**只有 2 个基础发行版**（实测）：`ubuntu 24.04` 约 60%，`debian 12` 约 40%。
而 agent 装的 apt 包列表是固定的（`git curl bash ca-certificates procps python3 python3-venv python3-pip`），
所以 deb 缓存按**发行版**复用，不按任务：每个发行版家族跑一个任务预热即可。

镜像和缓存是两回事：

| | Docker 镜像 | 包缓存 |
|---|---|---|
| 是什么 | 任务的环境（OS + 任务文件） | **agent 自己**的依赖 |
| 省掉 | 拉取/构建镜像 | 每个 trial 重下依赖 |
| 位置 | `docker images`（本地已有 65/89） | `OBO_TB_*_CACHE` 挂载目录 |

**任务镜像里没有 Ouroboros**，agent 依赖是每个 trial 在容器里现装的——镜像齐了不等于缓存热。

实测安装耗时（regex-log）：

| 状态 | 耗时 | 下载 |
|---|---|---|
| 无挂载 | >360s 超时失败 | ~232MB |
| 有挂载，deb 缓存空 | 54.9s | 32.9MB |
| 有挂载 + 修 docker-clean | 32.2s | 32.9MB（落进缓存） |
| 缓存热 | **17.7–20.9s** | **0** |

### 两个曾静默削弱缓存的坑（已修）

1. **`docker-clean` 删 deb**：Debian/Ubuntu 镜像的 `/etc/apt/apt.conf.d/docker-clean`
   在每次 apt 操作后执行 `rm -f /var/cache/apt/archives/*.deb`，导致挂载的 deb 缓存永远是空的
   （实测 0 个 `.deb`、52K）。现在安装前先移除该钩子。
2. **Debian 系没走国内镜像**：改写只匹配 `ubuntu.com`，而 Debian 用 `deb.debian.org`，
   约 40% 的任务被静默留在默认源。实测 `apt-get update`：默认源 **121 秒** vs 清华 **3 秒**，
   而 agent 安装总预算只有 360 秒。现已同时处理 deb822 `debian.sources` 和 legacy `sources.list`。

## 缓存与镜像：实际覆盖到哪些阶段

三处缓存目录（`OBO_TB_PIP_CACHE` / `OBO_TB_APT_CACHE` / `OBO_TB_HF_CACHE`）通过 bind mount
进入容器，**agent 安装阶段与验证器阶段共用同一份**（verifier 默认 shared 模式）。

镜像覆盖（按 89 个任务的 test.sh 实际用什么统计）：

| 阶段 | 工具 | 任务数 | 镜像/缓存是否覆盖 |
|---|---|---|---|
| agent 安装 | apt | 全部 | ✅ 国内源 + deb 缓存 + 移除 docker-clean |
| agent 安装 | uv/pip | 全部 | ✅ uv 缓存 + uv 镜像；pip 走回退路径 |
| 验证器 | `uvx` | 82 | ✅ 复用 agent 装的 uv + UV 索引/缓存 |
| 验证器 | `apt-get` | **84** | ✅ 已补：deb822/legacy 源改写 + deb 留存 |
| 验证器 | `pip` | 9 | ✅ 已补：`PIP_INDEX_URL` + `PIP_CACHE_DIR` |
| 验证器 | `conda` | 2 | ❌ 未覆盖（无对应镜像可指向） |

实测效果：`apt-get update` 在 Debian 12 上 **121 秒 → 3 秒**；安装总耗时（热缓存）**17.7–20.9 秒且零下载**。

镜像命名同时设 `UV_INDEX_URL`（uv ≤0.9）与 `UV_DEFAULT_INDEX`（当前名）——各版本只读自己认识的那个，
而验证器复用的是它找到的任意 uv，版本不由我们决定。

## 外部防线（为什么不会因网络/API 失败丢 trial）

| 层 | 措施 |
|---|---|
| 宿主 | `preflight.sh` 闸门；`.env` 的代理 + fallback 链 + 重试 |
| 容器内安装 | apt/pip 走清华镜像；**uv 引导带重试+镜像+完整性校验**；pip 缓存属主修正；uv/pip 缓存持久化到挂载目录 |
| 容器内运行时 | 长度截断快速失败；模型永久排除防振荡；降级上下文裁剪；连接错误退避 30–120s |
| 验证器 | 注入的 `test.sh` 复用已装 uv（不再从 GitHub 下载），缓存目录重定向到持久挂载 |
| 跑后 | `triage_run.py` 只把 infra 失败写进补跑清单 |

关于 uv：agent 侧安装现在以 `uv venv --seed` + `uv pip install` 为主路径，pip + 清华镜像是保留的回退。这条路径替换掉了原来那个裸的 `curl https://astral.sh/uv/install.sh | sh`——它硬编码 GitHub URL，CN 网络下空烧约 300 秒，且残缺下载会留下能通过 `command -v` 却一跑就段错误的 uv。

## 失败分三类，只有一类可以补跑

| 类别 | 含义 | 处理 |
|---|---|---|
| **infra** | 没得到公平机会（API 挂、传输断连、安装炸、未打分） | ✅ 补跑 |
| **截断** | 有公平机会但预算用完（`AgentTimeout`、`deadline_local`） | ❌ 保留为失败 |
| **真错** | 有公平机会、有预算、答错 | ❌ 保留为失败 |

**把「截断」当外部问题补跑，是让 pass@k 虚高最典型的方式。** 超时是数据集规则的一部分。

```bash
python devtools/benchmarks/terminal_bench/exp/triage_run.py \
  --run-root ~/bench_runs/terminal_bench/exp/smoke/regex-log \
  --infra-out devtools/benchmarks/terminal_bench/exp/remaining_tasks.txt
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `preflight.sh` | 跑前闸门 |
| `collect_smoke.py` | 逐任务产物 → 官方排版 |
| `verify_output.py` | 对照官方规则校验并报告缺口 |
| `triage_run.py` | infra / 截断 / 真错三方分类 |
| `all_tasks.txt` | 全部 89 个任务（数据集顺序） |
| `failed_tasks.txt` | v0 的 35 个失败任务 |
| `remaining_tasks.txt` | 待补跑的 infra 任务（triage 生成） |
| `task_metadata.md` | 89 个任务的官方限制（超时/资源/难度） |
| `capabilities/task_annotations.py` | 14 个任务的历史失败注解（默认关闭，`OUROBOROS_TB_TASK_ANNOTATIONS=1` 打开） |

## ⚠️ 三个必须知道的坑

**1. 容器创建的数据目录属 root，删不掉。**
每次 trial 的 `agent/ouroboros-data/` 由容器内 root 写入，`rm -rf` 会 `Permission denied`。清理旧运行需要 `sudo rm -rf <run-root>`。别把它写进 `&&` 链——失败会静默跳过后续步骤。

**2. `disclosure_ledger.json` 是累计的。**
`run_tb.py` 用 `rglob` 扫描整个 job 目录下所有 `result.json`。往同一个 run-root 重复跑会让账本越滚越大（`test_cap_rules` 就是这样变成「manifest 写 1 任务、账本 99 trial / 21 任务」）。**每个 arm / 每轮用干净的 run root。**

**3. `run_tb.py` 没有断点续跑。**
每次调用都是一次全新 job。中断后重跑请用新的 run root 或 `--tasks-file` 缩小范围。

## 榜单资格

有效提交要求：`k >= 5`、`timeout_multiplier == 1.0`、setup/build 超时乘数为 null、无 resource override、agent-web 关闭。

`$TERMINAL_BENCH_LOCAL_GUARD` 里的 setup/build 乘数会让运行**永久失去提交资格**，只能当本地实验。官方认可的替代是**预构建镜像**（`force_build: false`），而不是放大超时。

多 job 提交是官方支持的：任务覆盖与「每任务 ≥5 trial」在**全部 job 上合并评估**，这也是官方认可的「补跑失败/infra trial」的方式。但注意官方规则同时写着 **errored trial 计为 reward 0，永不排除**。
