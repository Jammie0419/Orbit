# SKILL_EVOLUTION_BOARD — Hermes 风格技能进化板块全文档

> **板块**: Phase 3 Skill Evolution（PAPER_INTEGRATION_ANALYSIS.md「Phase 3: Hermes 风格技能进化集成」）
> **开关**: `OUROBOROS_SKILL_EVOLUTION`（默认 **false**，opt-in；关闭 = 零技能写入、零路由评分变化，行为与接入前逐字节一致）
> **实现**: 2026-09-03（初版 + 同日加固与 GEPA 对齐升级，见 §15 变更记录）
> **覆盖**: 6 个新模块 ~1200 行 + 67 例自动化回归 + 真实 LLM 冒烟脚本
> **文档版本**: 2.0（2026-09-03 整理重排：15 章，机制章节 + 五幕实景剧本 + 变更记录）

---

## 1. 板块定位

技能进化板块解决论文指出的最后一环：**可复用资产（skill 库）的自动生成与持续进化**。进化层（不足 4+5+7）进化的是"策略/方法论"（promote 决策、plan 形态、经验复用）；本板块进化的是"技能本身"——从成功任务轨迹里提炼自编写技能，让失败的自编写技能被遗传算法改进，让审查结论反哺下一次生成/进化，并在审查失败时自动回滚、按历史哈希复原可执行性。

**核心原则**（与 Hermes GEPA 源案一致，且是安全底线）：

1. **只进化自编写技能**——社区/原生技能永不触碰；
2. **只采纳明显更优的变体**——真实失败轨迹驱动的变异 + 多案例评估，不优于当前成功率即保留原版；
3. **写与跑分离**——生成/进化只是产出"候选"，可执行性永远由既有审查/背书/哈希绑定门控；
4. **全程可审计、可复原**——五类账本记录每一步；覆盖前备份、审查失败自动回滚、命中历史结论即恢复可执行；
5. **关闭零差异**——单一开关，默认关。

## 2. 设计地图

### 2.1 组件与文件

```
ouroboros/skill_evolution/          ← 新包（与顶层 skill_* 领域模块同层）
├── __init__.py                     ← 包 docstring（设计契约）
├── stats.py                        ← SkillStatsLedger：执行账本（GEPA 门、路由加权、B4 校准的数据源）
├── auto_generation.py              ← SkillAutoGenerator：轨迹→技能生成 + 包落盘/校验/渲染（evolver 复用）
│                                     + recent_review_flags（审查反馈提取，生成/进化共用）
├── genetic_evolution.py            ← SkillEvolver：GEPA 进化（去重种群/反射变异/多案例评估/校准）
├── nudge.py                        ← SkillNudgeEngine：任务边界节奏（1h）+ 规则化近期工作分析
└── pipeline.py                     ← run_skill_evolution_step 编排 + rollback_failed_evolutions
                                      （自动回滚 + verdict 复原 + 冷却记录）
```

最小侵入改动（6 处）：

| 文件 | 改动 |
|---|---|
| `ouroboros/config.py` | `SETTINGS_DEFAULTS["OUROBOROS_SKILL_EVOLUTION"]="false"` + `get_skill_evolution_enabled()` |
| `ouroboros/post_task_evolution.py` | `maybe_promote` 内独立开关块调用 `run_skill_evolution_step` |
| `ouroboros/smart_router.py` | `_load_skills` 合并账本；自编写技能质量加分（cap 1.0 内） |
| `ouroboros/skill_loader.py` | `write_self_authored_markers()`（双 marker 原子写） |
| `ouroboros/skill_review_history.py` | `verdict_for_hash()`（哈希→可执行结论索引，A1） |
| `ouroboros/context.py` | `## Skills Needing Review or Backoff` 可见性段（A2） |

### 2.2 数据流总览

```
任务完成 ──→ maybe_promote（前置门）──开关─→ run_skill_evolution_step
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              ▼                               ▼                               ▼
         Step0 自动回滚                  Step1 账本刷新                  Step2 当前任务生成
    skills/self/*.replaced-*      logs/tools.jsonl ─→          steps ≥5 + 自我修复 + 成功
    + review.json=blockers        state/skill_stats.json      ─→ LLM 提取 → skills/self/<名>/
    + 哈希匹配 ─→ 还原+复原结论           │                       + 双 marker + 生成历史
              │                          ▼
              │                   Step3 nudge 到期（≥1h）？
              │                     ├─ 分析近期失败技能 / 可复用任务
              │                     ├─ GEPA 进化（最多 2 个候选）
              │                     └─ 记录 nudge 水位
              ▼
        审查环节（外部裁决）── skill_review 工具 / owner attest-review
              │            （context 里 ## Skills Needing Review 可见）
              ▼
        路由消费（SMART_ROUTING=true 时）── 自编写加分 → 推荐 → 任务调用
              └─────────────→ 新执行数据 → 回到 Step1（闭环）
```

## 3. 触发与入口

### 3.1 挂载点与前置门

`maybe_promote`（post_task_evolution.py）内、promote 决策之前的**独立开关块**：

```python
try:
    from ouroboros.config import get_skill_evolution_enabled
    if get_skill_evolution_enabled():
        from ouroboros.skill_evolution.pipeline import run_skill_evolution_step
        run_skill_evolution_step(env, task, reflection_entry, llm_client)
except Exception:
    log.debug("post_task_evolution: skill evolution step failed", exc_info=True)
```

前置门链（沿用 maybe_promote 既有）：`OUROBOROS_POST_TASK_EVOLUTION=true` → runtime ≠ light → 任务类型非 evolution/deep_self_review → 非 project-scoped → cadence ≠ off。技能块与 promote 决策互不依赖：promote 与否都执行。

### 3.2 开关语义

`_settings_flag_enabled("OUROBOROS_SKILL_EVOLUTION")`：settings.json 磁盘值 > 环境变量 > 默认 false；truthy 集合 `{"1","true","yes","on"}`。

- **关闭**：pipeline 不导入不执行；路由评分无增量（增量以自编写 marker + 账本为条件，天然为零）；无任何技能写入；context 无待审段。
- **开启**：每次合格任务跑 Step0-3；LLM 预算被任务门槛（生成三条件）与节奏（nudge 1h）双重约束，进化单轮 ≤2 候选、种群 ≤5、评估案例 ≤5。

## 4. 完整流程（任务边界四步）

### Step 0 — 自动回滚（先于一切）

`rollback_failed_evolutions(drive_root)`：扫描 `skills/self/*.replaced-*`，对每个备份：由名字剥离 `.replaced-<ts>` 得活跃技能 → 计算当前包 `compute_content_hash` → 读 `state/skills/<名>/review.json`——**只有 `status == "blockers"` 且 `content_hash == 当前哈希`**（审查者确实判的是进化后的字节；过期结论、pending、clean 一律不触发）才回滚。回滚动作详见 §8。

### Step 1 — 统计账本刷新

`SkillStatsLedger.aggregate()`：扫 `logs/tools.jsonl` 中 `tool == "skill_exec"` 的行（一行一次调用），按 `args.skill` 聚合 → `state/skill_stats.json`：

```json
{"demo-fix": {"execution_count": 12, "success_count": 8, "success_rate": 0.6667,
              "first_ts": "...", "last_ts": "...", "evolution_version": 1}}
```

- `logs/tools.jsonl` 是唯一事实源（events.jsonl 会重复计数，不纳入）；
- `evolution_version` 跨重建保留（进化器 bump）；
- 账本永远反映当前日志窗口（轮换即重置，相对成功率语义）。

### Step 2 — 当前任务 → 生成新技能

详见 §5（门槛、选步、提取、落盘、去重、降级）。

### Step 3 — Nudge 周期（进化 + 补充生成）

`SkillNudgeEngine`：任务边界查水位——`skill_nudges.jsonl` 末条 `ts` 距今 ≥3600s（无记录/不可解析 → 到期）。到期时：① `analyze_recent()`（规则化、零 LLM）产出 `failed_skills` + `best_reusable_task`；② **GEPA 进化**（§6，最多 2 个候选）；③ 若 `best_reusable_task` 非当前任务 → 对那个任务也跑一次生成（历史去重防重复）；④ `record()` 写水位。

## 5. 技能生成详解

`SkillAutoGenerator.maybe_generate_for_task(task_id, goal, outcome_hint, steps)`：

1. **轨迹重建**：`load_task_steps(task_id)` 从 tools.jsonl 过滤（含 `args` 透传）；
2. **三门槛**（论文触发条件 + 冒烟实证），全过才继续：
   - 工具步骤 ≥ `MIN_TOOL_CALLS=5`；
   - **自我修复**：存在 `steps[i].is_error and not steps[i+1].is_error`；
   - **任务成功**：outcome_hint ∈ {success/succeeded/completed/done/ok/pass} 或（hint 为空时）最后一步非错误；
3. **去重**：同 task_id 已在生成历史（成功或失败）→ 跳过；`discover_skills` 已有同名 → 提取后跳过不覆盖（生成永不覆盖已有包，因此生成侧无备份需求）；
4. **关键步骤选取**：`assign_credits`（0.5 基 + 成功 0.2 − 错误 0.3 + 快 0.1 + 省 token 0.1，归一化）→ `identify_critical_steps`（top-3 + 最低 2）→ 步骤行（tool/ok/args[:400]/result[:200]），上限 8 条；
5. **LLM 提取**（主槽位，reasoning=medium，4096 tokens）——prompt 结构：
   - Task goal（或"从步骤推断"）；
   - 信用排序关键步骤；
   - **[Reviewer flags to avoid]**（有审查失败历史时）：全局扫描各技能 review.json 的最近 FAIL findings，要求"不得重复这些被标模式"；
   - 严格 JSON schema（name/description/type/runtime/when_to_use/parameters/tags/scripts）；
   - 硬规则：名字与脚本名只允许 `[A-Za-z0-9._-]`；代码完整自包含（stdlib，依赖 vendor）；**技能之间不允许互相调用**；
6. **结构校验** `validate_generated_skill`：dict、canonical 名字非空、script 型必须非空安全脚本与代码、instruction 型必须有 body、runtime 兜底、tags ≤8；失败记 `failed` 历史；
7. **落盘** `write_skill_package`：`skills/self/<名>/SKILL.md`（YAML frontmatter: name/description/version/type/when_to_use/timeout_sec/scripts 名单/tags；body 与脚本分离——代码行 `---` 不会截断 frontmatter）+ `scripts/<名>` + **双 marker**（目录内 + `state/skills/<名>/self_authored.json`，schema_version=1/origin=self_authored/task_id/created_at 两侧一致，marker 最后写使 `initial_content_hash` 覆盖 payload）；
8. **历史**：`skill_generation_history.jsonl` 记 `created` / `skipped`（reason: name_exists / task_recorded）/ `failed`（reason: llm_extraction_failed / 结构原因）。

**新技能初始状态 = pending 审查 + disabled**——可执行性完全由既有管线决定（§7）。LLM 失败/校验失败全部静默降级，永不断链。

## 6. GEPA 进化详解（板块核心）

### 6.1 候选门

```python
is_evolution_candidate(skill, stats):
    skill.is_self_authored          # 只动自编写
    and execution_count >= 10      # EVOLUTION_MIN_EXECUTIONS
    and success_rate < 0.8          # EVOLUTION_MAX_SUCCESS_RATE
```

每轮（每次 nudge 到期）按成功率升序取前 **2** 个候选；**24h 内被自动回滚过的技能跳过**（`_recent_rollback`：进化历史 `action=="rolled_back"` 且 ts 在窗口内——防翻烙饼）。

### 6.2 单技能进化流程 `_evolve_one`

```
① 失败素材    _recent_failures：该技能最近 ≤8 条 skill_exec 错误行（真实报错文本）
② 失败分析    LLM：常见错误 → ≤2 条改进建议
              （prompt 注入本技能 [Recent reviewer findings]，要求变异避开）
③ 建种群(≤5)  [原版] + [每条建议→变异一个] + [策略池兜底补齐]
              · 渲染内容哈希去重（与原版/已收录变体相同 → 丢弃；空 dict 提案视为失败）
④ 评估       原版基线 = stats.success_rate（不调模型）
             每个变体对 ≤5 条 mini 案例逐例打分取均值（案例 = 自身历史：≤2 成功 rubric
             + 失败行；prompt 注明"重复审查标记问题必须低分"）
⑤ 校准       历史 ≥3 次采纳且评估均值−实测 ≥0.1 → fitness ×0.9（fitness_discount 记录）
⑥ 采纳判定   折扣后最高分 > max(当前成功率, 0.5) 且结构合法（渲染回读、名字不变）才采纳
⑦a 采纳      旧包完整备份 .replaced-<ts>（含 marker）→ 覆盖（版本小步 +1）
              → 账本 evolution_version +1 → 历史含 backup_dir/fitness_discount
⑦b 拒绝      原版原样保留，历史 {accepted: false, reason: no_better_variant}
```

### 6.3 反射式变异（B2，对齐 GEPA "reads traces → targeted mutations"）

`_mutate` 的变异 prompt 注入该技能**最近真实失败执行行**（result_preview 报错文本，≤6 条）：

```
{指令（建议原文 或 策略说明）}

[Current skill] {技能完整 JSON（含全部脚本代码）}

[Recent failing executions of THIS skill — the rewrite MUST make the script handle these cases]
- status=error: tarfile.ReadError: file is not a tar archive
- status=error: PermissionError: [Errno 13] Permission denied: 'logs.tar'
...

Return the COMPLETE modified skill as ONLY JSON: {...}
```

变异由此对着真实病灶改，而不是凭泛泛建议。建议驱动是主通道；固定策略池（add_error_handling / improve_description / optimize_parameters）在无建议或名额未满时兜底。

### 6.4 多案例评估（B3，对齐 metric-over-valset）

`_build_eval_cases`：从技能自身执行历史构造 ≤5 条 mini 案例（≤2 条成功执行的预期行为 + 失败案例）。`_evaluate` 每个变体对全部案例打分（`{"case_scores": [...]}`）取均值；兼容单值 `fitness` 回退，垃圾输出 0.0；LLM 失败 → 0.0（保守拒绝侧）。降低单次 LLM 判断方差（初版两次冒烟"永远拒绝"的部分成因）。

### 6.5 holdout 校准（B4，对齐 holdout 对比）

`_fitness_discount`：该技能进化历史 ≥3 次采纳（`accepted: true`）且"评估均值（new_success_rate）− 实测成功率（账本）≥ 0.1"→ 评估被判定系统性乐观 → 采纳门槛自动收紧（fitness ×0.9）。数据驱动、不改 prompt；`fitness_discount` 记入每条进化记录。历史不足时恒为 1.0（默认行为）。

### 6.6 关键常量

| 常量 | 值 | 出处 |
|---|---|---|
| `MIN_TOOL_CALLS`（生成） | 5 | 论文 |
| `EVOLUTION_MIN_EXECUTIONS` | 10 | 论文 |
| `EVOLUTION_MAX_SUCCESS_RATE` | 0.8 | 论文 |
| `POPULATION_SIZE` | 5 | 论文（种群） |
| `MAX_CANDIDATES_PER_RUN` | 2 | 预算约束 |
| `MAX_EVAL_CASES` / `MAX_EVAL_SUCCESS_CASES` | 5 / 2 | B3 |
| `NUDGE_INTERVAL_SEC` | 3600 | 论文（1h） |
| `ROLLBACK_COOLDOWN_HOURS` | 24 | 防翻烙饼 |
| `CALIBRATION_MIN_ACCEPTS` / `_OPTIMISM_THRESHOLD` / `_DISCOUNT` | 3 / 0.1 / 0.9 | B4 |
| 采纳底线 | `> max(rate, 0.5)`（折扣后） | 防劣化 |

## 7. 审查衔接：三道安全闸与哈希绑定

| 闸 | 主体 | 管什么 | 何时 |
|---|---|---|---|
| 写前闸 | evolver/generator（结构校验 + 多案例评估） | 值不值得写 | 写入前 |
| 审查闸 | `skill_review` 工具 / owner attest-review | 能不能安全执行 | 写入后（外部裁决） |
| 执行闸 | `skill_exec` | 此刻跑的 = 审过的那份 | 每次执行 |

**不变量**：审查结论（review.json）永远绑定其审查过的 `content_hash`；任何内容变化（生成、进化、手动编辑）使结论 stale → 不可执行 → 需新鲜结论。生成/进化**从不自动触发审查**（"写"与"批准"分离正是该不变量的来源；A3 自动重审开关仅记录不实现）。

**状态语义（重要）**：判断 blockers 时读 **review.json 原始值**——`load_review_state` 会按 findings 重新聚合（单条 FAIL → warnings），归一化状态会掩盖 blockers 判定。自动回滚触发、A2 可见性段、`recent_review_flags` 全部使用原始状态语义。

**人为路径**：owner UI 的 `POST /api/owner/skills/<名>/attest-review`（owner-only；浏览器工具被显式禁止代理访问）——确定性预检 + 结构校验后直接落 clean，跳过三模型 LLM 审查。

**A2 可见性**：context 动态区追加 `## Skills Needing Review or Backoff`（开关门控，非空才注入，上限 12 条）——pending/stale/blockers/broken 技能及原因（blockers 附首个 FAIL finding item）。无法执行的技能不再无声无息，agent 下一任务即可处理（调 skill_review 或 owner attest/编辑）。

**审查失败的处理**：进化版（有备份）→ 下个任务边界自动回滚（§8）；生成版（无覆盖）→ 保持 pending，文件不删，可改/重审/背书/忽略。

## 8. 回滚与复原

### 8.1 备份（前置）

`_backup_skill`：进化**采纳路径**覆盖写入前，旧包完整复制（SKILL.md + scripts/* + `.self_authored.json` 全量——**marker 参与内容哈希**，必须全量）到 `skills/self/<名>.replaced-<时间戳>/`（孤儿约定，发现机制自动跳过，不污染路由）；路径记入进化历史 `backup_dir`。生成从不覆盖，故无备份需求。

### 8.2 触发

Step 0 三条同时满足才回滚：① `.replaced-` 备份存在；② `review.json` 原始状态 == blockers；③ `content_hash == compute_content_hash(当前包)`（审查者判的确是进化版字节；pending/clean/哈希不匹配的过期结论不触发）。

### 8.3 回滚动作序列

```
1. 完整还原：备份的 SKILL.md + scripts/* + .self_authored.json 全量换回；
   （marker 参与内容哈希，不全量还原哈希就对不上）
2. _sync_state_marker：还原的 marker payload 同步写回 state 侧
   （两侧 task_id/created_at 一致，is_self_authored 判定保持为真）
3. A1 verdict 复原：verdict_for_hash(还原后哈希) → 先查 review.json 当前值，
   再扫描 review_history.jsonl → 命中历史 clean/warnings 结论（content_hash 匹配）
   → save_review_state 重新落盘 → 技能原地恢复可执行（等价 git revert）；
   未命中 → 保持 stale，照常重审（回滚只恢复内容，永不绕过哈希绑定）
4. 消费备份（删除）；记录：{"action": "rolled_back", "skill", "reason":
   "review_blockers", "backup_dir", "restored_version", "restored_verdict"}
5. 24h 冷却：evolver 检查 rolled_back 行，窗口内不再次进化（防翻烙饼）
```

### 8.4 边界

- 回滚恢复内容与可复用的旧结论；`restored_verdict == ""` 时保持 stale 等重审，审查结论绑定字节的防线在任何路径下不绕过；
- 回滚后 review.json 仍是 blockers（虽哈希已不匹配 → 不会二次触发），审查 flags 继续注入下一轮进化 prompt——老坑不重踩。

## 9. 反馈闭环

```
审查 FAIL findings ──→ 生成 prompt [Reviewer flags to avoid]（全局最近被标模式）
                   ──→ 进化 prompt（本技能 findings：失败分析 + 评估打分都要避开）
执行账本成功率 ──→ GEPA 候选门（<0.8 才进化）/ 路由加分（>0.8 再 +0.1）
                 ──→ 原版基线（实测）/ B4 校准（评估 vs 实测）
进化采纳 ──→ 版本+1 / 账本 evolution_version（路由 +0.05×版本）
审查 blockers ──→ 自动回滚（命中历史结论即复原）+ 24h 冷却 + flags 留存
路由推荐复用 ──→ 新执行数据 ──→ 账本 ──→ 循环
```

## 10. 状态文件与数据格式

| 文件 | 内容 | 写入点 |
|---|---|---|
| `state/skill_stats.json` | `{skill: {execution_count, success_count, success_rate, first_ts, last_ts, evolution_version}}` | Step 1 重建 / 采纳时 bump |
| `state/skill_generation_history.jsonl` | `{ts, task_id, skill_name, skill_description, type, outcome: created\|skipped\|failed, reason}` | 生成器 |
| `state/skill_evolution_history.jsonl` | `{ts, skill, old_success_rate, new_success_rate, mutation_type, accepted, reason, version_from, version_to, evolution_version, backup_dir, fitness_discount}`；回滚行 `{action: rolled_back, skill, reason, backup_dir, restored_version, restored_verdict}` | 进化器 / 回滚 |
| `state/skill_nudges.jsonl` | `{ts, analysis: {failed_skills, best_reusable_task, task_count}}` | Step 3 |
| `state/skills/<名>/review.json` + `review_history.jsonl` | 哈希绑定结论 + 历史（`verdict_for_hash` 索引源） | 既有 skill_review |
| `skills/self/<名>.replaced-<ts>/` | 进化采纳前旧包（孤儿约定，发现跳过） | `_backup_skill` |

## 11. 测试与真实冒烟验证

**`tests/test_skill_evolution.py`（67 例全绿）**：

- 开关：默认 false / env true / settings.json 磁盘值优先；
- 账本：聚合计数与成功率、evolution_version 保留、attach 合并、bump；
- 生成：三门槛各自否决、`task_succeeded` 启发式、完整落盘 + manifest 回读、双 marker 一致性、discovery 识别 self_authored、同名/同任务去重、LLM 失败/结构非法降级、`load_task_steps` args 透传；
- 进化：四门（非自编写/<10 次/≥0.8/回滚冷却）、accept 路径（版本+1、代码替换、账本版本、来源保持）、reject 路径、无 LLM 保守拒绝、候选上限与排序；
- nudge：首跑到期 / 1h 水位 / 坏时间戳到期 / 分析检出 / 记录；
- 路由：质量三档增量、社区零增量、无账本仅 +0.1、demote 压过最大正向组合、`_load_skills` 合并账本；
- 反馈：`recent_review_flags` 空/全局/本技能、生成 prompt 含 flags、进化分析/打分 prompt 含 flags；
- 回滚：blockers+哈希匹配触发 / 哈希不匹配 noop / clean noop / 无备份 noop、回滚后冷却、pipeline 集成；
- **A1**：`verdict_for_hash` 当前结论/历史行/未命中三态、回滚复原可执行（含 marker 全量还原 + state 同步 + 哈希一致）、无历史保持 stale；
- **A2**：可见性段开关门控、pending 列出、blockers 显示 finding item、可执行技能不列出；
- **B1-B4**：种群去重（含空提案拒绝）、反射变异 prompt 含失败行与无失败兜底、多案例均值/上限 5/降级回退、校准触发与不触发、`fitness_discount` 记录。

**回归**：`test_evolution_layer`（25）、`test_post_task_evolution`、`test_smart_router`、`test_harness_tree`、`test_skill_loader`、`test_skill_review`、`test_context` 全绿——既有精确断言零破坏（质量增量只作用于自编写技能且位于 cap 内）。

**真实冒烟**（`scripts/live/skills/skill_evolution_live.py`，MANUAL 操作脚本，temp drive）：

```bash
set -a; source .env; set +a
.venv/bin/python scripts/live/skills/skill_evolution_live.py
```

场景（多次运行实录，mimo-v2.5 主槽位，仓库零改动）：审查反馈种子（network-egress flag 流入进化 prompt）→ 账本聚合（12 次/0.667）→ 当前任务真 LLM 生成（3 次成功生成 command-retry-handler / retry-command-on-error / retry-transient-errors，1 次降级记录 failed）→ nudge 分析 → GEPA 真 LLM 进化（真实报错文本驱动变异，4 次运行均保守拒绝 no_better_variant）→ 自动回滚确定性场景（含历史 clean 结论 → `restored review.json: {'status': 'clean', ...}` 复原可执行）→ 发现/来源/备份后检。预算 ≈ 1 生成 + ≤30 进化调用。

## 12. 与 Hermes GEPA 源案对照

依据本地源码实证（`NousResearch/hermes-agent-self-evolution` 全仓 + `stanfordnlp/dspy/dspy/teleprompt/gepa/gepa.py` + `gepa-in-depth.md`）：Hermes 的 GEPA = **Genetic-Pareto Prompt Evolution**（反射式变异 + 验证集多例评估 + 帕累托前沿探索；引擎为外部 `gepa-ai/gepa` 包；技能文本是唯一优化参数；守则门 = size/growth/结构 + pytest + PR 人工合入；其 GEPA 优化循环实际使用的 metric 是关键词重叠启发式——LLM-as-judge 未进入循环）。

| 维度 | Hermes GEPA | Ouroboros 实装 |
|---|---|---|
| 变异来源 | 反射 LM 读低分轨迹 → 针对性变异 | **真实失败轨迹注入的反射式变异**（B2）+ 失败分析建议 |
| 变异对象 | 技能文本（整段重写，单 predictor） | 完整技能包 JSON（manifest + 脚本） |
| 评估 | metric 对验证集逐例打分聚合（实践为关键词重叠启发式） | **多案例 LLM 打分取均值**（B3，≤5 案例） |
| 探索 | 帕累托前沿采样 + merge + 多代种群 | 单轮种群 + 渲染哈希去重（B1）+ 跨周期代际累积 |
| 校准 | holdout 集对比后才算改进 | **历史乐观自适应折扣**（B4） |
| 部署 | 约束门 + pytest + PR 人工合入 | 结构校验 + 审查门 + 覆盖前备份 + 审查失败自动回滚（A1 复原） |
| 审查反馈 | 无（PR 人工即事件） | **review flags 注入生成/进化 prompt** + A2 可见性段 |
| 版本/回滚 | git lineage + git revert | `.replaced-` 备份 + verdict_for_hash 复原 |
| 前置工程 | 无（无执行账本概念） | `SkillStatsLedger`（tools.jsonl 离线聚合） |

**明确不做的**（记录在案）：逐例帕累托探索 + merge + 多代种群（候选是整包脚本，交叉无良定义）；pytest-on-repo 门（候选未经审查不可执行，等价物 = 结构校验 + 审查门 + 回滚）；DSPy/gepa 依赖（对象是完整技能包，自成一套）。

## 13. 已知边界与后续路线

**边界（设计内，非缺陷）**：

- 审查不自动触发（写/跑分离）；A3（采纳后自动重审开关）仅记录不实现，待 A2 可见性积累数据后决定；
- 技能可长期 pending，不阻塞任何路径（A2 保证可见）；
- 回滚恢复内容与可复用的旧结论，不绕过哈希绑定（无历史结论时照常重审）；
- 变异有效性依赖失败素材质量与模型判断——真实采纳尚未发生，**"有效"需真实执行数据兑现**（多次冒烟拒绝恰好验证了拒绝路径的正确性）；B3/B4 正是为"评估可信"准备的数据化手段；
- 账本以 `logs/tools.jsonl` 为窗口（轮换即重置）——相对成功率语义，已文档化。

**后续路线**：

1. L3/L4 数据驱动：路由历史回填技能实际调用率 → 技能权重自校准（已列入 SMART_ROUTING_BOARD）；
2. 有效性实验：P0 语料抽取后四臂（V0-V3）同语料开跑，用 `skill_stats.json` 新旧成功率对比验证进化增益（评估值 vs 实测值，B4 校准即此闭环的自动化形态）；
3. A3 自动重审开关（待数据决定）；
4. 如实测显著低于评估，调整评估 prompt 或引入候选 dry-run（确定性预检 + 沙箱语法检查，避开审查门放行前的执行红线）。

## 14. 全程实景剧本（超详细五幕版，含真实冒烟数据）

> 本剧本用真实冒烟运行的数据（mimo-v2.5 主槽位，temp drive，仓库零改动）把"技能的一生"完整走一遍——从任务结束开始，历经生成、进化、审查、回滚复原、路由复用，每一步的触发条件、动作、落盘文件、真实产物全部写出，不省略。它是 §5-§8 机制章节的叙述性复现；真实产物来自多次冒烟运行实录。

### 第 0 幕：任务结束 → 进化入口

假设你让 Ouroboros 处理任务 `live-skill-task`："把日志压缩后上传到备份服务器，上传总报错要处理"。任务执行中调用了 7 次工具：

```
read_file → search_code → run_command → edit_text
→ run_command ❌ (报错) → edit_text → run_command ✅
```

任务成功收尾。此时后台线程（`maybe_promote`，走 `run_skill_evolution_step`，前提开关 `OUROBOROS_SKILL_EVOLUTION=true`）在这**同一次任务结束之后**按顺序做四件事：

| 步 | 动作 | 数据源 → 落盘 |
|---|---|---|
| Step 0 | 自动回滚检查：有没有"进化版被审成 blockers"的技能要还原 | `skills/self/*.replaced-*` + `state/skills/<名>/review.json` → 进化历史 |
| Step 1 | 翻账本：扫描 `logs/tools.jsonl` 中全部 `skill_exec` 行（一行一次调用），按技能名聚合次数/成败/起止时间 | `logs/tools.jsonl` → `state/skill_stats.json` |
| Step 2 | 当前任务生成检查：三门槛 + 去重 + LLM 提取 + 落盘 | `logs/tools.jsonl` → `skills/self/<名>/` + `skill_generation_history.jsonl` |
| Step 3 | nudge 到期检查（距上一条 `skill_nudges.jsonl` ≥3600s；首次运行必到期）→ 失败技能进化 + 可复用任务补充生成 | `state/skill_nudges.jsonl` |

账本这轮统计出技能 `live-demo-skill` 的 12 次历史执行（分布在 `live-task-0/1/2` 三个任务，各 4 次——**注意账本统计的是历史汇总，不是单任务调用**）：**8 次成功、4 次失败 → 成功率 0.6667**。`state/skill_stats.json` 落盘内容：

```json
{"live-demo-skill": {"execution_count": 12, "success_count": 8,
                     "success_rate": 0.6667,
                     "first_ts": "2026-09-03T00:00:00Z",
                     "last_ts": "2026-09-03T00:00:00Z",
                     "evolution_version": 1}}
```

这个 0.6667 一会儿是进化的**候选门槛依据**和**原版基线**。

### 第 1 幕：生成——好任务沉淀成新技能

Step 2 检查当前任务 `live-skill-task` 的三道门槛（全部来自日志轨迹，零额外成本）：

- **工具调用 ≥5 次** ✅（7 步）；
- **有自我修复** ✅（第 5 步 `run_command` 报错、第 6 步 `edit_text` 补上、第 7 步成功——"错误步骤之后出现恢复步骤"）；
- **任务成功** ✅（outcome_hint 为 success，或最后一步非错误）。

三关全过后进入提取流程：

1. **选关键步骤**：复用进化层 `assign_credits`（0.5 基 + 成功 +0.2 − 错误 0.3 + 快 +0.1 + 省 token +0.1，归一化到和 1.0）+ `identify_critical_steps`（信用最高 top-3 = "扛起任务的步骤" + 最低 2 = "拖后腿的步骤"），拼成步骤行（tool/成败/args 截断 400/结果截断 200，上限 8 条）；
2. **LLM 提取**（主槽位 `chat_observed`，reasoning=medium，4096 tokens）：prompt = 任务目标（或"从步骤推断"）+ 信用排序的关键步骤 + **[Reviewer flags to avoid]**（若最近有其他技能被审出 FAIL findings，全局扫描 `state/skills/*/review.json` 提取后在此列出，要求"新技能不得重复这些被标模式"）+ 严格 JSON schema（name/description/type/runtime/when_to_use/parameters/tags/scripts）+ 硬规则（名字与脚本名只允许 `[A-Za-z0-9._-]`；代码必须完整自包含，stdlib 或 vendor；技能之间不允许互相调用）；
3. **结构校验** `validate_generated_skill`：dict、canonical 名字非空、script 型必须有非空安全名脚本与代码、instruction 型必须有 body、runtime 白名单兜底、tags ≤8；失败记 `failed` 历史（含原因）；
4. **落盘** `write_skill_package`：真实冒烟产物——

```
skills/self/command-retry-handler/
├── SKILL.md                  ← YAML frontmatter + 空 body
├── scripts/main.py           ← 完整可运行代码
└── .self_authored.json       ← "这是我写的"来源证书（state/skills/<名>/ 双写一份，task_id/created_at 两侧须一致）
```

真实 SKILL.md 落盘实录（frontmatter 由 `render_skill_manifest` 生成）：

```yaml
---
name: command-retry-handler
description: A skill that retries a specified shell command multiple times upon
  failure, specifically designed to handle transient errors such as network
  timeouts, temporary file locks, or system hiccups...
version: '1.0'
type: script
when_to_use: whenever a task involves executing commands or scripts that might
  fail intermittently due to temporary issues...
timeout_sec: 60
scripts:
- main.py
tags:
- retry
- command
- error-handling
- transient
- utility
---
```

5. **历史**：`skill_generation_history.jsonl` 记一行 `{ts, task_id, skill_name, skill_description, type, outcome: "created", reason: ""}`。

补充事实（多次冒烟实录）：同样的轨迹模型另一次生成的是 `retry-transient-errors`（名字因模型而异，机制一致）；还有一次 LLM 输出未通过 JSON 提取，走了**降级路径**——`outcome: "failed", reason: "llm_extraction_failed"`，不落盘、不影响任何后续步骤。**新技能此刻的状态：pending 审查 + disabled**——可以被发现、被路由推荐，但**不能执行**，执行权在第 3 幕。

### 第 2 幕：进化——失败技能被尝试改进

同一次任务结束，Step 3 的 nudge 首次运行必到期（`skill_nudges.jsonl` 尚无记录）。`analyze_recent()`（规则化、零 LLM）扫最近 400 行日志：检出 `failed_skills: ["live-demo-skill"]`、`best_reusable_task: {live-skill-task, 7 次调用}`。

`live-demo-skill` 过四道候选门：

| 门 | live-demo-skill 实测 |
|---|---|
| 自编写（`is_self_authored`，双 marker 校验） | ✅ |
| 执行 ≥10 次（`skill_stats.json`） | ✅ 12 次 |
| 成功率 <80% | ✅ 0.6667 |
| 近 24h 未自动回滚（进化历史 `action=="rolled_back"` 冷却） | ✅ |

进入 GEPA 进化主流程（**当前完整版，一字不省**）：

**① 取失败素材**：`_recent_failures` 从 `logs/tools.jsonl` 筛出该技能最近 ≤8 条失败执行，携带**真实报错文本**（result_preview）——本轮实际是这 4 条：

```
tarfile.ReadError: file is not a tar archive
PermissionError: [Errno 13] Permission denied: 'logs.tar'
subprocess.TimeoutExpired: command 'tar -czf' timed out after 60s
FileNotFoundError: [Errno 2] No such file or directory: 'archive.d'
```

**② 失败分析**（LLM，2048 tokens）：主槽位模型读技能代码 + 上面 4 条报错 + **[Recent reviewer findings for THIS skill]**（种子审查结论 `[high] network-egress: script must not contact external endpoints` 注入，要求变异避开），输出 `{common_errors, suggestions}`（建议 ≤2 条）。

**③ 建种群（≤5，含去重）**：

```
0 号 = 原版（基线 = 实测成功率 0.6667，不调模型、不打分）
1 号 = 按建议①变异（主通道）
2 号 = 按建议②变异（若有）
3-4 号 = 固定策略池兜底补齐（add_error_handling / improve_description / optimize_parameters，随机顺序）
```

每条建议/策略驱动的变异（`_mutate`，4096 tokens）prompt 结构：

```
{指令（建议原文 或 策略说明）}

[Current skill]
{技能完整 JSON（含全部脚本代码）}

[Recent failing executions of THIS skill — the rewrite MUST make the script handle these cases]
- status=error: tarfile.ReadError: file is not a tar archive
- status=error: PermissionError: [Errno 13] Permission denied: 'logs.tar'
...（≤6 条）

Return the COMPLETE modified skill as ONLY JSON: {...}
```

——这就是 **B2 反射式变异**：变异 prompt 带着真实失败轨迹，"必须消除这些失败模式"，不再凭泛泛建议。产出按**渲染内容哈希去重**（B1：与原版或已收录变体指纹相同 → 丢弃；模型返回 `{}` 空 dict → 视为变异失败不入种群）。

**④ 多案例评估**（B3）：`_build_eval_cases` 从该技能自身历史构造 ≤5 条 mini 案例（≤2 条成功执行的预期行为 + 失败案例），`_evaluate`（1024 tokens/变体）prompt：

```
Score this skill variant against each execution case below (0.0-1.0 per case).

[Variant] {技能 JSON}
[Historical context] executions: 12; current success rate: 0.6667
[Reviewer-flagged problems…: network-egress（重复必须低分）]

[Cases (from this skill's real executions)]
1. [success] compressed archives uploaded
2. [failure] tarfile.ReadError: file is not a tar archive
3. [failure] permission denied: 'logs.tar'
...

Return ONLY JSON: {"case_scores": [0.0-1.0, ...]}
```

每个变体=逐案例打分取均值；解析失败回退单值 `fitness`，垃圾输出 0.0；原版不调用模型，基线=实测成功率。

**⑤ 校准折扣**（B4）：查该技能进化历史——0 次采纳 → `fitness_discount = 1.0`（门槛不动）；若 ≥3 次采纳且"评估均值−实测成功率 ≥0.1"（系统性乐观）→ 折扣 0.9，`fitness_discount` 记入记录。

**⑥ 采纳判定**：`折扣后最高分 > max(当前成功率, 0.5)` **且**结构合法（渲染→重解析 round trip、名字不变、脚本安全）才采纳。

**拒绝分支（本轮真实结局）**：真模型评估后所有变体均未超过基线 → 拒绝。真实记录：

```json
{"ts": "2026-09-03T11:52:13+00:00", "skill": "live-demo-skill",
 "old_success_rate": 0.6667, "new_success_rate": 0.6667,
 "mutation_type": "none", "accepted": false, "reason": "no_better_variant",
 "version_from": "1.0", "version_to": "", "evolution_version": 0,
 "backup_dir": "", "fitness_discount": 1.0}
```

原版原样保留、版本不动、无备份产生（`backup_dir` 为空）。**这是设计内的最优结局**：模型对着真实报错改了一轮，确实没有变体更好——那就别动。"永远拒绝"不再是无差别保守：现在拒绝的依据是真实失败上下文下的逐案例打分。

**采纳分支（若模型给出 0.85 分变体 > 0.6667）**，动作序列：

```
1. _backup_skill：旧包完整复制 → skills/self/live-demo-skill.replaced-<ts>/
   （SKILL.md + scripts/* + .self_authored.json 全量——marker 参与内容哈希，必须全量）
2. 覆盖写入：版本 1.0 → 1.1（_bump_version，manifest version 小步 +1），main.py 换成新代码
3. 账本：evolution_version 1 → 2（bump_evolution_version，合并保留其余字段）
4. 历史记录：{accepted: true, old 0.6667, new 0.85, mutation_type,
   version_from "1.0", version_to "1.1", backup_dir, fitness_discount}
```

采纳后：内容哈希变化 → 审查结论 stale → **不可执行**，进入第 3 幕的待重审状态。

### 第 3 幕：审查——谁能真正跑起来

生成或采纳之后的技能，一律不可执行，等外部裁决（审查永不自动触发——"写"与"批准"分离是哈希绑定不变量的来源）：

| 状态 | 含义 | 出路 |
|---|---|---|
| **pending**（新生成） | 未被审过 | agent 后续任务调 `skill_review` 工具（确定性预检 + 三模型 LLM 审查），或 owner 在 UI 点 attest-review（`POST /api/owner/skills/<名>/attest-review`，owner-only，浏览器工具禁止代理访问，预检通过直接落 clean） |
| **stale**（进化/编辑后） | 审过但字节变了，旧结论过期（content_hash 不匹配） | 同样重审/背书 |
| **blockers**（审出 FAIL findings） | 结构/安全有阻断项 | 改/重审/背书/（有备份时）自动回滚 |

审查干净（clean/warnings）→ auto-grant（默认开）自动授权启用 → `skill_exec` 逐道闸校验（enabled → 审查新鲜 → grants → 双重哈希）才真正执行。

**A2 可见性**：无法执行的技能不再无声无息——下个任务的 context 动态区出现：

```
## Skills Needing Review or Backoff
These skills are NOT executable until handled: pending/stale need a skill_review
(or owner attestation); blockers need a fix or override.
- live-demo-skill: content changed since review — re-review needed; review is stale
- bad-skill: blocked by review (network-egress); review is stale
```

（状态读 **review.json 原始值**——`load_review_state` 会按 findings 重新聚合（单条 FAIL→warnings），归一化状态会掩盖 blockers 判定，故此处与回滚触发共用原始状态语义。段落在开关门控下非空才注入，上限 12 条。）

### 第 4 幕：回滚与复原——审查失败的两条路

**场景**：`live-demo-skill` 1.1（采纳版）被审成 blockers，verdict 哈希 == 当前 1.1 字节哈希。下个任务边界 Step 0 自动检查三项：`.replaced-` 备份存在 ✅ + `review.json` 状态为 blockers ✅ + `content_hash == compute_content_hash(当前包)` ✅（**哈希不匹配的过期结论、pending、clean 一律不触发**）→ 自动回滚：

```
1. 完整还原：备份的 SKILL.md + scripts/* + .self_authored.json 全量换回；
   （marker 参与内容哈希，不全量还原哈希就对不上——这是 A1 实现中挖出的关键细节）
2. _sync_state_marker：把还原的 marker payload 同步写回 state/skills/<名>/self_authored.json
   （两侧 task_id/created_at 一致，is_self_authored 判定保持为真）
3. A1 查历史结论：verdict_for_hash(还原后哈希)
   → 先看 review.json 当前值（已不匹配）→ 扫描 review_history.jsonl
   → 命中 2026-09-02 那条 clean（content_hash == 旧哈希）→ save_review_state 落回：
   restored review.json: {'status': 'clean', 'content_hash': '85bd32…'}
   → 技能原地恢复可执行（等价 git revert，无需人工重审）
4. 消费备份（删除）；版本回 1.0；provenance 完好
5. 进化历史记 rolled_back 行：
   {"action": "rolled_back", "skill": "live-demo-skill",
    "reason": "review_blockers", "backup_dir": "...",
    "restored_version": "1.0", "restored_verdict": "clean"}
6. 24h 冷却：evolver 的 _recent_rollback 检查该行，窗口内不再进化此技能（防翻烙饼）
```

**没有历史干净结论的情况**：`restored_verdict: ""`，回滚只恢复内容，保持 stale（review.json 仍是 blockers，但哈希已不匹配 → 不再触发二次回滚），照常重审/背书后执行——**回滚恢复内容与可复用的旧结论，但永不绕过哈希绑定**。

### 第 5 幕：消费与闭环——循环转起来

- **路由消费**（`OUROBOROS_SMART_ROUTING=true` 时每次任务开始）：`_load_skills` 发现技能 + 合并 `skill_stats.json` → `_calculate_skill_score` 对自编写技能加分（+0.1 自编、成功率 >80% 再 +0.1、evolution_version>1 加 0.05×(v−1)，cap 1.0 内）→ ≥0.6 进 `[SMART ROUTING]` Top-10 推荐 → 审查启用后的 `command-retry-handler` 出现在后续任务的推荐块里，agent 直接调用；
- **账本回归**：调用产生的成败进入 `skill_stats.json` → 下一轮进化的**基线**（原版分 = 实测成功率）与 **B4 校准的实测数据**；
- **审查反馈**：`network-egress` 这类 FAIL findings 持久留在 review.json → `recent_review_flags` 提取后注入下一轮**生成**（"[Reviewer flags to avoid]"）与**进化**（失败分析 + 评估打分，"重复被标必须低分"）——同一个坑不会反复踩；回滚后 review.json 仍是 blockers，flags 继续生效；
- **校准**：连续 3 次采纳 + 评估均值与实测差 ≥0.1 → 门槛 ×0.9 收紧——模型自评从此被实测数据管着。

### 全程账本与总览

| 文件 | 记录什么 | 本轮剧本里的内容 |
|---|---|---|
| `state/skill_stats.json` | 每技能执行次数/成功率/进化版本/校准数据 | live-demo-skill: 12 次 / 0.6667 / v1 |
| `state/skill_generation_history.jsonl` | 每次生成尝试（created/skipped/failed + 原因） | command-retry-handler: created |
| `state/skill_evolution_history.jsonl` | 每次进化判定 + 回滚行（含 restored_verdict/fitness_discount） | accepted: false, no_better_variant；rolled_back + clean |
| `state/skill_nudges.jsonl` | nudge 水位 + 当次分析 | failed_skills: [live-demo-skill] |
| `state/skills/<名>/review.json` + `review_history.jsonl` | 哈希绑定结论 + 历史（verdict_for_hash 索引源） | blockers → 回滚 → clean 复原 |

```
任务结束 → ①回滚检查 ②翻账本 ③当前任务→生成新技能(pending) ④nudge到期→进化
进化 = 真实报错驱动反射变异 + 去重种群 + 多案例打分 + 校准门槛 + 采纳才备份覆盖
生成/进化的产物一律等审查 → clean启用执行 / blockers自动回滚(命中历史结论即复原+24h冷却)
执行数据回流账本 → 路由加分 → 复用 → 新数据 → 循环
审查FAIL findings → 注入下一轮生成/进化 prompt → 老坑不重踩
```

## 15. 变更记录

| 时间 | 版本 | 内容 |
|---|---|---|
| 2026-09-03 上午 | v1.0 | 初版四件套：`stats`/`auto_generation`/`genetic_evolution`/`nudge` + `pipeline` 编排；合并开关 `OUROBOROS_SKILL_EVOLUTION`；51 例测试；真实冒烟（生成 2 次成功、进化 2 次拒绝）；文档成稿 12 章 |
| 2026-09-03 下午 | v1.1（加固） | ① 审查反馈闭环 `recent_review_flags`（生成/进化 prompt 注入 FAIL findings）；② 进化覆盖前 `.replaced-` 备份（含 backup_dir 记录）；③ 审查失败自动回滚（blockers+哈希匹配）→ 还原 + 24h 冷却；45→51 例 |
| 2026-09-03 晚间 | v1.2（GEPA 对齐） | A1 `verdict_for_hash` 哈希→结论索引，回滚命中历史 clean/warnings 即复原可执行（marker 全量还原 + state 同步）；A2 context 待审可见性段（原始状态语义）；B1 种群渲染哈希去重 + 空提案拒绝；B2 反射式变异（真实失败轨迹注入）；B3 多案例评估（≤5 案例取均值）；B4 校准（评估乐观 → fitness ×0.9）；51→67 例；冒烟含回滚复原场景 |
| 2026-09-03 深夜 | v2.0 | 文档整理重排：15 章（机制章节 + 五幕实景剧本 + 变更记录），去重旧剧本 |

---

**文档生成时间**: 2026-09-03（实现当日；含真实冒烟多次运行实录）