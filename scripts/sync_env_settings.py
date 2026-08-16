#!/usr/bin/env python3
"""Sync model/API settings from the base ``.env`` into the server settings.json.

Server reads ``settings.json`` (OUROBOROS_SETTINGS_PATH), NOT .env. This script
copies the model/API keys present in ``.env`` into settings.json so editing
``.env`` is the single place to change model configuration.

Usage:
    python scripts/sync_env_settings.py
    python scripts/sync_env_settings.py --env-custom .env.gaia   # also layer a custom env file

Only keys listed in SYNC_KEYS are copied; keys absent from the .env file are
left untouched in settings.json (existing values survive).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Optional

try:
    import dotenv  # type: ignore
except ImportError:
    dotenv = None

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ouroboros.config import SETTINGS_PATH  # noqa: E402

# Keys allowed to flow from .env into settings.json. Model slots + the
# OpenAI-compatible endpoint + the common provider API keys.
SYNC_KEYS: tuple[str, ...] = (
    "OUROBOROS_MODEL",
    "OUROBOROS_MODEL_HEAVY",
    "OUROBOROS_MODEL_LIGHT",
    "OUROBOROS_MODEL_VISION",
    "OUROBOROS_MODEL_CONSCIOUSNESS",
    "OUROBOROS_MODEL_FALLBACKS",
    "OUROBOROS_MODEL_DEEP_SELF_REVIEW",
    "OUROBOROS_REVIEW_MODELS",
    "OUROBOROS_SCOPE_REVIEW_MODEL",
    "OUROBOROS_SCOPE_REVIEW_MODELS",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_REGION",
    "CLOUDRU_FOUNDATION_MODELS_API_KEY",
    "CLOUDRU_FOUNDATION_MODELS_BASE_URL",
)


def _load_dotenv_vars(path: pathlib.Path) -> dict[str, str]:
    """Parse a .env file into a dict (via python-dotenv or a minimal fallback)."""
    if dotenv is not None:
        return {k: v for k, v in dotenv.dotenv_values(path).items() if v is not None}
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-custom", default=None,
                        help="additional .env-style file layered on top of .env (e.g. .env.gaia)")
    args = parser.parse_args(argv)

    base_env = REPO_ROOT / ".env"
    custom_env = pathlib.Path(args.env_custom) if args.env_custom else None
    if custom_env is not None and not custom_env.is_absolute():
        custom_env = REPO_ROOT / custom_env

    merged: dict[str, str] = {}
    merged.update(_load_dotenv_vars(base_env))
    if custom_env is not None:
        merged.update(_load_dotenv_vars(custom_env))  # custom file wins

    if not SETTINGS_PATH.exists():
        print(f"settings.json not found: {SETTINGS_PATH}", file=sys.stderr)
        return 1
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    changed: list[str] = []
    for key in SYNC_KEYS:
        if key in merged:
            if str(settings.get(key, "")) != str(merged[key]):
                settings[key] = merged[key]
                changed.append(key)

    if changed:
        # Preserve 4-space indentation and trailing newline of the settings file.
        SETTINGS_PATH.write_text(
            json.dumps(settings, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("Updated settings.json:")
        for key in changed:
            print(f"  {key} = {settings[key]}")
    else:
        print("No changes (settings.json already matches .env).")
    print(f"Settings file: {SETTINGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
