"""Harness tree (PAPER_INTEGRATION_ANALYSIS 不足 3): task-specific harness config.

The smart router (不足 1 + 不足 8) decides WHICH tools and skills a task sees;
the harness tree supplies the per-task-type ADJUSTMENTS on top of that shared
routing. It never reclassifies and never redefines a tool/skill list:

* **Tools** stay the smart router's ``TOOL_SETS[task_type]`` — the harness
  branch only *references* that set (``tool_set()``), never duplicates it, so
  the two cannot drift apart.
* **Skills** are scored by the smart router's generic relevance logic and then
  biased by the branch's ``skill_preferences`` (boost specific skills, boost a
  tag, pin skills that must always be recommended, or DEMOTE skills/tags that
  actively distract this task direction).
* **Tools** stay the smart router's ``TOOL_SETS[task_type]`` — the harness
  branch only references that set (``tool_set()``) and may NARROW it via
  ``tool_preferences.avoid`` (never widen, and control-plane tools can never
  be avoided).
* **System prompt** and **memory injection** are per-branch text/config that
  the context builder applies around the shared prompt (appended, never
  replacing the base SYSTEM.md — base capabilities stay resident). A branch
  may also ship an ``anti_patterns.md`` block (explicit negative guidance),
  rendered right after the positive extra as its own ``## Avoid`` section.

Branches are pre-defined, config-driven trees under ``harness_configs/``.
Missing or broken branches fall back to ``main``, which carries empty
adjustments and therefore behaves exactly like plain smart routing.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ouroboros.smart_router import (
    ALWAYS_ON_TOOLS,
    TASK_TYPE_SIMPLE,
    TOOL_SETS,
    VALID_TASK_TYPES,
)

log = logging.getLogger(__name__)

DEFAULT_BRANCH = "main"

MEMORY_CONFIG_FILENAME = "memory_config.json"
SKILL_PREFERENCES_FILENAME = "skill_preferences.json"
SYSTEM_PROMPT_EXTRA_FILENAME = "system_prompt_extra.md"
ANTI_PATTERNS_FILENAME = "anti_patterns.md"
TOOL_PREFERENCES_FILENAME = "tool_preferences.json"


def _read_json(path: pathlib.Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        log.warning("Harness: could not parse %s", path, exc_info=True)
        return {}


@dataclass
class SkillPreferences:
    """Per-branch skill bias applied on top of the smart router's scoring.

    ``boost`` adds a fixed score to a named skill; ``tags`` adds a smaller
    boost to any skill carrying one of these manifest tags; ``always`` pins
    skills into the recommendation regardless of the score threshold.
    ``demote``/``demote_tags`` are the NEGATIVE counterpart (L2 harness):
    named skills lose a fixed score, tag-matched skills lose a smaller one —
    a demoted skill falls below the recommendation threshold unless pinned.
    """

    boost: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    always: List[str] = field(default_factory=list)
    demote: List[str] = field(default_factory=list)
    demote_tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "SkillPreferences":
        raw = raw or {}
        boost_raw = raw.get("boost", {})
        boost: Dict[str, float] = {}
        if isinstance(boost_raw, dict):
            for name, value in boost_raw.items():
                try:
                    boost[str(name)] = float(value)
                except (TypeError, ValueError):
                    # One bad boost value must not poison the whole branch load.
                    log.warning(
                        "Harness: skipping non-numeric skill boost %r=%r", name, value
                    )
        return cls(
            boost=boost,
            tags=[str(t) for t in (raw.get("tags") or [])],
            always=[str(name) for name in (raw.get("always") or [])],
            demote=[str(name) for name in (raw.get("demote") or [])],
            demote_tags=[str(t) for t in (raw.get("demote_tags") or [])],
        )

    @classmethod
    def empty(cls) -> "SkillPreferences":
        return cls()

    @property
    def is_empty(self) -> bool:
        return not (
            self.boost or self.tags or self.always or self.demote or self.demote_tags
        )


@dataclass
class MemoryConfig:
    """Per-branch memory injection adjustments.

    ``include``/``exclude`` name the memory sections (stable: identity, world;
    volatile: scratchpad, dialogue, registry) to keep/drop; ``priority``
    reorders the injected sections; ``max_sections`` bounds how many sections
    are injected at all. Empty config == inject exactly as the base builder
    would.
    """

    include: Optional[List[str]] = None
    exclude: List[str] = field(default_factory=list)
    priority: List[str] = field(default_factory=list)
    max_sections: Optional[int] = None

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "MemoryConfig":
        raw = raw or {}
        return cls(
            include=[str(s) for s in (raw.get("include") or [])] or None,
            exclude=[str(s) for s in (raw.get("exclude") or [])],
            priority=[str(s) for s in (raw.get("priority") or [])],
            max_sections=raw.get("max_sections"),
        )

    @classmethod
    def empty(cls) -> "MemoryConfig":
        return cls()

    @property
    def is_empty(self) -> bool:
        return not self.include and not self.exclude and not self.priority and self.max_sections is None


@dataclass
class ToolPreferences:
    """Per-branch tool-envelope narrowing on top of the smart router's sets.

    ``avoid`` removes named tools from the branch's round-one envelope. Names
    are intersected with ``TOOL_SETS[task_type]`` (a reference, never a copy —
    the branch cannot add tools it does not know) and control-plane tools
    (``ALWAYS_ON_TOOLS``) can never be avoided; ``enable_tools`` remains the
    escape hatch for anything a branch did not pre-load. An empty config
    changes nothing: the smart router's set is used as-is.
    """

    avoid: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "ToolPreferences":
        raw = raw or {}
        return cls(avoid=[str(name) for name in (raw.get("avoid") or [])])

    @classmethod
    def empty(cls) -> "ToolPreferences":
        return cls()

    @property
    def is_empty(self) -> bool:
        return not self.avoid

    def excluded_tools(self, task_type: str) -> frozenset:
        """Tool names this branch drops from the envelope (already intersected
        with the branch's tool set and never touching the control plane)."""
        if not self.avoid:
            return frozenset()
        envelope = TOOL_SETS.get(task_type, TOOL_SETS[TASK_TYPE_SIMPLE])
        return frozenset(
            name for name in self.avoid
            if name in envelope and name not in ALWAYS_ON_TOOLS
        )


@dataclass
class HarnessBranch:
    """One task-type harness branch: prompt/anti-pattern/memory/skill/tool
    adjustments only.

    Tools are intentionally NOT an owned list — they come from
    ``smart_router.TOOL_SETS[self.task_type]`` via :meth:`tool_set`, and may
    only be narrowed via :meth:`avoided_tools`.
    """

    name: str
    task_type: str = DEFAULT_BRANCH
    system_prompt_extra: str = ""
    anti_patterns: str = ""
    memory_config: MemoryConfig = field(default_factory=MemoryConfig.empty)
    skill_preferences: SkillPreferences = field(default_factory=SkillPreferences.empty)
    tool_preferences: ToolPreferences = field(default_factory=ToolPreferences.empty)
    source_dir: Optional[pathlib.Path] = None

    def tool_set(self) -> frozenset:
        """The tool envelope for this branch = the smart router's set (reference,
        never a copy, so the two cannot drift). Falls back to ``main``'s simple
        set when the branch maps no task type."""
        return TOOL_SETS.get(self.task_type, TOOL_SETS[TASK_TYPE_SIMPLE])

    def avoided_tools(self) -> frozenset:
        """Round-one envelope narrowing for this branch (never touches the
        control plane; empty when the branch configures no ``avoid``)."""
        return self.tool_preferences.excluded_tools(self.task_type)

    @property
    def is_main(self) -> bool:
        return self.name == DEFAULT_BRANCH


class HarnessTree:
    """Loads the pre-defined harness config tree and selects a branch by task type.

    Selection is by task_type (the smart router classifies exactly once; the
    harness tree never reclassifies). Missing/broken branches fall back to the
    ``main`` branch — empty adjustments == plain smart routing.
    """

    def __init__(self, config_dir: pathlib.Path):
        self.config_dir = pathlib.Path(config_dir)
        self.branches: Dict[str, HarnessBranch] = {}
        self._main_branch: Optional[HarnessBranch] = None
        self._load()

    def _load(self) -> None:
        if not self.config_dir.is_dir():
            log.warning("Harness: config dir missing, using empty main only: %s", self.config_dir)
            self._main_branch = HarnessBranch(name=DEFAULT_BRANCH, task_type=DEFAULT_BRANCH)
            return
        for branch_dir in self.config_dir.iterdir():
            if not branch_dir.is_dir():
                continue
            branch_name = branch_dir.name
            task_type = branch_name if branch_name in VALID_TASK_TYPES else DEFAULT_BRANCH

            def _load_config(loader, raw):
                try:
                    return loader(raw)
                except Exception:
                    log.warning(
                        "Harness: %s config failed for branch %s, using empty",
                        loader.__name__, branch_name, exc_info=True,
                    )
                    return loader({})

            branch = HarnessBranch(
                name=branch_name,
                task_type=task_type,
                system_prompt_extra=self._read_text_file(branch_dir, SYSTEM_PROMPT_EXTRA_FILENAME),
                anti_patterns=self._read_text_file(branch_dir, ANTI_PATTERNS_FILENAME),
                memory_config=_load_config(
                    MemoryConfig.from_dict,
                    _read_json(branch_dir / MEMORY_CONFIG_FILENAME),
                ),
                skill_preferences=_load_config(
                    SkillPreferences.from_dict,
                    _read_json(branch_dir / SKILL_PREFERENCES_FILENAME),
                ),
                tool_preferences=_load_config(
                    ToolPreferences.from_dict,
                    _read_json(branch_dir / TOOL_PREFERENCES_FILENAME),
                ),
                source_dir=branch_dir,
            )
            if branch_name == DEFAULT_BRANCH:
                self._main_branch = branch
            else:
                self.branches[branch_name] = branch
        if self._main_branch is None:
            self._main_branch = HarnessBranch(name=DEFAULT_BRANCH, task_type=DEFAULT_BRANCH)

    @staticmethod
    def _read_text_file(branch_dir: pathlib.Path, filename: str) -> str:
        try:
            return (branch_dir / filename).read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def select_branch(self, task_type: str) -> HarnessBranch:
        """Pick the branch for a classified task type; anything missing falls
        back to ``main`` (empty adjustments == plain smart routing)."""
        if task_type in self.branches:
            return self.branches[task_type]
        return self._main_branch  # type: ignore[return-value]

    def branch_names(self) -> List[str]:
        names = [DEFAULT_BRANCH]
        names.extend(sorted(self.branches))
        return names


__all__ = [
    "DEFAULT_BRANCH",
    "HarnessBranch",
    "HarnessTree",
    "MemoryConfig",
    "SkillPreferences",
    "ToolPreferences",
]
