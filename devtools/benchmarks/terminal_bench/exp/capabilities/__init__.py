"""Terminal-Bench prompt-side capability.

Only ONE capability lives here: per-task annotations appended to the task
instruction (see `task_annotations.py`). The global behavior-rule block that once
accompanied it was dropped from the live path deliberately — rendering it produced
a >100 KB prompt that sent mimo-v2.5 into a single maxed-out 65536-token reply,
which was length-truncated about eight minutes in and then blew the deadline.

Because nothing rendered it and nothing consumed a snapshot of it, that module was
dead weight rather than a standby feature, so it was removed instead of kept "for
later". Its text stays recoverable from this repository's history (committed in
`a50728b7`) and from the historical `agent/instruction.txt` files of the
2026-08-25..09-02 runs, if an ablation arm ever needs it back.

Nothing imports this package as a package: the adapter imports
`...capabilities.task_annotations` directly, which keeps the live path immune to
anything added here later.
"""
from __future__ import annotations

from .task_annotations import (
    ENV_FLAG,
    TASK_ANNOTATIONS,
    annotated_task_count,
    annotated_tasks,
    annotations_enabled,
    render_task_annotations,
    resolve_task_name,
)

__all__ = [
    "ENV_FLAG",
    "TASK_ANNOTATIONS",
    "annotated_task_count",
    "annotated_tasks",
    "annotations_enabled",
    "render_task_annotations",
    "resolve_task_name",
]
