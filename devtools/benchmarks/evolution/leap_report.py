"""LEAP-shaped rendering for the evolution arm's run log.

The run log is the primary artifact of an evolution session, so it is grouped by
the LEAP operators of Algorithm 1 (``docs/orbit/PAPER_DRAFT.md`` §3) rather than by
the data source each line happens to come from. This module is FORMATTING ONLY:
no IO, no new metrics, no behaviour. Every datum the previous per-source labels
carried is still rendered here.

Operator numbering follows Algorithm 1 exactly:

    2  Execute              ``②执行``
    3  Attribute            ``③归因``
    4  MemWrite(E)          ``④记忆``
    5  PromoteDue/Worthwhile``⑤触发``
    6-7 Plan / Directed Variation ``⑥规划`` ``⑦变异``   (CODE: patch Δ in the clone)
    8  Selection            ``⑧选择``
    9-10 Absorb / Record    ``⑨遗传`` 代码级
    11 SkillEvolve          ``⑨遗传`` 行为级 (skill generation/mutation/review)
    12 MemWrite             ``⑪沉淀``

Two things the numbering makes explicit, because both were ambiguous in the flat
log:

* ``定向变异`` is the CODE-side operator (Algorithm 1 step 7: ``Δ ← Implement(plan;
  隔离克隆)``). The skill pipeline's own "反射式定向变异" (§3.5) belongs to
  **遗传·行为级** — Algorithm 1 step 11 is annotated ``▷ 遗传：行为级生成/变异/审查``,
  and the §4.2 ablation table files the whole skill chain under "−遗传". Skill events
  therefore never render under ⑦.
* Operator 1 (Expression) is NOT rendered. The isolated runner does not observe the
  agent's routing, and a placeholder line would claim a measurement that never
  happened (P1: a gap is represented, never filled in).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence, Tuple

# Algorithm 1 step -> (Chinese operator, English operator). Steps 6 and 7 share the
# Plan/Implement pair; 9-10 and 11 are both heredity (code-level / behaviour-level).
STAGES: dict[int, Tuple[str, str]] = {
    2: ("执行", "Execute"),
    3: ("归因", "Attribute"),
    4: ("记忆", "MemWrite"),
    5: ("触发", "Worthwhile"),
    6: ("规划", "Plan"),
    7: ("变异", "Variation"),
    8: ("选择", "Selection"),
    9: ("遗传", "Heredity"),
    11: ("沉淀", "Record"),
}

# Circled glyphs for the steps that own a rendered line. Kept next to STAGES so a
# step and its glyph cannot drift apart.
_STEP_GLYPH: dict[int, str] = {
    1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤",
    6: "⑥", 7: "⑦", 8: "⑧", 9: "⑨", 10: "⑩", 11: "⑪", 12: "⑫",
}

# The Algorithm-1 step each rendered line carries, as a glyph that runs on the line
# (τ task trace, E evidence, M memory, W worthiness, Δ patch, H heredity).
_GLYPH_BY_STEP = {2: "τ", 3: "E", 4: "M", 5: "W", 6: "P", 7: "Δ", 8: "✓", 9: "H", 11: "M"}


def step_glyph(step: int) -> str:
    """``②执行  τ  `` — the operator chip that prefixes a rendered line."""
    name = STAGES.get(step, ("?", "?"))[0]
    glyph = _GLYPH_BY_STEP.get(step, "")
    circle = _STEP_GLYPH.get(step, "?")
    head = f"{circle}{name}"
    return f" {head}  {glyph}  " if glyph else f" {head}  "


def stage_label(step: int) -> str:
    """``②执行`` — operator chip without the data glyph (for headers/tests)."""
    name = STAGES.get(step, ("?", "?"))[0]
    return f"{_STEP_GLYPH.get(step, '?')}{name}"


def block_header(title: str, width: int = 54) -> str:
    """``━━ title ━━━…`` used for record / campaign / session blocks."""
    pad = max(3, width - len(title))
    return f"━━ {title} " + "━" * pad


def _head(text: Any, limit: int) -> str:
    """Single bounded line: newlines collapsed, ellipsis when truncated."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: max(0, limit - 1)] + "…"


def _cont(step: int) -> str:
    """Continuation indent aligning under a chip (chip width + 1)."""
    return " " * (len(step_glyph(step)) + 1)


def _seq(value: Any) -> Sequence:
    """Coerce an optional/iterable field to a sequence.

    The block is emitted inside the feeding loop, so a malformed field must not be
    able to swallow it: ``None`` (and a non-iterable) contributes nothing instead of
    raising through the renderer.
    """
    if value is None:
        return ()
    try:
        return tuple(value)
    except TypeError:
        return ()


@dataclass
class RecordView:
    """Everything one corpus record's block renders — the harness fills it in.

    Only the fields a session actually produced are rendered; an empty/default field
    omits its line instead of printing a placeholder.
    """

    index: int
    total: int
    record_id: str
    level: str = "?"
    # ②执行
    goal: str = ""
    seeded: int = 0
    seed_error: str = ""
    rounds: Any = 0
    error_count: int = 0
    markers: Sequence[str] = field(default_factory=tuple)
    reflection_chars: int = 0
    summary: str = ""
    # ③归因
    credits_new: Sequence[dict] = field(default_factory=tuple)
    track_a: Sequence[str] = field(default_factory=tuple)
    track_b: Sequence[str] = field(default_factory=tuple)
    # ④记忆
    memory_actions: Sequence[Tuple[str, str]] = field(default_factory=tuple)
    memory_applied: Optional[int] = None
    memory_total: int = 0
    memory_parse_failed: bool = False
    experience_delta: int = 0
    experience_total: int = 0
    backlog_candidates: int = 0
    backlog_items: Sequence[dict] = field(default_factory=tuple)
    skill_eligibility: str = ""
    # ⑤触发
    decision_kind: str = ""          # promote | skip | refuse | ""
    cadence_text: str = ""
    decision_reason: str = ""
    promote_objective: str = ""
    promote_backlog_id: str = ""
    # ⑨遗传·行为级
    skill_events: Sequence[Tuple[str, str]] = field(default_factory=tuple)
    # ⑪沉淀
    checkpoint_lines: Sequence[str] = field(default_factory=tuple)


def _render_execute(view: RecordView, lines: List[str]) -> None:
    body: List[str] = []
    if view.goal:
        body.append(f"目标: {_head(view.goal, 80)}")
    markers = ",".join(str(m) for m in _seq(view.markers)) or "—"
    body.append(
        f"轮次 {view.rounds} | 错误 {view.error_count} | 标记 {markers}"
        f" | 反思 {view.reflection_chars} 字"
    )
    if view.summary:
        body.append(f"摘要: {_head(view.summary, 160)}")
    _emit(lines, 2, body)


def _emit(lines: List[str], step: int, body: List[str]) -> None:
    """Render a stage: the operator chip on its first line, indented continuation after.

    The chip must land on whichever line the stage actually produced — a record whose
    only attribution is a Track-A row still has to read as ③归因.
    """
    if not body:
        return
    lines.append(step_glyph(step) + body[0])
    cont = _cont(step)
    lines.extend(cont + line for line in body[1:])


def _render_attribute(view: RecordView, lines: List[str]) -> None:
    body: List[str] = []
    credits = _seq(view.credits_new)
    if credits:
        best = max(credits, key=lambda c: float(c.get("credit") or 0))
        worst = min(credits, key=lambda c: float(c.get("credit") or 0))
        body.append(
            f"信用 +{len(credits)} 步计分: 最高 {best.get('tool')} "
            f"{best.get('credit')} | 最低 {worst.get('tool')} {worst.get('credit')}"
        )
    body.extend(f"Track-A {summary}" for summary in _seq(view.track_a))
    body.extend(f"Track-B {summary}" for summary in _seq(view.track_b))
    _emit(lines, 3, body)


def _render_memory(view: RecordView, lines: List[str]) -> None:
    body: List[str] = []
    actions = _seq(view.memory_actions)
    if actions:
        # 每条一行：旧日志就是一行一条，挤成一条会在每次 2-3 条时超长截断。
        body.extend(f"{label}: {_head(content, 60)}" for label, content in actions)
        if view.memory_applied is not None:
            body.append(f"落库 {view.memory_applied}/{view.memory_total}")
    elif not view.memory_parse_failed:
        # The COUNT is a memory-layer statistic: "the model wrote nothing" is a
        # result, and dropping the line would lose it (only a broken payload is
        # reported as loss, below).
        body.append(f"落库 0/0（模型未产出 memory actions）")
    if view.memory_parse_failed:
        # Present-but-unparseable is data loss, not "the model wrote nothing".
        body.append("⚠ mem_parse_failed（MEMORY_ACTIONS_JSON 存在但不可解析，本记录未落库）")
    backlog_items = _seq(view.backlog_items)
    if view.backlog_candidates or backlog_items:
        counts: dict = {}
        for item in backlog_items:
            key = str(item.get("priority") or "?")
            counts[key] = counts.get(key, 0) + 1
        tally = " | ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        body.append(
            f"backlog 候选 {view.backlog_candidates} | 新增 {len(backlog_items)}"
            + (f"（{tally}）" if tally else "")
        )
        body.extend(
            f"  +{item.get('id')} \"{_head(item.get('summary'), 60)}\" "
            f"({item.get('priority')} | count={item.get('count')})"
            for item in backlog_items
        )
    if view.skill_eligibility:
        mark = "✅" if view.skill_eligibility == "ok" else "—"
        body.append(f"技能资格 {mark} ({view.skill_eligibility})")
    _emit(lines, 4, body)


def _render_experience(view: RecordView, lines: List[str]) -> None:
    """④记忆 的尾段：经验入账。数据由 promote 那一趟产出（store_experience 在
    maybe_promote 内），所以它只能跟后决策的那组一起发，不能留在前半边。"""
    if not (view.experience_delta or view.experience_total):
        return
    _emit(lines, 4, [f"+{view.experience_delta} 经验（账本累计 {view.experience_total}）"])


def _render_worthwhile(view: RecordView, lines: List[str]) -> None:
    if not view.decision_kind:
        return
    body: List[str] = []
    if view.decision_kind == "promote":
        body.append(
            f"cadence {view.cadence_text} | LLM: promote ✅ "
            f"理由: {_head(view.decision_reason, 90) or '—'}"
        )
    elif view.decision_kind == "skip":
        body.append(f"{view.decision_reason} → 跳过晋升")
    else:
        body.append(f"LLM: 不晋升 理由: {_head(view.decision_reason, 90) or '—'}")
    _emit(lines, 5, body)



def _render_plan(view: RecordView, lines: List[str]) -> None:
    """⑥规划 — the chosen objective and the backlog item it came from (Algorithm 1
    step 6: ``plan ← Plan(E, H)``). Rendering it under the worthiness verdict would
    file the plan under the trigger."""
    if view.decision_kind != "promote":
        return
    body = [f"目标: {_head(view.promote_objective, 100)}"]
    if view.promote_backlog_id:
        body[0] += f" | backlog: {view.promote_backlog_id}"
    _emit(lines, 6, body)

def _render_behavioural_heredity(view: RecordView, lines: List[str]) -> None:
    """Skill generation/mutation/review — heredity at the behaviour level (step 11).

    Algorithm 1 annotates step 11 ``SkillEvolve … ▷ 遗传：行为级生成/变异/审查`` and the
    §4.2 ablation table files the whole skill chain under "−遗传", so skill events
    render under ⑨ and never under ⑦ (which is the CODE-side patch).
    """
    body = [
        (f"技能{kind}: {detail}" if kind else str(detail))
        for kind, detail in _seq(view.skill_events)
    ]
    _emit(lines, 9, body)


def render_record_header(view: RecordView) -> str:
    """The block header: the "this record started" signal.

    Emitted when the record STARTS, not with the rest of the block: the first thing a
    record does is a reflection call that takes minutes on a slow provider, and a log
    that stays silent from the provider probe until the block completes reads as a
    stuck run (the flat log printed its header before that call).
    """
    return block_header(f"记录 {view.index:2d}/{view.total} · {view.record_id} (L{view.level})")


def render_record_start(view: RecordView) -> List[str]:
    """Header + what executing the record produced before the first LLM call."""
    chip = step_glyph(2)
    seeded = (
        f"轨迹播种失败（不影响回放）: {_head(view.seed_error, 90)}" if view.seed_error
        else f"轨迹播种 {view.seeded} 行"
    )
    return [render_record_header(view), f"{chip}{seeded}"]


def render_record_progress(view: RecordView) -> List[str]:
    """What the record produced BEFORE the promotion decision (②执行 + ④记忆).

    Emitted as soon as it exists: this half covers the reflection call, which is the
    longest wait of a record on a slow provider. Buffering it until the block completes
    made a live run look like it had produced nothing for minutes.
    """
    lines: List[str] = []
    _render_execute(view, lines)
    _render_memory(view, lines)
    return lines


def render_record_tail(view: RecordView) -> List[str]:
    """The post-decision operators, in Algorithm-1 order:
    ③归因 ④记忆 ⑤触发 ⑥规划 ⑨遗传 ⑪沉淀.

    Attribution (E) and its memory write (MemWrite(M, E) — the experience/credit
    booking) and the promotion verdict are all produced inside the promotion pass, so
    this half can only be emitted once it returns.
    """
    lines: List[str] = []
    # Algorithm-1 order: E ← Attribute(τ, H) then M ← MemWrite(M, E). The experience
    # booking IS that write (store_experience books the credits it just computed in the
    # same call), so it must follow the attribution lines it records — not precede them.
    for render in (_render_attribute, _render_experience, _render_worthwhile, _render_plan,
                   _render_behavioural_heredity):
        render(view, lines)
    return lines


def render_record_settle(view: RecordView) -> List[str]:
    """⑪沉淀 — step 12, `M ← MemWrite(M, Δ, S, 结果)`.

    Emitted AFTER the campaign transitions, not with the record's own operators: the
    cumulative ledger it reports is the write that follows the cycle's mutation and
    heredity (⑦⑧⑨), so rendering it first made the log read 沉淀 → 变异.
    """
    checkpoints = _seq(view.checkpoint_lines)
    lines: List[str] = []
    if checkpoints:
        _emit(lines, 11, list(checkpoints))
    return lines


def render_record_block(view: RecordView) -> List[str]:
    """The whole record in one group (both halves, no header, no seed line).

    The run emits the halves at their own moments — see render_record_progress/tail —
    while this grouping stays for tests and for callers that want the record at once.
    """
    return render_record_progress(view) + render_record_tail(view) + render_record_settle(view)


def render_evolution_event(*, cycle: Any, kind: str, detail: str, mark: str = "") -> str:
    """A campaign in-cycle transition: ⑦变异 开 / ⑧选择 commit / ⑨遗传 终态.

    The operator follows Algorithm 1: producing the patch is directed VARIATION
    (step 7, code side), landing it through the review chain is SELECTION (step 8),
    and resolving it to absorbed/abandoned is HEREDITY (steps 9-10).
    """
    step = {"open": 7, "commit": 8, "outcome": 9}.get(kind)
    if step is None:
        return f"[战役#{cycle}] {detail}"
    tail = f" {mark}".rstrip() if mark else ""
    return f"{step_glyph(step)}战役#{cycle} {detail}{tail}"


def checkpoints_lines(
    *,
    rows: int,
    cycles: Any,
    absorbed: Any,
    dist: dict,
    cost: float,
    absorbed_rows: Iterable[dict] = (),
) -> List[str]:
    """⑪沉淀 — the cumulative cycle ledger, as its own block line(s).

    Returned as a list so it can be emitted standalone (a wait-loop tick) or folded
    into a record block under the same operator chip.
    """
    if not dist:
        return [f"checkpoints: （尚无周期记录）"]
    lines = [
        f"checkpoints: 行={rows} 周期={cycles} 吸收={absorbed} "
        f"分布={dict(dist)} 成本=${cost}"
    ]
    for row in absorbed_rows:
        lines.append(
            f"  absorbed {str(row.get('commit_sha') or '')[:12]} | "
            f"{_head(row.get('campaign_objective'), 60)}"
        )
    return lines


def render_milestone(
    *,
    index: int,
    cycles: Any,
    absorbed: Any,
    no_op: Any,
    skills: int,
    experiences: int,
    backlog_open: Any,
) -> str:
    """Cumulative mid-run view (every N records) — one line, same facts as before."""
    return (
        f"━━ 里程碑 @记录{index} ━━ 周期{cycles} (吸收{absorbed}, no_op{no_op}) | "
        f"技能{skills} | 经验{experiences} | backlog开放{backlog_open}"
    )


def render_session_head(
    *,
    arm: str,
    records: int,
    cadence: str,
    cadence_n: int,
    max_absorbed: int,
    baseline: int,
    models: dict,
) -> List[str]:
    """Session banner: the run's fixed configuration (the loop's inputs)."""
    lines = [
        block_header(
            f"LEAP 进化会话 · 臂 {arm} · 语料 {records} 条 · cadence {cadence}", width=60
        ),
        f" 运行配置  模型槽位 main={models.get('main')} "
        f"light={models.get('light')} heavy={models.get('heavy')}",
        f"           战役预算 max={max_absorbed} | cadence 块大小={cadence_n} | "
        f"历史战役基线={baseline}",
    ]
    return lines


def render_session_foot(*, arm: str, ledger_path: pathlib.Path, commits: str) -> List[str]:
    """Session close: the tagged snapshot and the absorbed-commit lineage."""
    return [
        f"{step_glyph(11)}ledger: {ledger_path}",
        f"{_cont(11)}吸收 commit（{arm}-evolved tag 相对起点）: {commits.strip() or '(无)'}",
    ]
