"""Automatic skill generation from successful task trajectories (Phase 3).

A qualifying task — more than ``MIN_TOOL_CALLS`` tool steps, at least one
self-repair (an error step followed by a recovered step), and a successful
outcome — can be distilled into a reusable self-authored skill. The generator:

1. reuses the evolution layer's trace rebuild + credit scoring
   (``load_task_steps`` / ``assign_credits`` / ``identify_critical_steps``) to
   pick the steps that carried the task;
2. asks the main model slot for a complete skill package (manifest + scripts);
3. validates the shape (safe names, non-empty scripts),
4. writes it under the data-plane ``skills/self/<name>/`` tree with the dual
   self-authored markers (``write_self_authored_markers``), and
5. records the attempt in ``state/skill_generation_history.jsonl``.

Generated skills start ``pending`` review + ``disabled`` — the normal
review/attestation gates decide executability. Everything degrades silently
(no LLM client, LLM failure, invalid shape) and never raises.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

from ouroboros.contracts.skill_manifest import canonical_skill_name
from ouroboros.skill_loader import write_self_authored_markers
from ouroboros.utils import append_jsonl, read_json_dict, utc_now_iso

log = logging.getLogger(__name__)

# Data-plane buckets; "self" is a generic grouping container that discovery
# walks (see _walk_skill_packages) and the markers classify as self_authored.
SELF_BUCKET = "self"
MIN_TOOL_CALLS = 5
MAX_TAGS = 8
GENERATION_HISTORY_REL = pathlib.Path("state") / "skill_generation_history.jsonl"

_SAFE_SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_CALL_TYPE = "skill_auto_generation"
_MAX_TOKENS = 4096
_REASONING = "medium"

# Outcome hints that count as "the task succeeded" before falling back to the
# trace's final step (the pipeline passes reflection_entry/task status fields).
_SUCCESS_WORDS = {"success", "succeeded", "completed", "done", "ok", "pass"}


def _default_main_model() -> str:
    """Main-slot model (same resolution as the evolution layer; never empty)."""
    from ouroboros.config import SETTINGS_DEFAULTS
    return str(os.environ.get("OUROBOROS_MODEL", "") or SETTINGS_DEFAULTS["OUROBOROS_MODEL"]).strip()


def task_succeeded(outcome_hint: str, steps: List[Dict[str, Any]]) -> bool:
    """Explicit success signal wins; otherwise the trace's final step decides."""
    hint = str(outcome_hint or "").strip().lower()
    if hint:
        return hint in _SUCCESS_WORDS or hint.startswith("success")
    return bool(steps) and not bool(steps[-1].get("is_error"))


def recent_review_flags(
    drive_root: pathlib.Path,
    skill_name: str = "",
    limit: int = 6,
) -> List[str]:
    """Recent reviewer FAIL findings, formatted for prompt injection.

    With ``skill_name``, only that skill's review history is consulted
    (evolution time — "what the reviewer kept flagging about THIS skill").
    Without it, every skill's current ``review.json`` verdict is scanned
    (generation time — "what patterns reviewers recently flagged").
    Returns bounded, deduplicated one-line digests; empty when nothing failed.
    """
    flags: List[str] = []
    seen: set = set()

    def _collect(status: str, findings: Any) -> None:
        if str(status or "").lower() not in {"blockers", "warnings"}:
            return
        try:
            from ouroboros.skill_review_history import extract_fail_findings
            entries = extract_fail_findings(findings if isinstance(findings, list) else [])
        except Exception:
            entries = []
        for entry in entries:
            item = str(entry.get("item") or "?")
            severity = str(entry.get("severity") or "")
            reason = str(entry.get("reason_excerpt") or "").replace("\n", " ")[:160]
            line = f"[{severity}] {item}: {reason}".strip()
            signature = f"{item}:{severity}"
            if signature in seen or not line:
                continue
            seen.add(signature)
            flags.append(line)

    drive_root = pathlib.Path(drive_root)
    try:
        if skill_name:
            markers_root = (
                pathlib.Path(drive_root) / "state" / "skills"
                / canonical_skill_name(skill_name)
            )
            current = read_json_dict(markers_root / "review.json") or {}
            _collect(str(current.get("status") or ""), current.get("findings"))
            history_path = markers_root / "review_history.jsonl"
            if history_path.exists():
                for line in list(history_path.read_text(encoding="utf-8").splitlines())[-3:]:
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(row, dict):
                        _collect(str(row.get("status") or ""), row.get("findings"))
        else:
            skills_state = pathlib.Path(drive_root) / "state" / "skills"
            if skills_state.is_dir():
                for entry in sorted(skills_state.iterdir()):
                    data = read_json_dict(entry / "review.json") or {}
                    _collect(str(data.get("status") or ""), data.get("findings"))
                    if len(flags) >= limit:
                        break
    except Exception:
        log.debug("skill evolution: review flags read failed", exc_info=True)
    return flags[:limit]


def render_skill_manifest(skill: Dict[str, Any]) -> str:
    """Render a skill dict to SKILL.md (YAML frontmatter + body).

    Script code is NOT embedded in the frontmatter (a code line ``---`` would
    terminate the YAML block early); scripts live in ``scripts/`` files and the
    frontmatter only lists their names, exactly like data_write-authored skills.
    """
    import yaml  # type: ignore

    tags = [str(t) for t in (skill.get("tags") or []) if str(t).strip()][:MAX_TAGS]
    front = {
        "name": canonical_skill_name(skill.get("name") or ""),
        "description": str(skill.get("description") or ""),
        "version": str(skill.get("version") or "1.0"),
        "type": str(skill.get("type") or "script"),
        "when_to_use": str(skill.get("when_to_use") or ""),
        "timeout_sec": int(skill.get("timeout_sec") or 60),
        "scripts": [str(s["name"]) for s in (skill.get("scripts") or [])],
        "tags": tags,
    }
    try:
        front_yaml = yaml.safe_dump(front, sort_keys=False, allow_unicode=True)
    except Exception:
        front_yaml = yaml.safe_dump(front, sort_keys=False)
    body = str(skill.get("body") or "")
    if body.strip():
        return f"---\n{front_yaml}---\n{body.strip()}\n"
    return f"---\n{front_yaml}---\n"


def _write_text_atomic(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_skill_package(
    drive_root: pathlib.Path,
    skill: Dict[str, Any],
    *,
    task_id: str = "",
    created_by_tool: str = "skill_auto_generation",
) -> pathlib.Path:
    """Write a validated skill dict under ``skills/self/<name>/`` + markers.

    Markers are written LAST so the initial content hash covers the payload.
    Returns the skill directory. Callers validate before calling.
    """
    name = canonical_skill_name(skill.get("name") or "")
    skill_dir = pathlib.Path(drive_root) / "skills" / SELF_BUCKET / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(skill_dir / "SKILL.md", render_skill_manifest(skill))
    for script in skill.get("scripts") or []:
        script_path = skill_dir / "scripts" / str(script["name"])
        _write_text_atomic(script_path, str(script.get("code") or ""))
    write_self_authored_markers(
        skill_dir,
        pathlib.Path(drive_root),
        task_id=task_id,
        created_by_tool=created_by_tool,
    )
    return skill_dir


def validate_generated_skill(skill: Any) -> Optional[str]:
    """Structural validation of an LLM-generated skill; returns an error
    reason or None (mutating the dict into the canonical shape)."""
    if not isinstance(skill, dict):
        return "not_a_dict"
    name = canonical_skill_name(skill.get("name") or "")
    if not name or name == "_unnamed":
        return "missing_name"
    skill["name"] = name
    stype = str(skill.get("type") or "script").strip().lower()
    if stype == "script":
        scripts = skill.get("scripts")
        if not isinstance(scripts, list) or not scripts:
            return "script_type_requires_scripts"
        cleaned: List[Dict[str, str]] = []
        for item in scripts:
            if not isinstance(item, dict):
                return "script_item_not_dict"
            sname = str(item.get("name") or "").strip()
            if not _SAFE_SCRIPT_NAME_RE.fullmatch(sname):
                return "unsafe_script_name"
            code = str(item.get("code") or "")
            if not code.strip():
                return "empty_script_code"
            cleaned.append({"name": sname, "code": code})
        skill["scripts"] = cleaned
    elif stype == "instruction":
        if not str(skill.get("body") or "").strip():
            return "instruction_requires_body"
        skill["scripts"] = []
    else:
        return "unsupported_type"
    skill["type"] = stype
    skill["tags"] = [str(t) for t in (skill.get("tags") or []) if str(t).strip()][:MAX_TAGS]
    skill["runtime"] = str(skill.get("runtime") or "python").strip().lower() or "python"
    return None


class SkillAutoGenerator:
    """Turn a successful self-repairing task trace into a self-authored skill."""

    def __init__(self, drive_root: pathlib.Path, llm_client: Any = None):
        self.drive_root = pathlib.Path(drive_root)
        self.llm_client = llm_client
        self.history_path = self.drive_root / GENERATION_HISTORY_REL

    # -- gates ------------------------------------------------------------- #

    def is_eligible(self, steps: List[Dict[str, Any]], outcome_hint: str = "") -> bool:
        """Paper trigger: >5 tool calls, at least one self-repair, task success."""
        if not isinstance(steps, list) or len(steps) < MIN_TOOL_CALLS:
            return False
        if not task_succeeded(outcome_hint, steps):
            return False
        return any(
            bool(steps[i].get("is_error"))
            and i + 1 < len(steps)
            and not bool(steps[i + 1].get("is_error"))
            for i in range(len(steps) - 1)
        )

    def already_generated_for_task(self, task_id: str) -> bool:
        """History guard: this task already produced a skill (or failed)."""
        task_id = str(task_id or "").strip()
        if not task_id:
            return False
        rows = _read_jsonl(self.history_path)
        return any(str(row.get("task_id") or "") == task_id for row in rows)

    def name_exists(self, name: str) -> bool:
        """Discovery guard: a skill with this canonical name already exists
        (any bucket/repo) — never overwrite an existing package."""
        try:
            from ouroboros.skill_loader import discover_skills
            skills = discover_skills(self.drive_root)
        except Exception:
            log.debug("skill evolution: discovery check failed", exc_info=True)
            return True  # fail closed: do not clobber on discovery errors
        return any(str(getattr(s, "name", "") or "") == canonical_skill_name(name) for s in skills)

    # -- entry points ------------------------------------------------------ #

    def maybe_generate_for_task(
        self,
        task_id: str,
        goal: str = "",
        outcome_hint: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Gate + dedupe + generate for one task. Returns the record on
        success, None on skip/failure. Never raises."""
        try:
            task_id = str(task_id or "").strip()
            if not task_id:
                return None
            if steps is None:
                from ouroboros.evolution.trajectory_experience_learner import (
                    TrajectoryExperienceLearner,
                )
                steps = TrajectoryExperienceLearner(self.drive_root).load_task_steps(task_id)
            if not self.is_eligible(steps, outcome_hint=outcome_hint):
                return None
            if self.already_generated_for_task(task_id):
                return None
            return self.generate_for_task(task_id, goal=goal, steps=steps)
        except Exception:
            log.debug("skill evolution: auto-generation failed", exc_info=True)
            return None

    def generate_for_task(
        self,
        task_id: str,
        steps: List[Dict[str, Any]],
        goal: str = "",
    ) -> Optional[Dict[str, Any]]:
        """LLM extraction + validation + write. Returns the history record."""
        skill = self._extract_skill(task_id, goal, steps)
        if skill is None:
            self._record(task_id, skill_name="", outcome="failed",
                         reason="llm_extraction_failed")
            return None
        reason = validate_generated_skill(skill)
        if reason is not None:
            self._record(task_id, skill_name="", outcome="failed", reason=reason)
            return None
        name = canonical_skill_name(skill["name"])
        if self.name_exists(name):
            self._record(task_id, skill_name=name, outcome="skipped",
                         reason="name_exists")
            return None
        write_skill_package(
            self.drive_root, skill, task_id=task_id,
            created_by_tool="skill_auto_generation",
        )
        record = {
            "ts": utc_now_iso(),
            "task_id": task_id,
            "skill_name": name,
            "skill_description": str(skill.get("description") or "")[:200],
            "type": str(skill.get("type") or ""),
            "outcome": "created",
            "reason": "",
        }
        self._record_from(record)
        return record

    # -- internals --------------------------------------------------------- #

    def _extract_skill(
        self,
        task_id: str,
        goal: str,
        steps: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if self.llm_client is None:
            return None
        key_steps = self._key_steps(steps)
        if not key_steps:
            return None
        review_flags = recent_review_flags(self.drive_root)
        review_block = ""
        if review_flags:
            review_block = (
                "\n[Reviewer flags to avoid (recent skill reviews)]\n- "
                + "\n- ".join(review_flags)
                + "\nThe distilled skill MUST NOT repeat these flagged patterns.\n"
            )
        prompt = f"""You are distilling ONE reusable skill from a successful agent task trace.

[Task goal]
{str(goal or "")[:800] or "(unknown — infer the intent from the steps)"}

[Key steps — top rows carried the task, bottom rows dragged it (credit-ranked)]
{json.dumps(key_steps, ensure_ascii=False, indent=2)}
{review_block}
Return ONLY a JSON object (no prose around it):
{{
  "name": "kebab-case-name (letters/digits/dash/underscore/dot only, <=64 chars)",
  "description": "one paragraph — what it accomplishes and when to use it",
  "type": "script",
  "runtime": "python",
  "when_to_use": "whenever a task looks like ...",
  "parameters": {{"arg1": {{"type": "string", "description": "..."}}}},
  "tags": ["2-5 short lowercase tags that a task classifier would match"],
  "scripts": [
    {{"name": "main.py", "code": "#!/usr/bin/env python3\\n…complete runnable code…"}}
  ]
}}

Rules:
- name and script names: ONLY [A-Za-z0-9._-], no spaces, no paths.
- script code must be complete and self-contained (stdlib only, unless you
  vendor the dependency inside the skill directory).
- stay concrete to THIS trace; do not invent unrelated capabilities.
"""
        try:
            from ouroboros.llm_observability import chat_observed

            resp, _usage = chat_observed(
                self.llm_client,
                drive_root=self.drive_root,
                task_id=task_id,
                call_type=_CALL_TYPE,
                messages=[{"role": "user", "content": prompt}],
                model=_default_main_model(),
                reasoning_effort=_REASONING,
                max_tokens=_MAX_TOKENS,
            )
            content = (resp.get("content") or "") if isinstance(resp, dict) else ""
        except Exception:
            log.debug("skill evolution: generation LLM call failed", exc_info=True)
            return None
        return _loose_json(str(content))

    def _key_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Credit-rank the trace (evolution-layer core) and keep the carried
        steps (top-3) plus the dragged ones (lowest-2)."""
        try:
            from ouroboros.evolution.trajectory_experience_learner import (
                TrajectoryExperienceLearner,
            )

            learner = TrajectoryExperienceLearner(self.drive_root)
            credits = learner.assign_credits(steps)
            critical = learner.identify_critical_steps(credits) or []
        except Exception:
            log.debug("skill evolution: step ranking failed", exc_info=True)
            critical = []
        by_id = {int(s.get("step_id", -1)): s for s in steps}
        out: List[Dict[str, Any]] = []
        for entry in critical:
            step = by_id.get(int(entry.get("step_id", -1)))
            if step is None:
                continue
            out.append({
                "tool": str(step.get("tool") or ""),
                "ok": not bool(step.get("is_error")),
                "args": str(step.get("args") or "")[:400],
                "result": str(step.get("result_preview") or "")[:200],
            })
        return out[:8]

    def _record(self, task_id: str, *, skill_name: str, outcome: str, reason: str) -> None:
        self._record_from({
            "ts": utc_now_iso(),
            "task_id": str(task_id or ""),
            "skill_name": str(skill_name or ""),
            "skill_description": "",
            "type": "",
            "outcome": str(outcome or ""),
            "reason": str(reason or ""),
        })

    def _record_from(self, record: Dict[str, Any]) -> None:
        try:
            append_jsonl(self.history_path, record)
        except Exception:
            log.debug("skill evolution: generation history write failed", exc_info=True)


def _loose_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except Exception:
        log.debug("skill evolution: jsonl read failed", exc_info=True)
    return out


# Keep the round-trip contract importable for callers that validate written
# packages (the evolver re-parses rendered manifests).
__all__ = [
    "SkillAutoGenerator", "validate_generated_skill", "write_skill_package",
    "render_skill_manifest", "task_succeeded", "MIN_TOOL_CALLS", "SELF_BUCKET",
]