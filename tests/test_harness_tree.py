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

from ouroboros.harness_tree import HarnessTree, SkillPreferences
from ouroboros.smart_router import (
    TASK_TYPE_CODING,
    TASK_TYPE_KNOWLEDGE,
    TASK_TYPE_SIMPLE,
    SmartRouter,
)


def _write_branch(
    config_dir: pathlib.Path,
    name: str,
    *,
    prompt_extra: str = "",
    anti_patterns: str = "",
    memory_config: dict | None = None,
    skill_preferences: dict | None = None,
    tool_preferences: dict | None = None,
) -> pathlib.Path:
    branch_dir = config_dir / name
    branch_dir.mkdir(parents=True, exist_ok=True)
    if prompt_extra:
        (branch_dir / "system_prompt_extra.md").write_text(prompt_extra, encoding="utf-8")
    if anti_patterns:
        (branch_dir / "anti_patterns.md").write_text(anti_patterns, encoding="utf-8")
    if memory_config is not None:
        (branch_dir / "memory_config.json").write_text(
            json.dumps(memory_config), encoding="utf-8")
    if skill_preferences is not None:
        (branch_dir / "skill_preferences.json").write_text(
            json.dumps(skill_preferences), encoding="utf-8")
    if tool_preferences is not None:
        (branch_dir / "tool_preferences.json").write_text(
            json.dumps(tool_preferences), encoding="utf-8")
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

    # Routing must be ON for the classification -> branch chain to run; with
    # routing OFF the whole block is skipped and no branch is attached (the
    # flag is consumed from the environment at task time).
    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
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


def test_agent_signal_less_task_lands_on_neutral_main(tmp_path, monkeypatch):
    """无信号任务: harness 走 main (中性兜底), 即使 simple 分支存在——simple 只
    服务显式轻量任务; 工具信封仍按保守 simple 集, 路由/技能推荐照常。"""
    from ouroboros.agent import Env, OuroborosAgent
    from ouroboros.smart_router import ALWAYS_ON_TOOLS, TOOL_SETS, TASK_TYPE_SIMPLE

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "SYSTEM.md").write_text("You are Ouroboros.", encoding="utf-8")
    # simple 分支存在——证明无信号任务不走它
    (repo / "harness_configs" / "simple").mkdir(parents=True)
    (repo / "harness_configs" / "simple" / "system_prompt_extra.md").write_text(
        "## Simple Task Focus\nminimal answer", encoding="utf-8")
    drive = tmp_path / "drive"
    drive.mkdir()

    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
    monkeypatch.setattr(OuroborosAgent, "_log_worker_boot_once", lambda self: None)

    agent = OuroborosAgent(Env(repo_dir=repo, drive_root=drive))

    def _fake_build_llm_messages(**kwargs):
        return [], {}

    monkeypatch.setattr("ouroboros.agent.build_llm_messages", _fake_build_llm_messages)

    # 无任何信号的任务: type 缺、无 workspace、描述无关键词
    task = {"id": "h4", "chat_id": 1, "description": "hi there"}
    ctx, _messages, _cap = agent._prepare_task_context(task)
    assert ctx.harness_branch.is_main
    # 智能路由仍在: 保守 simple 信封 (加常驻 meta 工具), 且不包含 simple 分支的调整
    filt = agent.tools._router_filter
    assert filt is not None
    assert filt <= (TOOL_SETS[TASK_TYPE_SIMPLE] | ALWAYS_ON_TOOLS)


# ---------------------------------------------------------------------------
# L2 harness: tool preferences (avoid), anti-patterns, demote, robustness
# ---------------------------------------------------------------------------


def test_tool_preferences_avoid_narrows_envelope(tmp_path):
    """avoid 只剔除 TOOL_SETS 内的、非控制面的工具；未知名称被丢弃。"""
    from ouroboros.smart_router import TOOL_SETS

    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "knowledge", tool_preferences={
        "avoid": ["web_search", "enable_tools", "nonexistent_tool"],
    })
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_KNOWLEDGE)
    avoided = branch.avoided_tools()
    assert "web_search" in avoided
    assert "enable_tools" not in avoided  # control plane can never be avoided
    assert "nonexistent_tool" not in avoided  # unknown names are dropped
    assert avoided <= TOOL_SETS[TASK_TYPE_KNOWLEDGE]
    # A branch with no tool config avoids nothing.
    main = tree.select_branch("research")
    assert main.avoided_tools() == frozenset()


def test_agent_applies_avoid_tools_to_round_one_envelope(tmp_path, monkeypatch):
    """端到端：knowledge 分支 avoid web_search → 该工具不在 round-one 信封。"""
    from ouroboros.agent import Env, OuroborosAgent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "SYSTEM.md").write_text("You are Ouroboros.", encoding="utf-8")
    (repo / "harness_configs" / "knowledge").mkdir(parents=True)
    (repo / "harness_configs" / "knowledge" / "tool_preferences.json").write_text(
        json.dumps({"avoid": ["web_search"]}), encoding="utf-8")
    drive = tmp_path / "drive"
    drive.mkdir()

    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
    monkeypatch.setattr(OuroborosAgent, "_log_worker_boot_once", lambda self: None)

    agent = OuroborosAgent(Env(repo_dir=repo, drive_root=drive))

    def _fake_build_llm_messages(**kwargs):
        return [], {}

    monkeypatch.setattr("ouroboros.agent.build_llm_messages", _fake_build_llm_messages)

    task = {"id": "h3", "chat_id": 1, "type": "knowledge", "description": "remember something"}
    ctx, _messages, _cap = agent._prepare_task_context(task)
    assert ctx.harness_branch.name == "knowledge"
    filt = agent.tools._router_filter
    assert filt is not None
    assert "web_search" not in filt
    # The discovery escape hatch survives the branch-level narrowing.
    assert "enable_tools" in filt


def test_anti_patterns_loaded_with_branch(tmp_path):
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", anti_patterns="- avoid whole-file rewrites")
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.anti_patterns == "- avoid whole-file rewrites"
    # main carries no anti-patterns.
    main = tree.select_branch("research")
    assert main.anti_patterns == ""


def test_context_injects_anti_patterns_after_extra(tmp_path):
    """anti_patterns 渲染为独立 ## Avoid 段，跟在正向 extra 之后。"""
    from ouroboros.agent import Env
    from ouroboros.context import _capture_context_core
    from ouroboros.harness_tree import HarnessBranch
    from ouroboros.memory import Memory
    from ouroboros.tools.registry import ToolContext

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "SYSTEM.md").write_text("BASE SYSTEM", encoding="utf-8")
    (repo / "BIBLE.md").write_text("BIBLE", encoding="utf-8")
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "ARCHITECTURE.md").write_text("ARC", encoding="utf-8")
    drive = tmp_path / "drive"
    drive.mkdir()
    env = Env(repo_dir=repo, drive_root=drive)
    memory = Memory(drive_root=drive, repo_dir=repo)
    memory.ensure_files()

    ctx = ToolContext(repo_dir=repo, drive_root=drive)
    ctx.harness_branch = HarnessBranch(
        name="coding",
        task_type="coding",
        system_prompt_extra="## Coding Task Focus\nplan first",
        anti_patterns="- never whole-file rewrite",
    )

    core = _capture_context_core(env, memory, {}, None, ctx)
    assert "BASE SYSTEM" in core.base_prompt
    assert "## Coding Task Focus" in core.base_prompt
    assert "## Avoid (coding branch)" in core.base_prompt
    assert "- never whole-file rewrite" in core.base_prompt


def test_skill_preferences_boost_and_demote_together(tmp_path):
    """demote 把技能压到 0.6 阈值以下推出推荐；boost 仍可把另一个技能抬进来。"""
    drive = tmp_path / "drive"
    _write_skill(drive, "web-scraper", tags="web, research")
    _write_skill(drive, "git-cleanup", tags="git, code")
    cfg = _config_dir(tmp_path)
    _write_branch(
        cfg, "knowledge",
        skill_preferences={
            "boost": {"git-cleanup": 0.3},
            "demote": ["web-scraper"],
            "demote_tags": ["research"],
        },
    )
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_KNOWLEDGE)
    router = SmartRouter(drive)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(),
        task_type=TASK_TYPE_KNOWLEDGE,
        skill_preferences=branch.skill_preferences,
        branch=branch.name,
    )
    ranked = dict(result.skill_rankings)
    assert "web-scraper" not in ranked  # demoted below the 0.6 threshold
    assert "git-cleanup" in ranked  # boosted back above it


def test_demote_removes_even_full_relevance_skill(tmp_path):
    """满配技能 (所有字段命中, score 1.0) + 具名 demote → 0.5 < 0.6, 必然出局
    (DEMOTE_SKILL_PENALTY=0.5 大于任何正向增量组合的最大值 0.5)。"""
    drive = tmp_path / "drive"
    _write_skill(drive, "git-automation", tags="code, python, build, git")
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", skill_preferences={"demote": ["git-automation"]})
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
    assert "git-automation" not in dict(result.skill_rankings)


def test_non_numeric_boost_value_is_skipped(tmp_path):
    """一个坏 boost 值不毒化整个分支加载。"""
    cfg = _config_dir(tmp_path)
    _write_branch(cfg, "coding", skill_preferences={
        "boost": {"good": 0.2, "bad": "not-a-number"},
    })
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.skill_preferences.boost == {"good": 0.2}


def test_broken_skill_preferences_json_does_not_kill_branch(tmp_path):
    """skill_preferences 整体解析失败 → 空偏好，分支其余配置不受影响。"""
    cfg = _config_dir(tmp_path)
    branch_dir = _write_branch(
        cfg, "coding",
        prompt_extra="## Coding\nx",
        skill_preferences={"boost": {"x": 0.2}},
    )
    (branch_dir / "skill_preferences.json").write_text("[1,2,3]", encoding="utf-8")
    tree = HarnessTree(cfg)
    branch = tree.select_branch(TASK_TYPE_CODING)
    assert branch.name == "coding"
    assert branch.skill_preferences.is_empty
    assert branch.system_prompt_extra  # other config survives


def test_skill_preferences_is_empty_covers_new_fields():
    prefs = SkillPreferences()
    assert prefs.is_empty
    prefs.demote.append("x")
    assert not prefs.is_empty
    prefs = SkillPreferences()
    prefs.demote_tags.append("web")
    assert not prefs.is_empty


def test_registry_config_only_filters_explicit_mentions():
    """registry digest 过滤：只有显式提及 "memory registry" 的分支才有话语权。"""
    from ouroboros.context import _apply_harness_registry_config
    from ouroboros.harness_tree import MemoryConfig

    digest = "## Memory Registry\nregistry digest text"
    # Branch that never mentions registry: digest passes through unchanged.
    assert _apply_harness_registry_config(digest, MemoryConfig(priority=["scratchpad", "identity"], exclude=["dialogue"])) == digest
    # Exclude mentions registry: digest dropped (simple branch intent).
    assert _apply_harness_registry_config(digest, MemoryConfig(exclude=["dialogue", "memory registry"])) == ""
    # Include mentions registry: digest kept.
    assert _apply_harness_registry_config(digest, MemoryConfig(include=["memory registry"])) == digest
    # Include that never mentions registry: the branch has no opinion on the
    # registry digest, so it passes through unchanged (default behavior).
    assert _apply_harness_registry_config(digest, MemoryConfig(include=["scratchpad"])) == digest
    # No config / empty digest: unaffected.
    assert _apply_harness_registry_config(digest, None) == digest
    assert _apply_harness_registry_config("", MemoryConfig(include=["memory registry"])) == ""
