# task-capability (ablation): generic — does not participate in evolution
"""Extensible vision model prefix registry.

Allows declaring additional model ID prefixes that support vision (native
image input) via the OUROBOROS_VISION_EXTRA_PREFIXES environment variable.
This enables benchmark operators to declare vision capability for their
provider's models without modifying ouroboros source code.

Switch: OUROBOROS_VISION_EXTRA_PREFIXES="prefix1,prefix2,..." (comma-separated)
Example: OUROBOROS_VISION_EXTRA_PREFIXES="openai-compatible/mimo,my-provider/vision"

The prefixes are checked in supports_vision() (provider_models.py) BEFORE
the static _VISION_MODEL_PREFIXES table. A match here returns True immediately.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_cached_prefixes: tuple[str, ...] | None = None


def extra_vision_prefixes() -> tuple[str, ...]:
    """Return the tuple of extra vision prefixes from the environment.

    Result is cached on first call (env vars don't change mid-run).
    Returns empty tuple if the env var is unset or empty.
    """
    global _cached_prefixes
    if _cached_prefixes is not None:
        return _cached_prefixes

    raw = os.environ.get("OUROBOROS_VISION_EXTRA_PREFIXES", "").strip()
    if not raw:
        _cached_prefixes = ()
        return _cached_prefixes

    prefixes = tuple(
        p.strip()
        for p in raw.split(",")
        if p.strip()
    )
    if prefixes:
        log.info("task_capabilities.vision_registry: extra prefixes = %s", prefixes)
    _cached_prefixes = prefixes
    return _cached_prefixes


def reset_cache() -> None:
    """Reset the cached prefixes (for testing only)."""
    global _cached_prefixes
    _cached_prefixes = None
