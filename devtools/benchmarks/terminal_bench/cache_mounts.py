#!/usr/bin/env python3
"""Host cache mounts shared by every Terminal-Bench runner.

Why a separate module: both `run_tb.py` and `run_harbor_smoke.py` must emit the
SAME mounts, and they already import from each other (`run_tb` pulls
`AGENT_IMPORT` out of `run_harbor_smoke`), so hosting this in either one would
create a cycle. Keeping it here means a runner cannot silently drift to a
weaker mount set.

What the mounts buy (all of it is CN-network hardening, not leaderboard config --
these are deploy mounts like `--n-concurrent`, so static validation ignores them):

  * `/opt/ouro-pip-cache` -- pip/uv wheel + interpreter cache. Without it every
    trial re-downloads ~200 MB of large wheels (claude-agent-sdk 87 MB, playwright
    45 MB) inside a container that lives for one trial, which routinely overruns
    harbor's 360 s agent-setup budget.
  * `/var/cache/apt` + `/var/lib/apt/lists` -- the .deb cache AND the package index.
    Persisting the index matters as much as the debs: without it `apt-get update`
    re-fetches ~32 MB of Release/Packages files on every container start (~6 min at
    CN speeds) even when every .deb is already cached.
  * `/root/.cache/huggingface` (+ `/app/datasets`) -- HF artifacts for tasks that
    pull datasets or models.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

from devtools.benchmarks.common.run_roots import ensure_outside_repo

PIP_CACHE_TARGET = "/opt/ouro-pip-cache"


def ensure_uv_bin_in_cache(cache_dir: pathlib.Path) -> None:
    """Place usable uv/uvx binaries at <cache_dir>/uv-bin/ (idempotent).

    The injected verifier test.sh probes /opt/ouro-pip-cache/uv-bin/uv FIRST, before
    any download, so these files let every verifier and agent container reuse the
    host's uv/uvx. That matters most in CN: GitHub releases are blocked, astral's
    install.sh burns ~300s on the blocked connect, and a truncated gh-proxy download
    leaves a corrupt uv/uvx that `command -v` still finds but that segfaults on run.
    The original test.sh invokes `uvx`, so BOTH binaries must be present.

    Copy from the host PATH only when a cached copy is missing or its version
    differs, so an operator-pinned binary is left alone.
    """
    try:
        uv_bin_dir = cache_dir / "uv-bin"
        uv_bin_dir.mkdir(parents=True, exist_ok=True)
        host_uv = shutil.which("uv")
        if not host_uv:
            return
        host_uvx = shutil.which("uvx")
        try:
            host_ver = subprocess.run(
                [host_uv, "--version"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except Exception:
            host_ver = ""
        for name, host_path in (("uv", host_uv), ("uvx", host_uvx)):
            target = uv_bin_dir / name
            cached_ver = ""
            if target.exists():
                try:
                    cached_ver = subprocess.run(
                        [str(target), "--version"], capture_output=True, text=True, timeout=10
                    ).stdout.strip()
                except Exception:
                    cached_ver = ""
            if host_path and (not target.exists() or (host_ver and cached_ver != host_ver)):
                shutil.copy2(host_path, target)
                target.chmod(0o755)
    except Exception:
        # Best effort: the verifier's own download fallback still exists.
        pass


def cache_mounts(repo_root: pathlib.Path) -> list[dict[str, str]]:
    """Harbor `--mounts` entries for whichever caches the environment configures.

    Opt-in per cache via OBO_TB_PIP_CACHE / OBO_TB_APT_CACHE / OBO_TB_HF_CACHE.
    Unset everywhere -> empty list -> the runner emits no `--mounts` at all, so
    behavior is unchanged for a plain checkout.

    Raises (via ensure_outside_repo) when a cache path points inside the repo: a
    bind mount of the source tree would let a task container write to it.
    """
    pip_cache = os.environ.get("OBO_TB_PIP_CACHE", "").strip()
    apt_cache = os.environ.get("OBO_TB_APT_CACHE", "").strip()
    hf_cache = os.environ.get("OBO_TB_HF_CACHE", "").strip()
    if not (pip_cache or apt_cache or hf_cache):
        return []

    mounts: list[dict[str, str]] = []
    if pip_cache:
        cache_dir = ensure_outside_repo(pathlib.Path(pip_cache), repo_root)
        mounts.append({"type": "bind", "source": str(cache_dir), "target": PIP_CACHE_TARGET})
        ensure_uv_bin_in_cache(cache_dir)
    if apt_cache:
        apt_cache_dir = ensure_outside_repo(pathlib.Path(apt_cache), repo_root)
        mounts.append({"type": "bind", "source": str(apt_cache_dir), "target": "/var/cache/apt"})
        # The package INDEX lives in a sibling dir, auto-derived so there is no extra
        # config to forget. Without it apt-get update re-downloads ~32MB every start.
        apt_lists_dir = apt_cache_dir.parent / (apt_cache_dir.name + "-lists")
        apt_lists_dir.mkdir(parents=True, exist_ok=True)
        mounts.append({"type": "bind", "source": str(apt_lists_dir), "target": "/var/lib/apt/lists"})
    if hf_cache:
        hf_cache_dir = ensure_outside_repo(pathlib.Path(hf_cache), repo_root)
        mounts.append({"type": "bind", "source": str(hf_cache_dir), "target": "/root/.cache/huggingface"})
        datasets_dir = hf_cache_dir / "OpenThoughts-1k-sample"
        if datasets_dir.exists():
            mounts.append({"type": "bind", "source": str(datasets_dir), "target": "/app/datasets"})
    return mounts


def extend_with_cache_mounts(cmd: list[str], repo_root: pathlib.Path) -> list[str]:
    """Append a single `--mounts <json>` when any cache is configured."""
    mounts = cache_mounts(repo_root)
    if mounts:
        cmd.extend(["--mounts", json.dumps(mounts)])
    return cmd
