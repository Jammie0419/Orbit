"""Terminal-Bench behavior-discipline rules (the OUROBOROS_CAP_RULES block).

RECOVERED 2026-09-16: the original module was never committed (the exp/ tree
was listed in .gitignore by commit 203284e6) and was lost from disk. The rule
text below was extracted verbatim from the rendered instruction.txt files of
the 2026-08-25 .. 2026-09-02 campaign (125 trials carried the block).

Each rule is a task-agnostic behavior instruction appended to the task text.
They are plain prompt scaffolding, not hidden state: they land verbatim in
every trial's agent/instruction.txt, so a reviewer can diff them.

NOTE ON RENDERING: the current harbor_installed_agent._append_capability_guidance()
deliberately does NOT render this block into the instruction -- a >100 KB system
prompt made mimo-v2.5 emit one maxed-out 65536-token reply and blow the deadline.
render_rules() exists so a run can opt back in (and for ablation arms that need it).
"""

from __future__ import annotations

import os

CAP_RULES: dict[str, str] = {
    'write_verify': r"""每次 write_file / edit_text 之后，必须立刻运行一次验证（编译/执行/最小测试）并把输出贴回对话。禁止连续写多个文件而不验证。""",
    'recon_cap': r"""本任务是限时任务。采用增量开发模式：
1. 前 25% 预算内必须写出第一个可运行骨架（<500 行），立即验证；
2. 然后增量扩展：每次只加一个功能模块（<300 行），验证通过再继续；
3. 禁止一次性写超过 500 行的文件——如果超过，拆成多次 write_file + 验证。
侦察类动作（读文件/查格式）最多 5 轮就必须转入写作。先写骨架、跑、再按报错修正。""",
    'delivery_check': r"""交付物优先级检查（限时任务必须遵守）：
1. 在 50% 预算时，必须已生成任务要求的所有核心文件（如样本文件、输出文件）；
2. 如果 50% 预算时还缺少必要文件，立即停止调试，先生成最小可用版本；
3. 75% 预算时，所有交付物必须已完成并验证；
4. 最后 25% 预算只用于修复 bug 和优化，不得开始新功能。
结束前 list_files /app 核对所有产物都在工作区根、文件名完全一致。""",
    'budget_backcalc': r"""启动训练/采样/长计算前先估算完成时间；若超过剩余预算的三分之一，主动降参（epochs/iters/chains/维度/子采样）并说明取舍；不要照搬参考脚本的采样量。""",
    'forensics': r"""遇到待恢复或待分析的二进制/数据库文件：先 cp 到 /tmp 做只读备份，再用字节级工具（hexdump/xxd/python struct）分析；绝不在分析前用会改写文件的库打开它（例：sqlite3 会重置无法解析的 WAL 文件）。""",
    'tool_format': r"""工具格式：run_command 的 cmd 必须是真正的 JSON 数组（如 ["python3","-c","..."]），不要把数组写成字符串；多行 Python 逻辑用 run_script；管道/重定向/复合命令用 sh -c；前台常驻进程（nginx、服务器）用 start_service 而不是 run_command。""",
    'debug_limit': r"""调试次数限制（防止陷入无限调试循环）：
1. 对同一个 bug 最多调试 3 次；如果 3 次后仍未解决，换一种实现方案；
2. 如果总调试时间超过预算的 30%，立即停止调试，接受当前实现的不完美；
3. 优先保证所有必需文件都已生成，然后再考虑修复 bug。
记住：一个有 bug 但完整的实现 > 一个完美但不完整的实现。""",
    'precise_substitution': r"""精确替换纪律（适用于同义词替换、模式匹配替换等任务）：
1. 只允许修改任务明确要求替换的目标词/模式，严禁修改周围的任何词（包括冠词 a/an/the、介词、连词、标点等），即使从语法角度看修改是合理的；
2. 每次 edit_text 时，old_str 和 new_str 的长度（词数）必须相同——只替换目标词本身，不能同时替换多个词；
3. 如果替换导致语法不一致（如 an extraordinary → a remarkable），保留原文的冠词/形态，不要'修复'它；
4. 编辑后立即 diff 验证：确认只改了目标词，没有意外修改其他内容。""",
    'exhaustive_search': r"""穷举纪律（适用于需要找到所有答案/所有走法/所有解的任务）：
1. 明确题目要求'所有'、'全部'、'如果有多个'时，必须系统性搜索完整空间，不能找到一个就停；
2. 找到一个解后，立即追问：是否还有其他？穷举所有候选，逐一验证；
3. 对于棋类/博弈类任务：检查所有合法走法，对每个候选走法推演后续变化，列出所有必胜/最优走法；
4. 输出前自检：题目要求几个？我找到几个？是否遗漏？
5. 禁止'找到一个就交卷'——这通常是错误答案。""",
    'signal_repro': r"""涉及信号/键盘中断/取消清理（SIGINT、Ctrl-C、cleanup on cancel）的任务：
1. 验收几乎总是外部信号场景：子进程运行你的实现，按验收参数的时序（如启动约 500ms 后）向进程发 SIGINT；
2. 必须自己写这样的子进程测试脚本复现并断言输出中的清理计数，只在进程内主动 cancel()/对象取消做的测试与外部信号不同构，禁止作为唯一验证；
3. 若验收在'有排队任务'（任务数 > 并发上限）时也要求清理，测试必须覆盖该场景；
4. 实现侧：取消传播路径上避免对子任务二次 cancel()——二次取消会打断正在执行中的清理（如在 await 中间），导致清理代码永远不执行；用 TaskGroup 或只重新 gather 等待子任务完成，不要重复 cancel。""",
    'axis_anchor': r"""做轴/单位转换（波长↔波数、nm↔Å、缩放等）前，先用已知锚点验证假设：
1. 找 1-2 个你确信应落在某处的特征（如已知物质的已知峰位），用你的转换公式反推其原始坐标；
2. 检查原始数据在这些坐标处是否真有对应特征；对不上就换转换假设，不要在一个错误假设上反复调参；
3. 优先尝试最简单的解释（如波长轴直接取倒数 1e7/x），只有锚点吻合才引入更复杂的物理公式；
4. 锚点验证通过前不要开始拟合/建模。""",
}

# Historical render order, and the default when no explicit selection is given.
DEFAULT_RULE_ORDER: tuple[str, ...] = ('write_verify', 'recon_cap', 'delivery_check', 'budget_backcalc', 'forensics', 'tool_format', 'debug_limit', 'precise_substitution', 'exhaustive_search', 'signal_repro', 'axis_anchor')


def selected_rule_ids() -> list[str]:
    """Rule ids from OUROBOROS_CAP_RULES (empty/unset -> no rules)."""
    raw = os.environ.get("OUROBOROS_CAP_RULES", "").strip()
    if not raw:
        return []
    wanted = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in wanted if name not in CAP_RULES]
    if unknown:
        raise KeyError(f"unknown OUROBOROS_CAP_RULES ids: {unknown}")
    return wanted


def render_rules(rule_ids: list[str] | None = None) -> str:
    """Render the "benchmark behavior discipline" block, or "" when nothing is on."""
    ids = selected_rule_ids() if rule_ids is None else list(rule_ids)
    if not ids:
        return ""
    blocks = [f"<rule:{name}>\n{CAP_RULES[name]}\n</rule:{name}>" for name in ids]
    header = "--- benchmark behavior discipline (from OUROBOROS_CAP_RULES) ---"
    return header + "\n" + "\n\n".join(blocks)
