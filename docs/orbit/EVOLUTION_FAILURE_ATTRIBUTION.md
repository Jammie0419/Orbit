# 进化冒烟失败归因：谁的问题（smoke_test_10 + smoke_test_fix 全周期复盘）

> 2026-09-13。证据来源：smoke_test_fix 的 tools.jsonl / observability payload 时间线 /
> evolution_checkpoints.jsonl / supervisor.jsonl，全部可复核。结论先行：
> **0% 吸收率是源码缺陷的伪影——既不是 agent 进化改的代码坏了，也不是吸收机制坏了。**

## 一、"只吸收一次"的精确归因

**agent 的代码几乎每轮都是好的。** 每个周期的 agent 都真实完成了实现（cycle 10 加 139 行、
cycle 11 加 154 行、最终吸收的 cycle 12 加 329 行），测试 34/34 到 42/42 全过。失败从不发生在
"它写了什么"，而发生在"它能不能把写好的东西送过闸门"。

**吸收机制本身一直是好的。** boot reconcile（agent_startup_checks.py:806）第一次拿到它该拿的
输入（commit sha + 重启）就正确吸收了，没有出过一次错。

真正挡住吸收的是**到达吸收之前的一串闸门**，逐周期归因：

| 失败点 | 归因层 | 波及周期 |
|---|---|---|
| 1M scope 死墙（46 冻结工件全 required，评审包装不进去） | 源码架构缺陷（评审包组装） | 7 个 |
| stale 测试 `experience_digest` KeyError 拦死测试预检 | 源码回归（框架改 prompt 格式没改自己的测试） | 所有走到测试的周期 |
| shell commit 绕过评审链 + JSON cmd 绕洞 | 源码缺陷（缺栅栏 + 栅栏有洞） | 2 个 |
| agent 把闸门写进 `tools/registry.py`（冻结面） | **agent 修改越界**（唯一"进化代码有问题"的实例，且是治理问题非质量问题） | 1 个 |
| release tag 不可变被拦 | agent 越界 + 契约缺口 | 1 个 |
| schema 含 commit_reviewed 却从不发调用、自我说服"不可调用" | 弱模型行为（scratchpad 污染放大） | 1 个 |
| 无人执行重启（restart_request 事件无消费者） | 框架与产品间的假设缺口 | 所有到达 waiting_for_restart 的周期 |

## 二、四层失败分解（论文归因框架，每层有 observability 证据可引）

1. **源码缺陷层**（修在 `ouroboros/` 本体）：动态必需集 b347d06b、Track B schema 分裂 +
   runtime 字段 10b512ec、shell 栅栏及 JSON 绕洞 59109d21/2ff9f7a6、finalize 补消费 59109d21、
   stale 测试 a727ae17
2. **治理与配置层**：契约 v2 冻结面禁令 882cfcd7、owner_chat_id 闸门、objective 重复熔断 3/3
   （BUG3 防自维护回路按设计工作，换目标即恢复——不是缺陷）
3. **驱动层缺口**（产品有外部 launcher 兜底、隔离基准里没有；修在 `devtools/`，核心源码未动）：
   重启驱动 `maybe_bounce_for_restart`、`.env` 自动加载、scratchpad 卫生守卫 `_scratchpad_hygiene`
   （3f423435）
4. **弱模型能力层**（不修代码，如实记录为实验数据）：commit_reviewed 调用率不稳定
   （cycle 10 调了、11 没调；827K 字符系统提示下的工具注意力稀释是候选根因）、
   错误信念写入共享 scratchpad 的污染传播

**三批修复没有一处是因为"agent 进化改出来的代码有 bug"。**

## 三、对论文的含义

1. **机制可用性已证明**：harness 修好后，第一个完整周期（e7ab9a6a，commit 432237728995，
   +329/-0 零发布面触碰）即吸收——链路没有隐藏障碍。
2. **但 n=1，不能宣称 agent 成功率**：之前 0% 是 harness 伪影，现在 100%（1/1）同样是小样本。
   真实的周期成功率只有靠全量语料跑出。
3. **归因分解本身是实验资产**：四个失败层可分别测量，负结果可以精确说清"是哪一层的问题"，
   而不是笼统的"进化失败了"。

## 四、第十一轮冒烟命令（不含部署，人工执行）

前置确认（2026-09-13 已完成）：旧 server/trigger 进程已全部清理；语料
`gaia_corpus_smoke_2026-09-04.jsonl`（11 条，与第十轮同集）；新会话将从 9a091dc2 clone，
自动带上全部修复（P0 重启驱动 / P1 env 加载 / P2 卫生守卫 / 动态必需集）。

```bash
cd /mnt/disk2/lzm/ouroboros && .venv/bin/python devtools/benchmarks/evolution/run_evolution_arm.py \
  --arm V3 \
  --corpus /home/lzm/bench_runs/evolution_corpus/gaia_corpus_smoke_2026-09-04.jsonl \
  --session-dir /home/lzm/bench_runs/arms/smoke_test_11 \
  --cadence every_n:2 \
  --budget 20 \
  --campaign-timeout 1800
```

说明：

- **不含部署**：`--deploy` 默认关闭，不加即不跑部署期（部署由 run_skill_deploy.py 独立控制）。
- `.env` 不需要手动 source（P1 修复后 runner 自加载）；手动 source 也无害。
- `--campaign-timeout 1800`：实测单周期 15-40 分钟，默认 600s 会让逐记录等待频繁超时
  （无害但日志吵）；超时只影响同步等待，战役在 server 侧继续。
- 中断后续跑：同命令加 `--resume`（只喂未处理记录）。
- 收停条件：语料喂完或 `--max-absorbed`（默认 10）触发；runner 自行收尾出 ledger。
- 验收口径：`absorbed_cycles_done ≥ 1`；对照 smoke_test_fix 的环节-证据映射表
  （EVOLUTION_SMOKE_ANALYSIS.md）逐环节核对。

---

## 第五轮复盘补遗：第十一轮（smoke_test_11，2026-09-13）

**现象**：11 条语料全部喂完，7 个周期（7 个不同 objective——晋升覆盖问题确认已修复）全部
no_op；15 次 commit_reviewed 全部被拒；收尾时 main() 崩溃（`I/O operation on closed file`）。

**根因：1M owner-ack 是会话本地状态，不随代码走。** 动态必需集（b347d06b）工作正常——冻结面
被正确降级，但另一形态的死墙接棒：**不可约简 scope 提示**（canonical docs + checklist +
staged diff）实测 ~216K token（ARCHITECTURE.md 单文件 482KB ≈ 117K；DEVELOPMENT 37K +
CHECKLISTS 22K + BIBLE 10K），而新会话 data 目录里 owner_acks=0 → 评审窗口未知 → 保守 200K
→ 输入预算压到 90909。smoke_test_fix 的 cycle 12 能通过，靠的是当时手动录进那个会话的 1M ack。
**修复**（73f192c8）：runner 在会话创建时从 `OUROBOROS_OWNER_WINDOW_TOKENS` 播种 ack（无断言
则保持 fail-closed），指纹验证与生效记录一致（59d5cf7fd124e022）。

**其他观察**：
- cycle 1 与 cycle 7 以 `degraded tool_failure` 收尾（126 与 58 rounds），cycle 8 派发后 30
  分钟零工具调用——桥接间歇性故障的同一签名；非机制问题。
- Bible P6 顾问发现出现 5 次：agent 新增 `ouroboros/` 模块时未同步登记
  `docs/ARCHITECTURE.md`（不阻塞提交，记录为能力层数据）。
- 收尾崩溃：ledger 段先 close 日志句柄后打日志（顺序 bug）；ledger JSON 本身已写出。已修。
- agent 暂存内容全程干净（仅功能代码 + 测试，无 uv.lock/生成物）——契约约束有效。

**教训入册**：owner-ack 这类"会话内状态"必须由 session 供给方（runner）从同一环境变量派生播种，
否则换会话即失效——与 P1 的 .env 教训同构：**依赖 operator 手动步骤的配置都会在下一个会话里变成
一颗隐雷。**
