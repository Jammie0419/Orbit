# task-capability (ablation): generic — does not participate in evolution
"""Tool friction reduction: enhanced error hints for shell argument errors.

Provides additional corrective examples appended to SHELL_ARG_ERROR messages,
and an optional auto-recovery path that attempts to parse stringified arrays
using the existing recover_stringified_argv utility.

Switch: OUROBOROS_CAP_TOOL_FIX=msg|autorecover| (comma-separated modes)
  - msg: append enhanced examples to SHELL_ARG_ERROR messages (zero risk)
  - autorecover: attempt automatic argv recovery from stringified arrays
  - empty (default): off, no behavior change
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_ENHANCED_HINT = (
    "\n\nTip: if you need to run a multi-line script, use run_script instead:\n"
    '  run_script(language="python", code="...")\n'
    "For shell pipelines/redirects, wrap in sh -c:\n"
    '  run_command(cmd=["sh", "-c", "grep pattern file | sort | head -5"])'
)


def enabled_modes() -> frozenset[str]:
    raw = os.environ.get("OUROBOROS_CAP_TOOL_FIX", "").strip()
    if not raw:
        return frozenset()
    return frozenset(mode.strip() for mode in raw.split(",") if mode.strip())


def enabled() -> bool:
    return bool(enabled_modes())


def msg_mode() -> bool:
    return "msg" in enabled_modes()


def autorecover_mode() -> bool:
    return "autorecover" in enabled_modes()


def arg_error_hint() -> str:
    """Return the enhanced hint text to append to SHELL_ARG_ERROR messages.

    Returns empty string if msg mode is not enabled.
    """
    if not msg_mode():
        return ""
    return _ENHANCED_HINT


def try_autorecover(cmd_str: str) -> Optional[list[str]]:
    """Attempt to recover a proper argv list from a stringified array.

    Returns the recovered argv list if successful, None if autorecover mode
    is off or recovery fails. Uses the existing recover_stringified_argv
    utility from shell_parse.
    """
    if not autorecover_mode():
        return None
    if not isinstance(cmd_str, str) or not cmd_str.strip():
        return None
    try:
        from ouroboros.shell_parse import recover_stringified_argv

        recovered = recover_stringified_argv(cmd_str)
        if recovered and isinstance(recovered, list) and len(recovered) > 0:
            log.debug("tool_fix: auto-recovered argv from stringified cmd: %r", recovered)
            return recovered
    except Exception:
        log.debug("tool_fix: auto-recover failed for cmd=%r", cmd_str[:100], exc_info=True)
    return None
