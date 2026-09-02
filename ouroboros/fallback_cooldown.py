"""Process-local 429-aware cooldown for the cross-model fallback chain (F1, v6.39).

A model that just failed transiently (429 / 5xx / overloaded) is parked on a short
cooldown so the fallback chain skips it for a window instead of immediately hammering it
again. Scope is PER-PROCESS: it bounds re-hits WITHIN one worker — a single task's own
fallback walk and its repeated rounds stop re-trying a just-rate-limited model. It does
NOT coordinate across sibling worker processes (each worker has its own map), so it is
not a swarm-WIDE rate-limit governor; durable cross-worker coordination is the project
journal / task-tree blackboard's job (Phase 3), not this advisory in-process guard. The
cooldown is ADVISORY (never a durable "model is bad" verdict that could strand a user
after a transient provider event), and heal-back is PASSIVE: the entry simply expires by
timestamp. Default-on, fail-soft (every helper degrades to "not cooling / no-op" on a
bad config value).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, Tuple

_cooldown: Dict[Tuple[str, bool], float] = {}
_lock = threading.Lock()

# Task-scoped permanent exclusion: once a model has been tried and failed during the
# current task, it stays excluded for the rest of the task. This prevents oscillation
# where the main loop cycles between models every cooldown-expiry window (e.g.
# mimo-v2.5 → hy3 → mimo-v2.5 → hy3 every ~120s). Keyed by (model, use_local).
_excluded: Dict[int, set] = {}  # task_id_hash → set of (model, use_local)
_excluded_lock = threading.Lock()


def cooldown_enabled() -> bool:
    """Default-on; only an explicit falsey value disables it."""
    raw = str(os.environ.get("OUROBOROS_FALLBACK_COOLDOWN_ENABLED", "") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _cooldown_sec() -> float:
    try:
        return max(0.0, float(os.environ.get("OUROBOROS_FALLBACK_COOLDOWN_SEC", "") or 120.0))
    except (TypeError, ValueError):
        return 120.0


def attempts_per_model() -> int:
    """Total attempt ceiling for a SINGLE fallback candidate (1..2) — the chain tries a
    candidate this many times, then moves to the next link. Applied only to fallback
    candidates; the primary model keeps its full per-class retry budgets
    (OUROBOROS_TRANSIENT_RETRY_MAX / max_retries)."""
    try:
        return max(1, min(2, int(os.environ.get("OUROBOROS_FALLBACK_ATTEMPTS_PER_MODEL", "") or 1)))
    except (TypeError, ValueError):
        return 1


def mark_cooldown(model: str, use_local: bool = False) -> None:
    """Put a model on cooldown after a TRANSIENT failure (caller classifies)."""
    if not cooldown_enabled():
        return
    key = (str(model or ""), bool(use_local))
    with _lock:
        _cooldown[key] = time.time() + _cooldown_sec()


def is_cooling_down(model: str, use_local: bool = False) -> bool:
    """True while the model is inside its cooldown window. Passive heal-back: an expired
    entry is dropped and reads as available again."""
    if not cooldown_enabled():
        return False
    key = (str(model or ""), bool(use_local))
    now = time.time()
    with _lock:
        until = _cooldown.get(key, 0.0)
        if until and until > now:
            return True
        if until:
            _cooldown.pop(key, None)
        return False


def reset_for_tests() -> None:
    with _lock:
        _cooldown.clear()
    with _excluded_lock:
        _excluded.clear()


def mark_permanently_excluded(task_id_hash: int, model: str, use_local: bool = False) -> None:
    """Permanently exclude a model for the rest of the current task. Once a model has
    failed and we've moved on, don't cycle back to it — that causes oscillation where
    the main loop flips between two models every cooldown window, wasting tokens on
    cold cache."""
    if not model:
        return
    key = (str(model), bool(use_local))
    with _excluded_lock:
        bucket = _excluded.setdefault(task_id_hash, set())
        bucket.add(key)


def is_permanently_excluded(task_id_hash: int, model: str, use_local: bool = False) -> bool:
    """True if this model was already tried and failed during the current task."""
    key = (str(model), bool(use_local))
    with _excluded_lock:
        bucket = _excluded.get(task_id_hash)
        if bucket is None:
            return False
        return key in bucket


def clear_task_exclusions(task_id_hash: int) -> None:
    """Clean up exclusion state when a task finishes."""
    with _excluded_lock:
        _excluded.pop(task_id_hash, None)


def _task_id_hash(task_id: str) -> int:
    """Stable hash for a task ID string."""
    return hash(str(task_id or "")) & 0x7FFFFFFF
