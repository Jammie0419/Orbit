"""Terminal-Bench capability registry.

RECOVERED 2026-09-16. Two independent capability surfaces:

  * the generic runtime switches in ouroboros.task_capabilities (time
    checkpoints, delivery snapshot, tool fix, vision prefixes) -- see
    ouroboros/task_capabilities/enabled_map();
  * the Terminal-Bench-specific prompt rules and per-task annotations here.

capability_summary() is consumed by run_tb.py to snapshot what was active into
run_manifest.json under "capabilities", so an ablation arm can be attributed
after the fact instead of reconstructed from logs. Its key shape is reproduced
from the historical test_cap_rules/run_manifest.json.
"""

from __future__ import annotations

import os

from .rules import CAP_RULES, selected_rule_ids
from .task_annotations import TASK_ANNOTATIONS, annotated_task_count


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def capability_summary() -> dict[str, object]:
    """Snapshot the active TB-side capabilities for run_manifest.json."""
    try:
        rule_ids = selected_rule_ids()
    except KeyError as exc:
        rule_ids = [f"<invalid: {exc}>"]

    return {
        "tb_rules": list(rule_ids),
        "tb_rules_available": sorted(CAP_RULES),
        "tb_annotated_tasks": annotated_task_count(),
        "review_models": _env("OUROBOROS_REVIEW_MODELS"),
        "scope_review_model": _env("OUROBOROS_SCOPE_REVIEW_MODEL"),
        "image_input_mode": _env("OUROBOROS_IMAGE_INPUT_MODE"),
        "vision_extra_prefixes": _env("OUROBOROS_VISION_EXTRA_PREFIXES"),
        "vision_smoke_result": _env("OUROBOROS_VISION_SMOKE_RESULT") or "NO",
        "cap_time_checkpoints": _env("OUROBOROS_CAP_TIME_CHECKPOINTS") or "0",
        "cap_delivery_snapshot": _env("OUROBOROS_CAP_DELIVERY_SNAPSHOT") or "0",
        "cap_tool_fix": _env("OUROBOROS_CAP_TOOL_FIX"),
    }


__all__ = [
    "CAP_RULES",
    "TASK_ANNOTATIONS",
    "capability_summary",
    "selected_rule_ids",
    "annotated_task_count",
]
