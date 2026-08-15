"""Tests for the harness tree (PAPER_INTEGRATION_ANALYSIS 不足 3).

Covers: branch config loading (system prompt extra / memory config / skill
preferences), branch selection with main fallback, the tool-set *reference*
(nothing duplicated from the smart router), the skill-preference bias applied
inside SmartRouter.route, and the end-to-end agent wiring (branch rides on the
ToolContext and its system-prompt extra reaches the built messages).
"""

import json
import pathlib

import pytest

from ouroboros.harness_tree import HarnessTree
from ouroboros.smart_router import (
    TASK_TYPE_CODING,
    TASK_TYPE_SIMPLE,
    SmartRouter,
)


def _write_branch(
    config_dir: pathlib.Path,
    name: str,
    *,
    prompt_extra: str = "",
    memory_config: dict | None = None,
    skill_preferences: dict | None = None,
) -> pathlib.Path:
    branch_dir = config_dir / name
    branch_dir.mkdir(parents=True, exist_ok=True)
    if prompt_extra:
        (branch_dir / "system_prompt_extra.md").write_text(prompt_extra, encoding="utf-8")
    if memory_config is not None:
        (branch_dir / "memory_config.json").write_text(
            json.dumps(memory_config), encoding="utf-8")
    if skill_preferences is not None:
        (branch_dir / "skill_preferences.json").write_text(
            json.dumps(skill_preferences), encoding="utf-8")
    return branch_dir


def _config_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "harness_configs"


def _write_skill(drive: pathlib.Path, name: str, tags: str) -> pathlib.Path:
    skill_dir = drive / "skills" / "external" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name} helper\n"
        "version: 0.1.0\n"
        "type: instruction\n"
        f"tags: [{tags}]\n"
        "---\n# body\n",
        encoding="utf-8",
    )
    return skill_dir


def _write_self_authored_skill(drive: pathlib.Path, name: str, tags: str) -> pathlib.Path:
    """A real self-authored skill: dual provenance markers (skill-dir marker +
    drive state marker) with matching task_id/created_at, as the loader
    validates."""
    skill_dir = drive / "skills" / "self_authored" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name} helper\n"
        "version: 0.1.0\n"
        "type: instruction\n"
        f"tags: [{tags}]\n"
        "---\n# body\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": 1,
        "origin": "self_authored",
        "task_id": f"TASK-{name}",
        "created_at": "2026-01-01T00:00:00Z",
    }
    (skill_dir / ".self_authored.json").write_text(json.dumps(payload), encoding="utf-8")
    state_marker = drive / "state" / "skills" / name / "self_authored.json"
    state_marker.parent.mkdir(parents=True, exist_ok=True)
    state_marker.write_text(json.dumps(payload), encoding="utf-8")
    return skill_dir


@pytest.fixture(autouse=True)
def _clear_router_skills_cache():
    SmartRouter.invalidate_skills_cache()
    yield
    SmartRouter.invalidate_skills_cache()


# ---------------------------------------------------------------------------
# Config loading + selection
# ---------------------------------------------------------------------------


def test_select_branch_returns_dedicated_branch(tmp_path):
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", prompt_extra="## Coding\nfocus", memory_config={"exclude": ["dialogue"]}, skill_preferences={"boost": {"x": 0.2}})
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.name == "coding"
    assert branch.task_type == TASK_TYPE_CODING
    assert "## Coding" in branch.system_prompt_extra
    assert branch.memory_config.exclude == ["dialogue"]
    assert branch.skill_preferences.boost == {"x": 0.2}


def test_select_branch_falls_back_to_main(tmp_path):
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", prompt_extra="## Coding\nfocus")
    tree = HarnessTree(cfg)
    # A task type without a dedicated branch lands on `main`.
    missing = tree.select_branch("research")
    assert missing.name == "main"
    assert missing.is_main
    assert missing.system_prompt_extra == ""
    assert missing.skill_preferences.is_empty
    assert missing.memory_config.is_empty


def test_missing_config_dir_uses_empty_main(tmp_path):
    tree = HarnessTree(tmp_path / "does-not-exist")
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.is_main
    assert branch.system_prompt_extra == ""


def test_tool_set_references_smart_router_sets(tmp_path):
    """The harness branch must NOT own a tool list — it references the smart
    router's TOOL_SETS by task type, so the two cannot drift."""
    from ouroboros.smart_router import TOOL_SETS

    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding")
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    # The branch's tool set IS the smart router's coding set — same object source.
    assert branch.tool_set() == TOOL_SETS[TASK_TYPE_CODING]
    # main (no task type) falls back to the simple set, never to "all tools".
    main = tree.select_branch("research")
    assert main.tool_set() == TOOL_SETS[TASK_TYPE_SIMPLE]


def test_branch_names_listing(tmp_path):
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding")
    _write_branch(cfg, "research")
    tree = HarnessTree(cfg)
    names = tree.branch_names()
    assert names[0] == "main"
    assert "coding" in names and "research" in names


def test_broken_json_falls_back_to_empty(tmp_path):
    cfg = _config_dir(tmp_path)
    branch_dir = _write_branch(cfg, "coding", memory_config={"exclude": ["x"]})
    (branch_dir / "memory_config.json").write_text("{not json", encoding="utf-8")
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.memory_config.is_empty
    assert branch.name == "coding"


# ---------------------------------------------------------------------------
# Skill-preferences bias inside the smart router
# ---------------------------------------------------------------------------


def test_skill_preferences_boost_and_always(tmp_path):
    drive = tmp_path / "drive"
    _write_skill(drive, "git-cleanup", tags="git, code")
    _write_skill(drive, "hello-bot", tags="chat")
    cfg = _config_dir(tmp_path)
    _write_branch(
        cfg, "coding",
        skill_preferences={"boost": {"git-cleanup": 0.3}, "always": ["git-cleanup"]},
    )
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    router = SmartRouter(drive)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(),
        task_type=TASK_TYPE_CODING,
        skill_preferences=branch.skill_preferences,
        branch=branch.name,
    )
    ranked = dict(result.skill_rankings)
    assert "git-cleanup" in ranked
    # Boosted skill ranks above an equally-relevant one; branch recorded.
    assert result.branch == "coding"
    assert ranked["git-cleanup"] >= ranked.get("hello-bot", 0.0)


def test_preferences_pin_below_threshold_skill(tmp_path):
    drive = tmp_path / "drive"
    _write_skill(drive, "weak-skill", tags="unrelated")
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", skill_preferences={"always": ["weak-skill"]})
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    router = SmartRouter(drive)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(),
        task_type=TASK_TYPE_CODING,
        skill_preferences=branch.skill_preferences,
        branch=branch.name,
    )
    assert "weak-skill" in dict(result.skill_rankings)


def test_plain_dict_preferences_accepted(tmp_path):
    drive = tmp_path / "drive"
    _write_skill(drive, "git-cleanup", tags="git, code")
    router = SmartRouter(drive)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(),
        task_type=TASK_TYPE_CODING,
        skill_preferences={"boost": {"git-cleanup": 0.2}},
    )
    assert "git-cleanup" in dict(result.skill_rankings)


def test_self_authored_skill_ranks_first_at_equal_relevance(tmp_path):
    """The owner's own curated skills win ties against installed skills at
    equal relevance score (不足 3 harness integration, owner request)."""
    drive = tmp_path / "drive"
    _write_self_authored_skill(drive, "my-git-tool", tags="git, code")
    _write_skill(drive, "git-cleanup", tags="git, code")
    router = SmartRouter(drive)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p", "description": "implement"},
        available=set(),
        task_type=TASK_TYPE_CODING,
    )
    names = [name for name, _ in result.skill_rankings]
    assert names[0] == "my-git-tool", names
    assert "git-cleanup" in names


# ---------------------------------------------------------------------------
# Routing history carries the branch
# ---------------------------------------------------------------------------


def test_routing_history_records_branch(tmp_path):
    drive = tmp_path / "drive"
    router = SmartRouter(drive)
    router.route(
        {"id": "t1", "type": "api_task", "workspace_root": "C:/p"},
        available=set(),
        task_type=TASK_TYPE_CODING,
        branch="coding",
    )
    history = drive / "state" / "routing_history.jsonl"
    assert history.exists()
    record = json.loads(history.read_text(encoding="utf-8").splitlines()[-1])
    assert record["task_id"] == "t1"
    assert record["branch"] == "coding"


# ---------------------------------------------------------------------------
# End-to-end: agent wiring puts the branch on the ToolContext and its
# system-prompt extra reaches the built messages.
# ---------------------------------------------------------------------------


def test_agent_applies_harness_branch_to_context(tmp_path, monkeypatch):
    from ouroboros.agent import Env, OuroborosAgent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "SYSTEM.md").write_text("You are Ouroboros.", encoding="utf-8")
    (repo / "harness_configs" / "coding").mkdir(parents=True)
    (repo / "harness_configs" / "coding" / "system_prompt_extra.md").write_text(
        "## Coding Focus\nwork on code", encoding="utf-8")
    drive = tmp_path / "drive"
    drive.mkdir()

    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
    monkeypatch.setattr(OuroborosAgent, "_log_worker_boot_once", lambda self: None)

    agent = OuroborosAgent(Env(repo_dir=repo, drive_root=drive))
    captured = {}

    def _fake_build_llm_messages(**kwargs):
        captured.update(kwargs)
        return [], {}

    monkeypatch.setattr("ouroboros.agent.build_llm_messages", _fake_build_llm_messages)

    task = {
        "id": "h1",
        "chat_id": 1,
        "type": "api_task",
        "workspace_root": str(repo),
        "description": "implement a feature",
    }
    ctx, messages, _cap = agent._prepare_task_context(task)

    # Branch selected and carried on the ToolContext for context.py to use.
    assert ctx.harness_branch is not None
    assert ctx.harness_branch.name == "coding"
    assert "## Coding Focus" in ctx.harness_branch.system_prompt_extra


def test_agent_unclassified_task_lands_on_main(tmp_path, monkeypatch):
    from ouroboros.agent import Env, OuroborosAgent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "SYSTEM.md").write_text("You are Ouroboros.", encoding="utf-8")
    (repo / "harness_configs").mkdir(parents=True)
    drive = tmp_path / "drive"
    drive.mkdir()

    monkeypatch.setattr(OuroborosAgent, "_log_worker_boot_once", lambda self: None)
    agent = OuroborosAgent(Env(repo_dir=repo, drive_root=drive))
    captured = {}

    def _fake_build_llm_messages(**kwargs):
        captured.update(kwargs)
        return [], {}

    monkeypatch.setattr("ouroboros.agent.build_llm_messages", _fake_build_llm_messages)

    task = {"id": "h2", "chat_id": 1, "type": "chat", "description": "hi"}
    ctx, messages, _cap = agent._prepare_task_context(task)

    assert ctx.harness_branch is not None
    assert ctx.harness_branch.is_main
