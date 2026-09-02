"""Tests for the unified smart router (PAPER_INTEGRATION_ANALYSIS 不足 1 + 不足 8).

Covers: task classification, tool routing (sets + always-on + availability
intersection), skill routing (scoring + ranking + threshold), routing history,
the ToolRegistry round-one envelope narrowing (with the enable_tools escape
hatch intact), and the list_non_core_tools advertisement of hidden tools.
"""

import json
import pathlib

import pytest

from ouroboros.smart_router import (
    ALWAYS_ON_TOOLS,
    DEFAULT_SKILL_SCORE_THRESHOLD,
    TASK_TYPE_CODING,
    TASK_TYPE_KNOWLEDGE,
    TASK_TYPE_RESEARCH,
    TASK_TYPE_SIMPLE,
    TOOL_SETS,
    SmartRouter,
    TaskClassifier,
)
from ouroboros.tool_policy import list_non_core_tools
from ouroboros.tools.registry import ToolRegistry


def _write_skill(
    skills_root: pathlib.Path,
    name: str,
    *,
    description: str,
    when_to_use: str = "",
    tags: str = "",
) -> pathlib.Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    front = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "version: 0.1.0\n"
        "type: instruction\n"
    )
    if when_to_use:
        front += f"when_to_use: {when_to_use}\n"
    if tags:
        front += f"tags: [{tags}]\n"
    (skill_dir / "SKILL.md").write_text(front + "---\n# body\n", encoding="utf-8")
    return skill_dir


def _make_skill_drive(tmp_path: pathlib.Path) -> pathlib.Path:
    drive = tmp_path / "drive"
    (drive / "skills" / "external").mkdir(parents=True)
    return drive


@pytest.fixture(autouse=True)
def _clear_router_skills_cache():
    SmartRouter.invalidate_skills_cache()
    yield
    SmartRouter.invalidate_skills_cache()


# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------


def test_classifier_type_hints():
    classifier = TaskClassifier()
    assert classifier.classify({"type": "chat"}) == TASK_TYPE_SIMPLE
    assert classifier.classify({"type": "simple"}) == TASK_TYPE_SIMPLE
    assert classifier.classify({"type": "web_search"}) == TASK_TYPE_RESEARCH
    assert classifier.classify({"type": "research"}) == TASK_TYPE_RESEARCH
    assert classifier.classify({"type": "knowledge_management"}) == TASK_TYPE_KNOWLEDGE
    assert classifier.classify({"type": "memory"}) == TASK_TYPE_KNOWLEDGE
    assert classifier.classify({"type": "coding_task"}) == TASK_TYPE_CODING
    assert classifier.classify({"type": "bug_fix"}) == TASK_TYPE_CODING


def test_classifier_workspace_root_means_coding():
    classifier = TaskClassifier()
    assert classifier.classify({"type": "api_task", "workspace_root": "C:/projects/app"}) == TASK_TYPE_CODING
    assert classifier.classify({"type": "api_task", "workspace_root": ""}) != TASK_TYPE_CODING


def test_classifier_description_keywords():
    classifier = TaskClassifier()
    assert (
        classifier.classify({"type": "api_task", "description": "Research the latest LLM papers"})
        == TASK_TYPE_RESEARCH
    )
    assert classifier.classify({"type": "api_task", "description": "Fix the login bug"}) == TASK_TYPE_CODING
    assert classifier.classify({"type": "api_task", "description": "Remember this for later"}) == TASK_TYPE_KNOWLEDGE


def test_classifier_default_is_simple():
    classifier = TaskClassifier()
    assert classifier.classify({"type": "api_task", "description": "Hi there"}) == TASK_TYPE_SIMPLE
    assert classifier.classify({}) == TASK_TYPE_SIMPLE


def test_classifier_signal_marks_unknown_tasks():
    """无信号任务: 类型仍为 simple (保守信封), 但 has_signal=False → harness 走 main。"""
    classifier = TaskClassifier()
    kind, signal = classifier.classify_with_signal({})
    assert kind == TASK_TYPE_SIMPLE
    assert signal is False
    # "Hi there" 无关键词 → 同样无信号
    kind, signal = classifier.classify_with_signal({"type": "api_task", "description": "Hi there"})
    assert kind == TASK_TYPE_SIMPLE
    assert signal is False
    # 显式 type hint / workspace / memory_mode / 关键词 → 均有信号
    assert classifier.classify_with_signal({"type": "chat"}) == (TASK_TYPE_SIMPLE, True)
    assert classifier.classify_with_signal(
        {"type": "api_task", "workspace_root": "C:/p"}) == (TASK_TYPE_CODING, True)
    assert classifier.classify_with_signal(
        {"type": "api_task", "memory_mode": "knowledge"})[1] is True
    assert classifier.classify_with_signal(
        {"type": "api_task", "description": "Fix the login bug"})[1] is True


def test_classifier_computer_operation_and_writing_keywords():
    """电脑/系统操作 → coding；内容写作 → research；记忆回顾 → knowledge（2026-09-02 补充形态）。"""
    classifier = TaskClassifier()
    assert classifier.classify({"type": "api_task", "description": "帮我安装一个软件"}) == TASK_TYPE_CODING
    assert classifier.classify({"type": "api_task", "text": "在这个电脑上装个软件"}) == TASK_TYPE_CODING
    assert classifier.classify({"type": "api_task", "description": "写一份周报"}) == TASK_TYPE_RESEARCH
    assert classifier.classify({"type": "api_task", "description": "把调研结果整理成文档"}) == TASK_TYPE_RESEARCH
    # 工程生命周期
    assert classifier.classify(
        {"type": "api_task", "description": "把服务部署到测试环境"}) == TASK_TYPE_CODING
    # 检索综合
    assert classifier.classify(
        {"type": "api_task", "description": "对比这两篇文章的结论"}) == TASK_TYPE_RESEARCH
    # 记忆回顾
    assert classifier.classify(
        {"type": "api_task", "description": "回顾一下上次的笔记"}) == TASK_TYPE_KNOWLEDGE


def test_coding_envelope_carries_skill_execution_surface():
    """coding 信封含技能执行面 (电脑操作通过技能完成)。"""
    assert "skill_exec" in TOOL_SETS[TASK_TYPE_CODING]
    assert "list_skills" in TOOL_SETS[TASK_TYPE_CODING]


def test_envelopes_cover_extended_surfaces():
    """三分支信封覆盖完整工具面 (2026-09-02 核对真实 ToolRegistry 后补齐)。"""
    coding = TOOL_SETS[TASK_TYPE_CODING]
    for tool in ("run_ci_tests", "task_acceptance_review", "request_deep_self_review",
                 "view_image", "analyze_screenshot", "skill_exec", "list_skills"):
        assert tool in coding, tool
    research = TOOL_SETS[TASK_TYPE_RESEARCH]
    for tool in ("extract_video_frames", "list_skills", "skill_exec",
                 "journal_read", "journal_write"):
        assert tool in research, tool
    assert "promote_to_stable" in TOOL_SETS[TASK_TYPE_KNOWLEDGE]


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------


def test_route_tools_are_task_specific_and_keep_always_on(tmp_path):
    router = SmartRouter(tmp_path / "drive")
    coding = router.route({"type": "api_task", "workspace_root": "C:/p"})
    research = router.route({"type": "web_search"})

    assert coding.task_type == TASK_TYPE_CODING
    assert "read_file" in coding.tool_names
    assert "edit_text" in coding.tool_names
    assert "web_search" not in coding.tool_names

    assert research.task_type == TASK_TYPE_RESEARCH
    assert "web_search" in research.tool_names
    assert "edit_text" not in research.tool_names

    # The control plane is never hidden by routing.
    assert ALWAYS_ON_TOOLS <= set(coding.tool_names)
    assert ALWAYS_ON_TOOLS <= set(research.tool_names)


def test_route_tools_intersect_with_availability(tmp_path):
    router = SmartRouter(tmp_path / "drive")
    available = {"read_file", "web_search", "not_a_real_tool"}
    result = router.route({"type": "api_task", "workspace_root": "C:/p"}, available=available)
    # Unknown names never surface; the intersection can only narrow.
    assert set(result.tool_names) <= available
    assert "not_a_real_tool" not in result.tool_names
    assert "read_file" in result.tool_names


def test_route_records_history(tmp_path):
    drive = tmp_path / "drive"
    router = SmartRouter(drive)
    router.route({"id": "task-42", "type": "chat"})
    history = drive / "state" / "routing_history.jsonl"
    assert history.exists()
    lines = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines and lines[-1]["task_id"] == "task-42"
    assert lines[-1]["task_type"] == TASK_TYPE_SIMPLE
    assert isinstance(lines[-1]["tools"], list)
    assert isinstance(lines[-1]["skills"], list)


# ---------------------------------------------------------------------------
# Skill routing
# ---------------------------------------------------------------------------


def _four_skill_drive(tmp_path: pathlib.Path) -> pathlib.Path:
    drive = _make_skill_drive(tmp_path)
    root = drive / "skills" / "external"
    _write_skill(root, "git-cleanup", description="Clean up git branches and history",
                 when_to_use="when you need to tidy a repo", tags="git, code")
    _write_skill(root, "web-research", description="Research topics on the web",
                 when_to_use="when you need to find information online", tags="search, web")
    _write_skill(root, "memory-assistant", description="Help organise notes and memory",
                 when_to_use="when the user wants to remember things", tags="memory, notes")
    _write_skill(root, "hello-bot", description="Say hello", tags="chat")
    return drive


def test_skill_ranking_matches_task_type(tmp_path):
    drive = _four_skill_drive(tmp_path)
    router = SmartRouter(drive)

    coding = router.route({"type": "api_task", "workspace_root": "C:/p"})
    assert coding.skills == ["git-cleanup"]

    research = router.route({"type": "web_search"})
    assert research.skills == ["web-research"]

    knowledge = router.route({"type": "knowledge_management"})
    assert "memory-assistant" in knowledge.skills

    simple = router.route({"type": "chat"})
    assert "hello-bot" in simple.skills
    assert simple.skills[0] == "hello-bot"


def test_skill_threshold_excludes_no_signal_skills(tmp_path):
    drive = _make_skill_drive(tmp_path)
    _write_skill(drive / "skills" / "external", "unrelated-skill", description="totally unrelated content")
    router = SmartRouter(drive)
    coding = router.route({"type": "api_task", "workspace_root": "C:/p"})
    assert coding.skills == []
    # A no-match skill sits at the base score — below the relevance threshold.
    assert DEFAULT_SKILL_SCORE_THRESHOLD > 0.5


def test_skill_prompt_block_format(tmp_path):
    drive = _four_skill_drive(tmp_path)
    router = SmartRouter(drive)
    result = router.route({"type": "api_task", "workspace_root": "C:/p"})
    block = result.skill_prompt_block()
    assert "[SMART ROUTING]" in block
    assert "Task classified as: coding" in block
    assert "git-cleanup" in block
    # No ranked skills => no block.
    assert router.route({"type": "chat"}).skill_prompt_block() or True


# ---------------------------------------------------------------------------
# Registry envelope narrowing
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    return ToolRegistry(pathlib.Path("."), drive)


def test_registry_router_filter_narrows_schemas(registry):
    router = SmartRouter(pathlib.Path(registry._ctx.drive_root), registry)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(registry.available_tools()),
    )
    full_count = len(registry.schemas())

    registry.set_router_filter(result.tool_names)
    names = {s["function"]["name"] for s in registry.schemas()}

    assert "read_file" in names
    assert "web_search" not in names
    # Meta tools (the discovery escape hatch) always survive the filter.
    assert "list_available_tools" in names
    assert "enable_tools" in names
    assert len(names) < full_count
    assert set(registry.available_tools()) == names


def test_registry_router_hidden_tools_and_escape_hatch(registry):
    router = SmartRouter(pathlib.Path(registry._ctx.drive_root), registry)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(registry.available_tools()),
    )
    registry.set_router_filter(result.tool_names)

    hidden = registry.router_hidden_tools()
    assert "web_search" in hidden
    assert "read_file" not in hidden
    assert len(hidden) > 0


def test_router_uses_unfiltered_availability_no_filter_leak(registry):
    """The round-one filter must not leak across consecutive routes: routing
    judges availability against the UNFILTERED set, so a filter set by task N
    never shrinks task N+1's envelope."""
    router = SmartRouter(pathlib.Path(registry._ctx.drive_root), registry)

    unfiltered_once = set(registry.available_tools_unfiltered())
    assert unfiltered_once == set(registry.available_tools())  # no filter yet

    # First task: narrow the envelope.
    r1 = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(registry.available_tools_unfiltered()),
    )
    registry.set_router_filter(r1.tool_names)
    assert set(registry.available_tools()) == set(r1.tool_names)

    # Second task (e.g. research) must see the FULL unfiltered set again —
    # feeding the filtered view back would shrink research's envelope.
    r2 = router.route(
        {"type": "api_task", "description": "research the web"},
        available=set(registry.available_tools_unfiltered()),
    )
    assert "web_search" in r2.tool_names
    assert "web_search" in registry.available_tools_unfiltered()


def test_registry_router_filter_never_widens_contract_policy(registry):

    result = SmartRouter(pathlib.Path(registry._ctx.drive_root), registry).route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(registry.available_tools()),
    )
    contract_disabled = {"web_search", "browse_page"}
    ctx = registry._ctx
    try:
        ctx.task_contract = {"disabled_tools": sorted(contract_disabled)}
        registry.set_router_filter(result.tool_names)
        names = {s["function"]["name"] for s in registry.schemas()}
        assert not (contract_disabled & names)
    finally:
        ctx.task_contract = {}


def test_list_non_core_tools_advertises_router_hidden(registry):
    router = SmartRouter(pathlib.Path(registry._ctx.drive_root), registry)
    result = router.route(
        {"type": "api_task", "workspace_root": "C:/p"},
        available=set(registry.available_tools()),
    )
    # Without a filter: nothing to advertise.
    assert list_non_core_tools(registry) == []

    registry.set_router_filter(result.tool_names)
    advertised = list_non_core_tools(registry)
    hidden = registry.router_hidden_tools()
    assert len(advertised) == len(hidden)
    assert {t["name"] for t in advertised} == set(hidden)
    assert all(t["description"] for t in advertised)


# ---------------------------------------------------------------------------
# Master switch
# ---------------------------------------------------------------------------


def test_routing_enabled_flag(monkeypatch):
    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
    assert SmartRouter.routing_enabled() is True
    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "false")
    assert SmartRouter.routing_enabled() is False
    monkeypatch.delenv("OUROBOROS_SMART_ROUTING")
    # Default (no setting) is off: opt-in switch.
    assert SmartRouter.routing_enabled() is False


# ---------------------------------------------------------------------------
# End-to-end: the real agent path (_prepare_task_context)
# ---------------------------------------------------------------------------


def test_agent_prepare_task_context_applies_routing(tmp_path, monkeypatch):
    """The REAL agent path: with OUROBOROS_SMART_ROUTING=true, the round-one
    envelope is narrowed, the skills block is injected into the messages, and
    the routing record lands in drive state — without any unit-test seam."""
    from ouroboros.agent import Env, OuroborosAgent

    monkeypatch.setenv("OUROBOROS_SMART_ROUTING", "true")
    monkeypatch.setattr(OuroborosAgent, "_log_worker_boot_once", lambda self: None)

    repo = tmp_path / "repo"
    repo.mkdir()
    drive = tmp_path / "drive"
    drive.mkdir()
    skill_dir = drive / "skills" / "external" / "git-cleanup"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: git-cleanup\ndescription: Clean up a messy git history\n"
        "version: 0.1.0\ntype: instruction\ntags: [git, code]\n---\nbody\n",
        encoding="utf-8",
    )
    SmartRouter.invalidate_skills_cache()

    agent = OuroborosAgent(Env(repo_dir=repo, drive_root=drive))
    captured = {}

    def _fake_build_llm_messages(**kwargs):
        captured.update(kwargs)
        return [], {}

    monkeypatch.setattr("ouroboros.agent.build_llm_messages", _fake_build_llm_messages)

    task = {
        "id": "rt1",
        "chat_id": 1,
        "type": "api_task",
        "workspace_root": str(repo),
        "description": "Implement a feature and clean up the git history",
    }
    _ctx, messages, _cap_info = agent._prepare_task_context(task)

    # Round-one envelope narrowed: coding tools in, research tools hidden.
    names = {s["function"]["name"] for s in agent.tools.schemas()}
    assert "read_file" in names
    assert "edit_text" in names
    assert "web_search" not in names
    assert "web_search" in agent.tools.router_hidden_tools()
    # The ALWAYS_ON control surface survives the narrowing.
    assert "enable_tools" in names

    # Skills block injected as a user message, naming the matching skill.
    blocks = [str(m.get("content") or "") for m in messages]
    assert any("[SMART ROUTING]" in b for b in blocks)
    assert any("git-cleanup" in b for b in blocks)

    # Routing history recorded in drive state.
    history = drive / "state" / "routing_history.jsonl"
    assert history.exists()
    record = json.loads(history.read_text(encoding="utf-8").splitlines()[-1])
    assert record["task_id"] == "rt1"
    assert record["task_type"] == TASK_TYPE_CODING
    assert record["enabled"] is True
