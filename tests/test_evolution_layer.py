"""Tests for the evolution layer (PAPER 不足 4 + 5 + 7):

``OUROBOROS_MULTI_AGENT_EVOLVER`` switch gating, trajectory experience
learning (dual-track credit assignment: task traces + evolution-cycle traces
via the consumption cursor), and the multi-agent planner (structured plan
schema + degradation). Mock pattern follows tests/test_post_task_evolution.py
(no real LLM calls).
"""

import json
import pathlib
import types

import pytest

from ouroboros.evolution.multi_agent_evolver import MultiAgentEvolver
from ouroboros.evolution.trajectory_experience_learner import (
    TrajectoryExperienceLearner,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _drive(tmp_path: pathlib.Path) -> pathlib.Path:
    drive = tmp_path / "drive"
    (drive / "logs").mkdir(parents=True)
    (drive / "state").mkdir(parents=True)
    return drive


def _write_tool_row(drive: pathlib.Path, task_id: str, tool: str, *,
                    is_error: bool = False, status: str = "ok") -> None:
    row = {
        "ts": "2026-09-02T00:00:00Z",
        "type": "tool_call",
        "tool": tool,
        "task_id": task_id,
        "args": {},
        "result_preview": "ok",
        "is_error": is_error,
        "status": status,
    }
    with (drive / "logs" / "tools.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _write_checkpoint(drive: pathlib.Path, task_id: str, outcome: str, *,
                      objective: str = "Improve error recovery") -> None:
    row = {
        "schema_version": 1,
        "kind": "cycle_outcome",
        "ts": "2026-09-02T00:00:00Z",
        "source": "test",
        "task_id": task_id,
        "campaign_id": "test-c1",
        "campaign_objective": objective,
        "cycle_outcome": outcome,
        "commit_sha": "abc123",
    }
    with (drive / "state" / "evolution_checkpoints.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _fake_llm(monkeypatch, responses, captured=None):
    """Mock chat_observed to pop responses per call (list of dict)."""
    calls = []
    seq = [0]

    def _fake_chat_observed(client, **kwargs):
        calls.append(kwargs)
        idx = seq[0]
        seq[0] += 1
        if idx < len(responses):
            content = json.dumps(responses[idx])
        else:
            content = "{}"
        return {"content": content}, {}
    monkeypatch.setattr("ouroboros.llm_observability.chat_observed", _fake_chat_observed)
    if captured is not None:
        captured.update(calls=calls)
    return calls


def _promote_env(tmp_path: pathlib.Path):
    drive = _drive(tmp_path)
    return drive, types.SimpleNamespace(drive_root=drive, budget_drive_root=drive)


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------


def test_switch_defaults_off(monkeypatch):
    monkeypatch.delenv("OUROBOROS_MULTI_AGENT_EVOLVER", raising=False)
    from ouroboros.config import get_multi_agent_evolver_enabled

    assert get_multi_agent_evolver_enabled() is False


def test_switch_env_true(monkeypatch):
    monkeypatch.setenv("OUROBOROS_MULTI_AGENT_EVOLVER", "true")
    from ouroboros.config import get_multi_agent_evolver_enabled

    assert get_multi_agent_evolver_enabled() is True


# ---------------------------------------------------------------------------
# credit assignment core
# ---------------------------------------------------------------------------


def test_credit_formula_success_and_error():
    steps = [
        {"step_id": 0, "tool": "read_file", "is_error": False},
        {"step_id": 1, "tool": "run_command", "is_error": True},
    ]
    learner = TrajectoryExperienceLearner(pathlib.Path("."))
    credits = learner.assign_credits(steps)
    assert len(credits) == 2
    # error step is below the success step after normalization
    ok, err = credits[0], credits[1]
    assert ok["tool"] == "read_file" and err["tool"] == "run_command"
    assert ok["credit"] > err["credit"]
    assert abs(sum(c["credit"] for c in credits) - 1.0) < 1e-6


def test_credit_fast_and_thrifty_rewards():
    learner = TrajectoryExperienceLearner(pathlib.Path("."))
    creds = learner.assign_credits([
        {"step_id": 0, "tool": "a", "is_error": False,
         "duration_ms": 200, "tokens_used": 100},
        {"step_id": 1, "tool": "b", "is_error": False,
         "duration_ms": 5000, "tokens_used": 9000},
    ])
    assert creds[0]["credit"] > creds[1]["credit"]


def test_critical_steps_top3_and_lowest2():
    learner = TrajectoryExperienceLearner(pathlib.Path("."))
    credits = [
        {"step_id": i, "tool": f"t{i}", "credit": (10 - i) / 10.0}
        for i in range(6)
    ]
    critical = learner.identify_critical_steps(credits)
    ids = [c["step_id"] for c in critical]
    # top-3 (credit 1.0/0.9/0.8) + lowest-2 (0.5/0.4)
    assert ids[:3] == [0, 1, 2]
    assert sorted(ids[3:]) == [4, 5]


def test_classify_objective_keywords():
    learner = TrajectoryExperienceLearner(pathlib.Path("."))
    assert learner.classify_objective("fix the login bug") == "bug_fix"
    assert learner.classify_objective("optimize startup speed") == "performance"
    assert learner.classify_objective("add workspace export") == "capability"
    assert learner.classify_objective("refactor the loop") == "refactor"
    assert learner.classify_objective("hello world") == "other"


def test_store_and_load_roundtrip(tmp_path):
    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    learner.store_experience(
        kind="cycle", task_id="evo1", objective="fix bug",
        outcome="absorbed",
        steps=[{"step_id": 0, "tool": "edit_text", "is_error": False}],
        overall={"objective_type": "bug_fix", "success_factors": ["x"]},
    )
    recs = learner.load_experiences()
    assert len(recs) == 1
    assert recs[0]["kind"] == "cycle"
    assert recs[0]["outcome"] == "absorbed"
    assert recs[0]["credits"]
    # step_credits.jsonl carries the critical steps
    credits_log = (drive / "state" / "step_credits.jsonl").read_text(encoding="utf-8")
    assert "edit_text" in credits_log


def test_query_similar_filters_by_type_and_kind(tmp_path):
    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    learner.store_experience(kind="cycle", task_id="c1", objective="fix login bug",
                             outcome="absorbed",
                             steps=[{"step_id": 0, "tool": "a", "is_error": False}],
                             overall={"objective_type": "bug_fix"})
    learner.store_experience(kind="task", task_id="t1", objective="optimize speed",
                             outcome="task",
                             steps=[{"step_id": 0, "tool": "b", "is_error": False}],
                             overall={"objective_type": "performance"})
    similar = learner.query_similar_objectives("fix crash error", kind="cycle")
    assert len(similar) == 1
    assert similar[0]["task_id"] == "c1"


def test_suggest_no_history_is_standard(tmp_path):
    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    strategy = learner.suggest_evolution_strategy("fix a bug")
    assert strategy["strategy"] == "standard"
    assert strategy["confidence"] == 0.5


def test_suggest_optimized_from_cycle_history(tmp_path):
    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    learner.store_experience(
        kind="cycle", task_id="c1", objective="fix login bug", outcome="absorbed",
        steps=[{"step_id": 0, "tool": "edit_text", "is_error": False},
               {"step_id": 1, "tool": "run_command", "is_error": False}],
        overall={"objective_type": "bug_fix",
                 "success_factors": ["small targeted patch"],
                 "failure_factors": [], "reusable_pattern": "minimal diff wins"},
    )
    strategy = learner.suggest_evolution_strategy("fix the crash on login")
    assert strategy["strategy"] == "optimized"
    assert strategy["confidence"] == 1.0
    assert "minimal diff wins" in strategy["success_patterns"]
    assert strategy["recommended_tools"]


# ---------------------------------------------------------------------------
# dual-track entries
# ---------------------------------------------------------------------------


def test_extract_task_experience_track_a(tmp_path, monkeypatch):
    drive = _drive(tmp_path)
    _write_tool_row(drive, "t1", "read_file")
    _write_tool_row(drive, "t1", "edit_text", is_error=True, status="error")
    _write_tool_row(drive, "other", "run_command")  # different task, ignored
    captured = {}
    _fake_llm(monkeypatch, [{
        "objective_type": "bug_fix", "objective_complexity": "medium",
        "success_factors": ["located fast"], "failure_factors": ["bad edit"],
        "reusable_pattern": "read before edit",
    }], captured)
    learner = TrajectoryExperienceLearner(drive, llm_client=object())
    rec = learner.extract_task_experience("t1")
    assert rec is not None
    assert rec["kind"] == "task"
    assert len(rec["steps"]) == 2
    assert [s["tool"] for s in rec["steps"]] == ["read_file", "edit_text"]
    assert rec["overall"]["reusable_pattern"] == "read before edit"
    # LLM call type is observable
    assert captured["calls"][0]["call_type"] == "evolution_experience_extraction"


def test_extract_task_experience_empty_trace_returns_none(tmp_path):
    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    assert learner.extract_task_experience("missing-task") is None


def test_consume_pending_cycles_track_b_with_cursor(tmp_path, monkeypatch):
    drive = _drive(tmp_path)
    _write_checkpoint(drive, "evo1", "absorbed", objective="fix login bug")
    _write_checkpoint(drive, "evo2", "abandoned", objective="refactor internals")
    _write_checkpoint(drive, "evo3", "absorbed", objective="speed up startup")
    _write_tool_row(drive, "evo1", "edit_text")
    _write_tool_row(drive, "evo2", "run_command", is_error=True, status="error")
    captured = {}
    _fake_llm(monkeypatch, [
        {"objective_type": "bug_fix", "failure_factors": []},
        {"objective_type": "other", "failure_factors": ["verify failed"]},
        {"objective_type": "performance", "failure_factors": []},
    ], captured)
    learner = TrajectoryExperienceLearner(drive, llm_client=object())
    consumed = learner.consume_pending_cycles()
    assert consumed == 3
    recs = learner.load_experiences(kind="cycle")
    assert len(recs) == 3
    kinds = {r["task_id"] for r in recs}
    assert kinds == {"evo1", "evo2", "evo3"}
    # cursor advanced: a second pass analyzes nothing new
    assert learner.consume_pending_cycles() == 0
    assert len(learner.load_experiences(kind="cycle")) == 3
    # evo2 (abandoned) experiences carry the abandoned outcome
    evo2 = next(r for r in recs if r["task_id"] == "evo2")
    assert evo2["outcome"] == "abandoned"


def test_consume_skips_non_terminal_rows(tmp_path):
    drive = _drive(tmp_path)
    (drive / "state" / "evolution_checkpoints.jsonl").write_text(
        json.dumps({"kind": "task_done", "task_id": "x"}) + "\n", encoding="utf-8")
    _write_checkpoint(drive, "evo1", "waiting_for_restart")
    learner = TrajectoryExperienceLearner(drive)
    assert learner.consume_pending_cycles() == 0
    assert learner.load_experiences() == []


# ---------------------------------------------------------------------------
# multi-agent planner
# ---------------------------------------------------------------------------


def test_evolver_plan_schema(tmp_path, monkeypatch):
    drive = _drive(tmp_path)
    _fake_llm(monkeypatch, [
        {"root_causes": ["bad retry logic"],
         "improvements": [{"objective": "fix retry backoff",
                           "rationale": "timeouts pile up", "estimated_impact": "medium"}]},
        {"approach": "Exponential backoff in retry loop",
         "files_to_modify": ["ouroboros/loop_tool_execution.py"],
         "implementation_steps": ["Add backoff", "Clamp max"], "risks": ["Timeout softer"]},
        {"verification_plan": ["Run unit tests", "Restart verify"]},
    ])
    evolver = MultiAgentEvolver(drive, llm_client=object())
    plan = evolver.run_evolution_cycle(
        steps=[{"step_id": 0, "tool": "run_command", "is_error": True}],
        reflection_entry={"goal": "fix retries"},
        objective_hint="fix retry backoff",
    )
    assert plan["schema_version"] == 1
    assert plan["objective"] == "fix retry backoff"
    assert plan["root_causes"] == ["bad retry logic"]
    assert plan["approach"].startswith("Exponential")
    assert plan["files_to_modify"] == ["ouroboros/loop_tool_execution.py"]
    assert len(plan["implementation_steps"]) == 2
    assert len(plan["verification_plan"]) == 2


def test_evolver_degrades_without_llm(tmp_path):
    drive = _drive(tmp_path)
    evolver = MultiAgentEvolver(drive, llm_client=None)
    plan = evolver.run_evolution_cycle(
        steps=[{"step_id": 0, "tool": "x", "is_error": True}],
        reflection_entry=None,
        objective_hint="fix the bug",
    )
    assert plan["schema_version"] == 1
    assert plan["objective"] == "fix the bug"
    assert plan["root_causes"] == []
    assert plan["approach"] == ""
    assert plan["verification_plan"] == []


def test_verification_advice_strengthened_on_verify_failures(tmp_path, monkeypatch):
    drive = _drive(tmp_path)
    calls = {}
    _fake_llm(monkeypatch, [
        {"verification_plan": ["Build", "Run login tests"]},
    ], calls)
    evolver = MultiAgentEvolver(drive, llm_client=object())
    advice = evolver._verification_advice(
        {"objective": "fix login bug", "implementation_steps": ["Add guard"]},
        {"failure_factors": ["skipped restart verify", "no tests run"]},
    )
    assert len(advice) == 2
    verify_prompt = calls["calls"][0]["messages"][0]["content"]
    assert "verification-stage failures" in verify_prompt


def test_planner_stages_consume_experience_digest(tmp_path, monkeypatch):
    """失败回环: experience_digest 注入 Analyzer/Researcher prompt（含历史失败
    模式时避开已知失败路径）；无 digest 时不出现该段。"""
    drive = _drive(tmp_path)
    captured = {}
    _fake_llm(monkeypatch, [
        {"root_causes": ["c"], "improvements": [{"objective": "fix"}]},
        {"approach": "A", "files_to_modify": [], "implementation_steps": [], "risks": []},
        {"verification_plan": ["Build"]},
    ], captured)
    evolver = MultiAgentEvolver(drive, llm_client=object())
    digest = "Failure patterns: skipped restart verify | Success patterns: minimal diff\n(confidence 0.5)"
    evolver.run_evolution_cycle(
        steps=[{"step_id": 0, "tool": "x", "is_error": True}],
        objective_hint="fix",
        experience_digest=digest,
    )
    analyze_prompt = captured["calls"][0]["messages"][0]["content"]
    research_prompt = captured["calls"][1]["messages"][0]["content"]
    assert "[HISTORICAL PATTERNS" in analyze_prompt
    assert "skipped restart verify" in analyze_prompt
    assert "[HISTORICAL PATTERNS" in research_prompt
    # without digest the section is absent
    captured["calls"].clear()
    evolver.run_evolution_cycle(
        steps=[{"step_id": 0, "tool": "x", "is_error": True}],
        objective_hint="fix",
        experience_digest="",
    )
    assert "[HISTORICAL PATTERNS" not in captured["calls"][0]["messages"][0]["content"]


def test_layer_calls_use_explicit_main_model_slot(tmp_path, monkeypatch):
    """进化层 LLM 调用必须显式解析主模型槽位（空 model 会解析成
    provider=openrouter + 空模型名，真实运行时必失败）。"""
    monkeypatch.setenv("OUROBOROS_MODEL", "openai-compatible::mimo-v2.5")
    drive = _drive(tmp_path)
    captured = {}
    _fake_llm(monkeypatch, [
        {"root_causes": ["c"], "improvements": [{"objective": "fix"}]},
        {"approach": "A", "files_to_modify": [], "implementation_steps": [], "risks": []},
        {"verification_plan": ["Build"]},
    ], captured)
    evolver = MultiAgentEvolver(drive, llm_client=object())
    evolver.run_evolution_cycle(
        steps=[{"step_id": 0, "tool": "x", "is_error": True}],
        objective_hint="fix",
    )
    assert len(captured["calls"]) == 3  # analyze + research + verify
    for call in captured["calls"]:
        assert call["model"] == "openai-compatible::mimo-v2.5", call["model"]
        assert call["model"] != ""


# ---------------------------------------------------------------------------
# wiring: maybe_promote + request + campaign + task text
# ---------------------------------------------------------------------------


def _promote_task():
    return {
        "id": "t-promote", "chat_id": 1, "type": "api_task",
        "description": "fix the login bug",
    }


def test_maybe_promote_switch_off_matches_v4(tmp_path, monkeypatch):
    """Enabled envelope + DISABLED evolution layer == today's behavior:
    no [EVOLUTION EXPERIENCE] prompt section, no evolution_plan in the request."""
    import ouroboros.post_task_evolution as pte

    drive, env = _promote_env(tmp_path)
    monkeypatch.setenv("OUROBOROS_POST_TASK_EVOLUTION", "true")
    monkeypatch.setenv("OUROBOROS_MULTI_AGENT_EVOLVER", "false")
    captured = {}
    _fake_llm(monkeypatch, [
        {"promote": True, "objective": "fix login bug", "requires_plan_review": True,
         "backlog_id": ""},
    ], captured)
    decision = pte.maybe_promote(env, _promote_task(), None, llm_client=object())
    assert decision is not None
    prompt = captured["calls"][0]["messages"][0]["content"]
    assert "EVOLUTION EXPERIENCE" in prompt  # section exists (digest empty → "(no learned patterns yet)")
    req = json.loads((drive / "state" / "post_task_evolution_request.json").read_text(encoding="utf-8"))
    assert "evolution_plan" not in req


def test_maybe_promote_switch_on_extracts_and_plans(tmp_path, monkeypatch):
    import ouroboros.post_task_evolution as pte

    drive, env = _promote_env(tmp_path)
    _write_tool_row(drive, "t-promote", "read_file")
    _write_tool_row(drive, "t-promote", "edit_text", is_error=True, status="error")
    _write_checkpoint(drive, "evo-old", "absorbed", objective="fix login bug")
    _write_tool_row(drive, "evo-old", "run_command")
    monkeypatch.setenv("OUROBOROS_POST_TASK_EVOLUTION", "true")
    monkeypatch.setenv("OUROBOROS_MULTI_AGENT_EVOLVER", "true")
    captured = {}
    _fake_llm(monkeypatch, [
        # 1: task experience extraction (kind=task)
        {"objective_type": "bug_fix", "failure_factors": ["bad edit"]},
        # 2: cycle experience extraction (kind=cycle)
        {"objective_type": "bug_fix", "failure_factors": ["skipped verify"]},
        # 3: decision
        {"promote": True, "objective": "fix login bug", "requires_plan_review": True,
         "backlog_id": ""},
        # 4-6: planner stages
        {"root_causes": ["bad edit"], "improvements": [{"objective": "fix login bug"}]},
        {"approach": "Guard login parse", "files_to_modify": ["x.py"],
         "implementation_steps": ["Add guard"], "risks": []},
        {"verification_plan": ["Run login tests"]},
    ], captured)
    decision = pte.maybe_promote(env, _promote_task(), None, llm_client=object())
    assert decision is not None
    # decision prompt carries the learned cycle pattern
    decision_prompt = captured["calls"][2]["messages"][0]["content"]
    assert "skipped verify" in decision_prompt
    req = json.loads((drive / "state" / "post_task_evolution_request.json").read_text(encoding="utf-8"))
    assert req["evolution_plan"]["objective"] == "fix login bug"
    assert req["evolution_plan"]["approach"] == "Guard login parse"
    assert req["evolution_plan"]["verification_plan"] == ["Run login tests"]
    # cursor advanced past the old cycle
    cursor = json.loads((drive / "state" / "evolution_consumed.json").read_text(encoding="utf-8"))
    assert cursor["last_seq"] == 1


def test_apply_pending_request_attaches_plan_to_campaign(tmp_path, monkeypatch):
    import ouroboros.post_task_evolution as pte

    drive = _drive(tmp_path)
    req = {
        "schema_version": 1, "ts": "2026-09-02T00:00:00Z",
        "objective": "fix login bug", "requires_plan_review": True,
        "backlog_id": "", "source": "post_task", "origin_task_id": "t1",
        "evolution_plan": {"schema_version": 1, "objective": "fix login bug",
                           "approach": "Guard login parse", "verification_plan": ["Run tests"]},
    }
    (drive / "state" / "post_task_evolution_request.json").write_text(
        json.dumps(req), encoding="utf-8")
    campaigned: dict = {}
    monkeypatch.setenv("OUROBOROS_POST_TASK_EVOLUTION", "true")

    def _fake_start(objective, source="owner"):
        campaigned["objective"] = objective
        campaigned["status"] = "active"
        return campaigned

    def _fake_state_load():
        return {"owner_chat_id": 1, "evolution_owner_stopped": False,
                "evolution_mode_enabled": False}

    monkeypatch.setattr("supervisor.evolution_lifecycle.start_evolution_campaign", _fake_start)
    monkeypatch.setattr("supervisor.evolution_lifecycle.evolution_block_reason", lambda: "")
    monkeypatch.setattr("supervisor.state.load_state", _fake_state_load)

    def _fake_update_state(mutator):
        live = _fake_state_load()
        mutator(live)
        return live

    monkeypatch.setattr("supervisor.state.update_state", _fake_update_state)
    wrote = {}

    def _fake_read():
        return campaigned

    def _fake_write(camp, **kw):
        wrote.update(camp)
        return True

    monkeypatch.setattr("supervisor.evolution_lifecycle._read_evolution_campaign", _fake_read)
    monkeypatch.setattr("supervisor.evolution_lifecycle._write_evolution_campaign", _fake_write)
    assert pte.apply_pending_request(drive) is True
    assert wrote.get("evolution_plan", {}).get("approach") == "Guard login parse"


def test_build_evolution_task_text_injects_plan(monkeypatch):
    from supervisor.evolution_lifecycle import build_evolution_task_text

    campaign = {
        "id": "c1", "status": "active", "objective": "fix login bug",
        "source": "post_task", "evolution_plan": {
            "schema_version": 1, "objective": "fix login bug",
            "approach": "Guard the login parser",
            "implementation_steps": ["Add guard", "Clamp input"],
            "verification_plan": ["Run login tests", "Restart verify"],
            "risks": ["None known"],
        },
    }
    monkeypatch.setattr("supervisor.evolution_lifecycle._read_evolution_campaign",
                        lambda: campaign)
    text = build_evolution_task_text(1)
    assert "## Evolution Plan" in text
    assert "Guard the login parser" in text
    assert "Add guard" in text
    assert "Run login tests" in text


def test_build_evolution_task_text_injects_cycle_lessons(tmp_path, monkeypatch):
    """失败重试的 cycle 任务文本融入 Track-B 经验（## Lessons From Past Cycles）：
    重试结构不变（同 objective 跨 cycle 重试），但教训随任务文本注入；开关关时零变化。"""
    from supervisor.evolution_lifecycle import build_evolution_task_text

    drive = _drive(tmp_path)
    learner = TrajectoryExperienceLearner(drive)
    learner.store_experience(
        kind="cycle", task_id="evo-fail-1", objective="fix login bug",
        outcome="abandoned",
        steps=[{"step_id": 0, "tool": "edit_text", "is_error": False},
               {"step_id": 1, "tool": "run_command", "is_error": True}],
        overall={"objective_type": "bug_fix",
                 "failure_factors": ["skipped restart verify", "bad edit"],
                 "reusable_pattern": ""},
    )
    monkeypatch.setenv("OUROBOROS_MULTI_AGENT_EVOLVER", "true")
    monkeypatch.setattr(
        "supervisor.evolution_lifecycle._read_evolution_campaign",
        lambda: {"id": "c1", "status": "active", "objective": "fix the crash on login"},
    )
    monkeypatch.setattr("supervisor.queue.DRIVE_ROOT", str(drive))
    text = build_evolution_task_text(1)
    assert "## Lessons From Past Cycles" in text
    assert "skipped restart verify" in text
    assert "evo-fail-1" in text
    # 开关关 → 段不出现（V4 行为不变）
    monkeypatch.delenv("OUROBOROS_MULTI_AGENT_EVOLVER")
    text2 = build_evolution_task_text(2)
    assert "## Lessons From Past Cycles" not in text2


def test_build_evolution_task_text_without_plan_unchanged(monkeypatch):
    from supervisor.evolution_lifecycle import build_evolution_task_text

    campaign = {"id": "c1", "status": "active", "objective": "fix login bug",
                "source": "post_task"}
    monkeypatch.setattr("supervisor.evolution_lifecycle._read_evolution_campaign",
                        lambda: campaign)
    text = build_evolution_task_text(1)
    assert "## Evolution Plan" not in text
    assert "## Objective" in text
    assert "fix login bug" in text