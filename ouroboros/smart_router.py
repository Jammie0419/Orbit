"""Unified smart router for tools and skills (PAPER_INTEGRATION_ANALYSIS 不足 1 + 不足 8).

One task classifier feeds two routers that share its result:

* **Tool routing** narrows the round-one tool schema envelope to the tools
  relevant for the classified task type (everything else stays one
  ``enable_tools`` call away — see ``ToolRegistry.set_router_filter`` and
  ``ouroboros.tool_policy.list_non_core_tools``).
* **Skill routing** ranks installed skills by task relevance and recommends
  the Top-K in a prompt block the agent can act on.

The classification is rule-based and therefore free (no extra LLM call), and
every routing decision is recorded to ``state/routing_history.jsonl`` so the
router can be learned from later (P2 feedback loop).
"""

from __future__ import annotations

import logging
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ouroboros.utils import append_jsonl, utc_now_iso

log = logging.getLogger(__name__)

TASK_TYPE_CODING = "coding"
TASK_TYPE_RESEARCH = "research"
TASK_TYPE_KNOWLEDGE = "knowledge"
TASK_TYPE_SIMPLE = "simple"

VALID_TASK_TYPES = (TASK_TYPE_CODING, TASK_TYPE_RESEARCH, TASK_TYPE_KNOWLEDGE, TASK_TYPE_SIMPLE)

HISTORY_FILENAME = "routing_history.jsonl"

DEFAULT_TOP_K_SKILLS = 10
# Strictly above the base score (0.5): a skill must match at least ONE field
# (tags +0.3, name +0.2, description/when_to_use/body +0.1) to be recommended.
# A plain base-score skill is by definition "no signal" and stays unranked.
DEFAULT_SKILL_SCORE_THRESHOLD = 0.6

# Tool names that are NEVER hidden by routing. These are the control plane
# (task-tree coordination, model switching, owner communication) and the
# discovery escape hatch itself: the model can always enumerate and enable
# anything the router did not pre-load.
ALWAYS_ON_TOOLS = frozenset({
    "list_available_tools", "enable_tools",
    "switch_model", "compact_context", "request_restart",
    "send_user_message", "send_photo", "send_video", "send_file",
    "steer_task", "cancel_task", "wait_task", "wait_tasks", "get_task_result",
    "tree_note", "tree_read",
})

# Task-type tool sets. Names are the REAL registry names (verified against
# ToolRegistry.available_tools()). Unknown names are dropped at route time by
# intersecting with the registry's actual availability, so a stale set can
# never widen the envelope beyond what the registry really serves.
TOOL_SETS: Dict[str, frozenset] = {
    TASK_TYPE_CODING: frozenset({
        "read_file", "list_files", "write_file", "edit_text", "apply_patch", "edit_batch",
        "search_code", "query_code",
        "run_command", "run_script",
        "start_service", "service_status", "service_logs", "stop_service",
        "vcs_status", "vcs_diff", "vcs_commit_reviewed", "commit_reviewed",
        "vcs_restore", "vcs_revert", "vcs_pull_ff", "vcs_rollback",
        "plan_task", "verify_and_record", "codebase_health", "review_status",
        "schedule_subagent", "compare_subagent_patches", "integrate_subagent_patch",
        "integrate_delegated_patch",
        "recent_tasks", "chat_history", "journal_read", "journal_write",
    }),
    TASK_TYPE_RESEARCH: frozenset({
        "web_search", "browse_page", "browser_action", "analyze_screenshot",
        "view_image", "vlm_query", "ocr_pdf", "youtube_transcript",
        "read_file", "list_files", "search_code", "query_code",
        "knowledge_read", "knowledge_list",
        "chat_history", "recent_tasks", "workpad_read", "workpad_write",
    }),
    TASK_TYPE_KNOWLEDGE: frozenset({
        "knowledge_read", "knowledge_write", "knowledge_list",
        "update_scratchpad", "update_identity",
        "memory_map", "memory_update_registry",
        "workpad_read", "workpad_write", "journal_read", "journal_write",
        "list_skills", "skill_exec", "skill_review", "skill_preflight",
        "toggle_skill", "submit_skill_to_hub",
        "chat_history", "recent_tasks", "web_search",
    }),
    TASK_TYPE_SIMPLE: frozenset({
        "chat_history", "recent_tasks",
        "update_scratchpad", "update_identity",
        "list_projects", "ensure_project_scope", "route_to_project", "promote_chat_to_task",
        "knowledge_read", "knowledge_list",
    }),
}

# Substring tags that map a skill (name / description / when_to_use / body)
# onto a task type. Kept deliberately loose — a single hit only moves the
# score a little; specificity comes from matching across several fields.
SKILL_TAG_MAPPING: Dict[str, Tuple[str, ...]] = {
    TASK_TYPE_CODING: ("code", "coding", "program", "develop", "debug", "test",
                       "build", "git", "python", "shell", "refactor", "api"),
    TASK_TYPE_RESEARCH: ("search", "research", "web", "browse", "analyz", "investigat",
                         "explore", "summariz", "extract", "report", "data"),
    TASK_TYPE_KNOWLEDGE: ("memory", "knowledge", "learn", "note", "index", "recall",
                          "store", "journal", "workpad", "catalog"),
    TASK_TYPE_SIMPLE: ("chat", "communicat", "assistant", "helper", "qna", "brief",
                       "message", "respond"),
}


def _flatten_tags(raw: Any) -> List[str]:
    """Normalize a manifest ``tags`` value (list or string) into tokens."""
    if isinstance(raw, (list, tuple, set)):
        return [str(item or "").strip() for item in raw if str(item or "").strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


@dataclass
class RoutingResult:
    """The outcome of one unified route decision."""

    task_type: str = TASK_TYPE_SIMPLE
    task_id: str = ""
    branch: str = ""
    tool_names: List[str] = field(default_factory=list)
    skill_rankings: List[Tuple[str, float]] = field(default_factory=list)
    enabled: bool = False
    # Names the router hid from the round-one envelope (available but not routed).
    hidden_tool_names: List[str] = field(default_factory=list)

    @property
    def skills(self) -> List[str]:
        return [name for name, _score in self.skill_rankings]

    def skill_prompt_block(self, top_k: int = DEFAULT_TOP_K_SKILLS) -> str:
        """Render the recommended-skills section injected into the prompt.

        Defaults to the full ranked set the router produced (same cap as
        ``_route_skills``), so the prompt shows every recommended skill
        rather than a display-layer truncation that drops useful ones.
        """
        ranked = self.skill_rankings[:top_k]
        if not ranked:
            return ""
        lines = [
            "[SMART ROUTING]",
            f"Task classified as: {self.task_type}",
            f"Recommended skills (top {len(ranked)}):",
        ]
        for name, score in ranked:
            lines.append(f"- {name} (relevance {score:.2f})")
        return "\n".join(lines)


class TaskClassifier:
    """Rule-based task classifier shared by the tool and skill routers.

    Pure and deterministic (no LLM call) so routing adds zero provider cost.
    Signals, in priority order:
      1. Explicit ``task.type`` hints (research / knowledge / simple / coding).
      2. A bound ``workspace_root`` -> coding (path fact, not text guess).
      3. Keyword scan of the task description / memory mode.
      4. Default: ``simple``.
    """

    _TYPE_HINTS = {
        "research": TASK_TYPE_RESEARCH,
        "web_search": TASK_TYPE_RESEARCH,
        "websearch": TASK_TYPE_RESEARCH,
        "investigate": TASK_TYPE_RESEARCH,
        "browse": TASK_TYPE_RESEARCH,
        "knowledge_management": TASK_TYPE_KNOWLEDGE,
        "knowledge": TASK_TYPE_KNOWLEDGE,
        "memory": TASK_TYPE_KNOWLEDGE,
        "note": TASK_TYPE_KNOWLEDGE,
        "chat": TASK_TYPE_SIMPLE,
        "simple": TASK_TYPE_SIMPLE,
        "qna": TASK_TYPE_SIMPLE,
        "coding": TASK_TYPE_CODING,
        "coding_task": TASK_TYPE_CODING,
        "development": TASK_TYPE_CODING,
        "bug_fix": TASK_TYPE_CODING,
        "refactor": TASK_TYPE_CODING,
    }

    _DESCRIPTION_KEYWORDS = {
        TASK_TYPE_RESEARCH: ("research", "investigate", "find", "search", "summarize",
                             "compare", "web", "look up", "lookup",
                             # 中文用户: 调研 / 搜索 / 查找 / 总结 / 分析 / 论文 / 资料
                             "调研", "搜索", "查找", "查询", "总结", "分析", "研究",
                             "论文", "资料", "最新"),
        TASK_TYPE_KNOWLEDGE: ("remember", "memory", "knowledge", "note", "record",
                              "save for later", "store", "learn",
                              # 中文用户: 记住 / 存储 / 知识 / 笔记 / 长期记忆 / 保存
                              "记住", "存储", "保存", "知识", "笔记", "记忆",
                              "长期记忆", "学习记录", "归档"),
        TASK_TYPE_CODING: ("bug", "fix", "code", "implement", "refactor", "build",
                           "debug", "test", "write a", "program", "python", "function",
                           # 中文用户: 代码 / 写 / 实现 / 修复 / 重构 / 函数 / 模块 / 程序
                           "代码", "编写", "实现", "修复", "重构", "函数", "模块",
                           "程序", "脚本", "调试", "报错", "功能", "写一个"),
    }

    def classify(self, task: Dict[str, Any]) -> str:
        raw_type = str(task.get("type") or "").strip().lower()
        task_type = self._TYPE_HINTS.get(raw_type)
        if task_type is not None:
            return task_type

        workspace = str(task.get("workspace_root") or "").strip()
        if workspace:
            return TASK_TYPE_CODING

        memory_mode = str(task.get("memory_mode") or "").strip().lower()
        if memory_mode in {"knowledge", "memory"}:
            return TASK_TYPE_KNOWLEDGE

        # Chat turns carry the user's words in ``text`` (no description field);
        # tasks enqueued by the supervisor may carry either. Scan both so a
        # direct-chat message like "帮我调研 RAG" routes to research, not simple.
        haystack = " ".join(filter(None, [
            str(task.get("description") or "").strip().lower(),
            str(task.get("text") or "").strip().lower(),
        ]))
        if haystack:
            for candidate, keywords in self._DESCRIPTION_KEYWORDS.items():
                if any(keyword in haystack for keyword in keywords):
                    return candidate

        return TASK_TYPE_SIMPLE


class SmartRouter:
    """Unified router: classifies a task once and routes tools AND skills."""

    _skills_cache: Dict[pathlib.Path, Tuple[float, List[Any]]] = {}
    _skills_cache_ttl_sec: float = 30.0

    def __init__(
        self,
        drive_root: pathlib.Path,
        tool_registry: Any = None,
        *,
        history_file: Optional[pathlib.Path] = None,
        top_k_skills: int = DEFAULT_TOP_K_SKILLS,
        skill_score_threshold: float = DEFAULT_SKILL_SCORE_THRESHOLD,
    ):
        self.drive_root = pathlib.Path(drive_root)
        self.tool_registry = tool_registry
        self.history_file = (
            pathlib.Path(history_file)
            if history_file is not None
            else self.drive_root / "state" / HISTORY_FILENAME
        )
        self.top_k_skills = top_k_skills
        self.skill_score_threshold = skill_score_threshold
        self.task_classifier = TaskClassifier()

    @classmethod
    def invalidate_skills_cache(cls) -> None:
        cls._skills_cache.clear()

    @classmethod
    def routing_enabled(cls) -> bool:
        """Owner-controlled master switch (``OUROBOROS_SMART_ROUTING``)."""
        try:
            from ouroboros.config import get_smart_routing_enabled
            return get_smart_routing_enabled()
        except Exception:
            return False

    def route(
        self,
        task: Dict[str, Any],
        available: Optional[Set[str]] = None,
        *,
        task_type: Optional[str] = None,
        skill_preferences: Optional[Any] = None,
        branch: Optional[str] = None,
    ) -> RoutingResult:
        """Classify once, route tools and skills, record the decision.

        ``available`` is the registry's actual availability set (post
        subagent/contract filters); unknown tool names are never surfaced.

        ``task_type`` lets a caller that already classified (e.g. the harness
        tree) skip the classifier — classification still happens exactly once.
        ``skill_preferences`` is a branch-level bias (harness 不足 3) applied
        on top of the generic relevance scoring. ``branch`` names the harness
        branch that produced the preferences (recorded for the P2 feedback
        loop); it defaults to the task type when not supplied.
        """
        task_id = str(task.get("id") or "")
        task_type = task_type or self.task_classifier.classify(task)
        enabled = self.routing_enabled()

        full_available = set(available) if available is not None else set(self._registry_available())
        routed = self._route_tools(task_type, full_available)
        hidden = sorted(full_available - set(routed)) if enabled else []
        skill_rankings = self._route_skills(task_type, skill_preferences=skill_preferences)

        result = RoutingResult(
            task_type=task_type,
            task_id=task_id,
            branch=branch or task_type,
            tool_names=routed,
            skill_rankings=skill_rankings,
            enabled=enabled,
            hidden_tool_names=hidden,
        )
        self._record_routing(result, full_available)
        return result

    # -- tool routing ------------------------------------------------------ #

    def _registry_available(self) -> Set[str]:
        if self.tool_registry is None:
            return set()
        try:
            # Unfiltered availability: routing must never judge against the
            # round-one filter it set on a PREVIOUS task (the filter leaks
            # across consecutive tasks on one agent and shrinks the envelope).
            return set(self.tool_registry.available_tools_unfiltered())
        except Exception:
            try:
                return set(self.tool_registry.available_tools())
            except Exception:
                log.warning("SmartRouter: registry availability probe failed", exc_info=True)
                return set()

    def _route_tools(self, task_type: str, available: Set[str]) -> List[str]:
        selected = TOOL_SETS.get(task_type, TOOL_SETS[TASK_TYPE_SIMPLE])
        names = ALWAYS_ON_TOOLS | selected
        if available:
            names &= available
        return sorted(names)

    # -- skill routing ----------------------------------------------------- #

    def _load_skills(self) -> List[Any]:
        """Discover skills once per short window; never raises."""
        from ouroboros.skill_loader import discover_skills

        now = time.time()
        cached = self._skills_cache.get(self.drive_root)
        if cached is not None and (now - cached[0]) < self._skills_cache_ttl_sec:
            return list(cached[1])
        try:
            skills = discover_skills(self.drive_root)
        except Exception:
            log.warning("SmartRouter: skill discovery failed", exc_info=True)
            skills = []
        self._skills_cache[self.drive_root] = (now, skills)
        return list(skills)

    def _route_skills(
        self,
        task_type: str,
        *,
        skill_preferences: Optional[Any] = None,
    ) -> List[Tuple[str, float]]:
        task_tags = set(SKILL_TAG_MAPPING.get(task_type, ()))
        prefs = self._normalize_preferences(skill_preferences)
        rankings: List[Tuple[str, float]] = []
        pinned: List[Tuple[str, float]] = []
        for skill in self._load_skills():
            score = self._calculate_skill_score(skill, task_tags)
            score = self._apply_skill_preferences(skill, score, prefs)
            is_self_authored = bool(getattr(skill, "is_self_authored", False))
            if prefs["always"] and skill.name in prefs["always"]:
                pinned.append((skill.name, round(min(1.0, score), 3), is_self_authored))
            elif score >= self.skill_score_threshold:
                rankings.append((skill.name, round(score, 3), is_self_authored))
        # Self-authored skills are preferred over installed/native skills AT
        # EQUAL relevance (the owner's own curation wins ties). The score still
        # leads the ordering; self-authored is the tie-breaker.
        rankings.sort(key=lambda item: (item[1], item[2]), reverse=True)
        pinned.sort(key=lambda item: (item[1], item[2]), reverse=True)
        return [(name, score) for name, score, _ in (pinned + rankings)][: self.top_k_skills]

    @staticmethod
    def _normalize_preferences(skill_preferences: Optional[Any]) -> Dict[str, Any]:
        """Coerce a harness SkillPreferences (or plain dict) into a lookup shape."""
        if skill_preferences is None:
            return {"boost": {}, "tags": set(), "always": set()}
        if hasattr(skill_preferences, "boost"):
            return {
                "boost": dict(skill_preferences.boost or {}),
                "tags": {str(t) for t in (skill_preferences.tags or [])},
                "always": {str(name) for name in (skill_preferences.always or [])},
            }
        raw = dict(skill_preferences)
        return {
            "boost": {str(k): float(v) for k, v in dict(raw.get("boost") or {}).items()},
            "tags": {str(t) for t in (raw.get("tags") or [])},
            "always": {str(name) for name in (raw.get("always") or [])},
        }

    def _apply_skill_preferences(self, skill: Any, score: float, prefs: Dict[str, Any]) -> float:
        """Branch bias on top of generic relevance: named boost + tag boost."""
        boosted = score + prefs["boost"].get(str(getattr(skill, "name", "") or ""), 0.0)
        if prefs["tags"]:
            manifest = getattr(skill, "manifest", None)
            try:
                raw_tags = getattr(manifest, "raw_extra", {}).get("tags", [])
            except Exception:
                raw_tags = []
            skill_tags = {tag.lower() for tag in _flatten_tags(raw_tags)}
            if skill_tags & prefs["tags"]:
                boosted += 0.15
        return min(1.0, boosted)

    @staticmethod
    def _tag_hits_in_text(task_tags: Set[str], text: str) -> int:
        """Count task tags that appear as a word (or word-prefix) in ``text``.

        Uses word-boundary prefix matching so a stem tag like ``analyz`` hits
        ``analyzing`` but a short tag like ``code`` does NOT hit ``encode`` /
        ``compute`` — substring scanning was the reason real skills scored as
        relevant to every task type (v6.100+ smart-router audit).
        """
        words = [w for w in text.split() if w]
        hits = 0
        for tag in task_tags:
            if any(word.startswith(tag) for word in words):
                hits += 1
        return hits

    def _calculate_skill_score(self, skill: Any, task_tags: Set[str]) -> float:
        """Relevance of one loaded skill to the task-type tag set.

        Scored fields: manifest tags (frontmatter ``tags:``, via raw_extra),
        skill name, description, when_to_use and body. Base 0.5 so any skill
        can be recommended when nothing matches; each matching field adds a
        bounded increment.

        Text matches are a WEAK signal (+0.1 per tag, capped): by itself a
        text-only hit keeps a skill below the 0.6 threshold, so a long
        description cannot make an unrelated skill look relevant. Only the
        manifest tags (+0.3) and the skill name (+0.2) can carry a skill over
        the threshold on their own.
        """
        score = 0.5
        manifest = getattr(skill, "manifest", None)
        try:
            raw_tags = getattr(manifest, "raw_extra", {}).get("tags", [])
        except Exception:
            raw_tags = []
        skill_tags = {tag.lower() for tag in _flatten_tags(raw_tags)}
        if skill_tags & task_tags:
            score += 0.3

        name_lower = str(getattr(skill, "name", "") or "").lower()
        if any(tag in name_lower for tag in task_tags):
            score += 0.2

        desc_lower = " ".join([
            str(getattr(manifest, "description", "") or ""),
            str(getattr(manifest, "when_to_use", "") or ""),
            str(getattr(manifest, "body", "") or ""),
        ]).lower()
        score += min(0.2, 0.1 * self._tag_hits_in_text(task_tags, desc_lower))

        return min(1.0, score)

    # -- history ----------------------------------------------------------- #

    def _record_routing(self, result: RoutingResult, full_available: Set[str]) -> None:
        record = {
            "ts": utc_now_iso(),
            "task_id": result.task_id,
            "task_type": result.task_type,
            "branch": result.branch,
            "enabled": result.enabled,
            "available_tools_count": len(full_available),
            "tools_count": len(result.tool_names),
            "tools": result.tool_names,
            "skills_count": len(result.skill_rankings),
            "skills": [
                {"name": name, "score": score}
                for name, score in result.skill_rankings
            ],
        }
        try:
            append_jsonl(self.history_file, record)
        except Exception:
            log.warning("SmartRouter: failed to record routing history", exc_info=True)


__all__ = [
    "ALWAYS_ON_TOOLS",
    "DEFAULT_SKILL_SCORE_THRESHOLD",
    "DEFAULT_TOP_K_SKILLS",
    "HISTORY_FILENAME",
    "RoutingResult",
    "SKILL_TAG_MAPPING",
    "SmartRouter",
    "TASK_TYPE_CODING",
    "TASK_TYPE_KNOWLEDGE",
    "TASK_TYPE_RESEARCH",
    "TASK_TYPE_SIMPLE",
    "TOOL_SETS",
    "TaskClassifier",
    "VALID_TASK_TYPES",
]
