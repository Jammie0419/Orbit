# 进化实验执行规格（EVOLUTION_EXPERIMENT_SPEC）

> **版本**: 1.1
> **日期**: 2026-08-28
> **状态**: 已定案，待执行
> **配套文档**: `PAPER_INTEGRATION_ANALYSIS.md`（融合方法来源）、`devtools/benchmarks/`（基准基建）
> **主模型**: `mimo-v2.5`（自研推理模型，用于所有会话、战役、评估——不混用外部模型）

---

## 0. 实验总览

**研究问题**：融合方法（智能路由 / 记忆机制 / 多智能体进化 / 技能进化）能否提升基于 mimo-v2.5 的 Ouroboros 自进化能力，且进化出的能力是**通用能力**（跨任务形态迁移，而非针对特定任务的特化）。

**主张（论文口径）**：用 GAIA 语料进化、Terminal-Bench 验收——跨域进化迁移。**四臂 = 2×2 分层因子设计**：任务层（智能路由 + 记忆机制）× 进化层（多智能体进化 + 技能进化），经过**同一个 GAIA 进化期**（同语料、同配置，唯一差异 = 两层开关组合），各自在 **TB 全部 89 条 × pass@5** 上评估。全程单模型（mimo-v2.5），不混用外部模型，结果全部归因于 mimo-v2.5 + 融合方法。

**实验结构**：

```
GAIA 语料（正确+错误混合，存档）─┬──▶ V0（任务层关 × 进化层关）进化期 ──▶ TB 89 条 pass@5
                                ├──▶ V1（任务层开 × 进化层关）进化期 ──▶ TB 89 条 pass@5
                                ├──▶ V2（任务层关 × 进化层开）进化期 ──▶ TB 89 条 pass@5
                                └──▶ V3（任务层开 × 进化层开）进化期 ──▶ TB 89 条 pass@5
        每臂 1 次会话（4 个隔离环境）；全部会话同一固定任务顺序；主模型 mimo-v2.5
```

---

## 1. 进化语料（GAIA 分层抽取）

### 1.1 选取规则

- **来源**：已有 GAIA 运行结果（服务器目录，每实例记录了任务文本 + 执行过程轨迹 + pass/fail 结果）。GAIA 实例仅为进化材料，**不用于评估、不报道 GAIA 分数**。
- **构成**：**正确任务 + 错误任务混合**（建议各占一半或错误占比 ≥ 1/3）——失败任务是进化信号的主来源（反思/backlog/promote 由错误标记驱动），成功任务提供正向知识，两者都要。
- **分层**：GAIA 实例按难度分 Level 1/2/3，抽取时保持三层覆盖（进化的改进必须在各难度层都成立 → 逼出与难度无关的通用机制改进）。
- **规模**：30~40 条（不宜过多）。**无需重跑任务**——用"离线回放"把已有运行结果直接喂进化管道（§1.4），任务执行成本为零，成本大头在进化战役。
- 若吸收周期过少（§3.5），可扩充条数。

### 1.2 存档格式（语料 JSONL）

```jsonl
{"id": "2023_level1:7", "level": 1, "task": "...", "file_name": "...", "outcome": {"passed": true, "final_answer": "...", "reason_code": ""}, "trace_ref": "bench_runs/gaia_results/<sample>/logs/tools.jsonl"}
{"id": "2023_level2:13", "level": 2, "task": "...", "file_name": null, "outcome": {"passed": false, "final_answer": "...", "reason_code": "REVIEW_BLOCKED"}, "trace_ref": "bench_runs/gaia_results/<sample>/trace.json"}
{"id": "2023_level3:5", "level": 3, "task": "...", "file_name": "...", "outcome": {"passed": true, "final_answer": "...", "reason_code": ""}, "trace_ref": "bench_runs/gaia_results/<sample>/logs/tools.jsonl"}
```

字段说明：
- `id`：GAIA 实例定位（level + 序号，与 `run_gaia.py` 的 sample-id 格式一致：`f"{subset}:level{level}:{idx}"`）。
- `task`：任务指令原文（若实例带附件 `file_name`，从对应文件读取内容一并记录）。
- `outcome`：pass/fail + final_answer + reason_code（**失败任务的错误标记是反思触发的前提**，必须如实记录）。
- `trace_ref`：该实例的执行轨迹记录路径（见 §1.4 转换）。
- **存档位置**：`bench_runs/evolution_corpus/gaia_corpus_2026-08-28.jsonl`（随实验记录归档，作为可复现性的一部分）。

### 1.3 与评估切片不相交确认

- 评估集 = Terminal-Bench（用户环境 89 条），与 GAIA 实例天然不同源、不同题面 → **零重叠**。
- 写一条确认记录（语料 id 列表 + TB 切片 id 列表各自的 hash），存档于实验目录，论文附录引用。

### 1.4 结果转换与离线回放（不重跑任务）

已有 GAIA 运行结果（服务器目录）→ 每条记录转换 → 直接驱动进化管道：

| 管道输入 | 来源字段 |
|---------|---------|
| `task` | 实例题目文本 + id + level |
| `trace` | 运行轨迹（工具调用序列 + 结果 + 错误标记）；若为 Ouroboros 标准 `logs/tools.jsonl` 则零转换；若为自定义轨迹 JSON 则脚本映射到 {tool_name, args, result, is_error} |
| `outcome` | pass/fail + final_answer + reason_code |

转换产物即 §1.2 语料 JSONL（`trace_ref` 指向轨迹记录）。回放器按会话顺序对每条记录调用 post-task 管道（反思 → 记忆动作/backlog → maybe_promote），产生的进化请求由各会话 supervisor 空闲 tick 执行战役——**GAIA 任务本身不再执行**。

---

## 2. 四臂定义

### 2.1 起点

**以当前代码为起点（当前版本 6.102.0）**，不回到 v6.92.1（Smart Router 等融合实现已在当前代码中，回到 v6.92.1 需重新移植）。已发表 v6.92.1 的 TB 分数作为**外部锚点**（见 §6.2）。

### 2.2 臂矩阵（2×2 分层因子：任务层 × 进化层）

| 层 | 包含方法 | 开关 |
|----|---------|------|
| **任务层** | 智能路由（`smart_router.py`）、记忆机制（`memory_ext/smart_memory.py`）、Harness Tree（`harness_tree.py`） | `OUROBOROS_SMART_ROUTING`、`OUROBOROS_SMART_MEMORY`（已有） |
| **进化层** | 多智能体进化（Multi-Agent Evolver）、技能进化（Hermes 风格） | `OUROBOROS_MULTI_AGENT_EVOLVER`、`OUROBOROS_SKILL_EVOLUTION`（**新增，见 §2.4**） |

| 臂 | 任务层 | 进化层 |
|----|--------|--------|
| **V0** | ❌ | ❌ |
| **V1** | ✅ | ❌ |
| **V2** | ❌ | ✅ |
| **V3** | ✅ | ✅ |

**分析方式（2×2 结构自带）**：
- V1−V0 = **任务层主效应**（即时能力增强对进化的影响）；
- V2−V0 = **进化层主效应**（进化机制增强的贡献）；
- V3−V1−V2+V0 = **两层交互项**。
- 层内单个方法（路由 vs 记忆、多智能体 vs 技能进化）不在基准上区分，用机制级验证补充（§4）。

> **实现前置**：进化层两个方法**尚未实现**（对应代码文件不存在）——本实验纳入它们的前提是先完成实现（范围见 §2.4），否则 V2/V3 无内容可比。

### 2.3 隔离环境

每臂每次重复 = **全新隔离环境**（复用 `devtools/benchmarks/common/server_runner.py` 的 `IsolatedServer` 模式，参照 `devtools/benchmarks/evolve_smoke.py`）：
- 一次性克隆（throwaway clone）作为该会话的 repo；
- 独立 data root（drive）——记忆/日志/checkpoints 全部隔离；
- 一个独立 server 进程（supervisor 空闲 tick 驱动进化战役）。

### 2.4 实施前置：进化层方法的实现要求（必须先完成）

本实验的 V2/V3 臂包含两个**尚未实现**的进化层方法（`PAPER_INTEGRATION_ANALYSIS.md` 中的建议方案）。上臂前必须实现，范围如下（文档估算）：

| 方法 | 实现范围 | 接入点 | 开关 |
|------|---------|--------|------|
| **多智能体进化** | Analyzer / Researcher / Builder / Verifier 四阶段战役执行（~400-500 行） | 替代/增强现有战役执行（`post_task_evolution.py` 触发 → supervisor 战役执行） | `OUROBOROS_MULTI_AGENT_EVOLVER`（新增） |
| **技能进化** | 轨迹技能自动生成 + GEPA 风格变异进化（~1100 行） | 战役产物形态：生成/变异自编写技能（`skills/self/`） | `OUROBOROS_SKILL_EVOLUTION`（新增） |

要求（与既有融合方法一致）：
- 开关式注入（env/settings），**关闭时行为与现状完全一致**（保证 V0/V1 不受影响）；
- 附自动化回归测试（参照 `tests/test_smart_router.py` 等既有模式）；
- 实现完成后先跑 `devtools/benchmarks/evolve_smoke.py --self-mod` 冒烟，确认进化管道端到端可用，再启动正式会话。

---

## 3. 进化期（4 臂 × 1 次会话 = 4 个隔离环境）

### 3.1 会话方案（已定案：固定顺序 + 单次直跑）

- **4 个隔离环境**（每臂 1 个），全部会话使用**同一固定任务顺序**（消除任务序列方差，所有臂的难度位置/记忆演化位置对齐）。
- 单次运行的含义：**不排除 LLM 采样随机性**——反思文本、promote 决策、吸收内容每次会话都不同。论文须如实披露："序贯受控 + 单次运行，结果视为初步；多重复为未来工作"。
- 可选保险（预算允许时）：若 V0 vs V3 差距明显，仅对这两臂补 1 次重复（+2 会话）确认非抽样噪声。
- **环境不可复用**：每次会话 = 全新干净环境（克隆 + data root），因为进化会永久改变记忆与代码，复用自然不独立。

### 3.2 控制变量单（4 会话全部一致）

| 项 | 值 |
|----|-----|
| 进化语料 | 同一份 `gaia_corpus.jsonl`，**同一顺序**喂给每个会话 |
| 模型 | 同一模型（main/heavy/light/fallback/review 槽位全部 pin 同一模型，参照 bench 模板纪律） |
| settings 模板 | 同一份渲染模板（见 §5.1），**唯一差异 = 臂的开关组合** |
| 进化开关 | `OUROBOROS_POST_TASK_EVOLUTION=true` |
| cadence | `OUROBOROS_POST_TASK_EVOLUTION_CADENCE=every_n:5`（保证触发频率；`llm` 可能过少触发） |
| persistent objective | 同一文案（见 §3.3） |
| 预算 | 同一 `OUROBOROS_POST_TASK_EVOLUTION_BUDGET_USD` / `TOTAL_BUDGET` |
| 停止条件 | 同一规则（见 §3.5） |
| 运行时模式 | 非 light（light 会拦截进化，`post_task_evolution.py:331`） |

### 3.3 persistent objective（引导通用能力）

```text
改进通用执行策略：工具选择、错误恢复、上下文运用与结果验证；
改进必须对任务难度和任务形态无关地成立（跨 coding/research/knowledge/simple 均有效），
拒绝只对单一任务类型有效的特化技巧。
```

设置：`OUROBOROS_EVOLUTION_PERSISTENT_OBJECTIVE=<上述文案>`。

### 3.4 喂料节奏与监控

- 每条任务**一条一条喂**（参照 CL-Bench `run_clb.py` 的顺序喂料模式，`--instance-workers 1`）。
- 每条任务完成后：等待 post-task 管道（反思 → backlog → maybe_promote）完成，并给 supervisor **空闲 tick 窗口**让进化战役有机会触发，再喂下一条。
- 每会话中途观察 `state/evolution_checkpoints.jsonl`：

```bash
# 查看条数与最新记录
wc -l <drive>/state/evolution_checkpoints.jsonl
tail -n 5 <drive>/state/evolution_checkpoints.jsonl

# 汇总 outcome 分布与成本（python 3.8+）
python -c "
import json, collections
f='<drive>/state/evolution_checkpoints.jsonl'
c=[json.loads(l) for l in open(f,encoding='utf-8')]
print('条数',len(c),'| outcome:',dict(collections.Counter(x.get('cycle_outcome') for x in c)))
print('总成本 $',round(sum(x.get('cost_usd',0) for x in c),2))
"
```

### 3.5 停止条件

三条任一即停：

1. 语料全部跑完（自然停机，推荐主条件）；
2. 吸收周期 ≥ 10（若要求更多样本，可在语料扩展后继续）；
3. 预算到顶。

> **预期设定**：30~40 条语料 + every_n:5 的节奏下，单会话吸收周期数可能在 3~8 个之间。若会话结束时 absorbed < 3，需评估是否语料量不足，可扩充条数重跑（或接受过程指标照常报告）。

### 3.6 快照

每会话结束后打包该会话的"进化后 agent"：

```bash
# 代码（吸收的 commit 全部在会话克隆的 dev 分支上）
git -C <session_repo> tag "arm-V3-session2-evolved"
git -C <session_repo> log --oneline <起点tag>..HEAD > <run_dir>/absorbed_commits.txt

# 状态全套（记忆/技能/checkpoints/日志）
tar -C <session_drive_parent> -czf <run_dir>/drive_snapshot.tar.gz <session_drive>
```

**归因清单**：`evolution_checkpoints.jsonl` 里每个 absorbed 周期的 `commit_sha` = 该会话进化产物的精确清单。

---

## 4. 进化过程指标（"有用的指标"）

> 原则：只收录能支撑论文主张（融合方法让进化**更有效**）的指标；不收集无法比较或无人关心的数据。

### 4.1 时间序列（每会话，随任务序号推进）

| 指标 | 定义 | 数据来源 |
|------|------|---------|
| 累计吸收数 | 第 k 个任务后 absorbed 周期总数 | `evolution_checkpoints.jsonl` |
| 吸收率（滑动窗口） | 最近 W 个周期的 absorbed / (absorbed+abandoned+no_op) | 同上 |
| 累计成本 | 第 k 个任务后所有周期 cost_usd 之和 | 同上 |

### 4.2 会话汇总（每会话一行的对比表模板）

| 会话 | 吸收数 | 吸收率 | 每周期均成本 | 通用层占比 | 任务特定占比 | 语料完成度 |
|------|-------|-------|-------------|-----------|-------------|-----------|
| V0 | … | … | … | … | … | 全量 |
| V1 | … | … | … | … | … | 全量 |
| V2 | … | … | … | … | … | 全量 |
| V3 | … | … | … | … | … | 全量 |

- **吸收变更分类规则**（通用层 vs 任务特定）：按 absorbed commit 改动的文件路径分类——
  - 通用层：`ouroboros/prompts/`、`ouroboros/tools/`、`ouroboros/loop*.py`、`ouroboros/context*.py`、`ouroboros/config.py`、`BIBLE.md`、`prompts/` 等 harness/执行层文件；
  - 任务特定：改动内容特征化为 GAIA 题型/答案（人工或轻量 LLM 判定，分类结果存档）。
- 论文里这句最有分量：**"V3 会话吸收的变更中 X% 落在通用层（harness/提示/工具层），而 V0 为 Y%"** —— 通用能力证据。

### 4.3 4 臂对比（单次会话）

| 臂 | 吸收数 | 吸收率 | 每周期成本 $ | 通用层占比 |
|----|--------|--------|-------------|-----------|
| V0 | … | … | … | … |
| V1 | … | … | … | … |
| V2 | … | … | … | … |
| V3 | … | … | … | … |

**进阶分析（2×2 结构自带）**：主效应与交互项按 §2.2 计算——任务层主效应 = (V1+V3)−(V0+V2)；进化层主效应 = (V2+V3)−(V0+V1)；交互项 = V3−V1−V2+V0。论文汇报"任务层/进化层主效应"而非逐臂罗列。单次会话下这些是点估计，不伪造置信区间。

---

## 5. 评估（Terminal-Bench 全部 89 条 × pass@5）

### 5.1 评估配置（与已发表行对齐的纪律）

- **报告范围**：只报 Terminal-Bench。GAIA 分数不报（其题面已进进化语料）。
- **切片**：用户环境可跑的 **89 条全部**（固定、记录 id 列表存档）。
- **pass@5**：每条任务 5 次独立尝试（官方 leaderboard 形态 k=5，`devtools/benchmarks/terminal_bench/run_tb.py` 支持）；89 × 5 = **445 trial/臂**。
- **settings 模板**：复用 bench 提交模板的各项纪律（`OUROBOROS_POST_TASK_EVOLUTION=false`、单模型 pinning、`OUROBOROS_MAX_WORKERS=4`、同 effort、CLEAN SEED 要求——跑前 `git status --porcelain` 必须为空），模板渲染后存档。
- **模型**：与已发表 v6.92.1 行**同一模型**（如 Claude Opus-5 high），否则不可比。
- **被评估对象**：每臂的**进化后快照**（§3.6 打包代码 + 状态）；评估期间进化 OFF。
- **run_manifest.json 核验点**（每次跑完必查）：source commit、dirty 状态 = 0、模型槽位、渲染后设置差异（应只有臂开关不同）。

### 5.2 关键披露（论文必须写明）

**TB 每个 trial 都是全新容器 + 全新 data root（`/logs/agent/ouroboros-data`）** → 进化期积累的**记忆与技能不会传导**进评估；传导的只有**代码层吸收的变更**（prompts/工具/loop 等）。这在科学上是干净的，也让"通用机制改进"叙事成立：TB 分上涨 = 代码层通用能力提升，与记忆无关。

### 5.3 评估范围

- 每臂 1 个进化后快照，共 **4 份结果** → 总 trial 数 = 89×5×4 = **1780**。
- 若执行了 §3.1 的可选补测（V0/V3 第 2 次会话），被补测臂按 2 份快照评估，在对比表中单臂列两次结果。

---

## 6. 评估指标与对比表

### 6.1 每臂输出指标（全部来自官方 verifier + 运行账本）

| 类别 | 指标 | 数据来源 |
|------|------|---------|
| 完成率 | **pass@1**（89 条首尝试通过率） | Harbor 官方 verifier |
| 完成率 | **pass@5**（k=5 通过率，主指标） | 同上 |
| 效率 | 每成功任务平均成本 | `agent/ouroboros-run-summary.json` → cost_usd / usage ledger |
| 效率 | 每任务平均轮次、平均耗时 | 运行追踪 |
| Token | 每任务平均 token 消耗（输入/输出/总） | usage ledger（`usage_ledger.jsonl`） |
| 工具 | 每任务平均工具调用次数 | `logs/tools.jsonl` |
| 工具 | 工具失败率（TOOL_ERROR 占比） | 同上 |
| 工具 | 工具多样性（每任务使用不同工具数） | 同上 |

### 6.2 主对比表模板

| 臂 | pass@1 | **pass@5** | 每成功任务成本 $ | 每任务 token | 每任务工具调用 | 工具失败率 |
|----|--------|-----------|-----------------|-------------|---------------|-----------|
| V0（进化后） | … | … | … | … | … | … |
| V1（进化后） | … | … | … | … | … | … |
| V2（进化后） | … | … | … | … | … | … |
| V3（进化后） | … | … | … | … | … | … |
| **已发表 v6.92.1**（外部锚点，Opus-5 high） | — | 官方行 86.74%（raw 86.97%，一次 reward-hack 纠正） | … | … | … | … |
| **Claude Code + Fable 5**（外部锚点，已发表） | — | 83.8% | … | … | … | … |

> 外部锚点行取自 `README.md` 基准表（§131-147）与 `docs/benchmarks/evidence.json`；引用时注明"已发表、self-reported、模型+harness 口径"。

---

## 7. 成本估算与披露清单

### 7.1 成本量级（占位估算，执行前按实际模型单价重算）

| 阶段 | 组成 | 估算 |
|------|------|------|
| 进化期 | **离线回放，不重跑任务**（已有 GAIA 结果直接喂管道）；成本 = 4 个会话的进化战役（每战役 = LLM 轮次 + 自修改验证） | 战役成本由 checkpoints 逐周期记录 |
| 评估 | 89 × 5 = 445 trial/臂 × 4 臂 = **1780**（补测臂最多 +890） | 每次 trial = 一次完整 agent 求解 |

### 7.2 披露清单（论文/实验记录必含）

1. **LLM 随机性**：单次运行（全部会话固定任务顺序、序贯受控）；论文如实披露"序贯受控 + 单次运行，结果视为初步；多重复为未来工作"；若执行 V0/V3 补测则一并报告。不满足显著性检验条件时如实说明（不编造 p 值/置信区间）。
2. **GAIA 数据集**：仅用公开验证集作进化语料；注明数据来源与用途；**不报 GAIA 分数**。
3. **跨域迁移方向**：语料形态（知识检索/问答）≠ 验收形态（终端操作）；"通用能力"主张仅由 TB 结果 + 通用层占比支撑。
4. **fresh-memory 限制**：TB 评估不传导记忆/技能，只传导代码层吸收（§5.2）。
5. **评估口径一致性**：与已发表行对比的前提 = 同模型、同模板纪律、同切片机制；差异处逐项披露。
6. **语料与评估不相交**：语料 id 列表 + TB 89 条 id 列表的 hash 存档。
7. **吸收变更分类**：分类规则与判例存档，保证可复核。

---

## 8. 论文口径

### 8.1 主张模板（关联式，不做因果归因）

> "我们将外部自进化方法系统化整合进 Ouroboros（PAPER_INTEGRATION_ANALYSIS.md，适配度评估 + 最小改动实现），并按**任务层**（智能路由+记忆机制）与**进化层**（多智能体进化+技能进化）设计 **2×2 因子对照**：4 个版本在**相同的 GAIA 语料进化期**（分层抽取的正确/错误任务混合，离线回放已有运行结果，固定顺序、每臂单次会话、4 个隔离环境）后，**任务层主效应**使吸收率提升 X 个百分点、**进化层主效应**提升 Y 个百分点，每周期成本变化 Z%，吸收变更的通用层占比提升 …；进化后的各版本在 **Terminal-Bench（89 条，pass@5）**上分别达到 C%…D%，对比已发表基线 86.74%（v6.92.1）与 83.8%（Claude Code）。自进化机制本身的有效性已由该系统 161 天部署与已发表基准证实（arXiv 2608.08311）；本文聚焦整合方法的增量。"

### 8.2 两种结果都成立

- **TB 分数上涨** → 跨域进化迁移成立：语料（GAIA 形态）进化出的能力迁移到了验收场景（终端操作）→ 通用能力证据 + 融合方法增量。
- **TB 分数不涨** → 过程指标仍可支撑"融合方法改善了进化过程本身"（吸收率/成本/通用层占比），并如实报告迁移失败；这不是负面结果，而是诚实的边界。

---

## 9. 执行前准备清单

- [ ] 【实现前置】多智能体进化：四阶段战役执行 + `OUROBOROS_MULTI_AGENT_EVOLVER` 开关 + 回归测试（§2.4）
- [ ] 【实现前置】技能进化：轨迹技能生成 + GEPA 变异 + `OUROBOROS_SKILL_EVOLUTION` 开关 + 回归测试（§2.4）
- [ ] 【实现前置】`evolve_smoke.py --self-mod` 冒烟：进化管道端到端可用
- [ ] 语料：从服务器同步 GAIA 运行结果目录 → 转换存档 `gaia_corpus.jsonl`（正确+错误混合，§1.2/§1.4）
- [ ] 确认 4 个会话的隔离环境脚本（基于 `evolve_smoke.py` / `server_runner.py` 模式）
- [ ] 确认每臂开关组合注入方式（settings 模板 + env，§2.2）
- [ ] 确认 persistent objective 文案（§3.3）
- [ ] 确认模型与预算（§7.1）
- [ ] 评估：确认 TB 89 条 id 列表、模板、CLEAN SEED 纪律（§5.1）
- [ ] 评估前确认已发表行的模型/模板口径（§6.2）

---

## 10. 四会话实施流程（操作手册）

> 基础：`devtools/benchmarks/evolve_smoke.py` 已证明该模式端到端可用（一次性克隆 → 隔离 data root → 隔离 server → 任务 → post-task 管道 → 进化战役 → 吸收）。四个会话 = 该模式的四个实例，每臂一个。
> 本节所有代码/路径/函数签名均直接引自仓库现有实现（不虚构）。

### 10.1 目录结构（一次准备，四会话共享）

```
bench_runs/evolution/              ← run_root_base（持久目录，非临时）
├── gaia_corpus.jsonl              ← §1.2 语料存档
├── V0/, V1/, V2/, V3/             ← 四个会话目录
│   ├── clone/                     ← throwaway 仓库克隆（git 状态，会话后保留供溯源）
│   │   ├── ouroboros/             ← 当前代码（含融合方法实现）
│   │   └── .git/
│   ├── data/                      ← 隔离 data root
│   │   ├── .ouroboros_isolated_benchmark  ← supervisor/state.py:30 定义的哨兵
│   │   ├── settings.json          ← 该臂配置（开关、进化、cadence）
│   │   ├── state/
│   │   │   └── evolution_checkpoints.jsonl  ← 每周期一条（absorbed/abandoned/no_op）
│   │   ├── logs/                  ← chat.jsonl, tools.jsonl, task_reflections.jsonl
│   │   └── memory/
│   └── session_ledger.json        ← 该会话的最终汇总（checkpoint 计数、吸收 commit 列表、成本）
└── run_evolution_arm.py           ← 会话驱动脚本（泛化 evolve_smoke）
```

### 10.2 每臂开关配置表（驱动脚本内置）

```python
ARM_SWITCHES = {
    "V0": {},                                               # 全关
    "V1": {"OUROBOROS_SMART_ROUTING": "true",               # 任务层开
            "OUROBOROS_SMART_MEMORY": "true"},               # memory_ext/smart_memory.py
    "V2": {"OUROBOROS_MULTI_AGENT_EVOLVER": "true",         # 进化层开（需 §2.4 实现）
            "OUROBOROS_SKILL_EVOLUTION": "true"},
    "V3": {"OUROBOROS_SMART_ROUTING": "true",                # 全开
            "OUROBOROS_SMART_MEMORY": "true",
            "OUROBOROS_MULTI_AGENT_EVOLVER": "true",
            "OUROBOROS_SKILL_EVOLUTION": "true"},
}
# 注：OUROBOROS_SMART_ROUTING/SMART_MEMORY 已在 settings.json 默认键里
# （ouroboros/config.py:239/245），OFF 值即 "false"；进化层两开关为新增键。
```

### 10.3 会话启动（5 步，全部可复制）

```bash
# 步骤 1-2：从冻结 tag 克隆 + 隔离 origin
git clone --no-hardlinks -q <repo> bench_runs/evolution/<arm>/clone
git -C bench_runs/evolution/<arm>/clone checkout -B ouroboros exp-v1
git -C bench_runs/evolution/<arm>/clone remote remove origin   # 防 self-mod push 回 live

# 步骤 3：data root 初始化
mkdir -p bench_runs/evolution/<arm>/data
touch bench_runs/evolution/<arm>/data/.ouroboros_isolated_benchmark
# seed_owner_state + settings 由 Python 驱动脚本完成（见 §10.4）
```

**关键代码片段**（来自 `devtools/benchmarks/common/server_runner.py`，直接复用）：

```python
from devtools.benchmarks.common.server_runner import (
    IsolatedServer, build_isolated_settings, seed_owner_state, patch_settings_ports,
)

settings_path = data_root / "settings.json"
live_cfg = json.loads(LIVE_DATA.joinpath("settings.json").read_text(encoding="utf-8"))
overrides = {
    "OUROBOROS_RUNTIME_MODE": "advanced",
    "OUROBOROS_POST_TASK_EVOLUTION": "true",
    "OUROBOROS_POST_TASK_EVOLUTION_CADENCE": "every_n:5",
    "OUROBOROS_EVOLUTION_PERSISTENT_OBJECTIVE": "<§3.3 文案>",
    "TOTAL_BUDGET": 200.0,                                  # 每会话独立预算，按需调
    **ARM_SWITCHES[arm_name],
}
cfg = build_isolated_settings(live_cfg, **overrides)        # 只拷 provider/model/budget，strip secrets
settings_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

seed_owner_state(data_root)                                 # 只种子 owner_chat_id
env = Env(repo_dir=clone, drive_root=data_root, branch_dev="ouroboros")

server = IsolatedServer(clone, data_root, settings_path)
server.start(ready_timeout=240)
```

`IsolatedServer.start` 会启动 server 进程 + 等待 supervisor ready（`wait_for_health`），然后可以提交任务。

### 10.4 喂料循环（模式 R / 模式 P）

**模式 R（重跑）**——照 `evolve_smoke.py` 主循环：

```python
for i, rec in enumerate(corpus):
    ws = make_workspace(run_root, i)                      # 工作区：git init + notes.md
    task_id = server.submit(
        rec["task"],
        workspace_root=str(ws),
        memory_mode="forked",
        timeout_sec=1800,
    )
    result = server.wait_task(task_id, timeout=2100)
    if str(result.get("status")) == "timeout":
        server.cancel_task(task_id)
        result = server.wait_task(task_id, timeout=300)
    prev_sha = server.current_sha()
    prev_absorbed = absorbed_cycles_done(data_root)
    server.wait_for_absorb(prev_sha, prev_absorbed, timeout=1800, idle_grace=90)
    snapshot_checkpoint_summary(data_root)
```

**模式 P（离线回放，推荐）**——不执行任务，直接把已有记录喂 post-task 管道：

```python
from ouroboros.agent import Env
from ouroboros.reflection import generate_reflection, apply_memory_actions
from ouroboros.post_task_evolution import maybe_promote
from ouroboros.improvement_backlog import append_backlog_items
from ouroboros.llm import LLMClient

llm_client = LLMClient()

for i, rec in enumerate(corpus):
    task_dict = {"id": rec["id"], "text": rec["task"], "drive_root": str(data_root)}
    llm_trace = load_trace_from_path(rec["trace_ref"])   # 见 §10.6 映射
    trace_summary = build_trace_summary(llm_trace)        # ≤ 2000 字符

    reflection_entry = generate_reflection(
        task=task_dict,
        llm_trace=llm_trace,
        trace_summary=trace_summary,
        llm_client=llm_client,
        usage_dict={},
    )
    # reflection_entry 字段：ts, source, content, MEMORY_ACTIONS_JSON, BACKLOG_CANDIDATES_JSON

    memory_actions = reflection_entry.get("MEMORY_ACTIONS_JSON") or []
    if memory_actions:
        apply_memory_actions(env, memory_actions)
    backlog_cands = reflection_entry.get("BACKLOG_CANDIDATES_JSON") or []
    if backlog_cands:
        append_backlog_items(data_root, backlog_cands)

    # 关键：maybe_promote 内部检查 cadence（every_n:5 → 每 5 次调用才走一次）
    maybe_promote(env, task_dict, reflection_entry, llm_client)

    # 给 supervisor 空闲窗口消费 post_task_evolution_request.json → 启动战役
    poll_campaign_progress(data_root, timeout_sec=300)
    snapshot_checkpoint_summary(data_root)
```

**模式 P 关键约束**：
- `maybe_promote`（`ouroboros/post_task_evolution.py:317`）内部检查 `get_post_task_evolution_enabled()`、`get_runtime_mode() != "light"`、cadence（`every_n:5` → 每 5 次调用才走一次决策 LLM）——所以语料 30 条喂下来，实际触发战役决策 ≈ 6 次。
- 战役由 supervisor 空闲 tick 启动（`apply_pending_request` 在 `supervisor/evolution_lifecycle.py:367`），**需要 IsolatedServer 保持运行**（server.stop 必须在语料喂完后才调用）。

### 10.5 监控命令（每 5 条语料执行一次）

```bash
# 该会话已吸收周期数
python -c "
import json, collections
p = 'bench_runs/evolution/<arm>/data/state/evolution_checkpoints.jsonl'
rows = [json.loads(l) for l in open(p, encoding='utf-8')]
print('条数:', len(rows))
print('outcome 分布:', dict(collections.Counter(r.get('cycle_outcome') for r in rows)))
print('总成本 $:', round(sum(r.get('cost_usd', 0) for r in rows), 2))
print('吸收 commit SHA:')
for r in rows:
    if r.get('cycle_outcome') == 'absorbed':
        print(' ', r.get('commit_sha'), '|', r.get('campaign_objective'))
"

# 该会话克隆的当前 HEAD（若有 self-mod，会与起点的 exp-v1 tag 不同）
git -C bench_runs/evolution/<arm>/clone log --oneline -3

# 反思数（反映 post-task 管道是否正常工作）
wc -l bench_runs/evolution/<arm>/data/logs/task_reflections.jsonl

# 改进积压条目数
wc -l bench_runs/evolution/<arm>/data/memory/knowledge/improvement-backlog.md
```

**checkpoint 记录结构**（`ouroboros/evolution_checkpoints.py:46`）：

```jsonl
{"kind": "cycle_outcome", "task_id": "...", "campaign_objective": "Reduce tool-selection latency in coding tasks", "git_sha": "abc123...", "git_branch": "ouroboros", "cycle_outcome": "absorbed", "commit_sha": "abc123...", "cost_usd": 1.27, "rounds": 8, "identity_sha256": "...", "scratchpad_sha256": "..."}
{"kind": "cycle_outcome", "task_id": "...", "campaign_objective": "Improve memory retrieval relevance", "cycle_outcome": "abandoned", "abandoned_reason": "Verifier tests failed on 2/5 cases", "cost_usd": 0.91}
{"kind": "cycle_outcome", "cycle_outcome": "no_op", "cost_usd": 0.42}
```

**吸收率** = `count(cycle_outcome=='absorbed') / len(rows)`；**通用层 vs 任务特定**分类：按每个 `commit_sha` 的 `git diff --name-only` 结果按 §4.2 的文件路径规则归类。

### 10.6 轨迹映射（离线回放必需）

语料的 `trace_ref` 指向的记录 → 需映射成 `generate_reflection` 需要的 `llm_trace` 结构：

```python
def load_trace_from_path(trace_ref: str) -> dict:
    """trace_ref 是语料里每条记录的轨迹文件路径。
    支持两种来源：
      (a) Ouroboros 标准 tools.jsonl → 直接构造 llm_trace
      (b) GAIA 适配器自定义轨迹 JSON → 字段映射
    """
    p = pathlib.Path(trace_ref)
    data = json.loads(p.read_text(encoding="utf-8"))

    if "tool_calls" in data:
        # 形式 (b)：自定义轨迹（含 tool_calls / result / is_error）
        return data

    # 形式 (a)：tools.jsonl 逐行记录
    calls = []
    for line in p.open(encoding="utf-8"):
        rec = json.loads(line)
        calls.append({
            "tool": rec.get("tool") or rec.get("function", {}).get("name"),
            "args": rec.get("args") or rec.get("function", {}).get("arguments", {}),
            "result": rec.get("result", ""),
            "is_error": bool(rec.get("is_error")),
            "duration_ms": rec.get("duration_ms", 0),
            "tokens_used": rec.get("tokens_used", 0),
        })
    return {"tool_calls": calls, "reasoning_notes": [], "trace_summary": ""}
```

**缺失字段的容忍**：`generate_reflection` 对缺失的 `review_evidence` / `child_evidence` / `usage_snapshot_text` / `sealed_final_text` 都给了默认值（`"(none)"` / `""`），所以回放时不必补齐。

### 10.7 收尾与快照（每会话）

```python
# 等语料喂完 + 在途战役结束
server.wait_for_absorb(
    prev_sha=server.current_sha(),
    prev_absorbed=absorbed_cycles_done(data_root),
    timeout=1800,
)
server.stop()

# 快照
clone = Path("bench_runs/evolution/<arm>/clone")
tag_name = f"<arm>-evolved"
subprocess.run(["git", "-C", str(clone), "tag", tag_name], check=True)
subprocess.run(
    ["git", "-C", str(clone), "log", "--oneline", f"exp-v1..{tag_name}"],
    capture_output=True, text=True
).stdout.splitlines()   # 吸收 commit 列表

# 打包 drive（可选：保留也可）
subprocess.run(
    ["tar", "-C", "bench_runs/evolution/<arm>", "-czf",
     f"<arm>-drive-snapshot.tar.gz", "data"],
    check=True,
)

# 写汇总 ledger
ledger = {
    "arm": "<arm>",
    "tag": tag_name,
    "absorbed_count": len([r for r in checkpoints if r["cycle_outcome"] == "absorbed"]),
    "abandoned_count": len([r for r in checkpoints if r["cycle_outcome"] == "abandoned"]),
    "no_op_count": len([r for r in checkpoints if r["cycle_outcome"] == "no_op"]),
    "total_cost_usd": sum(r.get("cost_usd", 0) for r in checkpoints),
    "absorbed_commit_shas": [...],
    "corpus_completed": len(corpus),
}
Path("bench_runs/evolution/<arm>/session_ledger.json").write_text(
    json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

### 10.8 常见坑（按踩坑频率排）

1. **忘删 origin**：self-mod push 会污染 live 仓库；必做 `git remote remove origin`。
2. **忘 `checkout -B ouroboros exp-v1`**：`safe_restart`（战役执行中的自我重启）依赖 `BRANCH_DEV=ouroboros`；分支不存在会直接崩溃。
3. **模式 P 必须先产反思**：`maybe_promote`（`post_task_evolution.py:317`）内部 `_eligible` 和 LLM 决策都依赖 `reflection_entry`，传 `None` 时直接返回 `None`。
4. **`every_n:5` 节奏**：每 5 次 `maybe_promote` 调用才走一次决策 LLM，所以语料 30 条实际只触发 6 次战役决策——若吸收率太低，先改 `every_n:3` 跑一次确认管线正常，再切回 5。
5. **`IsolatedServer` 必须跨整个语料期保持运行**：战役由 supervisor 空闲 tick 启动，`server.stop()` 只能在语料喂完且战役结束后调用。
6. **模式 R 的 cancel 语义**：`wait_task` 超时返回 `{"status": "timeout"}`，但任务还在跑；必须先 `cancel_task` 再 `wait_task` 一次等终态，否则下一轮的 `reset_per_task_budget`（`supervisor/state.py`）会和仍在跑的 worker 竞争。
7. **每会话独立 `TOTAL_BUDGET`**：并行跑时预算不共享，但要避免一个会话的战役把预算烧光导致后续战役中止；建议 `TOTAL_BUDGET ≥ 150` 给每会话。
8. **轨迹文件编码**：Windows 下 `tools.jsonl` 可能有 BOM；`read_text(encoding="utf-8-sig")` 更安全。