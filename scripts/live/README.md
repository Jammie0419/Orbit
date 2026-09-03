# scripts/live — 真实 LLM 手动冒烟测试

⚠️ **MANUAL OPERATOR SCRIPTS** — 不是 pytest 测试、不属于 CI。这些脚本调用真实模型 API,
会花真实预算,且需要真实凭据(`DEEPSEEK_API_KEY`,位于 `.env.gaia` 或环境变量)。
自动化确定性回归在各板块对应的 `tests/test_*.py`。

按优化板块(对应 `PAPER_INTEGRATION_ANALYSIS.md` 的"不足")分目录存储:

| 目录 | 板块 | 脚本 | 验证内容 |
|---|---|---|---|
| `routing/` | 不足 1 + 不足 8(Unified Smart Router)+ 不足 3(Harness Tree) | `smart_router_live_smoke.py` / `_multi.py` / `_rounds.py` | 分类→分支→工具信封收窄→技能推荐→anti_patterns 注入→真实工具调用→连续会话无 filter 泄漏→无信号任务走 main 中性兜底(2026-09-02)。harness 分支随路由脚本一起覆盖(分支=路由产出,不单独建脚本) |
| `memory/` | 不足 2(Smart Memory) | `smart_memory_live.py` | 真实 LLM 重要性仲裁、标签提取、按重要性淘汰、标签/重要性检索 |
| `evolution/` | 不足 4 + 5 + 7(进化层: 轨迹经验学习 + Multi-Agent 规划器) | `evolution_layer_live.py` | 真实 LLM 双轨信用分配(任务轨迹 A + 进化循环轨迹 B)、策略建议、结构化 evolution plan 产物(不做完整 campaign 闭环——那是 run_evolution_arm.py 的领域) |

## 运行前提

1. 激活 `.env`（或 export 环境变量）提供真实模型凭据与模型配置:
   - `OPENAI_COMPATIBLE_API_KEY` / `OPENAI_COMPATIBLE_BASE_URL`(必需)
   - `OUROBOROS_MODEL`(缺省为空时脚本会失败退出——先配置再跑)
   - 也可写入 `~/Ouroboros/data/settings.json`(脚本从 settings.json 读值,**非空时**覆盖环境变量;settings.json 不存在时脚本不会清掉 .env 提供的值)
2. 设置对应开关(opt-in) — `.env` / 环境变量 / settings.json 均可:
   - 路由:`OUROBOROS_SMART_ROUTING=true`
   - 智能记忆:`OUROBOROS_SMART_MEMORY=true`
   - 脚本内部会强制置 true(直接设置环境变量),即使漏配也能跑
3. 从仓库根运行:
   ```powershell
   python scripts/live/routing/smart_router_live_smoke.py
   python scripts/live/routing/smart_router_live_multi.py
   python scripts/live/routing/smart_router_live_rounds.py
   python scripts/live/memory/smart_memory_live.py
   ```

## 结构约定

- 脚本自包含:内部用 `parents[3]` 定位仓库根(脚本位于 `scripts/live/<板块>/` 下,比 `scripts/` 深两层)
- 每个脚本带醒目的 MANUAL OPERATOR 头注,说明成本、凭据、所属自动化回归位置
- 新板块的脚本:先在对应 `tests/test_*.py` 有确定性回归,再补充真实 LLM 冒烟脚本
