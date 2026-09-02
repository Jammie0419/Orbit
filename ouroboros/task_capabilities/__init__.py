# task-capability (ablation): generic — does not participate in evolution
"""Task capabilities: generic, ablation-friendly task execution enhancements.

Each module is gated by an OUROBOROS_CAP_* env var (default off/empty).
All code here is benchmark-neutral — no terminal-bench, harbor, /app, or
task-name references. See devtools/benchmarks/terminal_bench/exp/capabilities/
for TB-specific rules and filters.

Ablation contract: every capability registers in enabled_map() so run manifests
can snapshot the active configuration for reproducible experiments.
"""
from __future__ import annotations

import os


def _env_flag(key: str, default: str = "0") -> str:
    return os.environ.get(key, default).strip()


def enabled_map() -> dict[str, str]:
    """Snapshot all capability开关状态. Values are strings for JSON serialization.

    Callers (run_tb.py manifest, ablation_report.py) use this to record which
    capabilities were active during a run, enabling per-key attribution.
    """
    return {
        "time_checkpoints": _env_flag("OUROBOROS_CAP_TIME_CHECKPOINTS"),
        "delivery_snapshot": _env_flag("OUROBOROS_CAP_DELIVERY_SNAPSHOT"),
        "tool_fix": _env_flag("OUROBOROS_CAP_TOOL_FIX", ""),
        "vision_extra_prefixes": _env_flag("OUROBOROS_VISION_EXTRA_PREFIXES", ""),
    }
