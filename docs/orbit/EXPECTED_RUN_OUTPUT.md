# 进化臂运行日志：预期输出对照（max=1 / max=2 / 先 max=1 再 resume max=2）

本文件是 `devtools/benchmarks/evolution/run_evolution_arm.py` 当前输出契约的对照样本，用于跑完后逐行核对。
生成方式：用 `devtools/benchmarks/evolution/leap_report.py` 的渲染器 + 真实运行（smoke_boundry_4）的数值渲染，**不是手写示意**。

## 读日志前须知（三条）

1. **哪些行只进终端、不进日志文件**
   `[isolated-server] …`（重启 bounce 的提示）是 harness 调用的子进程助手的裸 `print`，**不会**写入
   `run_evolution_arm.log`（实测命中 0）。所以终端可能比日志文件更"吵"，而**产物始终干净**。
   同一段 busy 只报一次（状态变化后才再报）。

2. **两套编号，含义不同**
   - `[战役] 第 N/M 个战役已提交请求`：**本 session 内**的计数 / 本 session 的 max 预算。
     resume 后重新计数（基线是 session 开始前已有的战役数）。
   - `⑦变异 Δ 战役#K 开` / `⑧选择 ✓ 战役#K ⤷ commit` / `⑨遗传 H 战役#K ⤷ 终态`：**campaign 的 cycle 号**，
     跨 session 连续（同一 campaign 文档里的第 K 个周期）。

3. **算子的含义按论文算法 1**
   `②执行 τ` / `③归因 E` / `④记忆 M`（含 `+1 经验` 这一次写入）/ `⑤触发 W` / `⑥规划 P` /
   `⑦变异 Δ`（**代码侧**补丁，隔离克隆）/ `⑧选择 ✓` / `⑨遗传 H`（代码级＝吸收提交；行为级＝技能生成）/
   `⑪沉淀 M`（第 12 步，**结果已知之后**的账本写入）。
   `等待 ·` 与 `运行 ·` 是运行态行（不属于任何算子），算子标因此只表示一件事。

## 逐记录的三段输出时机

| 时刻 | 出现的内容 |
|---|---|
| 记录开始（播种后） | 块头 + `②执行 轨迹播种 N 行` |
| 反思返回后（promote 前） | `②执行` 目标/轮次/摘要 + `④记忆`（记忆落库、backlog、技能资格） |
| promote 决策返回后 | `③归因` → `④记忆 +经验` → `⑤触发` → `⑥规划` → `⑨遗传(行为级)` → `[战役] …` → `⑦变异 开` |
| 战役终态被轮询到 | `⑨遗传 ⤷ absorbed/abandoned/no_op/infra_failed` → `⑪沉淀 checkpoints: …` |

---

## 以下为三个版本的预期输出

==============================================================================
版本一：--max-absorbed 1（一次 session，语料 11 条）
==============================================================================
━━ LEAP 进化会话 · 臂 V3 · 语料 11 条 · cadence every_n:5 ━━━━━━━━━━━━━━
 运行配置  模型槽位 main=openai-compatible::mimo-v2.5 light=openai-compatible::mimo-v2.5 heavy=openai-compatible::mimo-v2.5
           战役预算 max=1 | cadence 块大小=5 | 历史战役基线=0
 运行  ·  starting isolated server on http://127.0.0.1:54621 …
 运行  ·  provider 探活: ✅（…链路正常）

【记录 1 的完整三段；记录 2–4 同结构，仅 cadence 计数递增】
━━ 记录  1/11 · 2023_level1:36 (L1) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 37 行
        ↓（静默数分钟＝反思 LLM 调用中）
 ②执行  τ  目标: 2023_level1:36 的任务目标…
          轮次 39 | 错误 13 | 标记 SHELL_EXIT_ERROR | 反思 1663 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-01 "改进项 #1" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level1:36 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 1）
 ⑤触发  W  cadence 1/5 未到期 → 跳过晋升
━━ 记录  2/11 …  3/11 …  4/11 ━━  （同三段，⑤触发：cadence 2/5、3/5、4/5 未到期）

【记录 5：边界 → 发起战役 #1】
━━ 记录  5/11 · 2023_level2:35 (L2) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 175 行
 ②执行  τ  目标: 2023_level2:35 的任务目标…
          轮次 155 | 错误 16 | 标记 SHELL_EXIT_ERROR,TOOL_ERROR | 反思 1757 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-05 "改进项 #5" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level2:35 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 5）
 ⑤触发  W  cadence 0/5 | LLM: promote ✅ 理由: …依据归因证据…
 ⑥规划  P  目标: Add automatic capability pre-check before task execution | backlog: ibl-05
 ⑨遗传  H  技能生成: skill-5
[战役]    第 1/1 个战役已提交请求
[战役]    达到战役上限 1，停止喂料（剩余 6 条记录未处理）
 ⑦变异  Δ  战役#1 开: "Add automatic capability pre-check…" (task 675e1043)
   ↑ 这里没有 ⑪沉淀：战役尚无结果
━━ 里程碑 @记录5 ━━ 周期0 (吸收0, no_op0) | 技能4 | 经验5 | backlog开放7

【收尾：等战役 #1 落账（记录 6–11 未处理）】
 等待  ·  等待最后一个战役完成…
 等待  ·  300s · 战役进行中 · 调用 30 · 编辑 4 · shell 3 · 提交 3 · 参数错 2 · 闸门拦 2 · 最近 advisory_review
 ⑧选择  ✓  战役#1 ⤷ commit ✅ b2f0c13f40
[isolated-server] restart signal: server busy — will retry (silenced until it changes)      ← 仅终端，一次
[isolated-server] restart signal staged (marker=True tx_outcome=waiting_for_restart) — bouncing server …   ← 仅终端
 ⑨遗传  H  战役#1 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=2 周期=1 吸收=1 分布={'absorbed': 1, 'waiting_for_restart': 1} 成本=$0
 等待  ·  战役收尾完成（absorbed）
 运行  ·  Track-B 补消费: 1 个周期入账
━━ 会话收尾 · 臂 V3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ⑪沉淀  M  记录 5/11 | 失败 0
          吸收 1 | 放弃 0 | no_op 0 | 成本 $0
          账本分布 absorbed=1, waiting_for_restart=1
          吸收提交:
            b2f0c13f404c  feat: add tool preflight checks
          clone b2f0c13f | tag V3-evolved
          ledger: /…/session_ledger.json

==============================================================================
版本二：--max-absorbed 2（一次 session，语料 11 条 → 2 个战役 + 1 条尾巴）
==============================================================================
━━ LEAP 进化会话 · 臂 V3 · 语料 11 条 · cadence every_n:5 ━━━━━━━━━━━━━━
 运行配置  模型槽位 main=openai-compatible::mimo-v2.5 light=openai-compatible::mimo-v2.5 heavy=openai-compatible::mimo-v2.5
           战役预算 max=2 | cadence 块大小=5 | 历史战役基线=0
 运行  ·  provider 探活: ✅

【记录 1–4：同版本一的三段结构】

【记录 5：发起战役 #1（第 1/2，未到上限 → 继续喂料）】
━━ 记录  5/11 · 2023_level2:35 (L2) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 175 行
 ②执行  τ  目标: 2023_level2:35 的任务目标…
          轮次 155 | 错误 16 | 标记 SHELL_EXIT_ERROR,TOOL_ERROR | 反思 1757 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-05 "改进项 #5" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level2:35 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 5）
 ⑤触发  W  cadence 0/5 | LLM: promote ✅ 理由: …依据归因证据…
 ⑥规划  P  目标: Add automatic capability pre-check before task execution | backlog: ibl-05
 ⑨遗传  H  技能生成: skill-5
[战役]    第 1/2 个战役已提交请求
 ⑦变异  Δ  战役#1 开: "Add automatic capability pre-check…" (task 675e1043)
━━ 里程碑 @记录5 ━━ 周期0 (吸收0, no_op0) | 技能4 | 经验5 | backlog开放7

【记录 6：先等执行完，再与吸收并行反思 ← 你问的那段】
 等待  ·  在途战役仍在执行——等它提交后再开始下一轮反思
   （执行等待期只报心跳；bounce 不在此驱动，因为重启请求还没提出）
 等待  ·  240s · 战役进行中 · 调用 30 · 编辑 4 · shell 3 · 提交 3 · 参数错 2 · 闸门拦 2 · 最近 advisory_review
 ⑧选择  ✓  战役#1 ⤷ commit ✅ 1a2b3c4d5e
 等待  ·  战役执行完成（commit 已落定）——下一轮反思与吸收并行进行
━━ 记录  6/11 · 2023_level2:51 (L2) · 并行 战役#1 吸收中 ━━━━━━━━━━
 ②执行  τ  轨迹播种 99 行
        ↓（反思期间服务端重启 + boot 自检＝吸收；日志安静）
 ②执行  τ  目标: 2023_level2:51 的任务目标…
          轮次 116 | 错误 22 | 标记 SHELL_EXIT_ERROR | 反思 1690 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-06 "改进项 #6" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level2:51 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 6）
 ⑤触发  W  cadence 1/5 未到期 → 跳过晋升
   （记录 6 自己的算子到此；战役的结局在下一次轮询浮现 ↓）
 ⑨遗传  H  战役#1 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=2 周期=1 吸收=1 分布={'absorbed': 1, 'waiting_for_restart': 1} 成本=$0
[isolated-server] restart signal: server busy — will retry (…)   ← 只报一次，通常落在记录 6 末尾这一段

【记录 7–9：正常块（无战役在途 → header 不带「并行」）】

【记录 10：第二个边界 → 战役 #2 → 撞上限停喂料】
━━ 记录 10/11 · 2023_level3:10 (L3) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 35 行
 ②执行  τ  目标: 2023_level3:10 的任务目标…
          轮次 26 | 错误 7 | 标记 SHELL_EXIT_ERROR | 反思 1552 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-10 "改进项 #10" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level3:10 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 10）
 ⑤触发  W  cadence 0/5 | LLM: promote ✅ 理由: …依据归因证据…
 ⑥规划  P  目标: Add a PDF-download-and-extract helper pattern | backlog: ibl-10
 ⑨遗传  H  技能生成: skill-10
[战役]    第 2/2 个战役已提交请求
[战役]    达到战役上限 2，停止喂料（剩余 1 条记录未处理）
 ⑦变异  Δ  战役#2 开: "Add a PDF-download-and-extract helper pattern…" (task cec5c826)
━━ 里程碑 @记录10 ━━ 周期1 (吸收1, no_op0) | 技能8 | 经验10 | backlog开放16

【收尾：等战役 #2 落账】
 等待  ·  等待最后一个战役完成…
 等待  ·  420s · 战役进行中 · 调用 34 · 编辑 6 · shell 4 · 提交 1 · 参数错 2 · 闸门拦 2 · 最近 commit_reviewed
 ⑧选择  ✓  战役#2 ⤷ commit ✅ 9f8e7d6c5b
 ⑨遗传  H  战役#2 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=4 周期=2 吸收=2 分布={'absorbed': 2, 'waiting_for_restart': 2} 成本=$0
 等待  ·  战役收尾完成（absorbed）
━━ 会话收尾 · 臂 V3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ⑪沉淀  M  记录 10/11 | 失败 0
          吸收 2 | 放弃 0 | no_op 0 | 成本 $0
          账本分布 absorbed=2, waiting_for_restart=2
          吸收提交:
            1a2b3c4d5e6f  feat: add tool preflight checks
            9f8e7d6c5b4a  feat: add PDF download helper
          clone 9f8e7d6c | tag V3-evolved
          ledger: /…/session_ledger.json

==============================================================================
版本三：先 --max-absorbed 1 跑一轮，再 --resume --max-absorbed 2 接着跑
==============================================================================
── session A：max=1（记录 1–5 → 战役 #1 → 停）──
   与版本一的 1–5 完全相同（同一 session 目录），结尾是：
 ⑨遗传  H  战役#1 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=2 周期=1 吸收=1 …
 ⑪沉淀  M  记录 5/11 | 失败 0 | 吸收 1（会话收尾块）

── session B：--resume --max-absorbed 2（复用同一 clone+data，基线=1）──
━━ LEAP 进化会话 · 臂 V3 · 语料 11 条 · cadence every_n:5 ━━━━━━━━━━━━━━
 运行配置  模型槽位 main=openai-compatible::mimo-v2.5 light=openai-compatible::mimo-v2.5 heavy=openai-compatible::mimo-v2.5
           战役预算 max=2 | cadence 块大小=5 | 历史战役基线=1
   ↑ 历史战役基线=1：session A 的战役 #1 已落账，所以本 session 的新预算是 2 个（本次只会用到 1 个）
 运行  ·  provider 探活: ✅

【记录 6–9：三段结构照常（这次 header 不带「并行」——上一次的战役在 session A 已吸收完）】

【记录 10：边界（计数器 5→10）→ 战役 = CYCLE #2，本 session 第 1/2】
━━ 记录 10/11 · 2023_level3:10 (L3) ━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 35 行
 ②执行  τ  目标: 2023_level3:10 的任务目标…
          轮次 26 | 错误 7 | 标记 SHELL_EXIT_ERROR | 反思 1552 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-10 "改进项 #10" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level3:10 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 10）
 ⑤触发  W  cadence 0/5 | LLM: promote ✅ 理由: …依据归因证据…
 ⑥规划  P  目标: Add a PDF-download-and-extract helper pattern | backlog: ibl-10
 ⑨遗传  H  技能生成: skill-10
[战役]    第 1/2 个战役已提交请求                              ← 会话内计数
 ⑦变异  Δ  战役#2 开: "Add a PDF-download-and-extract helper pattern…" (task cec5c826)
   ↑ 战役行用的是 campaign 的 cycle 号（#2）；[战役] 那行用的是本 session 计数（1/2）。两者都对，含义不同

【记录 11：尾巴（11 % 5 = 1，不满一块 → 只反思，不晋升）】
━━ 记录 11/11 · 2023_level1:6 (L1) ━━━━━━━━━━━━━━━━━━━━━━━━━
 ②执行  τ  轨迹播种 0 行
 ②执行  τ  目标: 2023_level1:6 的任务目标…
          轮次 7 | 错误 0 | 标记 — | 反思 123 字
 ④记忆  M  scratchpad_append: LIGHT_MODE_BLOCKED fires when…
          落库 1/1
          backlog 候选 1 | 新增 1（high 1）
            +ibl-11 "改进项 #11" (high | count=1)
          技能资格 ✅ (ok)
 ③归因  E  信用 +1 步计分: 最高 web_search 0.012 | 最低 web_search 0.012
          Track-A task=2023_level1:6 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)
 ④记忆  M  +1 经验（账本累计 11）
 ⑤触发  W  cadence 1/5 未到期 → 跳过晋升

【收尾】
 提示  ·  本次 session 处理 6 条，末尾 1 条不足一个 cadence 块（N=5）——已积累反思/经验，未触发晋升（共 1 个战役；resume 会从下一条继续，尾巴可与其后的记录凑满一块）
 等待  ·  等待最后一个战役完成…
 ⑨遗传  H  战役#2 ⤷ absorbed ✅
 ⑪沉淀  M  checkpoints: 行=4 周期=2 吸收=2 分布={'absorbed': 2, 'waiting_for_restart': 2} 成本=$0
━━ 会话收尾 · 臂 V3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ⑪沉淀  M  记录 11/11 | 失败 0
          吸收 2 | 放弃 0 | no_op 0 | 成本 $0
          账本分布 absorbed=2, waiting_for_restart=2
          吸收提交:
            1a2b3c4d5e6f  feat: add tool preflight checks
            9f8e7d6c5b4a  feat: add PDF download helper
          clone 9f8e7d6c | tag V3-evolved
          ledger: /…/session_ledger.json
