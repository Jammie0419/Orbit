"""The evolution run log is grouped by LEAP operators (Algorithm 1).

Formatting only: these tests pin the grouping, the operator numbering, and — most
importantly — that re-grouping the log did not drop a single datum the previous
per-source labels carried.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from devtools.benchmarks.evolution import leap_report  # noqa: E402


def _full_view(**overrides):
    """A record that exercised every stage, with each field holding a real value."""
    values = dict(
        index=5, total=11, record_id="2023_level2:35", level="2",
        goal="What is the maximum length in meters of #9…",
        seeded=175, rounds=155, error_count=16,
        markers=("SHELL_EXIT_ERROR", "TOOL_ERROR"),
        reflection_chars=1297, summary="**Reflection** the task failed because…",
        credits_new=(
            {"tool": "web_search", "credit": 0.033},
            {"tool": "run_command", "credit": 0.005},
        ),
        track_a=("task=2023_level2:35 | 结果=task | 类型=capability(h) | 关键=web_search(0.01)",),
        track_b=("cycle=f0523253 | 结果=no_op | 类型=capability(m) | 关键=search_code(0.02)",),
        memory_actions=(("scratchpad_append", "When youtube_transcript returns…"),),
        memory_applied=1, memory_total=1,
        experience_delta=1, experience_total=11,
        backlog_candidates=2,
        backlog_items=({"id": "ibl-abc123", "summary": "Add early capability-detection step…",
                        "priority": "high", "count": 1},),
        skill_eligibility="ok",
        decision_kind="promote", cadence_text="0/5",
        decision_reason="The recent task failed due to lack of vision capability detection",
        promote_objective="Add early capability-detection step for vision-dependent tasks",
        promote_backlog_id="ibl-3a4364ba2650",
        skill_events=(("生成", "standards-document-retriever (task 2023_level3:10)"),),
        checkpoint_lines=("checkpoints: 行=1 周期=1 吸收=0 分布={'no_op': 1} 成本=$0",),
    )
    values.update(overrides)
    return leap_report.RecordView(**values)


def _full_record_text(view=None):
    """The whole record as the run prints it: the start half, then the rest.

    They are emitted at different moments on purpose (the header must precede the
    reflection call), so the information guard has to look at both.
    """
    view = view if view is not None else _full_view()
    return "\n".join(leap_report.render_record_start(view) + leap_report.render_record_block(view))


def test_record_start_carries_the_header_and_seed_line_before_any_llm_call():
    """The header is the "this record started" signal: it must not wait for the
    reflection call, or a slow provider makes the run look stuck."""
    view = _full_view()
    start = "\n".join(leap_report.render_record_start(view))
    rest = "\n".join(leap_report.render_record_block(view))

    assert "记录  5/11" in start and "2023_level2:35" in start
    assert "轨迹播种 175 行" in start
    assert "轨迹播种" not in rest, "the seed line belongs to the start half only"
    assert "记录  5/11" not in rest, "the header is not repeated in the rest"
    assert "轮次 155" in rest and "轮次 155" not in start


def test_record_start_reports_a_seeding_failure_and_still_emits_the_rest():
    view = _full_view(seeded=0, seed_error="corpus trace unreadable")
    start = "\n".join(leap_report.render_record_start(view))
    rest = "\n".join(leap_report.render_record_block(view))
    assert "轨迹播种失败（不影响回放）: corpus trace unreadable" in start
    assert "轨迹播种" not in rest
    assert "⑤触发" in rest


def test_record_block_keeps_every_datum_the_old_labels_carried():
    """The re-grouping must not lose information: every value the per-source labels
    used to print still appears (this is the guard for the whole refactor)."""
    text = _full_record_text()

    # ②执行 — corpus seeding, the reflection's rounds/errors/markers/goal/summary
    assert "轨迹播种 175 行" in text
    assert "What is the maximum length in meters of #9…" in text
    assert "轮次 155" in text and "错误 16" in text
    assert "SHELL_EXIT_ERROR,TOOL_ERROR" in text
    assert "反思 1297 字" in text
    assert "**Reflection** the task failed because…" in text
    # ③归因 — credit extremes + both experience tracks, verbatim
    assert "信用 +2 步计分" in text
    assert "最高 web_search 0.033" in text and "最低 run_command 0.005" in text
    assert "Track-A task=2023_level2:35 | 结果=task" in text
    assert "Track-B cycle=f0523253 | 结果=no_op" in text
    # ④记忆 — each action, the applied ratio, experience accumulation, backlog cadence
    assert "scratchpad_append: When youtube_transcript returns…" in text
    assert "落库 1/1" in text
    assert "+1 经验（账本累计 11）" in text
    assert "backlog 候选 2 | 新增 1" in text
    assert "ibl-abc123" in text and "high | count=1" in text
    assert "技能资格 ✅ (ok)" in text
    # ⑤触发 — cadence, the promote verdict with its reason, objective and backlog link
    assert "cadence 0/5 | LLM: promote ✅" in text
    assert "lack of vision capability detection" in text
    assert "Add early capability-detection step for vision-dependent tasks" in text
    assert "backlog: ibl-3a4364ba2650" in text
    # ⑨遗传·行为级 / ⑪沉淀
    assert "技能生成: standards-document-retriever" in text
    assert "checkpoints: 行=1 周期=1 吸收=0 分布={'no_op': 1} 成本=$0" in text


def test_record_block_reports_the_counts_even_when_nothing_was_produced():
    """`mem=0` / `backlog=0` used to be printed unconditionally; the memory count is
    a memory-layer statistic, so its absence must still be stated (and a broken
    payload must be distinguishable from a deliberate empty)."""
    text = "\n".join(leap_report.render_record_block(_full_view(
        memory_actions=(), memory_applied=None, memory_total=0,
        backlog_candidates=0, backlog_items=(), skill_events=(), checkpoint_lines=(),
        track_a=(), track_b=(), credits_new=(),
    )))
    assert "落库 0/0" in text
    assert "mem_parse_failed" not in text


def test_record_block_marks_an_unparseable_memory_block_as_loss():
    text = "\n".join(leap_report.render_record_block(_full_view(
        memory_actions=(), memory_applied=None, memory_total=0,
        memory_parse_failed=True,
    )))
    assert "mem_parse_failed" in text
    assert "落库 0/0" not in text, "loss must not be rendered as a deliberate empty"


@pytest.mark.parametrize("kind,glyph", [
    ("skip", "⑤触发"), ("refuse", "⑤触发"), ("promote", "⑤触发"),
])
def test_decision_always_renders_under_the_worthiness_operator(kind, glyph):
    text = "\n".join(leap_report.render_record_block(
        _full_view(decision_kind=kind, decision_reason="cadence 1/5 未到期")))
    assert glyph in text


def test_stage_numbering_matches_algorithm_1():
    """Labels must stay tied to the paper's loop: Algorithm 1 steps -> operators.

    A drifted number would silently re-file a datum under the wrong operator (the
    skill chain, for one, belongs to heredity and was NOT filed there before).
    """
    assert leap_report.stage_label(2) == "②执行"
    assert leap_report.stage_label(3) == "③归因"
    assert leap_report.stage_label(4) == "④记忆"
    assert leap_report.stage_label(5) == "⑤触发"
    assert leap_report.stage_label(7) == "⑦变异"
    assert leap_report.stage_label(8) == "⑧选择"
    assert leap_report.stage_label(9) == "⑨遗传"
    assert leap_report.stage_label(11) == "⑪沉淀"
    # Operator 1 (Expression) is never rendered: the runner does not observe routing.
    text = "\n".join(leap_report.render_record_block(_full_view()))
    assert "①表达" not in text


def test_skill_events_render_under_heredity_not_variation():
    """Algorithm 1 annotates step 11 `SkillEvolve … ▷ 遗传：行为级生成/变异/审查`, and
    the §4.2 ablation table files the whole skill chain under "−遗传". ⑦变异 is the
    CODE-side patch operator — skill events must never render there."""
    text = "\n".join(leap_report.render_record_block(_full_view()))
    skill_line = next(line for line in text.splitlines() if "standards-document-retriever" in line)
    assert "⑨遗传" in skill_line
    assert "⑦变异" not in skill_line


def test_evolution_event_operators_follow_the_loop():
    """Campaign transitions: producing the patch is variation (7), landing it through
    review is selection (8), resolving it to absorbed/abandoned is heredity (9)."""
    opened = leap_report.render_evolution_event(cycle=1, kind="open", detail='开: "obj" (task 12345678)')
    committed = leap_report.render_evolution_event(cycle=1, kind="commit", detail="⤷ commit ✅ abc1234567")
    absorbed = leap_report.render_evolution_event(cycle=1, kind="outcome", detail="⤷ absorbed", mark="✅")

    assert "⑦变异" in opened and "⑦变异" not in committed
    assert "⑧选择" in committed
    assert "⑨遗传" in absorbed and absorbed.rstrip().endswith("✅")


def test_missing_stages_are_omitted_not_padded():
    """A stage with no data contributes no line at all (no placeholder), while the
    stages that did run keep their chips."""
    view = leap_report.RecordView(index=1, total=1, record_id="t", seeded=7, rounds=2)
    text = _full_record_text(view)
    assert "轨迹播种 7 行" in text
    assert "③归因" not in text and "⑤触发" not in text
    assert "⑨遗传" not in text and "⑪沉淀" not in text


def test_checkpoints_lines_report_the_cumulative_ledger():
    empty = leap_report.checkpoints_lines(rows=0, cycles=0, absorbed=0, dist={}, cost=0.0)
    assert empty == ["checkpoints: （尚无周期记录）"]

    filled = leap_report.checkpoints_lines(
        rows=3, cycles=2, absorbed=1, dist={"absorbed": 1, "no_op": 1}, cost=0.25,
        absorbed_rows=[{"commit_sha": "abcdef1234567890", "campaign_objective": "Harden the loop"}],
    )
    assert "行=3 周期=2 吸收=1" in filled[0]
    assert "成本=$0.25" in filled[0]
    assert "absorbed abcdef123456" in filled[1]


def test_session_head_and_foot_carry_the_run_identity():
    head = "\n".join(leap_report.render_session_head(
        arm="V3", records=130, cadence="every_n:5", cadence_n=5,
        max_absorbed=10, baseline=2, models={"main": "m", "light": "l", "heavy": "h"},
    ))
    assert "臂 V3" in head and "语料 130 条" in head and "every_n:5" in head
    assert "main=m light=l heavy=h" in head
    assert "max=10" in head and "cadence 块大小=5" in head and "历史战役基线=2" in head

    foot = "\n".join(leap_report.render_session_foot(
        arm="V3", ledger_path=pathlib.Path("/s/session_ledger.json"), commits="abc123 feat: x",
    ))
    assert "ledger: /s/session_ledger.json" in foot
    assert "吸收 commit（V3-evolved tag 相对起点）: abc123 feat: x" in foot
    empty_foot = "\n".join(leap_report.render_session_foot(
        arm="V3", ledger_path=pathlib.Path("/s/ledger.json"), commits="  ",
    ))
    assert "(无)" in empty_foot


def test_render_never_raises_on_hostile_values():
    """The block is emitted inside the feeding loop: rendering must survive whatever
    the upstream data holds (None rounds, non-dict items, huge strings)."""
    view = _full_view(
        rounds=None, markers=None, credits_new=({"tool": None, "credit": None},),
        track_a=("",), memory_actions=((None, None),),
        backlog_items=({"id": None, "summary": None},),
        skill_events=((None, None),), checkpoint_lines=("x" * 500,),
        decision_kind="refuse", decision_reason=None,
    )
    lines = leap_report.render_record_block(view)
    assert lines and all(isinstance(line, str) for line in lines)


def test_objective_renders_under_plan_not_under_the_trigger():
    """Algorithm 1 step 6 is ``plan ← Plan(E, H)``: the chosen objective is the PLAN,
    while the promote verdict belongs to the worthiness trigger (step 5)."""
    text = "\n".join(leap_report.render_record_block(_full_view()))
    objective_line = next(line for line in text.splitlines() if "early capability-detection step for" in line)
    assert "⑥规划" in objective_line, objective_line
    assert "⑤触发" in text, "the verdict itself still belongs to the trigger"


def test_plan_line_is_absent_when_nothing_was_promoted():
    text = "\n".join(leap_report.render_record_block(_full_view(
        decision_kind="skip", decision_reason="cadence 1/5 未到期")))
    assert "⑥规划" not in text
    assert "⑤触发" in text


def test_three_phase_emission_keeps_every_line_once():
    """A record is emitted at three moments (start / pre-decision / post-decision)
    so a slow provider cannot make the log look dead — and each datum must appear
    exactly once across the three, at the moment it actually exists."""
    view = _full_view()
    start = leap_report.render_record_start(view)
    progress = leap_report.render_record_progress(view)
    tail = leap_report.render_record_tail(view)
    settle = leap_report.render_record_settle(view)

    # ① header + seed right after seeding
    assert any("记录  5/11" in l for l in start)
    assert any("轨迹播种 175 行" in l for l in start)
    # ② reflection output + the memory writes that follow it, BEFORE the decision
    assert any("轮次 155" in l for l in progress)
    assert any("落库 1/1" in l for l in progress)
    assert any("ibl-abc123" in l for l in progress)
    # ③ the promotion decision and everything it produces, after it returns
    assert any("信用 +2 步计分" in l for l in tail)
    assert any("promote ✅" in l for l in tail)
    assert any("经验（账本累计 11）" in l for l in tail)

    # No line is duplicated between the halves and none is dropped.
    # ⑪沉淀 rides after the campaign transitions, so it is its own phase.
    assert any("checkpoints:" in l for l in settle)
    all_lines = start + progress + tail + settle
    assert len(all_lines) == len(set(all_lines)), "a line was emitted twice"
    joined = "\n".join(all_lines)
    for datum in ("轨迹播种 175 行", "轮次 155", "落库 1/1", "backlog 候选 2",
                  "技能资格 ✅ (ok)", "信用 +2 步计分", "Track-A", "经验（账本累计 11）",
                  "promote ✅", "目标:", "技能生成", "checkpoints:"):
        assert datum in joined, datum


def test_experience_line_is_not_placed_before_it_exists():
    """`+1 经验` is produced BY the promotion pass (store_experience runs inside
    maybe_promote), so the pre-decision half must never carry it — that half is
    emitted before the value exists."""
    view = _full_view()
    progress = "\n".join(leap_report.render_record_progress(view))
    tail = "\n".join(leap_report.render_record_tail(view))
    assert "经验" not in progress
    assert "经验（账本累计 11）" in tail


def test_tail_follows_algorithm_order_attribution_then_its_memory_write():
    """Algorithm 1: `3: E ← Attribute(τ, H)` then `4: M ← MemWrite(M, E)`. The
    experience booking IS the MemWrite of the attribution evidence (store_experience
    books the credits it just computed), so ③归因 must lead and ④记忆 follow."""
    lines = leap_report.render_record_tail(_full_view())
    order = []
    for i, line in enumerate(lines):
        for label in ("③归因", "④记忆", "⑤触发", "⑥规划", "⑨遗传"):
            if label in line and label not in order:
                order.append(label)
    assert order == ["③归因", "④记忆", "⑤触发", "⑥规划", "⑨遗传"], order
    # ⑪沉淀 是战役落账那一步（step 12），排在战役行之后，不在本组里。
    assert all("⑪沉淀" not in line for line in lines)
    assert any("⑪沉淀" in line for line in leap_report.render_record_settle(_full_view()))
    # 具体到那两行
    attr = next(i for i, l in enumerate(lines) if "信用 +" in l)
    booked = next(i for i, l in enumerate(lines) if "经验（账本累计" in l)
    assert attr < booked


def test_harness_emits_a_record_in_phases_not_as_one_block():
    """The run must emit each record at the moment its data exists — the batching made
    a slow provider look like a dead run. This pins the WIRING in the harness (the
    render-level tests above cannot see whether the run calls them in order)."""
    import inspect

    from devtools.benchmarks.evolution import run_evolution_arm as arm

    source = inspect.getsource(arm.main)
    order = [
        "render_record_start(_view)",
        "render_record_progress(_view)",
        "_emit_record_tail(_view)",
        "_campaign_transitions(data_root)",
        "render_record_settle(_view)",
    ]
    positions = []
    for call in order:
        index = source.find(call)
        assert index != -1, f"harness never calls {call}"
        positions.append(index)
    assert positions == sorted(positions), (
        "record emission order must be start -> progress -> tail -> campaign -> settle, "
        f"found {order} at {positions}"
    )
    # The old one-shot emission must be gone, or the batching could silently return.
    assert "render_record_block(" not in source, (
        "main() must not emit the whole record in one call"
    )
