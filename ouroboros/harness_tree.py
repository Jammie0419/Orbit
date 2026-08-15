"""Harness tree (PAPER_INTEGRATION_ANALYSIS 不足 3): task-specific harness config.

The smart router (不足 1 + 不足 8) decides WHICH tools and skills a task sees;
the harness tree supplies the per-task-type ADJUSTMENTS on top of that shared
routing. It never reclassifies and never redefines a tool/skill list:

* **Tools** stay the smart router's ``TOOL_SETS[task_type]`` — the harness
  branch only *references* that set (``tool_set()``), never duplicates it, so
  the two cannot drift apart.
* **Skills** are scored by the smart router's generic relevance logic and then
  biased by the branch's ``skill_preferences`` (boost specific skills, boost a
  tag, or pin skills that must always be recommended).
* **System prompt** and **memory injection** are per-branch text/config that
  the context builder applies around the shared prompt (appended, never
  replacing the base SYSTEM.md — base capabilities stay resident).

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
    TASK_TYPE_SIMPLE,
    TOOL_SETS,
    VALID_TASK_TYPES,
)

log = logging.getLogger(__name__)

DEFAULT_BRANCH = "main"

MEMORY_CONFIG_FILENAME = "memory_config.json"
SKILL_PREFERENCES_FILENAME = "skill_preferences.json"
SYSTEM_PROMPT_EXTRA_FILENAME = "system_prompt_extra.md"


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
    """

    boost: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    always: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "SkillPreferences":
        raw = raw or {}
        boost_raw = raw.get("boost", {})
        boost = {
            str(name): float(value)
            for name, value in boost_raw.items()
            if isinstance(boost_raw, dict)
        }
        return cls(
            boost=boost,
            tags=[str(t) for t in (raw.get("tags") or [])],
            always=[str(name) for name in (raw.get("always") or [])],
        )

    @classmethod
    def empty(cls) -> "SkillPreferences":
        return cls()

    @property
    def is_empty(self) -> bool:
        return not self.boost and not self.tags and not self.always


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
class HarnessBranch:
    """One task-type harness branch: prompt/memory/skill adjustments only.

    Tools are intentionally NOT a member — they come from
    ``smart_router.TOOL_SETS[self.task_type]`` via :meth:`tool_set`.
    """

    name: str
    task_type: str = DEFAULT_BRANCH
    system_prompt_extra: str = ""
    memory_config: MemoryConfig = field(default_factory=MemoryConfig.empty)
    skill_preferences: SkillPreferences = field(default_factory=SkillPreferences.empty)
    source_dir: Optional[pathlib.Path] = None

    def tool_set(self) -> frozenset:
        """The tool envelope for this branch = the smart router's set (reference,
        never a copy, so the two cannot drift). Falls back to ``main``'s simple
        set when the branch maps no task type."""
        return TOOL_SETS.get(self.task_type, TOOL_SETS[TASK_TYPE_SIMPLE])

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
            branch = HarnessBranch(
                name=branch_name,
                task_type=task_type,
                system_prompt_extra=self._read_system_prompt_extra(branch_dir),
                memory_config=MemoryConfig.from_dict(
                    _read_json(branch_dir / MEMORY_CONFIG_FILENAME)
                ),
                skill_preferences=SkillPreferences.from_dict(
                    _read_json(branch_dir / SKILL_PREFERENCES_FILENAME)
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
    def _read_system_prompt_extra(branch_dir: pathlib.Path) -> str:
        try:
            return (branch_dir / SYSTEM_PROMPT_EXTRA_FILENAME).read_text(encoding="utf-8").strip()
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
]
