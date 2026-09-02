# task-capability (ablation): generic — does not participate in evolution
"""Time-proportion checkpoints for deadline-aware tasks.

Replaces the default periodic self-check cadence with time-ratio checkpoints
at 25%, 50%, 75% of elapsed deadline. Each checkpoint injects a user-turn
message urging the agent to assess progress and converge.

Switch: OUROBOROS_CAP_TIME_CHECKPOINTS=1 (default 0 = off, original behavior).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_CHECKPOINT_THRESHOLDS: tuple[tuple[float, str, str], ...] = (
    (0.25, "25%",
     "You have used ~25% of your time budget. Assess: is your current approach working? "
     "If exploration has not yielded a working prototype, STOP exploring new approaches and "
     "converge on the simplest viable implementation."),
    (0.50, "50%",
     "You have used ~50% of your time budget. You should have a working draft by now. "
     "Focus on fixing known issues and verifying your current implementation rather than "
     "starting new approaches."),
    (0.75, "75%",
     "You have used ~75% of your time budget. CONVERGE NOW: finalize your best current "
     "implementation, verify it, and ensure all deliverables are written to the workspace. "
     "Do not start any new work."),
)


def enabled() -> bool:
    return os.environ.get("OUROBOROS_CAP_TIME_CHECKPOINTS", "0").strip() in ("1", "true", "yes")


def maybe_inject_time_checkpoint(
    *,
    elapsed_sec: float,
    total_sec: float,
    round_idx: int,
    last_checkpoint_pct: float = 0.0,
) -> Tuple[bool, str, float]:
    """Decide whether to inject a time checkpoint this round.

    Args:
        elapsed_sec: seconds since task start
        total_sec: total time budget (deadline - created_at)
        round_idx: current round number
        last_checkpoint_pct: the threshold of the last fired checkpoint (0.0 = none)

    Returns:
        (should_inject, checkpoint_text, new_last_checkpoint_pct)
    """
    if not enabled():
        return False, "", last_checkpoint_pct
    if total_sec <= 0:
        return False, "", last_checkpoint_pct

    fraction_elapsed = elapsed_sec / total_sec

    # Find the tightest crossed threshold that hasn't fired yet
    for threshold, label, text in _CHECKPOINT_THRESHOLDS:
        if fraction_elapsed >= threshold and threshold > last_checkpoint_pct:
            checkpoint_text = (
                f"[TIME CHECKPOINT — ~{label} of budget elapsed]\n"
                f"{text}\n"
                "Use this as a planning signal: if your current path is not converging, "
                "switch to the shortest path to a verifiable result."
            )
            return True, checkpoint_text, threshold

    return False, "", last_checkpoint_pct
