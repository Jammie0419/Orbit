# 智能路由板块（Unified Smart Router + Harness Tree）实现全文档

> **板块范围**：不足 1（工具选择智能化）+ 不足 8（技能发现智能化）+ 不足 3（任务适应性），三者由**同一个任务分类器**驱动，是"一次分类 → 横向路由 + 纵向适配"的一体设计。
> **实施状态**：首版 2026-08-15（Smart Router + Smart Memory + Harness Tree）；L2 专业化 + 信号判定 + demote 修正 2026-09-02。
> **开关**：`OUROBOROS_SMART_ROUTING`（默认 false，opt-in；Harness Tree 无独立开关，随本开关启停）。
> **配套文档**：`PAPER_INTEGRATION_ANALYSIS.md`（融合方案总纲）；本文件是板块级实现细节全文档。

---

## 1. 板块定位

| 不足 | 解决机制 | 消费者 |
|------|---------|--------|
| 不足 1：工具选择缺乏智能化 | 工具路由：按任务类型收窄 round-one schema 信封 | `ToolRegistry._router_filter` |
| 不足 8：技能发现缺乏智能化 | 技能路由：按任务相关性评分 + 分支偏置，Top-K 推荐注入 prompt | `[SMART ROUTING]` 技能块 |
| 不足 3：任务适应性不足 | Harness Tree：任务类型分支调整（prompt/记忆/技能/工具四层） | `ctx.harness_branch` → `context.py` |

设计前提（重要）：
- **智能技能路由/工具路由是 SmartRouter 内置能力，不依赖 harness**——main 分支（harness 全空）下路由照常，只有偏置/注入消失。
- **harness 分支不重新分类、不持有工具集**（引用 `TOOL_SETS`，不会漂移）、**只追加不替换**（base SYSTEM.md 能力常驻）、**main 兜底**（缺失/损坏分支 → 空调整 == 纯智能路由）。
- **逃生通道永在**：`get_schema_by_name` 不受过滤、`enable_tools` 随时可开被隐藏工具、`list_non_core_tools` 广告被隐藏工具——路由只收窄初始信封，从不移除能力。

## 2. 架构总览：一次分类，两个消费者

```
task
 ├─ TaskClassifier.classify_with_signal(task) ──→ (task_type, has_signal)    ① 分类（仅一次，纯规则零成本）
 │     ├─ 消费者 A（横向）：SmartRouter.route() → 工具信封 + 技能评分 → 推荐
 │     └─ 消费者 B（纵向）：HarnessTree.select_branch() → 分支调整（prompt/记忆/技能偏置/工具avoid）
 └─ 路由历史：state/routing_history.jsonl（task_type/branch/tools/skills，P2 反馈回路的数据基础）
```

## 3. 完整执行流程

### 3.1 八步链路（`agent.py:1066-1094`）

1. **分类**：`classify_with_signal(task)` → `(task_type, has_signal)`（§5）。
2. **选分支**：`HarnessTree.select_branch(task_type if has_signal else DEFAULT_BRANCH)`——**harness 先于路由执行**，因为 `route()` 的签名要消费分支产物（`skill_preferences`、`branch` 名）。
3. **路由**：`SmartRouter.route(task, available=可用集, task_type, skill_preferences, branch)` 一次完成两件事：
   - `_route_tools`：`TOOL_SETS[task_type]` ∩ 实际可用集 → 信封（§6）；
   - `_route_skills`：全技能相关性评分 → 分支偏置 → Top-K（§7）；
   - 写 `routing_history.jsonl`。
4. **收窄**：`kept = set(routing.tool_names) - branch.avoided_tools()` → `tools.set_router_filter(kept)`（meta/控制面工具由 filter 内部并集兜底，永不误删）。
5. **注入**：`ctx.harness_branch = branch` → 交给 context 构建。
6. **上下文组装**（`context.py`）：`base_prompt` = SYSTEM.md + 分支 `system_prompt_extra` + `## Avoid (<branch> branch)` 反模式段；memory 段按分支 `memory_config` 过滤/排序/截断；registry digest 按显式提及过滤；`[SMART ROUTING]` 技能推荐块以 user 消息追加在 capability-delta 之前。
7. **LLM 主循环**：模型在信封内决策，被隐藏工具经 `enable_tools` 逃生。
8. **路由关闭时**：整个块跳过（不分类、不路由、不注入、不写历史），与旧版行为完全一致。

### 3.2 完整示例（"帮我安装 Google Chrome 并打开它"，无 workspace/type）

| 步骤 | 环节 | 产出 |
|------|------|------|
| 1 | 分类 | description 含"安装" → **(coding, has_signal=True)** |
| 2 | 选分支 | `select_branch("coding")` → coding 分支（6 个配置文件） |
| 3 | 路由 | 信封 = `TOOL_SETS[coding]`（约 40 工具：run_command/run_script/`skill_exec`/`list_skills`/view_image/`run_ci_tests`/`task_acceptance_review`…）∩ 108 可用集；技能：`unix_computer_use`（computer/desktop 标签命中 + boost 0.2 → 0.7+ ≥0.6 → 推荐），`telegram`（无命中 0.5 → 出局）；历史记录 type=coding/branch=coding |
| 4 | 收窄 | coding avoid 空 → 信封原样 → 模型只见约 40 个 schema |
| 5-6 | 注入 | `## Coding Task Focus`（定位→最小改动→构建门→diff 证据）+ `## Avoid (coding branch)`（禁整文件重写/禁 force 掩盖失败…）；memory 按 priority=[scratchpad, identity, environment profile, dialogue] 截 4 段 |
| 7 | 循环 | `list_skills` → `skill_exec(unix_computer_use)` 安装/操作 → `view_image` 截图确认 |

**对照 A——无信号任务（如 "hi there"，无 type/无关键词）**：`(simple, False)` → **main 分支**：harness 四层调整全空（prompt/记忆/技能偏置/avoid 全部不生效），但信封仍为保守 simple 集（~10 工具）、技能推荐走无偏置通用评分——"不确定任务给兜底，鲁棒任务给全量"。

**对照 B——显式轻量任务（type=chat）**：`(simple, True)` → **simple 分支**（最小应答 + 显式升级引导）。simple 分支与无信号的 main 由此区分：前者是明确形态主张，后者是中立兜底。

### 3.3 为什么 harness 必须先于路由

`route()` 的调用签名要求 `skill_preferences`（分支偏置影响技能评分）与 `branch`（写入路由历史），所以 `select_branch` 在 `route` 之前；而 harness 对工具的作用（avoid）是路由**之后**的减法——数据依赖决定了这个次序，也保证了"harness 的调整都是加法/减法，不改路由主体"。

## 4. 已实现组件与修改文件清单

### 4.1 新增文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `ouroboros/smart_router.py` | 581 | `TaskClassifier`（含 `classify_with_signal`）、`SmartRouter`（route/_route_tools/_route_skills/评分/历史）、`RoutingResult`（含 `skill_prompt_block`）、`TOOL_SETS`、`SKILL_TAG_MAPPING`、`ALWAYS_ON_TOOLS`、评分常量（阈值 0.6 / Top-10 / demote 0.5/0.2） |
| `ouroboros/harness_tree.py` | 314 | `HarnessTree`（select_branch/main 兜底）、`HarnessBranch`（tool_set/avoided_tools）、`SkillPreferences`（boost/tags/always/demote/demote_tags，含容错）、`MemoryConfig`（include/exclude/priority/max_sections）、`ToolPreferences`（avoid） |
| `harness_configs/` | 27 文件 | main（README.json）+ coding/research/knowledge/simple 各 6 个配置文件（见 §8.2） |
| `tests/test_smart_router.py` | 21 例 | 分类/信封/技能评分/偏置/逃生通道/过滤不泄漏/关键词/信号判定/信封完整性 |
| `tests/test_harness_tree.py` | 24 例 | 分支加载/main 兜底/工具引用/偏置/avoid/anti_patterns/demote/容错/registry 过滤/端到端/无信号→main |

### 4.2 修改文件

| 文件 | 改动 | 要点 |
|------|------|------|
| `ouroboros/agent.py` | 初始化 + `_prepare_task_context` | `__init__` 实例化 `SmartRouter`/`HarnessTree`；任务级：`classify_with_signal` → `select_branch`（无信号→main）→ `route` → `kept - avoided_tools()` → `set_router_filter` → `ctx.harness_branch`；技能块 append；异常 → 全量信封降级 |
| `ouroboros/context.py` | 注入点 + 两个过滤函数 | base_prompt 追加 extra + `## Avoid` 段；`_apply_harness_memory_config`（section 过滤/排序/截断）；`_apply_harness_registry_config`（registry digest，仅显式提及 "memory registry" 的分支有话语权） |
| `ouroboros/tools/registry.py` | 信封机制 | `set_router_filter`（None 恢复全量；meta 工具恒保留）、`router_hidden_tools`、`_available_tool_names_unfiltered`/`available_tools_unfiltered`（防跨任务过滤泄漏）、`schemas`/`_schemas_for_entry` 过滤、`ToolContext.harness_branch` 字段 |
| `ouroboros/tool_policy.py` | 逃生通道透明化 | `ToolSchemaProvider` Protocol 扩展；`list_non_core_tools` 广告被路由隐藏的工具 |
| `ouroboros/config.py` | 开关 | `OUROBOROS_SMART_ROUTING`（默认 false）+ `get_smart_routing_enabled()` |
| `scripts/live/routing/` | 3 个冒烟脚本 | 真实 LLM 手动验证（非 CI）；simple 期望修正（`main` → `simple` 分支，因 simple 分支已存在） |
| `ouroboros/smart_router.py` 常数 | — | `DEMOTE_SKILL_PENALTY` 0.5（2026-09-02 修正，§7.4） |

## 5. 任务分类（TaskClassifier）

### 5.1 信号优先级（`classify_with_signal`，纯规则零成本确定性）

1. `task.type` 命中 `_TYPE_HINTS`（research/web_search/investigate/browse → research；knowledge_management/knowledge/memory/note → knowledge；chat/simple/qna → simple；coding/coding_task/bug_fix/refactor → coding）；
2. `workspace_root` 非空 → coding（路径事实，不靠文本猜）；
3. `memory_mode` ∈ {knowledge, memory} → knowledge；
4. `description` + `text` 关键词扫描（中英文，直接聊天的话语在 text 里）；
5. **全部落空 → `(simple, False)`**——类型仍为 simple（保守信封），但 `has_signal=False` → harness 选 main 中性兜底（§5.3）。

### 5.2 关键词映射全表（2026-09-02 核对扩充）

| 任务形态 | 关键词（中文，节选） | 分支 | 理由 |
|---------|--------------------|------|------|
| 编程/代码 | 代码/实现/修复/重构/函数/模块/脚本/调试/报错/写一个 + bug/fix/code/… | coding | 执行面（编辑/vcs/run）在此 |
| 电脑/系统操作 | 安装/软件/电脑/桌面/装一个 | coding | 经 `skill_exec` + `unix_computer_use` 执行 |
| 工程生命周期 | 部署/配置/发布/接口/测试 | coding | 编码工作流高信号词 |
| 调研/检索 | 调研/搜索/查找/查询/总结/分析/研究/论文/资料/最新 + research/search/… | research | 采集面（web/browse）在此 |
| 内容写作 | 文档/文章/报告/周报/写作/撰写/整理成 | research | 写作 = 综合素材 + 沉淀产出 |
| 检索综合 | 对比/收集/调查/翻译 | research | 多源综合信号词 |
| 记忆/知识管理 | 记住/存储/保存/知识/笔记/记忆/长期记忆/归档 + memory/knowledge/… | knowledge | 沉淀面（knowledge/memory 工具）在此 |
| 记忆回顾 | 回顾/收藏/记一下/记一个 | knowledge | 与"整理成文档"写作形态分流 |
| 轻量对话（显式） | type=chat/simple/qna | simple | 只有显式轻量信号才启用 simple 分支 |
| **无信号** | — | **main** | 不给任何方向主张 |

### 5.3 无信号 → main（2026-09-02 定案）

"不知道是什么任务"不能继承任何分支的方向假设（此前落 simple 分支 = 给未知任务套"轻量应答"主张，对实际重任务有害）。现语义：无信号任务信封仍按保守 simple 集（`enable_tools` 逃生保留），但 harness 四层调整全部不生效；`simple` 分支只服务显式轻量任务。

## 6. 工具路由（TOOL_SETS + 信封机制）

### 6.1 四类信封（2026-09-02 对照 ToolRegistry 108 工具核对补齐）

- **coding**（~40）：read/write/edit/apply_patch/edit_batch/search_code/query_code/run_command/run_script/start_service/service_*/vcs_*/plan_task/verify_and_record/codebase_health/review_status/schedule_subagent/compare_subagent_patches/integrate_*_patch/**skill_exec/list_skills**（电脑操作面）/**run_ci_tests/task_acceptance_review/request_deep_self_review**（工程验证环）/**view_image/analyze_screenshot**（视觉调试）/recent_tasks/chat_history/journal_*
- **research**（~22）：web_search/browse_page/browser_action/analyze_screenshot/view_image/vlm_query/ocr_pdf/youtube_transcript/**extract_video_frames**（视频配套）/read_file/list_files/search_code/query_code/knowledge_read/knowledge_list/**list_skills/skill_exec**（写作技能）/**journal_read/journal_write**（研究日志）/chat_history/recent_tasks/workpad_*
- **knowledge**（~20）：knowledge_read/write/list/update_scratchpad/update_identity/memory_map/memory_update_registry/**promote_to_stable**（记忆生命周期收尾）/workpad_*/journal_*/list_skills/skill_exec/skill_review/skill_preflight/toggle_skill/submit_skill_to_hub/chat_history/recent_tasks/web_search
- **simple**（~10）：chat_history/recent_tasks/update_scratchpad/update_identity/list_projects/ensure_project_scope/route_to_project/promote_chat_to_task/knowledge_read/knowledge_list

### 6.2 信封机制要点

- `ALWAYS_ON_TOOLS`（控制面 15 个：list_available_tools/enable_tools/switch_model/compact_context/request_restart/send_*/steer_task/cancel_task/wait_*/tree_*…）**永不隐藏**；`set_router_filter` 内部并回 meta 工具，双保险。
- `available_tools_unfiltered()`：路由判定基于未过滤可用集——过滤视图喂回下一次路由会跨任务收缩信封（v6.100+ 审计修复）。
- `avoid` 收窄（ToolPreferences）：`avoid ∩ TOOL_SETS[task_type]`、控制面免疫、未知名称静默丢弃；只剔除不新增。
- 逃生通道：`get_schema_by_name` 不过滤；`enable_tools` 可开任意工具；`list_non_core_tools` 广告被隐藏工具（模型知道"还有什么可开"）。

## 7. 技能路由与评分（数值与比例）

### 7.1 相关性评分（`_calculate_skill_score`，智能路由侧，封顶 1.0）

| 因子 | 加分 | 相对基础分增量 |
|------|------|----------------|
| 基础分 | 0.5 | — |
| manifest tags 命中任务标签 | +0.3 | 60% |
| 技能名命中（word-boundary 前缀匹配） | +0.2 | 40% |
| description/when_to_use/body 文本命中 | +0.1/项（上限 +0.2） | 20%~40% |

### 7.2 分支偏置（`_apply_skill_preferences`，harness 侧）

| 因子 | 数值 | 量级对照 |
|------|------|---------|
| boost 具名（当前配置） | coding +0.2 / research +0.1 | ≈ 一个名称命中 / 半个 |
| tags 标签偏置 | +0.15 | ≈ 1.5 个文本命中 |
| always 钉住 | 无视阈值 | 硬通道 |
| demote 具名 | **-0.5** | 大于任何正向增量组合（见 7.4） |
| demote_tags | -0.2 | ≈ 一个标签命中 |

**比例结论**：相关性主导——tag 命中（+0.3）> boost（+0.2）> 名称命中（+0.2）> 标签偏置（+0.15）。正常推荐路径偏置增量 ≤ 相关性增量的 2/3；demote 是刻意压倒性的（负向必须压过正向）。

### 7.3 阈值 0.6 与 Top-10

- **阈值 0.6 语义**（代码注释定案）："strictly above base 0.5——技能必须至少命中一个字段"。tag 命中 0.8 ✓、名称 0.7 ✓、文本 0.6 ✓（压线）、无命中 0.5 ✗；boost 0.2 → 0.7 ✓（分支显式主张合理）。阈值 = "至少一字段命中"的数学表达，自洽。
- **推荐数 = min(过阈值技能数, 10)**——Top-10 是天花板不是目标。当前技能库仅 2 个（`unix_computer_use`、`telegram`），实际推荐 0-1 个：coding/research 任务推 `unix_computer_use`（标签/boost 命中），其余任务 0 个。Top-10 空转无害；技能库 >30 或推荐精度下降时再考虑调整，且优先旋钮是分支级阈值/偏置（L3 扩展点），不是 top_k。
- 技能块每行 ≈ 50-80 tokens，10 行 ≈ 500-800 tokens 上限。

### 7.4 demote -0.5 修正（2026-09-02）

原 -0.4 对**满配技能**（1.0，全字段命中）不成立：1.0-0.4 = **0.6 恰好压线通过**（`score >= threshold`）。修正为 **-0.5**：大于任何正向增量组合的最大值（tags +0.3 + 名称 +0.2 + 文本 +0.2 = +0.5），满配 1.0 → 0.5 < 0.6 必出局，唯一幸存通道是 `always` 钉住。测试 `test_demote_removes_even_full_relevance_skill` 锁死该场景。

### 7.5 技能标签映射（SKILL_TAG_MAPPING）

coding 组 2026-09-02 补入 `computer/desktop/automate/install`——`unix_computer_use` 凭名称/描述命中即可进入推荐，不再依赖 boost。其余组：research（search/research/web/browse/analyz/investigat/explore/summariz/extract/report/data）、knowledge（memory/knowledge/learn/note/index/recall/store/journal/workpad/catalog）、simple（chat/communicat/assistant/helper/qna/brief/message/respond）。

## 8. Harness Tree（任务适配层）

### 8.1 设计原则

不重新分类（复用同一次分类）、不持有工具集（`tool_set()` 引用 `TOOL_SETS`）、只追加不替换（SYSTEM.md 常驻 + 分支 extra/anti 追加其后）、main 兜底（缺失/损坏 → 空调整）、无独立开关（随 `OUROBOROS_SMART_ROUTING`）。

### 8.2 配置 schema（每分支 6 个文件）

1. **`system_prompt_extra.md`**——正向执行策略，追加在 SYSTEM.md 之后；
2. **`anti_patterns.md`**——负向指令（L2 维度），渲染为独立 `## Avoid (<branch> branch)` 段紧跟正向 extra；显式"禁止"比正向礼仪更能改变行为；
3. **`memory_config.json`**——include/exclude/priority/max_sections 四操作，匹配键：scratchpad/identity/environment profile/dialogue/memory registry（后者的过滤仅对显式提及的分支生效）；空配置 == 与基础构建器一致；
4. **`skill_preferences.json`**——boost/tags/always/demote/demote_tags（§7.2）；demote 必杀、always 硬通道；
5. **`tool_preferences.json`**——`avoid` 信封收窄（§6.2）；prefer（信封内排序）留 L3；
6. **`README.json`**——分支说明（main 仅此文件，其余分支为 5 配置 + 可缺省）。

加载容错：bad JSON → 空配置 + warning；坏 boost 值逐条跳过；`from_dict` 整体异常 → 空偏好——任何配置错误都不毒化整棵树，最坏退回该分支为空调整。

### 8.3 四分支配置摘要（2026-09-02 重写为 L2 方向级执行策略）

| 分支 | 锁定成败行为 | 反模式主题 | 技能偏置 | 工具收窄 | 记忆注入 |
|------|-------------|-----------|----------|----------|----------|
| coding | 定位→最小改动→构建门→diff 证据→git 历史 | 整文件重写/force 掩盖失败/不验证就提交/平台行为靠猜/杂乱提交 | boost unix_computer_use 0.2；tags [code test build git python]；demote_tags [research web browse] | 无（信封已窄） | scratchpad→identity→world→dialogue，截 4 |
| research | 搜索→读原文→双源校验→来源跟踪→结构化综合→沉淀 | 单源定论/抄网页/片段断言数字/丢引用/忽略反证 | boost unix_computer_use 0.1；tags [research web search data] | 无 | scratchpad→dialogue→world；排除 identity，截 3 |
| knowledge | 先查后写→结构化→索引纪律→技能杠杆→合并 | 重复条目/裸 dump/只写不索引/孤儿笔记/重读已注入内容 | tags [memory knowledge index note]；demote_tags [web browse research] | 无（内部优先用引导表达，不做能力移除——知识任务常以外部材料为起点，硬剔除会砍掉"读网页→归档"第一跳；硬收窄留给 L3） | registry→identity→scratchpad；排除 dialogue，截 3 |
| simple | 上下文应答→最小工具→显式升级 | 仪式化工具链/半答真任务/过度解释/丢连续性 | 无（保持 is_empty，推荐块干净） | 无 | 仅 dialogue；排除 registry+world，截 1 |
| main | —（对照组） | — | 空 | 空 | 全量默认 |

### 8.4 五级专业度框架

| 级别 | 形态 | 特征 | 判别 |
|------|------|------|------|
| L0 | 空配置 | main：零调整，纯路由 | 配置全空 |
| L1 | 通用礼仪 | 方向性提醒，任何通用 agent 都写得出来 | 换到任意方向仍成立 → 无信息增益 |
| L2 | 方向级执行策略 | 成败路径 + 验收标准 + 反模式，正向策略落真实工具名 | 分支 vs main 行为可区分且更优 |
| L3 | 数据驱动校准 | 配置从轨迹统计生成（高频工具/错误/产出形态） | 配置 diff 对应语料统计证据 |
| L4 | 闭环自适应 | P2 反馈：结果回填 → 参数自动调优 → 防过拟合 | 成功率/成本随轮次收敛 |

当前四分支达到 L2；L3/L4 是路线（§11）。

### 8.5 已修复的 gap（2026-09-02）

1. **memory registry 配置空转**——`## Memory Registry`/registry digest 不走 stable/volatile 分区，knowledge priority 与 simple exclude 里的 "memory registry" 此前无效；现 `_apply_harness_registry_config` 对**显式提及**的分支生效，未提及分支行为不变；
2. **`SkillPreferences.from_dict` 无容错**——坏 boost 值/损坏 JSON 曾让整棵树加载失败，现逐条跳过 + 整体兜底；
3. **live 脚本陈旧期望**——simple 期望 `main`→`simple`（simple 分支已存在）；
4. **demote 压线漏洞**——0.4→0.5（§7.4）。

## 9. 开关与启用

- 读取链：`settings.json`（磁盘显式值优先，UI 切换免重启）→ 环境变量 → 默认 false。
- 启用：settings.json 加 `"OUROBOROS_SMART_ROUTING": "true"`，或环境变量 `OUROBOROS_SMART_ROUTING=true`。
- 关闭行为：agent.py 整个路由块跳过——不分类、不路由、不写历史、`set_router_filter(None)` 全量信封，与旧版完全一致。
- 与 `OUROBOROS_SMART_MEMORY`（不足 2）相互独立，可分别开、一起开。
- 基准跑法：`devtools/benchmarks/evolution/run_evolution_arm.py` 的 ARM_SWITCHES 已按臂注入（V1/V3 开任务层）。

## 10. 测试与验证

- `tests/test_smart_router.py`（21 例）：type hints/workspace/关键词分类、`classify_with_signal` 信号语义、电脑操作与写作新词、信封任务特定性与 ALWAYS_ON 保留、可用集交集、路由历史、技能评分阈值、推荐块格式、registry 过滤/逃生通道/过滤不泄漏/契约政策/隐藏工具广告、信封完整面。
- `tests/test_harness_tree.py`（24 例）：分支加载/main 兜底/缺失目录/工具集引用/分支清单/坏 JSON 兜底、boost/demote 组合、always 钉住、plain dict 兼容、自建技能平局优先、路由历史带分支、端到端分支注入、未分类→main、避免工具收窄（含控制面免疫）、无信号→main（有 simple 分支时）、anti_patterns 加载与注入、demote 满配必杀、boost 容错、损坏配置不崩、is_empty 新字段、registry 显式提及过滤。
- 回归范围：`test_smart_router.py + test_harness_tree.py + test_context.py`（101 例全绿）。
- 真实 LLM 冒烟：`scripts/live/routing/smart_router_live_{smoke,multi,rounds}.py`（手动，需 DEEPSEEK_API_KEY）。

## 11. 局限与路线（L3/L4）

1. **数据驱动校准（L3）**：`state/routing_history.jsonl`（已有 branch/tools/skills）+ `tools.jsonl`（实际调用）+ GAIA 轨迹（`extract_evolution_corpus.py` 已具备抽取）→ 每任务类型高频工具/错误/产出形态统计 → 校准报告 → 人工确认后回填配置。候选落地：`tool_preferences.prefer`（schema 排序）、`TOOL_SETS` 按实际使用率瘦身、技能权重按真实 `skill_exec` 调用率校准。
2. **闭环自适应（L4 = P2 反馈回路）**：路由历史回填任务终态（`task_done.reason_code`）→ 三闭环：工具集自动瘦身、技能权重自校准、分支参数自调优（强化有效分支/回退无收益分支）。防过拟合约束：`enable_tools` 主动开启过的工具保底、变更可回滚、每类任务 ≥20 样本才动参数。
3. **分支级旋钮**：`top_k`/阈值按分支可配；`prefer` 工具排序；新任务形态若成规模（如桌面办公）可新增 `TASK_TYPE` + 分支目录（main 兜底保证不崩）。
4. **simple 分支语义**：只服务显式轻量任务；无信号归 main。

## 12. 实验度量建议（对接 EVOLUTION_EXPERIMENT_SPEC）

- V1 臂（任务层开）差异化卖点 = 分支**可区分性**：A/B 设计（同一 GAIA 分层子集，main 对照组 vs 专攻分支实验组）比较成功率/路径质量/Token 成本；
- **行为级证据**（比 end-to-end 分数更早可观测）：从轨迹提取"分支专属行为是否发生"——coding 分支任务是否在提交前出现 `vcs_diff`、knowledge 分支是否在写入前出现 `knowledge_read`、research 是否出现双源工具序列——这是 L2 达标最硬的证据；
- `routing_history.jsonl` 的 `branch` 字段是天然的臂内观测点（哪些任务走了哪个分支/是否落 main）。