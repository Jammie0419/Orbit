"""Per-skill execution ledger (Phase 3 前置工程).

``skill_exec`` records its lifecycle in ``logs/events.jsonl`` and every call in
``logs/tools.jsonl`` (``tool="skill_exec"``), but nothing aggregates outcomes
per skill. This module rebuilds that accounting offline and idempotently into
``state/skill_stats.json``::

    {"<skill>": {"execution_count": int, "success_count": int,
                 "success_rate": float, "first_ts": str, "last_ts": str,
                 "evolution_version": int}}

Consumers:

* the GEPA gate — at least ``EVOLUTION_MIN_EXECUTIONS`` runs and a success
  rate below ``EVOLUTION_MAX_SUCCESS_RATE``;
* the router's quality-aware scoring — success-rate and version boosts.

``logs/tools.jsonl`` is the single source of truth (one row per call, with
``is_error``/``status``); ``events.jsonl`` is not folded in because the same
skill_exec call is logged in both files and would double-count.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

from ouroboros.utils import atomic_write_json

log = logging.getLogger(__name__)

STATS_REL = pathlib.Path("state") / "skill_stats.json"
TOOLS_LOG_REL = pathlib.Path("logs") / "tools.jsonl"

# GEPA gate requirements (PAPER Phase 3 spec values).
EVOLUTION_MIN_EXECUTIONS = 10
EVOLUTION_MAX_SUCCESS_RATE = 0.8

_ERROR_STATUSES = {"error", "timeout", "failed"}


def _skill_name_from_args(args: Any) -> str:
    """Extract the skill name from a logged ``skill_exec`` args value.

    The sanitized log keeps ``{"skill": "...", "script": "..."}`` (secrets are
    scrubbed at write time); tolerate JSON-encoded and bare-string shapes.
    """
    if isinstance(args, dict):
        for key in ("skill", "skill_name", "name"):
            value = args.get(key)
            if value:
                return str(value).strip()
        return ""
    if isinstance(args, str):
        text = args.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict):
                return _skill_name_from_args(data)
        return text[:80]
    return ""


def _row_is_error(row: Dict[str, Any]) -> bool:
    if bool(row.get("is_error")):
        return True
    status = str(row.get("status") or "").strip().lower()
    return status in _ERROR_STATUSES


class SkillStatsLedger:
    """Offline, idempotent per-skill outcome accounting + statistic merge."""

    def __init__(self, drive_root: pathlib.Path):
        self.drive_root = pathlib.Path(drive_root)
        self.stats_path = self.drive_root / STATS_REL

    # -- aggregation ------------------------------------------------------- #

    def aggregate(self) -> Dict[str, Dict[str, Any]]:
        """Rebuild ``state/skill_stats.json`` from ``logs/tools.jsonl``.

        Prior ``evolution_version`` values survive the rebuild; count fields
        always reflect the current log window (append-only with rotation).
        Never raises.
        """
        counts: Dict[str, Dict[str, Any]] = {}
        try:
            rows = _read_jsonl(self.drive_root / TOOLS_LOG_REL)
        except Exception:
            log.debug("skill evolution: tools.jsonl read failed", exc_info=True)
            rows = []
        for row in rows:
            if str(row.get("tool") or "") != "skill_exec":
                continue
            name = _skill_name_from_args(row.get("args"))
            if not name:
                continue
            entry = counts.setdefault(name, {
                "execution_count": 0,
                "success_count": 0,
                "first_ts": "",
                "last_ts": "",
            })
            entry["execution_count"] += 1
            if not _row_is_error(row):
                entry["success_count"] += 1
            ts = str(row.get("ts") or "")
            if ts:
                if not entry["first_ts"] or ts < entry["first_ts"]:
                    entry["first_ts"] = ts
                if ts > entry["last_ts"]:
                    entry["last_ts"] = ts
        prev = self.load()
        result: Dict[str, Dict[str, Any]] = {}
        for name, entry in counts.items():
            count = int(entry["execution_count"] or 0)
            entry["success_rate"] = round(
                int(entry["success_count"]) / count, 4) if count else 0.0
            entry["evolution_version"] = int(
                (prev.get(name) or {}).get("evolution_version") or 1)
            result[name] = entry
        try:
            atomic_write_json(self.stats_path, result)
        except Exception:
            log.debug("skill evolution: stats write failed", exc_info=True)
        return result

    # -- reads ------------------------------------------------------------- #

    def load(self) -> Dict[str, Dict[str, Any]]:
        """Current ledger contents (empty dict when absent/broken)."""
        data = _read_json(self.stats_path)
        return data if isinstance(data, dict) else {}

    def get(self, name: str) -> Dict[str, Any]:
        return dict(self.load().get(str(name), {}))

    def attach_to_skills(self, skills: List[Any]) -> List[Any]:
        """Merge each skill's ledger entry onto the LoadedSkill object.

        The router reads ``skill.skill_stats`` during scoring; skills without
        an entry carry ``{}`` so every quality increment stays zero.
        """
        stats = self.load()
        for skill in skills:
            try:
                setattr(skill, "skill_stats", dict(stats.get(str(skill.name), {})))
            except Exception:
                pass
        return skills

    def bump_evolution_version(self, name: str) -> int:
        """Increment ``evolution_version`` for one skill after an accepted
        evolution (merge-preserving write). Returns the new version."""
        data = self.load()
        entry = dict(data.get(str(name)) or {})
        new_version = int(entry.get("evolution_version") or 1) + 1
        entry["evolution_version"] = new_version
        data[str(name)] = entry
        try:
            atomic_write_json(self.stats_path, data)
        except Exception:
            log.debug("skill evolution: version bump write failed", exc_info=True)
        return new_version


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
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
    return out


def _read_json(path: pathlib.Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None