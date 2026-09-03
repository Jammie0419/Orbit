"""Tests for the Hermes-Style Skill Evolution envelope (PAPER Phase 3).

Domain: per-skill stats ledger, trajectory -> self-authored skill generation,
GEPA genetic evolution, nudge cadence, quality-aware router scoring, and the
``maybe_promote`` wiring behind ``OUROBOROS_SKILL_EVOLUTION`` (default OFF).

Mock strategy mirrors test_evolution_layer.py: real call paths, LLM faked by
patching ``ouroboros.llm_observability.chat_observed`` with a response queue.
"""

import json
import pathlib
import types

import pytest

from ouroboros.contracts.skill_manifest import parse_skill_manifest_text
from ouroboros.skill_evolution.auto_generation import write_skill_package
from ouroboros.skill_evolution import auto_generation as ag
from ouroboros.skill_evolution import genetic_evolution as ge
from ouroboros.skill_evolution import nudge as nud
from ouroboros.skill_evolution import stats as st
from ouroboros.smart_router import SmartRouter

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _drive(tmp_path):
    drive = pathlib.Path(tmp_path) / "drive"
    (drive / "logs").mkdir(parents=True)
    (drive / "state").mkdir(parents=True)
    return drive


def _promote_env(tmp_path):
    drive = _drive(tmp_path)
    env = types.SimpleNamespace(drive_root=drive, budget_drive_root=drive)
    return drive, env


def _write_tool_row(drive, task_id, tool, is_error, *, status="ok", args=None):
    row = {
        "ts": "2026-09-03T00:00:00Z",
        "type": "tool_call",
        "tool": tool,
        "task_id": task_id,
        "args": args if args is not None else {},
        "result_preview": f"{tool} -> ok" if not is_error else f"{tool} -> boom",
        "is_error": bool(is_error),
        "status": "error" if is_error else status,
    }
    with (drive / "logs" / "tools.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_stats(drive, data):
    (drive / "state" / "skill_stats.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _seed_skill(drive, name, *, version="1.0", code="print('hi')\n", tags=None):
    """A discovered, self-authored skill package (markers included)."""
    return write_skill_package(
        drive,
        {
            "name": name,
            "description": f"seed {name}",
            "version": version,
            "type": "script",
            "runtime": "python",
            "when_to_use": "when seeding",
            "scripts": [{"name": "main.py", "code": code}],
            "tags": tags or ["seed"],
        },
        task_id="seed-task",
        created_by_tool="test",
    )


def _fake_llm(monkeypatch, responses, captured=None):
    """Queue-based chat_observed fake; pops one response per call."""
    if captured is None:
        captured = {"calls": []}
    seq = [0]

    def _fake(client, **kwargs):
        captured["calls"].append(kwargs)
        idx = seq[0]
        seq[0] += 1
        content = json.dumps(responses[idx]) if idx < len(responses) else "{}"
        return {"content": content}, {}

    monkeypatch.setattr("ouroboros.llm_observability.chat_observed", _fake)
    return captured


@pytest.fixture(autouse=True)
def _clear_router_cache():
    SmartRouter.invalidate_skills_cache()
    yield
    SmartRouter.invalidate_skills_cache()


def _discovered(drive):
    from ouroboros.skill_loader import discover_skills
    return discover_skills(drive)


# --------------------------------------------------------------------------- #
# switch (config getter)
# --------------------------------------------------------------------------- #

def test_switch_default_off(monkeypatch):
    monkeypatch.delenv("OUROBOROS_SKILL_EVOLUTION", raising=False)
    from ouroboros.config import get_skill_evolution_enabled
    assert get_skill_evolution_enabled() is False


def test_switch_env_true(monkeypatch):
    monkeypatch.setenv("OUROBOROS_SKILL_EVOLUTION", "true")
    from ouroboros.config import get_skill_evolution_enabled
    assert get_skill_evolution_enabled() is True


def test_switch_settings_json_wins(monkeypatch, tmp_path):
    settings_path = pathlib.Path(tmp_path) / "settings.json"
    settings_path.write_text(
        json.dumps({"OUROBOROS_SKILL_EVOLUTION": "true"}), encoding="utf-8")
    monkeypatch.setattr("ouroboros.config.SETTINGS_PATH", settings_path)
    monkeypatch.delenv("OUROBOROS_SKILL_EVOLUTION", raising=False)
    from ouroboros.config import get_skill_evolution_enabled
    assert get_skill_evolution_enabled() is True


# --------------------------------------------------------------------------- #
# stats ledger
# --------------------------------------------------------------------------- #

def test_stats_aggregate_counts_and_rate(tmp_path):
    drive = _drive(tmp_path)
    for i in range(3):
        _write_tool_row(drive, "t1", "skill_exec", False, args={"skill": "demo"})
    _write_tool_row(drive, "t1", "skill_exec", True, args={"skill": "demo"})
    _write_tool_row(drive, "t1", "Terminal", False)  # non-skill rows ignored
    result = st.SkillStatsLedger(drive).aggregate()
    entry = result["demo"]
    assert entry["execution_count"] == 4
    assert entry["success_count"] == 3
    assert entry["success_rate"] == pytest.approx(0.75)
    assert entry["evolution_version"] == 1
    assert pathlib.Path(drive, "state", "skill_stats.json").exists()


def test_stats_aggregate_preserves_evolution_version(tmp_path):
    drive = _drive(tmp_path)
    _write_stats(drive, {"demo": {"evolution_version": 5}})
    _write_tool_row(drive, "t1", "skill_exec", False, args={"skill": "demo"})
    result = st.SkillStatsLedger(drive).aggregate()
    assert result["demo"]["evolution_version"] == 5


def test_stats_load_missing_is_empty(tmp_path):
    drive = _drive(tmp_path)
    assert st.SkillStatsLedger(drive).load() == {}


def test_stats_attach_to_skills(tmp_path):
    drive = _drive(tmp_path)
    _write_stats(drive, {"demo": {"execution_count": 3, "success_rate": 0.9}})
    skills = [types.SimpleNamespace(name="demo"), types.SimpleNamespace(name="other")]
    st.SkillStatsLedger(drive).attach_to_skills(skills)
    assert skills[0].skill_stats["success_rate"] == 0.9
    assert skills[1].skill_stats == {}


def test_stats_bump_evolution_version(tmp_path):
    drive = _drive(tmp_path)
    _write_stats(drive, {"demo": {"evolution_version": 1}})
    new_version = st.SkillStatsLedger(drive).bump_evolution_version("demo")
    assert new_version == 2
    assert st.SkillStatsLedger(drive).get("demo")["evolution_version"] == 2


# --------------------------------------------------------------------------- #
# auto generation: gates
# --------------------------------------------------------------------------- #

def _eligible_steps():
    # 7 steps: an error followed by a recovery = self-repair, last step ok.
    return [
        {"step_id": i, "tool": "Terminal", "is_error": False,
         "status": "ok", "result_preview": "ok", "args": "{}"}
        for i in range(6)
    ] + [{"step_id": 6, "tool": "Terminal", "is_error": True, "status": "error"}]


def test_generate_eligible_true(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    gen = ag.SkillAutoGenerator(drive)
    steps = _eligible_steps()
    steps[2] = {"step_id": 2, "tool": "Edit", "is_error": True, "status": "error"}
    assert gen.is_eligible(steps, outcome_hint="success") is True


def test_generate_gate_too_few_calls(tmp_path):
    drive = _drive(tmp_path)
    gen = ag.SkillAutoGenerator(drive)
    steps = _eligible_steps()[:4]  # < MIN_TOOL_CALLS
    assert gen.is_eligible(steps, outcome_hint="success") is False


def test_generate_gate_no_self_repair(tmp_path):
    drive = _drive(tmp_path)
    gen = ag.SkillAutoGenerator(drive)
    steps = [dict(s, is_error=False) for s in _eligible_steps()]
    assert gen.is_eligible(steps, outcome_hint="success") is False


def test_generate_gate_task_failed(monkeypatch, tmp_path):
    monkeypatch.delenv("OUROBOROS_SKILL_EVOLUTION", raising=False)
    drive = _drive(tmp_path)
    gen = ag.SkillAutoGenerator(drive)
    steps = _eligible_steps()
    assert gen.is_eligible(steps, outcome_hint="failure") is False


def test_generate_task_succeeded_heuristic():
    assert ag.task_succeeded("", [{"is_error": False}]) is True
    assert ag.task_succeeded("", [{"is_error": True}]) is False
    assert ag.task_succeeded("failure", [{"is_error": False}]) is False
    assert ag.task_succeeded("SUCCESS", []) is True


# --------------------------------------------------------------------------- #
# auto generation: creation path
# --------------------------------------------------------------------------- #

def test_generate_creates_skill_package(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)  # self-repair
    skill_json = {
        "name": "log-bouncer",
        "description": "bounces logs",
        "type": "script",
        "runtime": "python",
        "when_to_use": "when log files grow",
        "tags": ["log", "cleanup"],
        "scripts": [{"name": "main.py", "code": "#!/usr/bin/env python3\nprint('ok')\n"}],
    }
    _fake_llm(monkeypatch, [skill_json])
    gen = ag.SkillAutoGenerator(drive, llm_client=object())
    record = gen.maybe_generate_for_task("t9", goal="bounce the logs")
    assert record is not None and record["outcome"] == "created"
    skill_dir = drive / "skills" / "self" / "log-bouncer"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "scripts" / "main.py").read_text(encoding="utf-8") == skill_json["scripts"][0]["code"]
    parsed = parse_skill_manifest_text((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    assert parsed.name == "log-bouncer"
    assert parsed.version == "1.0"
    assert parsed.scripts[0]["name"] == "main.py"


def test_generate_dual_markers_match(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    _fake_llm(monkeypatch, [{
        "name": "log-bouncer", "description": "b", "type": "script",
        "scripts": [{"name": "main.py", "code": "print(1)\n"}],
    }])
    ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    from ouroboros.skill_loader import is_self_authored_skill_dir
    skill_dir = drive / "skills" / "self" / "log-bouncer"
    assert is_self_authored_skill_dir(skill_dir, drive_root=drive) is True
    dir_marker = json.loads((skill_dir / ".self_authored.json").read_text(encoding="utf-8"))
    state_marker = json.loads((drive / "state" / "skills" / "log-bouncer" / "self_authored.json").read_text(encoding="utf-8"))
    assert dir_marker["task_id"] == "t9"
    assert state_marker["task_id"] == dir_marker["task_id"]
    assert state_marker["created_at"] == dir_marker["created_at"]
    assert dir_marker["created_by_tool"] == "skill_auto_generation"


def test_generate_discovered_as_self_authored(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    _fake_llm(monkeypatch, [{
        "name": "log-bouncer", "description": "b", "type": "script",
        "scripts": [{"name": "main.py", "code": "print(1)\n"}],
    }])
    ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    skills = _discovered(drive)
    found = [s for s in skills if s.name == "log-bouncer"]
    assert len(found) == 1
    assert found[0].is_self_authored is True
    assert found[0].source == "self_authored"


def test_generate_name_dedupe_skips(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "log-bouncer")
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    # Name is only known after extraction, so one LLM call happens; write is skipped.
    captured = _fake_llm(monkeypatch, [{
        "name": "log-bouncer", "description": "b", "type": "script",
        "scripts": [{"name": "main.py", "code": "print(1)\n"}],
    }])
    record = ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    assert record is None
    assert len(captured["calls"]) == 1
    history = [json.loads(l) for l in (drive / "state" / "skill_generation_history.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert history[-1]["outcome"] == "skipped"
    assert history[-1]["reason"] == "name_exists"


def test_generate_task_already_recorded_skips(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    # Pre-existing history row for the same task (a prior failed attempt).
    with (drive / "state" / "skill_generation_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"task_id": "t9", "outcome": "failed"}) + "\n")
    captured = _fake_llm(monkeypatch, [])
    record = ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    assert record is None
    assert captured["calls"] == []


def test_generate_llm_failure_degrades(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    _fake_llm(monkeypatch, ["this is not json at all"])
    record = ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    assert record is None
    assert not (drive / "skills").exists()
    history = [json.loads(l) for l in (drive / "state" / "skill_generation_history.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert history[-1]["outcome"] == "failed"


def test_generate_invalid_shape_records_failed(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    _fake_llm(monkeypatch, [{"name": "broken", "type": "script"}])  # no scripts
    record = ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    assert record is None
    history = [json.loads(l) for l in (drive / "state" / "skill_generation_history.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert history[-1]["reason"] == "script_type_requires_scripts"


def test_generate_no_llm_client_silent(tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    record = ag.SkillAutoGenerator(drive, llm_client=None).maybe_generate_for_task("t9")
    assert record is None
    assert not (drive / "skills").exists()


def test_load_task_steps_args_passthrough(tmp_path):
    drive = _drive(tmp_path)
    _write_tool_row(drive, "t1", "skill_exec", False, args={"skill": "demo", "script": "main.py"})
    from ouroboros.evolution.trajectory_experience_learner import TrajectoryExperienceLearner
    steps = TrajectoryExperienceLearner(drive).load_task_steps("t1")
    assert steps and "args" in steps[0]
    assert '"skill": "demo"' in steps[0]["args"]


# --------------------------------------------------------------------------- #
# genetic evolution: gates + flow
# --------------------------------------------------------------------------- #

def test_evolver_gate_refuses_community(tmp_path):
    drive = _drive(tmp_path)
    skill = types.SimpleNamespace(name="comm", is_self_authored=False)
    assert ge.SkillEvolver.is_evolution_candidate(
        skill, {"execution_count": 20, "success_rate": 0.4}) is False


def test_evolver_gate_counts_and_rate(tmp_path):
    drive = _drive(tmp_path)
    skill = types.SimpleNamespace(name="mine", is_self_authored=True)
    evolver = ge.SkillEvolver(drive)
    assert evolver.is_evolution_candidate(skill, {"execution_count": 9, "success_rate": 0.4}) is False
    assert evolver.is_evolution_candidate(skill, {"execution_count": 12, "success_rate": 0.9}) is False
    assert evolver.is_evolution_candidate(skill, {"execution_count": 12, "success_rate": 0.6}) is True


def test_evolver_accept_path(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.5833, "evolution_version": 1}})
    for i in range(4):
        _write_tool_row(drive, "tE", "skill_exec", True, args={"skill": "demo-fix"})
    improved = {
        "name": "demo-fix", "description": "with retries", "type": "script",
        "runtime": "python", "scripts": [{"name": "main.py", "code": "import time\ntime.sleep(0.1)\nprint('retry ok')\n"}],
        "tags": ["seed"],
    }
    responses = [
        {"suggestions": ["add retry logic"]},   # failure analysis
        improved,                                # suggestion-driven mutation
        "not json", "not json", "not json",      # strategy mutations fail
        {"fitness": 0.85},                       # single variant fitness
    ]
    _fake_llm(monkeypatch, responses)
    skills = _discovered(drive)
    stats = st.SkillStatsLedger(drive).load()
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(skills, stats)
    assert len(records) == 1
    assert records[0]["accepted"] is True
    assert records[0]["old_success_rate"] == pytest.approx(0.5833)
    assert records[0]["new_success_rate"] == pytest.approx(0.85)
    # version bumped + payload replaced on disk
    text = (drive / "skills" / "self" / "demo-fix" / "SKILL.md").read_text(encoding="utf-8")
    assert parse_skill_manifest_text(text).version == "1.1"
    code = (drive / "skills" / "self" / "demo-fix" / "scripts" / "main.py").read_text(encoding="utf-8")
    assert "retry" in code
    # ledger evolution_version bumped
    assert st.SkillStatsLedger(drive).get("demo-fix")["evolution_version"] == 2
    # provenance survives the rewrite
    from ouroboros.skill_loader import is_self_authored_skill_dir
    assert is_self_authored_skill_dir(drive / "skills" / "self" / "demo-fix", drive_root=drive) is True


def test_evolver_reject_path(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original_code = "print('original')\n"
    _seed_skill(drive, "demo-fix", code=original_code)
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.6, "evolution_version": 1}})
    responses = [
        {"suggestions": ["add retry logic"]},
        {"name": "demo-fix", "description": "v", "type": "script",
         "scripts": [{"name": "main.py", "code": "print('variant')\n"}]},
        "not json", "not json", "not json",
        {"fitness": 0.55},  # below baseline 0.6 -> reject
    ]
    _fake_llm(monkeypatch, responses)
    skills = _discovered(drive)
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(skills, st.SkillStatsLedger(drive).load())
    assert records[0]["accepted"] is False
    assert records[0]["reason"] == "no_better_variant"
    # old package untouched
    text = (drive / "skills" / "self" / "demo-fix" / "SKILL.md").read_text(encoding="utf-8")
    assert parse_skill_manifest_text(text).version == "1.0"
    assert (drive / "skills" / "self" / "demo-fix" / "scripts" / "main.py").read_text(encoding="utf-8") == original_code
    assert st.SkillStatsLedger(drive).get("demo-fix")["evolution_version"] == 1


def test_evolver_no_llm_keeps_original(tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix", version="2.0")
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 5, "success_rate": 0.42, "evolution_version": 1}})
    skills = _discovered(drive)
    records = ge.SkillEvolver(drive, llm_client=None).evolve_candidates(skills, st.SkillStatsLedger(drive).load())
    assert records[0]["accepted"] is False
    text = (drive / "skills" / "self" / "demo-fix" / "SKILL.md").read_text(encoding="utf-8")
    assert parse_skill_manifest_text(text).version == "2.0"


def test_evolver_candidates_capped_and_sorted(tmp_path):
    drive = _drive(tmp_path)
    for name, version in (("a-fix", "1.0"), ("b-fix", "1.0"), ("c-fix", "1.0")):
        _seed_skill(drive, name, version=version)
    _write_stats(drive, {
        "a-fix": {"execution_count": 12, "success_rate": 0.5, "evolution_version": 1},
        "b-fix": {"execution_count": 12, "success_rate": 0.7, "evolution_version": 1},
        "c-fix": {"execution_count": 12, "success_rate": 0.6, "evolution_version": 1},
        "newbie": {"execution_count": 3, "success_rate": 0.9, "evolution_version": 1},
    })
    skills = _discovered(drive)
    records = ge.SkillEvolver(drive, llm_client=None).evolve_candidates(skills, st.SkillStatsLedger(drive).load())
    names = [r["skill"] for r in records]
    assert names == ["a-fix", "c-fix"]  # worst two rates, capped at 2; newbie under-gated


# --------------------------------------------------------------------------- #
# nudge
# --------------------------------------------------------------------------- #

def test_nudge_due_first_run(tmp_path):
    drive = _drive(tmp_path)
    assert nud.SkillNudgeEngine(drive).is_due() is True


def test_nudge_cadence(tmp_path):
    from datetime import datetime, timezone
    drive = _drive(tmp_path)
    engine = nud.SkillNudgeEngine(drive)
    fresh_epoch = 1_788_000_000.0  # 2026-08-28 (UTC)
    fresh_ts = datetime.fromtimestamp(fresh_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_ts = datetime.fromtimestamp(fresh_epoch - 100_000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with (drive / "state" / "skill_nudges.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": old_ts, "analysis": {}}) + "\n")
    # The LAST row is the watermark: old_ts here, so *any* now later than it
    # by >= 1h is due — use a now 30 min after old_ts (not due from fresh).
    assert engine.is_due(now=fresh_epoch - 100_000 + 1800) is False
    assert engine.is_due(now=fresh_epoch - 100_000 + 7200) is True
    # Append a fresh watermark; a few seconds later it is NOT due.
    with (drive / "state" / "skill_nudges.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": fresh_ts, "analysis": {}}) + "\n")
    assert engine.is_due(now=fresh_epoch + 60) is False
    assert engine.is_due(now=fresh_epoch + 7200) is True
    with (drive / "state" / "skill_nudges.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "garbage", "analysis": {}}) + "\n")
    assert engine.is_due(now=fresh_epoch) is True  # unparsable -> due


def test_nudge_analyze_recent(tmp_path):
    drive = _drive(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "taskA", "Terminal", False)
    _write_tool_row(drive, "taskB", "skill_exec", True, args={"skill": "alpha"})
    _write_tool_row(drive, "taskB", "skill_exec", False, args={"skill": "alpha"})
    _write_tool_row(drive, "taskC", "skill_exec", True, args={"skill": "beta"})
    _write_tool_row(drive, "taskC", "Read", True)  # last row error -> C not reusable
    analysis = nud.SkillNudgeEngine(drive).analyze_recent()
    assert analysis["failed_skills"] == ["alpha", "beta"]
    assert analysis["best_reusable_task"] == {"task_id": "taskA", "tool_calls": 6}


def test_nudge_record_writes(tmp_path):
    drive = _drive(tmp_path)
    engine = nud.SkillNudgeEngine(drive)
    engine.record({"failed_skills": [], "task_count": 0})
    assert (drive / "state" / "skill_nudges.jsonl").exists()
    assert engine.is_due() is False


# --------------------------------------------------------------------------- #
# router quality scoring
# --------------------------------------------------------------------------- #

def _fake_skill(name, *, self_authored=False, stats=None, tags=None, desc=""):
    manifest = types.SimpleNamespace(
        raw_extra={"tags": tags or []}, description=desc, when_to_use="", body="")
    skill = types.SimpleNamespace(
        name=name, manifest=manifest, is_self_authored=self_authored)
    # attach the ledger shape the router sets in _load_skills
    stats = dict(stats or {})
    setattr(skill, "skill_stats", stats)
    return skill


def test_router_quality_increments_self_authored(tmp_path):
    drive = _drive(tmp_path)
    router = SmartRouter(drive_root=drive, tool_registry=set())
    skill = _fake_skill("mine", self_authored=True,
                        stats={"success_rate": 0.9, "evolution_version": 3})
    score = router._calculate_skill_score(skill, set())
    # 0.5 base + 0.1 self-authored + 0.1 high-rate + 0.05*(3-1) = 0.8
    assert score == pytest.approx(0.8)


def test_router_no_quality_for_community(tmp_path):
    drive = _drive(tmp_path)
    router = SmartRouter(drive_root=drive, tool_registry=set())
    skill = _fake_skill("comm", self_authored=False,
                        stats={"success_rate": 0.99, "evolution_version": 9})
    assert router._calculate_skill_score(skill, set()) == pytest.approx(0.5)


def test_router_no_stats_no_boost(tmp_path):
    drive = _drive(tmp_path)
    router = SmartRouter(drive_root=drive, tool_registry=set())
    skill = _fake_skill("mine", self_authored=True, stats={})
    assert router._calculate_skill_score(skill, set()) == pytest.approx(0.6)  # 0.5 + 0.1


def test_router_demote_beats_full_quality_stack(tmp_path):
    from ouroboros.smart_router import SKILL_TAG_MAPPING
    drive = _drive(tmp_path)
    router = SmartRouter(drive_root=drive, tool_registry=set())
    skill = _fake_skill(
        "hot", self_authored=True, stats={"success_rate": 0.95, "evolution_version": 6},
        tags=["coding"], desc="coding python shell build git debug")
    # Direct invariant: the full positive stack caps at 1.0; demote -0.5
    # pushes it to 0.5 < 0.6, so the skill drops out of recommendations.
    score = router._calculate_skill_score(skill, set(SKILL_TAG_MAPPING["coding"]))
    assert score == pytest.approx(1.0)
    assert score - 0.5 == pytest.approx(0.5)
    assert score - 0.5 < 0.6


def test_router_load_skills_attaches_stats(tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "log-bouncer")
    _write_stats(drive, {"log-bouncer": {"success_rate": 0.85, "evolution_version": 2}})
    router = SmartRouter(drive_root=drive, tool_registry=set())
    skills = router._load_skills()
    found = [s for s in skills if s.name == "log-bouncer"]
    assert found and found[0].skill_stats["success_rate"] == 0.85
    assert found[0].skill_stats["evolution_version"] == 2


# --------------------------------------------------------------------------- #
# pipeline + maybe_promote wiring
# --------------------------------------------------------------------------- #

def test_pipeline_full_flow(monkeypatch, tmp_path):
    drive, env = _promote_env(tmp_path)
    for i in range(6):
        _write_tool_row(drive, "t1", "Terminal", False)
    _write_tool_row(drive, "t1", "Bash", True)
    _write_tool_row(drive, "t1", "Bash", False)
    _write_tool_row(drive, "t1", "skill_exec", False, args={"skill": "old-skill"})
    _fake_llm(monkeypatch, [{
        "name": "sync-logs", "description": "syncs logs", "type": "script",
        "scripts": [{"name": "main.py", "code": "print('sync')\n"}],
        "tags": ["sync"],
    }])
    from ouroboros.skill_evolution.pipeline import run_skill_evolution_step
    run_skill_evolution_step(
        env, {"id": "t1", "type": "task", "text": "sync the logs"},
        {"goal": "sync the logs", "outcome": "success"}, llm_client=object())
    assert (drive / "skills" / "self" / "sync-logs" / "SKILL.md").exists()
    assert (drive / "state" / "skill_stats.json").exists()
    # first nudge is due -> recorded
    assert (drive / "state" / "skill_nudges.jsonl").exists()


def test_maybe_promote_switch_off_zero_calls(monkeypatch, tmp_path):
    drive, env = _promote_env(tmp_path)
    monkeypatch.setenv("OUROBOROS_POST_TASK_EVOLUTION", "true")
    monkeypatch.delenv("OUROBOROS_SKILL_EVOLUTION", raising=False)
    calls = []
    monkeypatch.setattr(
        "ouroboros.skill_evolution.pipeline.run_skill_evolution_step",
        lambda *a, **k: calls.append(a))
    captured = _fake_llm(monkeypatch, [{"promote": False, "objective": ""}])
    from ouroboros.post_task_evolution import maybe_promote
    result = maybe_promote(env, {"id": "t1", "type": "task", "text": "x"}, None, llm_client=object())
    assert result is None
    assert calls == []
    assert captured["calls"][0]["call_type"] == "post_task_evolution_decision"


def test_maybe_promote_switch_on_calls_pipeline(monkeypatch, tmp_path):
    drive, env = _promote_env(tmp_path)
    monkeypatch.setenv("OUROBOROS_POST_TASK_EVOLUTION", "true")
    monkeypatch.setenv("OUROBOROS_SKILL_EVOLUTION", "true")
    calls = []
    monkeypatch.setattr(
        "ouroboros.skill_evolution.pipeline.run_skill_evolution_step",
        lambda *a, **k: calls.append(a))
    _fake_llm(monkeypatch, [{"promote": False, "objective": ""}])
    from ouroboros.post_task_evolution import maybe_promote
    maybe_promote(env, {"id": "t1", "type": "task", "text": "x"}, None, llm_client=object())
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# review-feedback loop + pre-overwrite backup (2026-09-03 hardening)
# --------------------------------------------------------------------------- #

def _seed_review_finding(drive, name, item="network-egress", status="blockers"):
    state_dir = drive / "state" / "skills" / name
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "review.json").write_text(json.dumps({
        "status": status,
        "findings": [{
            "item": item, "verdict": "FAIL", "severity": "high",
            "reason": f"{item}: skill payload calls external endpoints",
        }],
        "reviewer_models": ["reviewer-one"],
        "timestamp": "2026-09-03T00:00:00Z",
    }), encoding="utf-8")


def test_recent_review_flags_empty(tmp_path):
    drive = _drive(tmp_path)
    assert ag.recent_review_flags(drive) == []
    assert ag.recent_review_flags(drive, skill_name="demo-fix") == []


def test_recent_review_flags_global_scan(tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "other-skill")
    _seed_review_finding(drive, "other-skill")
    flags = ag.recent_review_flags(drive)
    assert any("network-egress" in flag for flag in flags)
    # clean verdicts contribute nothing
    _seed_review_finding(drive, "other-skill", item="clean-item", status="clean")
    flags = ag.recent_review_flags(drive)
    assert not any("clean-item" in flag for flag in flags)


def test_generation_prompt_includes_review_flags(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "other-skill")
    _seed_review_finding(drive, "other-skill")
    for i in range(6):
        _write_tool_row(drive, "t9", "Terminal", False)
    _write_tool_row(drive, "t9", "Bash", True)
    _write_tool_row(drive, "t9", "Bash", False)
    captured = _fake_llm(monkeypatch, [{
        "name": "log-bouncer", "description": "b", "type": "script",
        "scripts": [{"name": "main.py", "code": "print(1)\n"}],
    }])
    ag.SkillAutoGenerator(drive, llm_client=object()).maybe_generate_for_task("t9")
    prompt = captured["calls"][0]["messages"][0]["content"]
    assert "Reviewer flags to avoid" in prompt
    assert "network-egress" in prompt


def test_evolver_review_flags_in_analysis_prompt(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    _seed_review_finding(drive, "demo-fix", item="os-shell-injection")
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.5833, "evolution_version": 1}})
    for i in range(4):
        _write_tool_row(drive, "tE", "skill_exec", True, args={"skill": "demo-fix"})
    captured = _fake_llm(monkeypatch, [
        {"suggestions": ["add retry logic"]},
        {"name": "demo-fix", "description": "v", "type": "script",
         "scripts": [{"name": "main.py", "code": "print('v')\n"}]},
        "not json", "not json", "not json",
        {"fitness": 0.7},
    ])
    skills = _discovered(drive)
    ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(skills, st.SkillStatsLedger(drive).load())
    analysis_prompt = captured["calls"][0]["messages"][0]["content"]
    assert "Recent reviewer findings for THIS skill" in analysis_prompt
    assert "os-shell-injection" in analysis_prompt
    # fitness prompt also carries the flags (repeat-of-flags must score low)
    fitness_prompt = captured["calls"][-1]["messages"][0]["content"]
    assert "os-shell-injection" in fitness_prompt


def test_evolver_backup_before_overwrite(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    old_code = "print('original')\n"
    _seed_skill(drive, "demo-fix", code=old_code)
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.5833, "evolution_version": 1}})
    for i in range(4):
        _write_tool_row(drive, "tE", "skill_exec", True, args={"skill": "demo-fix"})
    responses = [
        {"suggestions": ["add retry logic"]},
        {"name": "demo-fix", "description": "with retries", "type": "script",
         "scripts": [{"name": "main.py", "code": "print('new version')\n"}]},
        "not json", "not json", "not json",
        {"fitness": 0.9},
    ]
    _fake_llm(monkeypatch, responses)
    skills = _discovered(drive)
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(skills, st.SkillStatsLedger(drive).load())
    assert records[0]["accepted"] is True
    assert records[0]["backup_dir"]
    backup = pathlib.Path(records[0]["backup_dir"])
    assert backup.is_dir()
    assert "replaced-" in backup.name
    # the pre-overwrite payload is preserved verbatim in the backup
    assert (backup / "scripts" / "main.py").read_text(encoding="utf-8") == old_code
    assert (backup / "SKILL.md").exists()
    # the backup is invisible to discovery (orphan convention)
    names = [s.name for s in _discovered(drive)]
    assert names == ["demo-fix"]


# --------------------------------------------------------------------------- #
# auto-rollback: evolved version fails re-review -> restore from backup
# --------------------------------------------------------------------------- #

def _accept_and_seed_blockers_review(monkeypatch, drive, old_code="print('original')\n"):
    """Evolve demo-fix (accept), then write a blockers verdict bound to the
    NEW payload hash — the condition the auto-rollback reacts to."""
    _seed_skill(drive, "demo-fix", code=old_code)
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.5833, "evolution_version": 1}})
    for i in range(4):
        _write_tool_row(drive, "tE", "skill_exec", True, args={"skill": "demo-fix"})
    responses = [
        {"suggestions": ["add retry logic"]},
        {"name": "demo-fix", "description": "with retries", "type": "script",
         "scripts": [{"name": "main.py", "code": "print('new version')\n"}]},
        "not json", "not json", "not json",
        {"fitness": 0.9},
    ]
    _fake_llm(monkeypatch, responses)
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(
        _discovered(drive), st.SkillStatsLedger(drive).load())
    assert records[0]["accepted"] is True
    from ouroboros.skill_loader import compute_content_hash

    live = drive / "skills" / "self" / "demo-fix"
    state_dir = drive / "state" / "skills" / "demo-fix"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "review.json").write_text(json.dumps({
        "status": "blockers",
        "content_hash": compute_content_hash(live),
        "findings": [{"item": "network-egress", "verdict": "FAIL"}],
        "timestamp": "2026-09-03T01:00:00Z",
    }), encoding="utf-8")
    return live


def test_auto_rollback_triggers_on_blockers(monkeypatch, tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    drive = _drive(tmp_path)
    old_code = "print('original')\n"
    _accept_and_seed_blockers_review(monkeypatch, drive, old_code=old_code)
    backups_before = list((drive / "skills" / "self").glob("*.replaced-*"))
    assert len(backups_before) == 1
    records = rollback_failed_evolutions(drive)
    assert len(records) == 1
    assert records[0]["action"] == "rolled_back"
    assert records[0]["reason"] == "review_blockers"
    live = drive / "skills" / "self" / "demo-fix"
    # payload restored to the pre-overwrite version
    assert (live / "scripts" / "main.py").read_text(encoding="utf-8") == old_code
    text = (live / "SKILL.md").read_text(encoding="utf-8")
    assert parse_skill_manifest_text(text).version == "1.0"
    # backup consumed, discovery clean, provenance intact
    assert list((drive / "skills" / "self").glob("*.replaced-*")) == []
    assert [s.name for s in _discovered(drive)] == ["demo-fix"]
    from ouroboros.skill_loader import is_self_authored_skill_dir
    assert is_self_authored_skill_dir(live, drive_root=drive) is True
    # history carries the rollback
    history = [json.loads(l) for l in (drive / "state" / "skill_evolution_history.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert history[-1]["action"] == "rolled_back"


def test_auto_rollback_hash_mismatch_noop(monkeypatch, tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    drive = _drive(tmp_path)
    live = _accept_and_seed_blockers_review(monkeypatch, drive)
    # re-point the verdict at a DIFFERENT hash (stale verdict for an old payload)
    (drive / "state" / "skills" / "demo-fix" / "review.json").write_text(json.dumps({
        "status": "blockers", "content_hash": "not-the-current-hash",
        "findings": [], "timestamp": "2026-09-03T01:00:00Z"}), encoding="utf-8")
    assert rollback_failed_evolutions(drive) == []
    assert list((drive / "skills" / "self").glob("*.replaced-*"))  # backup kept
    assert (live / "scripts" / "main.py").read_text(encoding="utf-8") == "print('new version')\n"


def test_auto_rollback_clean_verdict_noop(monkeypatch, tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    drive = _drive(tmp_path)
    live = _accept_and_seed_blockers_review(monkeypatch, drive)
    (drive / "state" / "skills" / "demo-fix" / "review.json").write_text(json.dumps({
        "status": "clean", "content_hash": "whatever",
        "findings": [], "timestamp": "2026-09-03T01:00:00Z"}), encoding="utf-8")
    assert rollback_failed_evolutions(drive) == []
    assert (live / "scripts" / "main.py").read_text(encoding="utf-8") == "print('new version')\n"


def test_auto_rollback_no_backups_noop(tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    assert rollback_failed_evolutions(drive) == []


def test_evolver_skips_rolled_back_skill(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 5, "success_rate": 0.42, "evolution_version": 1}})
    # a recent auto-rollback record puts the skill in cooldown
    from ouroboros.utils import utc_now_iso
    with (drive / "state" / "skill_evolution_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": utc_now_iso(), "action": "rolled_back", "skill": "demo-fix",
            "reason": "review_blockers"}) + "\n")
    captured = _fake_llm(monkeypatch, [])
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(
        _discovered(drive), st.SkillStatsLedger(drive).load())
    assert records == []
    assert captured["calls"] == []


def test_pipeline_rolls_back_before_evolve(monkeypatch, tmp_path):
    drive, env = _promote_env(tmp_path)
    old_code = "print('original')\n"
    _accept_and_seed_blockers_review(monkeypatch, drive, old_code=old_code)
    captured = _fake_llm(monkeypatch, [])
    from ouroboros.skill_evolution.pipeline import run_skill_evolution_step
    run_skill_evolution_step(
        env, {"id": "t1", "type": "task", "text": "x"},
        {"goal": "x", "outcome": "success"}, llm_client=object())
    live = drive / "skills" / "self" / "demo-fix"
    assert (live / "scripts" / "main.py").read_text(encoding="utf-8") == old_code
    # the cooldown also suppressed re-evolution in the same run (no LLM calls)
    assert captured["calls"] == []


# --------------------------------------------------------------------------- #
# A1: hash -> executable-verdict index (rollback restores executability)
# --------------------------------------------------------------------------- #

def test_verdict_for_hash_current_review(tmp_path):
    from ouroboros.skill_review_history import verdict_for_hash
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    from ouroboros.skill_loader import compute_content_hash
    current_hash = compute_content_hash(drive / "skills" / "self" / "demo-fix")
    _seed_review_finding(drive, "demo-fix", status="clean")
    # rewrite with a matching content_hash (the helper seeds without one)
    review_path = drive / "state" / "skills" / "demo-fix" / "review.json"
    data = json.loads(review_path.read_text(encoding="utf-8"))
    data["content_hash"] = current_hash
    review_path.write_text(json.dumps(data), encoding="utf-8")
    verdict = verdict_for_hash(drive, "demo-fix", current_hash)
    assert verdict is not None and verdict["status"] == "clean"
    assert verdict["content_hash"] == current_hash


def test_verdict_for_hash_history_row(tmp_path):
    from ouroboros.skill_review_history import verdict_for_hash
    drive = _drive(tmp_path)
    state_dir = drive / "state" / "skills" / "demo-fix"
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "review_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-09-01T00:00:00Z", "status": "blockers",
                             "content_hash": "h-old"}) + "\n")
        fh.write(json.dumps({"ts": "2026-09-02T00:00:00Z", "status": "clean",
                             "content_hash": "h-old", "reviewer_models": ["m1"]}) + "\n")
    verdict = verdict_for_hash(drive, "demo-fix", "h-old")
    assert verdict is not None and verdict["status"] == "clean"
    assert verdict["reviewer_models"] == ["m1"]


def test_verdict_for_hash_none(tmp_path):
    from ouroboros.skill_review_history import verdict_for_hash
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    _seed_review_finding(drive, "demo-fix", status="blockers")
    assert verdict_for_hash(drive, "demo-fix", "no-such-hash") is None
    assert verdict_for_hash(drive, "demo-fix", "") is None


def test_rollback_restores_executable_verdict(monkeypatch, tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    from ouroboros.skill_loader import compute_content_hash, review_status_allows_execution
    drive = _drive(tmp_path)
    old_code = "print('original')\n"
    _accept_and_seed_blockers_review(monkeypatch, drive, old_code=old_code)
    state_dir = drive / "state" / "skills" / "demo-fix"
    # historical CLEAN verdict bound to the PRE-EVOLUTION bytes (the backup —
    # incl. its provenance marker, which participates in the content hash)
    backups = list((drive / "skills" / "self").glob("*.replaced-*"))
    assert len(backups) == 1
    old_hash = compute_content_hash(backups[0])
    with (state_dir / "review_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-09-01T00:00:00Z", "status": "clean",
                             "content_hash": old_hash,
                             "reviewer_models": ["r1"]}) + "\n")
    records = rollback_failed_evolutions(drive)
    assert len(records) == 1
    assert records[0]["restored_verdict"] == "clean"
    # review.json was re-applied to the restored hash -> executable again
    live = drive / "skills" / "self" / "demo-fix"
    review = json.loads((state_dir / "review.json").read_text(encoding="utf-8"))
    assert review["status"] == "clean"
    assert review["content_hash"] == compute_content_hash(live) == old_hash
    assert review_status_allows_execution(review["status"]) is True
    # provenance survived the full restore (marker + state marker in sync)
    from ouroboros.skill_loader import is_self_authored_skill_dir
    assert is_self_authored_skill_dir(live, drive_root=drive) is True


def test_rollback_no_verdict_stays_stale(monkeypatch, tmp_path):
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    drive = _drive(tmp_path)
    _accept_and_seed_blockers_review(monkeypatch, drive)  # no clean history row
    records = rollback_failed_evolutions(drive)
    assert records[0]["restored_verdict"] == ""
    review = json.loads((drive / "state" / "skills" / "demo-fix" / "review.json").read_text(encoding="utf-8"))
    assert review["status"] == "blockers"  # unchanged: normal re-review applies


# --------------------------------------------------------------------------- #
# A2: skills-needing-review visibility section
# --------------------------------------------------------------------------- #

def test_review_needs_section_gated_by_switch(monkeypatch, tmp_path):
    from ouroboros.context import _build_skills_needing_review_section
    drive = _drive(tmp_path)
    _seed_skill(drive, "pending-skill")  # no review state -> pending
    env = types.SimpleNamespace(drive_root=drive)
    monkeypatch.delenv("OUROBOROS_SKILL_EVOLUTION", raising=False)
    assert _build_skills_needing_review_section(env) == ""
    monkeypatch.setenv("OUROBOROS_SKILL_EVOLUTION", "true")
    section = _build_skills_needing_review_section(env)
    assert "pending-skill" in section
    assert "pending review" in section


def test_review_needs_section_blockers_shows_finding(monkeypatch, tmp_path):
    from ouroboros.context import _build_skills_needing_review_section
    drive = _drive(tmp_path)
    _seed_skill(drive, "bad-skill")
    _seed_review_finding(drive, "bad-skill", item="network-egress")
    monkeypatch.setenv("OUROBOROS_SKILL_EVOLUTION", "true")
    section = _build_skills_needing_review_section(
        types.SimpleNamespace(drive_root=drive))
    assert "bad-skill" in section
    assert "blocked by review" in section
    assert "network-egress" in section


def test_review_needs_section_skips_executable(monkeypatch, tmp_path):
    from ouroboros.context import _build_skills_needing_review_section
    from ouroboros.skill_loader import compute_content_hash
    drive = _drive(tmp_path)
    _seed_skill(drive, "good-skill")
    state_dir = drive / "state" / "skills" / "good-skill"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "review.json").write_text(json.dumps({
        "status": "clean",
        "content_hash": compute_content_hash(drive / "skills" / "self" / "good-skill"),
        "findings": [], "timestamp": "2026-09-03T00:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setenv("OUROBOROS_SKILL_EVOLUTION", "true")
    section = _build_skills_needing_review_section(
        types.SimpleNamespace(drive_root=drive))
    assert "good-skill" not in (section or "")


# --------------------------------------------------------------------------- #
# B1: population dedupe
# --------------------------------------------------------------------------- #

def test_population_dedupe_identical_variants(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original = {
        "name": "demo-fix", "description": "d", "type": "script",
        "runtime": "python", "scripts": [{"name": "main.py", "code": "print(1)\n"}],
    }
    same_variant = {
        "name": "demo-fix", "description": "d", "type": "script",
        "runtime": "python", "scripts": [{"name": "main.py", "code": "print(2)\n"}],
    }
    _fake_llm(monkeypatch, [same_variant, same_variant, same_variant])
    evolver = ge.SkillEvolver(drive, llm_client=object())
    variants = evolver._build_population(original, ["s1", "s2"], [])
    # original + exactly ONE copy of the (identical-to-each-other) variant
    assert len(variants) == 2
    assert [v.get("_mutation") for v in variants[1:]] == ["suggested"]


# --------------------------------------------------------------------------- #
# B2: reflective mutation (real failure traces in the prompt)
# --------------------------------------------------------------------------- #

def test_mutation_prompt_includes_failure_traces(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original = {"name": "demo-fix", "description": "d", "type": "script",
                "scripts": [{"name": "main.py", "code": "print(1)\n"}]}
    captured = _fake_llm(monkeypatch, [{"name": "demo-fix", "type": "script",
                                        "scripts": [{"name": "main.py", "code": "print(2)\n"}]}])
    evolver = ge.SkillEvolver(drive, llm_client=object())
    evolver._mutate(original, prompt_kind="strategy", strategy="add_error_handling",
                    failures=[{"status": "error", "result": "tarfile: file not found"}])
    prompt = captured["calls"][0]["messages"][0]["content"]
    assert "Recent failing executions" in prompt
    assert "tarfile: file not found" in prompt
    assert "MUST" in prompt


def test_mutation_prompt_no_failures_fallback(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original = {"name": "demo-fix", "description": "d", "type": "script",
                "scripts": [{"name": "main.py", "code": "print(1)\n"}]}
    captured = _fake_llm(monkeypatch, [{"name": "demo-fix", "type": "script",
                                        "scripts": [{"name": "main.py", "code": "print(2)\n"}]}])
    evolver = ge.SkillEvolver(drive, llm_client=object())
    evolver._mutate(original, prompt_kind="strategy", strategy="improve_description",
                    failures=None)
    prompt = captured["calls"][0]["messages"][0]["content"]
    assert "Recent failing executions" not in prompt


# --------------------------------------------------------------------------- #
# B3: multi-case evaluation
# --------------------------------------------------------------------------- #

def test_evaluate_multi_case_mean(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original = {"name": "demo-fix", "description": "d", "type": "script",
                "scripts": [{"name": "main.py", "code": "print(1)\n"}]}
    cases = [
        {"kind": "success", "result": "compressed ok"},
        {"kind": "failure", "result": "timeout"},
        {"kind": "failure", "result": "file not found"},
    ]
    _fake_llm(monkeypatch, [{"case_scores": [0.9, 0.5, 0.7]}])
    evolver = ge.SkillEvolver(drive, llm_client=object())
    fitness = evolver._evaluate(dict(original), original,
                                {"execution_count": 12, "success_rate": 0.6}, cases)
    assert fitness == pytest.approx(0.7)


def test_evaluate_case_limit_and_degrade(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    original = {"name": "demo-fix", "description": "d", "type": "script",
                "scripts": [{"name": "main.py", "code": "print(1)\n"}]}
    evolver = ge.SkillEvolver(drive, llm_client=object())
    # the cap lives in _build_eval_cases (10 failure rows -> at most 5 cases)
    cases = evolver._build_eval_cases(
        [], [{"kind": "failure", "result": f"error {i}"} for i in range(10)])
    assert len(cases) == 5
    captured = _fake_llm(monkeypatch, [{"case_scores": [0.1] * 5}])
    evolver._evaluate(dict(original), original, {"execution_count": 10, "success_rate": 0.4}, cases)
    prompt = captured["calls"][0]["messages"][0]["content"]
    assert prompt.count("[failure]") == 5  # capped at MAX_EVAL_CASES=5
    # degraded responses: fallback to fitness, then 0.0
    _fake_llm(monkeypatch, [{"fitness": 0.6}])
    assert evolver._evaluate(dict(original), original, {}, [{"kind": "success", "result": "x"}]) == pytest.approx(0.6)
    _fake_llm(monkeypatch, ["garbage"])
    assert evolver._evaluate(dict(original), original, {}, [{"kind": "success", "result": "x"}]) == 0.0


# --------------------------------------------------------------------------- #
# B4: holdout calibration (evaluated vs realized)
# --------------------------------------------------------------------------- #

def test_calibration_discount_triggered(tmp_path):
    drive = _drive(tmp_path)
    now = "2026-09-03T08:00:00Z"
    with (drive / "state" / "skill_evolution_history.jsonl").open("a", encoding="utf-8") as fh:
        for _ in range(3):
            fh.write(json.dumps({"ts": now, "skill": "demo-fix", "accepted": True,
                                 "new_success_rate": 0.9}) + "\n")
    evolver = ge.SkillEvolver(drive)
    assert evolver._fitness_discount("demo-fix", {"success_rate": 0.5}) == pytest.approx(0.9)
    # under the optimism threshold -> no discount (realized close to evaluated)
    with (drive / "state" / "skill_evolution_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now, "skill": "demo-fix", "accepted": True,
                             "new_success_rate": 0.55}) + "\n")
    evolver2 = ge.SkillEvolver(drive)
    assert evolver2._fitness_discount("demo-fix", {"success_rate": 0.75}) == pytest.approx(1.0)


def test_calibration_no_history_no_discount(tmp_path):
    drive = _drive(tmp_path)
    assert ge.SkillEvolver(drive)._fitness_discount("demo-fix", {"success_rate": 0.5}) == 1.0


def test_evolver_record_carries_fitness_discount(monkeypatch, tmp_path):
    drive = _drive(tmp_path)
    _seed_skill(drive, "demo-fix")
    _write_stats(drive, {"demo-fix": {
        "execution_count": 12, "success_count": 7, "success_rate": 0.5833, "evolution_version": 1}})
    for i in range(4):
        _write_tool_row(drive, "tE", "skill_exec", False, args={"skill": "demo-fix"})
    _fake_llm(monkeypatch, [{"suggestions": ["add retry logic"]},
                            {"name": "demo-fix", "description": "v", "type": "script",
                             "scripts": [{"name": "main.py", "code": "print('v')\n"}]},
                            "not json", "not json", "not json",
                            {"case_scores": [0.5, 0.5]}])
    skills = _discovered(drive)
    records = ge.SkillEvolver(drive, llm_client=object()).evolve_candidates(
        skills, st.SkillStatsLedger(drive).load())
    # 0.5 mean < baseline 0.5833 -> reject, discount recorded as 1.0 (no accepts yet)
    assert records[0]["accepted"] is False
    assert records[0]["fitness_discount"] == 1.0