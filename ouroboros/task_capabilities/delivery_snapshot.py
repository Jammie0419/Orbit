# task-capability (ablation): generic — does not participate in evolution
"""Workspace delivery snapshot for deadline finalization.

Reads the workspace's git status (or file listing if not a git repo) and
produces a concise summary that can be injected into the forced-finalization
prompt. This gives the agent visibility into what it has actually written,
preventing the common failure mode of deadline expiry with no deliverables
in the workspace root.

Switch: OUROBOROS_CAP_DELIVERY_SNAPSHOT=1 (default 0 = off).
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SNAPSHOT_LIMIT = 20
_TIMEOUT_SEC = 5.0


def enabled() -> bool:
    return os.environ.get("OUROBOROS_CAP_DELIVERY_SNAPSHOT", "0").strip() in ("1", "true", "yes")


def workspace_snapshot(workspace_root: str | Path, *, limit: int = _SNAPSHOT_LIMIT) -> str:
    """Read workspace state and return a concise summary string.

    Tries git status --porcelain first (most informative); falls back to
    os.listdir if not a git repo or git is unavailable. Fail-soft: any
    exception returns an empty string (the caller should not crash).
    """
    if not enabled():
        return ""
    root = Path(workspace_root)
    if not root.is_dir():
        return ""

    # Try git status first
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=_TIME_SEC,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            truncated = len(lines) > limit
            shown = lines[:limit]
            summary = "\n".join(shown)
            if truncated:
                summary += f"\n... and {len(lines) - limit} more files"
            return f"[Workspace snapshot — {len(lines)} files modified/added]\n{summary}"
        elif result.returncode == 0:
            return "[Workspace snapshot — clean (no modified/added files)]"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fall back to directory listing
    try:
        entries = sorted(root.iterdir())
        files = [e.name for e in entries if e.is_file()][:limit]
        dirs = [e.name for e in entries if e.is_dir()][:limit]
        parts = []
        if files:
            parts.append(f"Files ({len(files)}): {', '.join(files)}")
        if dirs:
            parts.append(f"Dirs ({len(dirs)}): {', '.join(dirs)}")
        if not parts:
            return "[Workspace snapshot — empty]"
        return "[Workspace snapshot]\n" + "\n".join(parts)
    except OSError:
        return ""


def inject_into_finalization_prompt(base_prompt: str, snapshot: str) -> str:
    """Append workspace snapshot to a forced-finalization prompt.

    If snapshot is empty (capability off or unreadable), returns base_prompt
    unchanged.
    """
    if not snapshot:
        return base_prompt
    return (
        base_prompt
        + "\n\n"
        + snapshot
        + "\n\nReview the snapshot above: ensure your deliverables are complete "
        "and written to the workspace root before time expires."
    )
