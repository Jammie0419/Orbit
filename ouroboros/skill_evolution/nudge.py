"""Nudge engine — the periodic review cadence for skill evolution (Phase 3).

The paper's 1-hour timer becomes a task-boundary check: the engine is only
consulted when a task finishes, and ``is_due()`` compares the wall clock
against the previous nudge's timestamp (``state/skill_nudges.jsonl``). The
analysis itself is rule-based (no LLM):

* ``failed_skills`` — skills whose ``skill_exec`` rows errored recently
  (evolution candidates are filtered by the evolver's own gates later);
* ``best_reusable_task`` — the most tool-rich successful recent task, a
  generation candidate when the current task did not qualify.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ouroboros.utils import append_jsonl, utc_now_iso

log = logging.getLogger(__name__)

NUDGES_REL = pathlib.Path("state") / "skill_nudges.jsonl"
TOOLS_LOG_REL = pathlib.Path("logs") / "tools.jsonl"

# Paper spec cadence (1 hour). The worker probes on task boundaries only.
NUDGE_INTERVAL_SEC = 3600.0

# Scan bounds: at most this many recent tool rows / distinct tasks are viewed.
RECENT_ROWS = 400
RECENT_TASK_LIMIT = 10
MIN_REUSABLE_TOOL_CALLS = 5


class SkillNudgeEngine:
    """Task-boundary cadence + rule-based recent-work analysis."""

    def __init__(self, drive_root: pathlib.Path):
        self.drive_root = pathlib.Path(drive_root)
        self.nudges_path = self.drive_root / NUDGES_REL

    def is_due(self, now: Optional[float] = None) -> bool:
        """True when at least ``NUDGE_INTERVAL_SEC`` elapsed since the last
        nudge (or no nudge was ever recorded / the timestamp is unparsable)."""
        last = self._last_nudge_ts()
        if not last:
            return True
        now = time.time() if now is None else now
        try:
            parsed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            elapsed = now - parsed.timestamp()
        except Exception:
            return True  # unparsable timestamp: assume stale, allow a nudge
        return elapsed >= NUDGE_INTERVAL_SEC

    def analyze_recent(self) -> Dict[str, Any]:
        """Rule-based scan of recent tool rows: failed skills + the best
        reusable recent task. Never raises."""
        rows = self._read_rows()
        failed_skills: List[str] = []
        best_task: Optional[Dict[str, Any]] = None
        task_rows: Dict[str, int] = {}
        task_last_error: Dict[str, bool] = {}
        for row in rows:
            task_id = str(row.get("task_id") or "")
            tool = str(row.get("tool") or "")
            is_error = bool(row.get("is_error")) or str(
                row.get("status") or "").strip().lower() in {"error", "timeout"}
            if tool == "skill_exec":
                args = row.get("args")
                name = args.get("skill") if isinstance(args, dict) else ""
                if is_error and name and name not in failed_skills:
                    failed_skills.append(str(name))
            if task_id:
                task_rows[task_id] = task_rows.get(task_id, 0) + 1
                task_last_error[task_id] = is_error
        for task_id, count in task_rows.items():
            if count < MIN_REUSABLE_TOOL_CALLS:
                continue
            if task_last_error.get(task_id):
                continue
            if best_task is None or count > best_task["tool_calls"]:
                best_task = {"task_id": task_id, "tool_calls": count}
        return {
            "failed_skills": failed_skills,
            "best_reusable_task": best_task,
            "task_count": len(task_rows),
        }

    def record(self, analysis: Dict[str, Any]) -> None:
        """Persist one nudge row (and thereby the cadence watermark)."""
        try:
            append_jsonl(self.nudges_path, {
                "ts": utc_now_iso(),
                "analysis": analysis,
            })
        except Exception:
            log.debug("skill evolution: nudge record failed", exc_info=True)

    # -- internals --------------------------------------------------------- #

    def _last_nudge_ts(self) -> str:
        rows = self._read_nudges()
        if not rows:
            return ""
        return str(rows[-1].get("ts") or "")

    def _read_nudges(self) -> List[Dict[str, Any]]:
        if not self.nudges_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with self.nudges_path.open(encoding="utf-8") as fh:
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
            log.debug("skill evolution: nudges read failed", exc_info=True)
        return out

    def _read_rows(self) -> List[Dict[str, Any]]:
        path = self.drive_root / TOOLS_LOG_REL
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
            log.debug("skill evolution: tools.jsonl read failed", exc_info=True)
        return out[-RECENT_ROWS:]