"""Harbor installed-agent entrypoint for evaluating full Ouroboros in Terminal-Bench.

This adapter intentionally does not translate Ouroboros decisions into shell
commands. Harbor starts a task container, this class installs Ouroboros inside
that container, starts the normal Ouroboros server/supervisor, and submits the
Terminal-Bench instruction as an external workspace task rooted at ``/app``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path
from typing import Any

from devtools.benchmarks.common.manifests import openrouter_key_remaining, repo_provenance, write_json
from devtools.benchmarks.common.model_slots import single_model_subagents_setting
from devtools.benchmarks.common.result_index import RUNTIME_TRUNCATION_REASON_CODES

try:  # Harbor is an optional benchmark dependency.
    from harbor.agents.installed.base import BaseInstalledAgent
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except Exception:  # pragma: no cover - exercised when Harbor is absent.
    BaseInstalledAgent = object  # type: ignore[assignment]
    BaseEnvironment = Any  # type: ignore[assignment]
    AgentContext = Any  # type: ignore[assignment]


_CONTAINER_SRC = "/opt/ouroboros-src"
_CONTAINER_VENV = "/opt/ouroboros-venv"
# Optional host-mounted pip wheel cache (mount a host dir here via Harbor --mounts to make the
# per-trial Ouroboros pip install offline-fast and resilient to mirror/network drops). Safe by
# default: if nothing is mounted at this path it is just an ephemeral in-container cache dir, so
# behavior is unchanged. pip keys cached wheels by (name, version, python-tag, platform-tag), so a
# single shared cache is correct across heterogeneous task images (py3.11/3.12, different glibc) and
# concurrency-safe (atomic-rename writes of identical content). See run_tb.py OBO_TB_PIP_CACHE.
_CONTAINER_PIP_CACHE = "/opt/ouro-pip-cache"
_CONTAINER_DATA = "/logs/agent/ouroboros-data"
_CONTAINER_WORKSPACE = "/app"
_SERVER_URL = "http://127.0.0.1:8765"
_CONTAINER_SECRET_OPT_IN = "OUROBOROS_BENCH_ALLOW_CONTAINER_SECRETS"
_SECRET_ENV_KEYS = frozenset({
    "ANTHROPIC_API_KEY",
    "CLOUDRU_FOUNDATION_MODELS_API_KEY",
    "GIGACHAT_CREDENTIALS",
    "GIGACHAT_PASSWORD",
    "GIGACHAT_USER",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENROUTER_API_KEY",
})
log = logging.getLogger(__name__)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_host_settings_path() -> Path:
    return Path(os.environ.get("OUROBOROS_SETTINGS_PATH") or _workspace_root() / "data" / "settings.json")


def _json_load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _secret_shaped_source_name(name: str) -> bool:
    lower = name.lower()
    secret_extensions = (".json", ".yaml", ".yml", ".toml", ".ini", ".txt")
    if lower.startswith(".env") or lower.endswith(".env") or ".env." in lower:
        return True
    if lower.endswith((".key", ".pem", ".pfx", ".p12")):
        return True
    if lower in {".git-credentials", ".netrc", ".npmrc", ".pypirc", "id_ed25519", "id_rsa"}:
        return True
    if lower in {"credentials.json", "token.json", "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml"}:
        return True
    if any(token in lower for token in ("secret", "credential", "token", "service-account")):
        return lower.endswith(secret_extensions)
    return False


def _task_name_from_trial_dir(logs_dir: Path | str) -> str:
    """Resolve a trial's task NAME without trusting the trial directory's name.

    Harbor names a trial dir ``<task>__<hash>`` when the task was resolved by name, but
    ``<taskhash>__<hash>`` when it was resolved by PATH. Measured on gpt2-codegolf: its dirs
    are ``fe42af8e...__JujTBFJ`` while the task is ``terminal-bench/gpt2-codegolf``. Deriving
    the name from the dir therefore yields a hash, and every lookup keyed by the task name --
    the annotation table, the cached ``task.toml``, and through it the test.sh patch that puts
    uv on the verifier's PATH -- quietly does nothing.

    ``config.json`` is written when the trial dir is created, before the agent runs, so it is
    readable here. Order: ``task.name`` (name-resolved), then ``task.path``'s parent directory
    (path-resolved), then the dir name as a last resort.
    """
    trial_dir = Path(logs_dir).resolve().parent
    try:
        data = json.loads((trial_dir / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        task = data.get("task") if isinstance(data.get("task"), dict) else {}
        named = str(task.get("name") or "").strip()
        if named:
            return named.rsplit("/", 1)[-1]
        local_path = str(task.get("path") or "").strip()
        if local_path:
            # .../packages/<org>/<task>/<digest> -> <task>
            parent = Path(local_path).parent.name
            if parent:
                return parent
    name = trial_dir.name
    return name.rsplit("__", 1)[0] if "__" in name else name


# test.sh mirror bootstrap block, injected right after the shebang by
# _patch_test_sh_for_china (both the host package-cache copy — the actual source
# the verifier uploads — and the in-container copy, when shared). Semantics:
# 1) PyPI + python-build-standalone downloads go through CN mirrors;
# 2) an already-installed uv is reused before any download: the host-cache bind
#    mount /opt/ouro-pip-cache/uv-bin (a copy of the host's own uv binary, made
#    by the operator), the agent venv, ~/.local/bin, or the PATH. The original
#    `curl -LsSf https://astral.sh/uv/... | sh` step does NOT check PATH and
#    burns a ~300s blocked-connect timeout even when uv exists;
# 3) uv's own cache is redirected into the same mounted host dir so uvx package
#    downloads (torch etc.) survive container teardown and are reused across
#    trials — the verifier's uvx downloads were always cache-miss fresh);
# 4) if uv is genuinely absent, fetch the binary via gh-proxy with retry +
#    integrity check + cleanup (astral's install.sh hardcodes a GitHub release
#    URL, unreachable from CN; a truncated download leaves a corrupt uv/uvx
#    that shadows the original install line and segfaults).
_TEST_SH_MIRROR_BLOCK = """export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
# Both names: UV_INDEX_URL is what uv <=0.9 read, UV_DEFAULT_INDEX is the current
# one. Setting both is safe (each uv version reads the name it knows and ignores
# the other), and the verifier reuses whatever uv it finds on PATH, so the version
# there is not ours to pin.
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export UV_PYTHON_INSTALL_MIRROR="https://cdn.npmmirror.com/binaries/python-build-standalone"
# huggingface.co is blocked in CN; hf-mirror mirrors the hub AND the raw
# `resolve/` file paths (e.g. reshard-c4-data's verifier load_dataset()s
# allenai/c4 shard 00009 at test time — that file is NOT in the shared HF cache).
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
# Prefer an already-installed uv over downloading from GitHub (blocked in CN).
# Each candidate must pass a `--version` smoke test: a truncated download leaves
# a corrupt uv/uvx that `command -v` still finds yet segfaults on run.
if [ -x "/opt/ouro-pip-cache/uv-bin/uv" ] && /opt/ouro-pip-cache/uv-bin/uv --version >/dev/null 2>&1; then
    export PATH="/opt/ouro-pip-cache/uv-bin:$PATH"; export UV_ALREADY_AVAILABLE=1
elif [ -x "/opt/ouroboros-venv/bin/uv" ] && /opt/ouroboros-venv/bin/uv --version >/dev/null 2>&1; then
    export PATH="/opt/ouroboros-venv/bin:$PATH"; export UV_ALREADY_AVAILABLE=1
elif [ -x "$HOME/.local/bin/uv" ] && "$HOME/.local/bin/uv" --version >/dev/null 2>&1; then
    export PATH="$HOME/.local/bin:$PATH"; export UV_ALREADY_AVAILABLE=1
elif command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
    export UV_ALREADY_AVAILABLE=1
else
    # No uv anywhere: fetch the binary via gh-proxy, with retry + integrity check.
    _ouro_arch="$(uname -m)"
    case "$_ouro_arch" in
        aarch64|arm64) _ouro_target="aarch64-unknown-linux-gnu" ;;
        *) _ouro_target="x86_64-unknown-linux-gnu" ;;
    esac
    _ouro_ver="${UV_INSTALL_VERSION:-0.9.5}"
    _ouro_url="https://gh-proxy.com/https://github.com/astral-sh/uv/releases/download/${_ouro_ver}/uv-${_ouro_target}.tar.gz"
    _ouro_ok=0
    for _i in 1 2 3; do
        curl -LsSf --retry 3 --connect-timeout 20 --max-time 300 "$_ouro_url" -o /tmp/ouro-uv.tar.gz || continue
        if gzip -t /tmp/ouro-uv.tar.gz 2>/dev/null && tar -xzf /tmp/ouro-uv.tar.gz -C /usr/local/bin --strip-components=1; then
            _ouro_ok=1; break
        fi
        rm -f /usr/local/bin/uv /usr/local/bin/uvx /tmp/ouro-uv.tar.gz
        sleep 2
    done
    rm -f /tmp/ouro-uv.tar.gz
    if [ "$_ouro_ok" = "1" ] && uv --version >/dev/null 2>&1; then
        export UV_ALREADY_AVAILABLE=1
    else
        rm -f /usr/local/bin/uv /usr/local/bin/uvx
    fi
fi
# uvx must reuse the mounted host cache dir (default ~/.cache/uv dies with the
# container, so every verifier run re-downloads python+torch; UV_CACHE_DIR here
# makes the bind-mounted host dir persistent across trials).
mkdir -p /opt/ouro-pip-cache 2>/dev/null || true
chown -R "$(id -u):$(id -g)" /opt/ouro-pip-cache 2>/dev/null || true
chmod -R a+rwX /opt/ouro-pip-cache 2>/dev/null || true
export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/ouro-pip-cache}"
# Downloaded interpreters install into UV_PYTHON_INSTALL_DIR (default
# ~/.local/share/uv/python, which dies with the container). Point it at the same
# mounted dir so a python fetched once is reused by every later trial
# (verified: fresh container then hits it in ~0.5s instead of re-downloading).
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/opt/ouro-pip-cache/uv-python}"
mkdir -p "$UV_PYTHON_INSTALL_DIR" 2>/dev/null || true

# ---- pip -------------------------------------------------------------------
# uvx covers 82 of the 89 task test.sh scripts, but 9 of them reach for pip, and
# without these every such install resolves against pypi.org from CN.
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/opt/ouro-pip-cache}"
mkdir -p "$PIP_CACHE_DIR" 2>/dev/null || true

# ---- apt -------------------------------------------------------------------
# 84 of the 89 task test.sh scripts shell out to apt-get. During a shared-mode run
# the agent install has already rewritten these sources, but a verifier in its own
# container has not -- and there deb.debian.org costs ~121s for the index alone
# (measured) against the verifier's own timeout. Rewriting is idempotent, so doing
# it unconditionally is cheap in the shared case and decisive in the separate one.
if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
    sed -i -E 's#URIs: http://[a-z.-]*(ubuntu|security.ubuntu).com/ubuntu/#URIs: http://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
fi
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
    sed -i -E 's#URIs: https?://[a-z.-]*deb\\.debian\\.org/debian-security#URIs: https://mirrors.tuna.tsinghua.edu.cn/debian-security#g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
    sed -i -E 's#URIs: https?://[a-z.-]*deb\\.debian\\.org/debian#URIs: https://mirrors.tuna.tsinghua.edu.cn/debian#g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
fi
sed -i -E 's#(deb|deb-src) http://[a-z.-]*(archive|security).ubuntu.com/ubuntu#\\1 http://mirrors.tuna.tsinghua.edu.cn/ubuntu#g' /etc/apt/sources.list 2>/dev/null || true
sed -i -E 's#https?://[a-z.-]*deb\\.debian\\.org/debian#https://mirrors.tuna.tsinghua.edu.cn/debian#g' /etc/apt/sources.list 2>/dev/null || true
# These images ship /etc/apt/apt.conf.d/docker-clean, which deletes
# /var/cache/apt/archives/*.deb after every apt operation. The verifier installing
# into a mounted /var/cache/apt is exactly the case where keeping them pays off:
# the next trial of the same task installs offline.
rm -f /etc/apt/apt.conf.d/docker-clean 2>/dev/null || true
"""

# Single source of truth for how uv is located and, only if genuinely absent,
# downloaded. Both the agent's own bootstrap (the container install script) and the
# verifier's injected test.sh use this exact block, so the two cannot drift: the
# agent publishes a uv that the verifier then reuses.
_UV_BOOTSTRAP_BLOCK = _TEST_SH_MIRROR_BLOCK

# Marks a test.sh as already carrying our block. Kept as one constant because the
# idempotence check and the writer must agree on the exact string.
_TEST_SH_INJECTED_MARKER = "# Injected by harbor_installed_agent.py for China network"

# Marks a test.sh as already carrying the apt lock shim, and is a SEPARATE key from the
# block marker on purpose: the block marker went out in the first rollout, so the 19 task
# packages that already carry it would never receive anything appended to the block
# afterwards. Keying the shim on its own marker is what lets an already-patched test.sh
# pick the shim up.
_APT_SHIM_MARKER = "# Injected by harbor_installed_agent.py: apt lock shim"

# The verifier's apt calls are NOT ours to wrap, so the lock is taken at the apt entry
# point instead of at a phase boundary. Measured 2026-09-18: two verifier runs died in
# 1.87 s and 3.24 s with "Could not get lock /var/lib/apt/lists/lock. It is held by
# process 0" -- that PID is unresolvable because the holder sits in another container's
# PID namespace, and the task's own `set -e` turned the warning into an instant zero
# (the results were never graded; one trial had run 38 turns of correct work). apt
# cannot be asked to wait for its own lock: libapt-pkg 2.8.3 knows only
# DPkg::Lock::Timeout, which guards dpkg's lock, not Dir::State::lists. So the shim
# queues at the call site. /usr/local/bin precedes /usr/bin in the container PATH for
# both `bash -lc` and `sh -c` (measured), which is what makes it catch a bare
# `apt-get` from four different callers: our own install, the task's test.sh, the
# verify.sh that test.sh generates inside pytest, and the agent typing
# `apt-get install ...` mid-task. Every failure path is fail-open (no flock, unwritable
# lock file, or a timed-out wait all fall through to the real binary), so the worst case
# is exactly today's behavior. It is a no-op on images without apt-get (apk/yum).
_APT_SHIM_BLOCK = r'''# Injected by harbor_installed_agent.py: apt lock shim
if [ -x /usr/bin/apt-get ] && command -v flock >/dev/null 2>&1; then
  mkdir -p /usr/local/bin 2>/dev/null || true
  for OUP in apt-get apt; do
    [ -x "/usr/bin/$OUP" ] || continue
    if [ -e "/usr/local/bin/$OUP" ]; then continue; fi
    cat > "/usr/local/bin/$OUP" <<'OURO_APT_SHIM' || true
#!/bin/sh
# Serialize apt across containers. /var/lib/apt/lists and /var/cache/apt are shared
# bind mounts, so apt's own lock files in them are global, and apt has no way to be
# told to wait for them (see the calling block for the measurement).
self=$(basename "$0")
if [ -z "${OURO_APT_LOCK_HELD:-}" ] && command -v flock >/dev/null 2>&1; then
  mkdir -p /var/cache/apt 2>/dev/null || true
  if exec 9>/var/cache/apt/.apt-phase.lock; then
    flock -w "${OURO_APT_LOCK_WAIT:-300}" 9 2>/dev/null || :
  fi
fi
exec "/usr/bin/$self" "$@"
OURO_APT_SHIM
    chmod 755 "/usr/local/bin/$OUP" 2>/dev/null || true
  done
fi'''


def _ghproxy_github_urls(text: str) -> str:
    """Rewrite plain https://github.com/... URLs to the gh-proxy mirror.

    Direct `.../raw/...` (which redirects to raw.githubusercontent) and release
    assets are blocked in CN — measured: sam-cell-seg's verifier curls
    github.com/.../raw/.../mobile_sam.pt for the weight and dies direct, while
    the same URL through gh-proxy returns 206. gh-proxy is already the mirror
    block's uv channel. Lines that mention gh-proxy are left alone, so the
    transform is idempotent.
    """
    out = []
    for line in text.splitlines(keepends=True):
        if "gh-proxy.com" in line:
            out.append(line)
        else:
            out.append(line.replace(
                "https://github.com/", "https://gh-proxy.com/https://github.com/"
            ))
    return "".join(out)


def _inject_test_sh_mirror_block(text: str) -> str | None:
    """Return test.sh with the CN bootstrap block and the apt lock shim injected, or
    None when both are already present (idempotent).

    The two are injected on independent keys, so a test.sh that carries only the older
    block still receives the shim. The original uv install line is kept (harmless: the
    block above already ensures uv exists, and the astral curl is gated by
    UV_ALREADY_AVAILABLE via the surrounding `||` guard below)."""
    # Idempotence is keyed on OUR markers, not on "UV_INDEX_URL". Task packages in this
    # cache have been edited to set UV_INDEX_URL themselves, so testing for that string
    # returned None ("already patched") on exactly the files that most need the block --
    # the injection silently did nothing and the verifier ran with no PATH to uvx.
    need_block = _TEST_SH_INJECTED_MARKER not in text
    need_shim = _APT_SHIM_MARKER not in text
    if not (need_block or need_shim):
        # Markers in place, but the github rewrite still applies to the task's own
        # lines (a file patched by an older run carries no gh-proxy coverage yet).
        rewritten = _ghproxy_github_urls(text)
        return rewritten if rewritten != text else None
    lines = text.splitlines()
    if lines and lines[0].startswith("#!"):
        head, rest = lines[0], lines[1:]
        new_lines = [head]
        if need_block:
            new_lines.append(_TEST_SH_INJECTED_MARKER)
            new_lines.extend(_TEST_SH_MIRROR_BLOCK.rstrip("\n").splitlines())
            new_lines.append("# Gate the original uv install line (uv already bootstrapped above):")
            gated = []
            for line in rest:
                if line.strip().startswith("curl -LsSf https://astral.sh/uv/") and "install.sh" in line:
                    stmt = line.strip()
                    # bash `{ list; }` needs a command terminator before `}` so the
                    # gated original install line stays a valid brace group.
                    gated.append(f'[ -n "$UV_ALREADY_AVAILABLE" ] || {{ {stmt}; }}')
                else:
                    gated.append(line)
            rest = gated
        if need_shim:
            new_lines.extend(_APT_SHIM_BLOCK.rstrip("\n").splitlines())
        new_lines.extend(rest)
        return _ghproxy_github_urls("\n".join(new_lines) + "\n")
    if text.startswith("#!/"):
        return None  # not a shebang we understand; leave untouched
    # No shebang at all: prepend whichever piece is missing (rare; some tasks ship a
    # plain script). The marker line travels with the block here too -- without it the
    # next call cannot tell the block was already prepended and would add a second copy.
    prefix = ""
    if need_block:
        prefix += f"{_TEST_SH_INJECTED_MARKER}\n{_TEST_SH_MIRROR_BLOCK}"
    if need_shim:
        prefix += _APT_SHIM_BLOCK + "\n"
    return _ghproxy_github_urls(prefix + text)


def _copy_clean_source(source: Path, target: Path) -> None:
    excluded_dirs = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "data",
        "data_evaluated",
        "dist",
        "node-standalone",
        "node_modules",
        "python-standalone",
        "venv",
    }
    excluded_suffixes = {".pyc", ".pyo"}
    excluded_names = {
        ".DS_Store",
        ".env.example",
        ".release_notes.md",
        "repo.bundle",
        "repo_bundle_manifest.json",
    }

    def ignore(current_dir: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        # Annotation bodies are keyed by task name, and at least one task name trips the
        # secret-shaped heuristic: `count-dataset-tokens.txt` matches ("token" plus a
        # text extension) and would be dropped from the upload, silently disabling that
        # one task's annotation while the enable flag still reads as on. Exempt precisely
        # this directory; the heuristic keeps applying everywhere else in the tree.
        in_annotations_dir = Path(current_dir).name == "annotations"
        for name in names:
            if name in excluded_dirs or name in excluded_names:
                ignored.add(name)
                continue
            if not in_annotations_dir and _secret_shaped_source_name(name):
                ignored.add(name)
                continue
            if any(name.endswith(suffix) for suffix in excluded_suffixes):
                ignored.add(name)
        return ignored

    shutil.copytree(source, target, ignore=ignore, symlinks=True)


def _tree_digest(root: Path) -> dict[str, Any]:
    digest = sha256()
    file_count = 0
    symlink_count = 0
    byte_count = 0
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
        rel = str(path.relative_to(root)).replace(os.sep, "/")
        if path.is_symlink():
            symlink_count += 1
            digest.update(f"L\0{rel}\0{os.readlink(path)}\0".encode("utf-8", errors="replace"))
            continue
        if not path.is_file():
            continue
        file_count += 1
        size = path.stat().st_size
        byte_count += int(size)
        digest.update(f"F\0{rel}\0{size}\0".encode("utf-8", errors="replace"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return {
        "sha256": digest.hexdigest(),
        "files": file_count,
        "symlinks": symlink_count,
        "bytes": byte_count,
    }


def _source_copy_provenance(source: Path, copied_tree: Path | None = None) -> dict[str, Any]:
    provenance = repo_provenance(source)
    provenance["copy_policy"] = {
        "schema": "ouroboros.benchmark.source_copy.v1",
        "git_dir_copy_allowed": False,
        "runtime_data_copy_allowed": False,
        "secret_shaped_file_copy_allowed": False,
        "copy_target": _CONTAINER_SRC,
    }
    if copied_tree is not None:
        provenance["copied_tree"] = _tree_digest(copied_tree)
    return provenance


class OuroborosTerminalBenchAgent(BaseInstalledAgent):
    """Install and run full Ouroboros inside the Terminal-Bench task container."""

    SUPPORTS_WINDOWS = False

    def __init__(
        self,
        logs_dir: Path,
        model_name: str = "ouroboros-inside",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        workspace_dir = str(kwargs.pop("workspace_dir", _CONTAINER_WORKSPACE))
        host_settings_path = str(kwargs.pop("host_settings_path", ""))
        install_timeout_sec = int(kwargs.pop("install_timeout_sec", 900))
        server_start_timeout_sec = int(kwargs.pop("server_start_timeout_sec", 180))
        task_timeout_sec = kwargs.pop("task_timeout_sec", None)
        openrouter_min_credit_usd = float(kwargs.pop("openrouter_min_credit_usd", os.environ.get("OUROBOROS_BENCH_OPENROUTER_MIN_CREDIT_USD", 5.0)))
        # 3-4 decomposition slots for the agent's own subagents (the root takes one lane).
        # Historic reason: `plan_task` used to run pooled planning scouts, so 1 worker forced a
        # capacity-degraded fallback. Since the 2026-08-15 spec-gate redesign plan review runs
        # NO scouts and needs no pool; the default stays 4 because container memory (a full
        # python process per worker) is what bounds it.
        max_workers = int(kwargs.pop("max_workers", 4))  # v6.55.0: 3-4 subagent slots (root takes one); 10 would blow container memory (full python proc per worker)
        runtime_mode = str(kwargs.pop("runtime_mode", "pro"))
        review_enforcement = str(kwargs.pop("review_enforcement", "blocking"))
        # Safety mode: configurable (full|light|off). Default light keeps the v6.55.0
        # scaffold behavior (LLM safety for integration tools only); off disables the
        # LLM safety pass entirely for a fully-disposable jail. Deterministic guards
        # are unaffected either way.
        safety_mode = str(kwargs.pop("safety_mode", "light")).strip().lower()
        if safety_mode not in ("full", "light", "off"):
            safety_mode = "light"
        task_review_mode = str(kwargs.pop("task_review_mode", "required"))
        disable_agent_web = str(kwargs.pop("disable_agent_web", "true")).strip().lower() not in (
            "0", "false", "no", "off", "",
        )
        # Dataset identity ("<org>/<name>"), threaded from the job config so the adapter can
        # resolve the right per-task cache subtree instead of assuming one hardcoded org.
        dataset = str(kwargs.pop("dataset", "") or "")
        ouroboros_model = str(kwargs.pop("ouroboros_model", ""))
        ouroboros_light_model = str(kwargs.pop("ouroboros_light_model", "google/gemini-3.5-flash"))
        leave_server_running_for_verifier = bool(kwargs.pop("leave_server_running_for_verifier", True))
        # Declared reasoning effort of the submission key (job config kwargs).
        # Forwarded into the container as OUROBOROS_EFFORT_TASK below, so the
        # effort declared in the job config always equals the one the agent
        # actually runs with (leaderboard-honest labeling).
        reasoning_effort = str(kwargs.pop("reasoning_effort", "") or "").strip().lower() or None
        try:
            super().__init__(*args, logs_dir=logs_dir, model_name=model_name, **kwargs)
        except TypeError:
            super().__init__()
            self.logs_dir = Path(logs_dir)
            self.model_name = model_name
        self.workspace_dir = workspace_dir
        self.host_settings_path = Path(
            host_settings_path
            or os.environ.get("OUROBOROS_SETTINGS_PATH")
            or _default_host_settings_path()
        ).expanduser()
        self.install_timeout_sec = int(install_timeout_sec)
        self.server_start_timeout_sec = int(server_start_timeout_sec)
        self.task_timeout_sec = (
            int(task_timeout_sec)
            if task_timeout_sec is not None and int(task_timeout_sec) > 0
            else None
        )
        self.openrouter_min_credit_usd = float(openrouter_min_credit_usd)
        self.max_workers = int(max_workers)
        self.runtime_mode = runtime_mode
        self.review_enforcement = review_enforcement
        self.safety_mode = safety_mode
        self.task_review_mode = task_review_mode
        self.disable_agent_web = bool(disable_agent_web)
        self.dataset = dataset
        self.ouroboros_model = ouroboros_model
        self.ouroboros_light_model = ouroboros_light_model
        self.leave_server_running_for_verifier = bool(leave_server_running_for_verifier)
        self.reasoning_effort = reasoning_effort
        self._run_summary: dict[str, Any] = {}
        # Monotonic timestamp of run() start, so the deadline we hand the agent accounts for the
        # install/server time already consumed inside Harbor's external per-task wall-clock cap.
        self._run_started_monotonic: float | None = None

    @staticmethod
    def name() -> str:
        return "Ouroboros Installed"

    def version(self) -> str | None:
        try:
            version = (_repo_root() / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return version or None

    def _host_settings(self) -> dict[str, Any]:
        from ouroboros.context_mode_compat import normalize_context_mode_compat

        return normalize_context_mode_compat(_json_load(self.host_settings_path))

    def _container_secret_injection_allowed(self, settings: dict[str, Any]) -> bool:
        value = os.environ.get(_CONTAINER_SECRET_OPT_IN)
        if value is None:
            value = settings.get(_CONTAINER_SECRET_OPT_IN)
        return str(value or "").strip().lower() in {"1", "true", "yes", "allow"}

    def _available_host_secret_keys(self, settings: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        for key in sorted(_SECRET_ENV_KEYS):
            if str(os.environ.get(key) or settings.get(key) or "").strip():
                keys.append(key)
        return keys

    def _openrouter_credit_preflight(self, settings: dict[str, Any]) -> None:
        """Refuse to start a trial on a key that cannot pay for it.

        Reads the shared ``openrouter_key_remaining`` helper, i.e. the authoritative
        ``/api/v1/key`` ``limit_remaining``. The old ``/api/v1/credits`` arithmetic
        (``total_credits − total_usage``) is the metric documented to LIE on a nearly
        exhausted key — a key with $0.23 left passed that check and killed half a run — so it
        is gone rather than kept as a fallback. An UNCAPPED key (``limit: null`` → None) has
        no threshold to fail. Transport failures stay non-blocking (the trial would surface
        provider errors anyway and the log is preserved); an unauthorized key still refuses."""
        key = str(os.environ.get("OPENROUTER_API_KEY") or settings.get("OPENROUTER_API_KEY") or "").strip()
        if not key:
            return
        threshold = max(0.0, float(self.openrouter_min_credit_usd or 0.0))
        if threshold <= 0:
            return
        record = self.logs_dir / "openrouter-credit-preflight.json"
        try:
            remaining = openrouter_key_remaining(key)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise RuntimeError("OpenRouter credit preflight failed: token is unauthorized") from exc
            record.write_text(
                json.dumps({"ok": False, "status": exc.code, "warning": "non-blocking"}, indent=2),
                encoding="utf-8",
            )
            return
        except Exception as exc:
            record.write_text(
                json.dumps({"ok": False, "error": type(exc).__name__, "warning": "non-blocking"}, indent=2),
                encoding="utf-8",
            )
            return
        record.write_text(
            json.dumps(
                {
                    "ok": True,
                    "source": "openrouter:/api/v1/key:limit_remaining",
                    "uncapped": remaining is None,
                    "remaining_usd": remaining,
                    "threshold_usd": threshold,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if remaining is not None and remaining < threshold:
            raise RuntimeError(
                f"OpenRouter credit preflight failed: remaining ${remaining:.2f} below threshold ${threshold:.2f}"
            )

    def _enforce_container_secret_policy(self, env: dict[str, str]) -> None:
        settings = self._host_settings()
        blocked = self._available_host_secret_keys(settings)
        if blocked and not self._container_secret_injection_allowed(settings):
            names = ", ".join(blocked)
            raise RuntimeError(
                "Terminal-Bench installed-container mode refuses to inject long-lived provider "
                f"credentials into task containers by default ({names}). Use a host-mediated LLM "
                "bridge when available, or set OUROBOROS_BENCH_ALLOW_CONTAINER_SECRETS=1 only for "
                "trusted local smoke runs where the task container and logs are under operator control."
            )
        if not blocked and not any(key in env for key in _SECRET_ENV_KEYS):
            return

    def _task_annotation_effort(self) -> str | None:
        """Per-task reasoning-effort override declared in the task's annotation file.

        A line ``reasoning-effort: <level>`` (``reasoning_effort`` accepted too) in the
        annotation body lets ONE task run a different thinking budget than the rest of
        the suite — measured on gpt2-codegolf, whose 900s window died on round-1
        reasoning more than on solution quality while the other 88 tasks keep their
        configured effort. The explicit ``--agent-kwarg reasoning_effort=...`` wins
        when present; annotation directives never override it.
        """
        try:
            from devtools.benchmarks.terminal_bench.exp.capabilities import task_annotations as _ann
            if not _ann.annotations_enabled():
                return None
            task_name = _task_name_from_trial_dir(self.logs_dir)
            body = _ann.TASK_ANNOTATIONS.get(task_name) or ""
        except Exception:  # best-effort only — degrade to the configured effort
            return None
        m = re.search(r"(?m)^\s*reasoning[-_]effort\s*:\s*([a-zA-Z]+)\s*$", body)
        return m.group(1).lower() if m else None

    def _container_env(self) -> dict[str, str]:
        settings = self._host_settings()
        allow_secrets = self._container_secret_injection_allowed(settings)
        keys = [
            "OPENAI_BASE_URL",
            "OPENAI_COMPATIBLE_BASE_URL",
            "CLOUDRU_FOUNDATION_MODELS_BASE_URL",
            "GIGACHAT_SCOPE",
            "GIGACHAT_BASE_URL",
            "GIGACHAT_VERIFY_SSL_CERTS",
            "GIGACHAT_PROFANITY_CHECK",
            "OUROBOROS_MODEL",
            "OUROBOROS_MODEL_LIGHT",
            "OUROBOROS_SUBAGENTS",
            "OUROBOROS_REVIEWER_SLOTS",
            "USE_LOCAL_MAIN",
            "USE_LOCAL_LIGHT",
            "USE_LOCAL_FALLBACK",
            "USE_LOCAL_CONSCIOUSNESS",
            # OUROBOROS_MODEL_FALLBACK is deliberately NOT forwarded: the
            # benchmark metric must stay single-model (a host-configured
            # fallback would silently contaminate the measurement).
            "OUROBOROS_WEBSEARCH_MODEL",
            "OUROBOROS_REVIEW_MODELS",
            "OUROBOROS_SCOPE_REVIEW_MODELS",
            "OUROBOROS_SCOPE_REVIEW_MODEL",
            "OUROBOROS_MODEL_DEEP_SELF_REVIEW",
            "CLAUDE_CODE_MODEL",
            "OUROBOROS_EFFORT_TASK",
            "OUROBOROS_EFFORT_REVIEW",
            "OUROBOROS_EFFORT_SCOPE_REVIEW",
            "OUROBOROS_EFFORT_DEEP_SELF_REVIEW",
            "OUROBOROS_RETURN_REASONING",
            # Working-context mode (low | max) for context-ablation runs: the
            # container has no settings.json, so without this forward the
            # runtime silently falls back to the default ("max"). The one-window
            # false provenance tombstone travels with an explicit persisted Low;
            # a bare env Low intentionally remains owner Max for P3.
            "OUROBOROS_CONTEXT_MODE",
            "OUROBOROS_CONTEXT_MODE_AUTO_LOW",
            "TOTAL_BUDGET",
            "OUROBOROS_PER_TASK_COST_USD",
            "OUROBOROS_SOFT_TIMEOUT_SEC",
            "OUROBOROS_HARD_TIMEOUT_SEC",
            "OUROBOROS_TOOL_TIMEOUT_SEC",
        ]
        if allow_secrets:
            keys.extend(sorted(_SECRET_ENV_KEYS))
        env: dict[str, str] = {}
        for key in keys:
            value = os.environ.get(key)
            if value is None:
                value = settings.get(key)
            if value not in (None, ""):
                env[key] = str(value)
        marker_key = "OUROBOROS_CONTEXT_MODE_AUTO_LOW"
        mode_from_env = "OUROBOROS_CONTEXT_MODE" in os.environ
        marker_source = os.environ.get(marker_key) if mode_from_env else settings.get(marker_key)
        marker = str(marker_source or "").strip().lower()
        if marker in {"0", "false", "off"}:
            env[marker_key] = "false"
        else:
            # Context intent is one authority pair.  When mode comes from env, an
            # absent/legacy env marker cannot inherit false owner provenance from disk.
            # Keep that Low bare (effective Low, owner Max) and never recreate true.
            env.pop(marker_key, None)

        if self.ouroboros_model:
            env["OUROBOROS_MODEL"] = self.ouroboros_model
            env["OUROBOROS_SUBAGENTS"] = single_model_subagents_setting(self.ouroboros_model)
        if self.ouroboros_light_model:
            env["OUROBOROS_MODEL_LIGHT"] = self.ouroboros_light_model
        if self.reasoning_effort:
            env["OUROBOROS_EFFORT_TASK"] = self.reasoning_effort
        else:
            # Per-task override declared inside the task's own annotation file
            # (``reasoning-effort: low``). One task can run a different thinking
            # budget than the rest of the suite without a per-run kwarg; the
            # explicit --agent-kwarg reasoning_effort=... still wins when present.
            ann_effort = self._task_annotation_effort()
            if ann_effort:
                env["OUROBOROS_EFFORT_TASK"] = ann_effort

        # Agent-phase pip mirrors the verifier's test.sh: the install shell already
        # writes /root/.pip/pip.conf (file-level TUNA), but env wins over pip.conf
        # for every consumer and covers tools that only read environment. Host
        # value overrides, matching test.sh's ${PIP_INDEX_URL:-...} semantics.
        env["PIP_INDEX_URL"] = os.environ.get("PIP_INDEX_URL") or "https://pypi.tuna.tsinghua.edu.cn/simple"
        env["PIP_TRUSTED_HOST"] = os.environ.get("PIP_TRUSTED_HOST") or "pypi.tuna.tsinghua.edu.cn"
        # Same story for Hugging Face on the agent side: hf.co is blocked in CN,
        # hf-mirror carries the hub + resolve/ files. huggingface_hub reads the
        # endpoint at IMPORT time, so having it in the process env (not just a
        # per-snippet os.environ patch) is what actually makes it stick. Host
        # value overrides, same pattern as PIP_INDEX_URL.
        env["HF_ENDPOINT"] = os.environ.get("HF_ENDPOINT") or "https://hf-mirror.com"

        # Pin the fallback to the EFFECTIVE main model: the container has no
        # settings.json, so leaving the key unset resurrects the
        # SETTINGS_DEFAULTS fallback (a DIFFERENT model) and contaminates the
        # single-model metric; an empty-string env value is skipped by
        # load_settings the same way. Resolution order: explicit kwarg ->
        # forwarded host main model -> packaged default main model.
        fallback_pin = self.ouroboros_model or env.get("OUROBOROS_MODEL", "")
        if not fallback_pin:
            try:
                from ouroboros.config import SETTINGS_DEFAULTS as _DEFAULTS

                fallback_pin = str(_DEFAULTS.get("OUROBOROS_MODEL") or "")
            except Exception:
                fallback_pin = ""
        if fallback_pin:
            # Pin BOTH the legacy singular AND the current plural key. config.parse_fallback_chain
            # reads OUROBOROS_MODEL_FALLBACKS (plural) BEFORE the legacy singular, and the container's
            # SETTINGS_DEFAULTS plural is a DIFFERENT model (the shipped cross-model chain). Leaving
            # the plural unset lets that default shadow the singular pin and contaminate the
            # single-model metric, so we pin the plural to the main model too.
            env["OUROBOROS_MODEL_FALLBACK"] = fallback_pin
            env["OUROBOROS_MODEL_FALLBACKS"] = fallback_pin

        env.update(
            {
                "OUROBOROS_REPO_DIR": _CONTAINER_SRC,
                "OUROBOROS_DATA_DIR": _CONTAINER_DATA,
                "OUROBOROS_SETTINGS_PATH": f"{_CONTAINER_DATA}/settings.json",
                "OUROBOROS_PID_FILE": "/logs/agent/ouroboros.pid",
                "OUROBOROS_PORT_FILE": f"{_CONTAINER_DATA}/state/server_port",
                "OUROBOROS_SERVER_HOST": "127.0.0.1",
                "OUROBOROS_SERVER_PORT": "8765",
                "OUROBOROS_WORKER_START_METHOD": "spawn",
                "OUROBOROS_RUNTIME_MODE": self.runtime_mode,
                "OUROBOROS_REVIEW_ENFORCEMENT": self.review_enforcement,
                "OUROBOROS_TASK_REVIEW_MODE": self.task_review_mode,
                # Pin the shared paid review-cycle ceiling off (bench methodology:
                # historical campaigns ran unbounded acceptance panels; the shipped
                # default of 2 would silently change comparability).
                "OUROBOROS_REVIEW_MAX_CYCLES": "unlimited",
                "OUROBOROS_MAX_WORKERS": str(self.max_workers),
                # v6.55.0: the container is an isolated jail — the LLM safety layer
                # adds cost/latency without protecting anything the deterministic
                # guards don't (34% of all LLM calls in the k=5 run); light keeps
                # the LLM check for integration tools only (Owner decision #14).
                # Configurable via the safety_mode agent-kwarg (full|light|off).
                "OUROBOROS_SAFETY_MODE": self.safety_mode,
                "PYTHONUNBUFFERED": "1",
            }
        )
        return env

    async def _append_log(self, environment: BaseEnvironment, message: str) -> None:
        safe = json.dumps(message)
        await environment.exec(
            command=f"mkdir -p /logs/agent && python3 - <<'PY'\n"
            "from pathlib import Path\n"
            f"Path('/logs/agent/ouroboros-install.log').open('a', encoding='utf-8').write({safe} + '\\n')\n"
            "PY",
            user="root",
        )

    async def _upload_source(self, environment: BaseEnvironment) -> None:
        source = _repo_root()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ouroboros-tb-src-") as tmp:
            clean = Path(tmp) / "repo"
            _copy_clean_source(source, clean)
            write_json(self.logs_dir / "source-provenance.json", _source_copy_provenance(source, clean))
            await environment.exec(
                command=f"rm -rf {_CONTAINER_SRC} && mkdir -p {_CONTAINER_SRC}",
                user="root",
            )
            await environment.upload_dir(clean, _CONTAINER_SRC)

    async def install(self, environment: BaseEnvironment) -> None:
        started = time.monotonic()
        await self._append_log(environment, "install: starting source upload")
        await self._upload_source(environment)
        await self._append_log(environment, "install: source uploaded")

        install_cmd = textwrap.dedent(
            f"""
            set -euo pipefail
            mkdir -p /logs/agent {_CONTAINER_DATA}/logs {_CONTAINER_DATA}/state
            {{
              echo "install: installing system dependencies"
              # CN 网络：把 apt 源切成清华镜像（容器内无代理，直连官方
              # archive.ubuntu.com 能通但慢/不稳；镜像源 22.8s vs 104s，实测）。
              # 兼容 deb822（ubuntu.sources）和 legacy（sources.list）两种格式。
              if command -v apt-get >/dev/null 2>&1; then
                export DEBIAN_FRONTEND=noninteractive
                # Install the apt lock shim BEFORE any apt runs. It serializes every
                # apt call in the container against the other containers through the
                # shared mounts; see _APT_SHIM_BLOCK for why the lock belongs at the
                # call site rather than around this phase.
                {_APT_SHIM_BLOCK}
                # Neutralize docker-clean BEFORE any apt work. Debian/Ubuntu images ship
                # /etc/apt/apt.conf.d/docker-clean, whose DPkg::Post-Invoke and
                # APT::Update::Post-Invoke hooks `rm -f /var/cache/apt/archives/*.deb`.
                # That silently defeats the mounted .deb cache: every trial deletes the
                # archives it just downloaded, so the next trial re-fetches the full
                # ~33MB over the CN network. Measured before this fix: 52 `Get:` lines
                # and an empty cache dir (0 .deb, 52K). Removing the hook is container-
                # local and disposable, which is exactly the scope we want.
                rm -f /etc/apt/apt.conf.d/docker-clean || true
                if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
                  sed -i -E 's#URIs: http://[a-z.-]*(ubuntu|security.ubuntu).com/ubuntu/#URIs: http://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' /etc/apt/sources.list.d/ubuntu.sources || true
                fi
                sed -i -E 's#(deb|deb-src) http://[a-z.-]*(archive|security).ubuntu.com/ubuntu#\\1 http://mirrors.tuna.tsinghua.edu.cn/ubuntu#g' /etc/apt/sources.list 2>/dev/null || true
                # Debian-family images (about 40% of the task images here: VERSION_ID=12,
                # bookworm) use deb.debian.org, which the ubuntu rules above never match, so
                # they were silently left on the default mirror. Measured with apt-get update
                # on alexgshaw/fix-git: 121s against deb.debian.org vs 3s against tuna -- and
                # the whole agent install gets only 360s, so a Debian task on a cold cache
                # would spend a third of its budget on index refresh alone. The security
                # rewrite runs first only for readability; the main rewrite's prefix match
                # would already produce .../debian-security correctly.
                if [ -f /etc/apt/sources.list.d/debian.sources ]; then
                  sed -i -E 's#URIs: https?://[a-z.-]*deb\\.debian\\.org/debian-security#URIs: https://mirrors.tuna.tsinghua.edu.cn/debian-security#g' /etc/apt/sources.list.d/debian.sources || true
                  sed -i -E 's#URIs: https?://[a-z.-]*deb\\.debian\\.org/debian#URIs: https://mirrors.tuna.tsinghua.edu.cn/debian#g' /etc/apt/sources.list.d/debian.sources || true
                fi
                sed -i -E 's#https?://[a-z.-]*deb\\.debian\\.org/debian#https://mirrors.tuna.tsinghua.edu.cn/debian#g' /etc/apt/sources.list 2>/dev/null || true
                # apt is the one install step NOT safe to run concurrently, for two
                # measured reasons (2026-09-17):
                #   * the shared deb cache is a bind mount, so it inherits the HOST dir's
                #     ownership. apt downloads as the `_apt` sandbox user, so once any
                #     container leaves a 0700 `lists/partial` behind, every later trial
                #     dies with "open (13: Permission denied)" — one bad write poisons the
                #     cache for good (observed: a uid-1007/0700 partial killed every
                #     subsequent trial). chmod 777 + Sandbox::User=root below make every
                #     writer root, so ownership cannot drift again.
                #   * the CN mirror does not tolerate parallel streams: with 3 trials
                #     installing at once, 1 in 3 died even WITH retries ("Unable to
                #     connect to mirrors.tuna.tsinghua.edu.cn"); 5-way lost 2 of 5.
                # The serialization now lives in the shim installed above rather than in
                # a flock around this phase (2026-09-18). A phase-level lock here could
                # only ever cover OUR apt call, and the two zeros it cost came from the
                # VERIFIER's apt -- the task's verify.sh is generated inside pytest, so
                # there is no boundary to wrap, and the loser of the race dies in under
                # two seconds because that script starts with `set -e`. The shim takes
                # the same lock file per invocation, so this install phase, every
                # verifier, and any `apt-get` the agent types mid-task all queue on one
                # lock, and a slow install delays a verifier instead of racing it.
                for d in /var/cache/apt /var/cache/apt/archives /var/cache/apt/archives/partial \
                         /var/lib/apt/lists /var/lib/apt/lists/partial; do
                  mkdir -p "$d" 2>/dev/null || true
                  chmod 777 "$d" 2>/dev/null || true
                done
                APT_OK=0
                for attempt in 1 2; do
                  if apt-get -o APT::Sandbox::User=root -o Acquire::Retries=3 update \
                     && apt-get -o APT::Sandbox::User=root -o Acquire::Retries=3 -o Binary::apt::APT::Keep-Downloaded-Packages=true install -y --no-install-recommends git curl bash ca-certificates procps python3 python3-venv python3-pip; then
                    APT_OK=1
                    break
                  fi
                  echo "install: apt attempt $attempt/2 failed; retrying in $((attempt * 10))s"
                  sleep $((attempt * 10))
                done
                if [ "$APT_OK" != "1" ]; then
                  # --- degraded mode ---------------------------------------------------
                  # Measured 2026-09-18 on debian:bullseye-slim: bullseye LTS ended
                  # 2026-08-31, the bullseye-security INDEX is still published (so apt
                  # resolves every security-updated package to it) but its POOL is gone --
                  # 57/57 fetches 404 on tuna AND on security.debian.org, and because apt
                  # is transactional git and curl went down with python3-venv. Five
                  # trials of one task died here before ever starting the agent.
                  #
                  # The image itself was built from a snapshot.debian.org timestamp (this
                  # one ships it as a commented-out source), and that snapshot still has
                  # every file at exactly the versions the image's packages were built
                  # against -- so re-point the withdrawn suite there. A years-old
                  # snapshot needs Acquire::Check-Valid-Until=false, written to
                  # apt.conf.d so the agent's and the verifier's later apt calls inherit
                  # it. Without a shipped timestamp, fall back to pinning the security
                  # suites out and accepting base-pool versions (best effort: an image
                  # whose baked packages are newer than the base pool can then have
                  # uninstallable extras, which the uv venv path below does not need).
                  # `|| true` is load-bearing: the *.list/*.sources globs can match
                  # nothing, grep then exits 2, and under `set -euo pipefail` that would
                  # abort the whole install right here. The pattern deliberately omits
                  # the scheme: in ERE a backslash-question-mark is a LITERAL question
                  # mark, not an optional quantifier (it matched nothing for an hour),
                  # and this block is a non-raw f-string that cannot carry one anyway.
                  # http:// is prepended at the substitution instead.
                  _ouro_snap="$(grep -hsoE 'snapshot\\.debian\\.org/archive/debian-security/[0-9TZ]+' \
                      /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null | head -1 || true)"
                  if [ -n "$_ouro_snap" ]; then
                    echo "install: re-pointing the security suite at the image's build snapshot $_ouro_snap"
                    sed -i -E "s#https?://[^ ]*/debian-security#http://$_ouro_snap#g" \
                        /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true
                    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99-ouroboros-snapshot || true
                  else
                    echo "install: no build snapshot known; pinning the *-security suites out (base-pool versions)"
                    printf 'Package: *\nPin: release n=*security*\nPin-Priority: -1\n' > /etc/apt/preferences.d/ouroboros-drop-security || true
                  fi
                  if apt-get -o APT::Sandbox::User=root -o Acquire::Retries=3 -o Acquire::Check-Valid-Until=false update \
                     && apt-get -o APT::Sandbox::User=root -o Acquire::Retries=3 -o Binary::apt::APT::Keep-Downloaded-Packages=true install -y --no-install-recommends git curl bash ca-certificates procps python3 python3-venv python3-pip; then
                    APT_OK=1
                  fi
                fi
                if [ "$APT_OK" != "1" ]; then
                  # A failed apt is only fatal when it leaves us without a tool every
                  # later step needs; anything else degrades to a warning.
                  for _ouro_tool in git curl python3; do
                    if ! command -v "$_ouro_tool" >/dev/null 2>&1; then
                      echo "install: apt could not provide $_ouro_tool, which the runtime requires"
                      exit 1
                    fi
                  done
                  echo "install: apt failed but every required tool is present; continuing"
                fi
              elif command -v apk >/dev/null 2>&1; then
                apk add --no-cache git curl bash ca-certificates procps python3 py3-pip py3-virtualenv
              elif command -v yum >/dev/null 2>&1; then
                yum install -y git curl bash ca-certificates procps python3 python3-pip
              else
                echo "install: no known package manager; assuming required tools already exist"
              fi

              # ---- uv bootstrap ----------------------------------------------------
              # Must precede the venv: uv creates the venv and installs into it. This
              # replaces the naive `curl -LsSf https://astral.sh/uv/install.sh | sh` that
              # used to sit in the Python-too-old branch: that script hardcodes a GitHub
              # release URL, so from CN it burns ~300s on a blocked connect, and a
              # truncated response leaves a uv/uvx that `command -v` still finds but that
              # segfaults on run. The shared block reuses an existing uv when one is
              # present and otherwise downloads behind CN mirrors with retry + integrity
              # check, so the agent and the verifier cannot drift apart.
{_UV_BOOTSTRAP_BLOCK}
              if ! command -v uv >/dev/null 2>&1; then
                echo "install: no uv available; dependency install will fall back to pip"
              fi

              PYTHON_BIN="$(command -v python3 || command -v python)"
              PY_OK="$("$PYTHON_BIN" - <<'PY'
import sys
print(1 if sys.version_info >= (3, 10) else 0)
PY
)"
              if [ "$PY_OK" != "1" ]; then
                if command -v uv >/dev/null 2>&1; then
                  echo "install: system Python is too old; installing Python 3.12 with uv"
                  if uv python install 3.12; then
                    FOUND_PY="$(uv python find 3.12 || true)"
                    [ -n "$FOUND_PY" ] && PYTHON_BIN="$FOUND_PY"
                  fi
                else
                  echo "install: system Python is too old and uv is unavailable; continuing with $PYTHON_BIN"
                fi
              fi
              echo "install: using $PYTHON_BIN"

              # venv: `uv venv --seed` is much faster than `python -m venv` and still
              # leaves a pip in the environment, which the fallback path below needs.
              # Every step degrades to the plain interpreter, so a uv problem cannot
              # block the trial.
              if command -v uv >/dev/null 2>&1; then
                uv venv --seed --python "$PYTHON_BIN" {_CONTAINER_VENV} || true
              fi
              if [ ! -x {_CONTAINER_VENV}/bin/python ]; then
                "$PYTHON_BIN" -m venv {_CONTAINER_VENV} || {{
                  "$PYTHON_BIN" -m pip install --break-system-packages --user virtualenv || "$PYTHON_BIN" -m pip install --user virtualenv
                  "$PYTHON_BIN" -m virtualenv {_CONTAINER_VENV}
                }}
              fi

              . {_CONTAINER_VENV}/bin/activate
              # pip 也走清华镜像（与 apt 同理：容器无代理，官方 pypi.org 慢；镜像稳）。
              export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
              export PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn"
              mkdir -p "$HOME/.pip"
              printf '[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n' > "$HOME/.pip/pip.conf"
              export PIP_CACHE_DIR={_CONTAINER_PIP_CACHE}
              mkdir -p "$PIP_CACHE_DIR" 2>/dev/null || true
              # pip 强制要求缓存目录属主 == 运行用户，否则静默禁用缓存并全量重下
              # （宿主 OBO_TB_PIP_CACHE 挂载目录属主是宿主机 uid，容器内 pip 通常以
              # root/其它 uid 跑 → 属主不匹配 → cache disabled。启动前 chown 一次，
              # 777 权限下宿主仍可读写，只是属主标记归容器运行用户）。
              chown -R "$(id -u):$(id -g)" "$PIP_CACHE_DIR" 2>/dev/null || true
              # chown 可能把 uv 自建的 755 目录（uv-python 等）留给宿主不可写；
              # 共享挂载目录要求宿主/容器多用户都能写，权限位补 a+rwX（含后续新增）。
              chmod -R a+rwX "$PIP_CACHE_DIR" 2>/dev/null || true
              # uv 包缓存同样落到挂载目录（默认 ~/.cache/uv 随容器销毁，每次 trial
              # 全量重下 python+torch）。verifier 的注入 test.sh 也读这个挂载点。
              export UV_CACHE_DIR="$PIP_CACHE_DIR"
              # 解释器安装目录也落挂载（默认 ~/.local/share/uv/python 随容器销毁，
              # 新容器每次重下 python；持久化后跨 trial 复用，实测命中 ~0.5s）。
              export UV_PYTHON_INSTALL_DIR="$PIP_CACHE_DIR/uv-python"
              mkdir -p "$UV_PYTHON_INSTALL_DIR" 2>/dev/null || true
              VENV_PY={_CONTAINER_VENV}/bin/python
              # ---- dependency install: uv primary, pip fallback --------------------
              # uv resolves and downloads far faster than pip and shares the mounted
              # UV_CACHE_DIR, so repeated trials stop re-fetching the same wheels.
              UV_INSTALL_OK=0
              if command -v uv >/dev/null 2>&1; then
                if uv pip install --python "$VENV_PY" -r {_CONTAINER_SRC}/requirements-runtime.lock; then
                  UV_INSTALL_OK=1
                else
                  echo "install: uv requirements install failed; retrying without optional tree-sitter code-intel deps (lazy runtime import, degrades gracefully)"
                  grep -ivE 'tree[-_]sitter' {_CONTAINER_SRC}/requirements-runtime.lock > /tmp/ouro_reqs_no_treesitter.txt
                  uv pip install --python "$VENV_PY" -r /tmp/ouro_reqs_no_treesitter.txt && UV_INSTALL_OK=1
                fi
              fi
              if [ "$UV_INSTALL_OK" != "1" ]; then
                echo "install: falling back to pip for requirements"
                "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
                python -m pip install --upgrade pip setuptools wheel
                python -m pip install -r {_CONTAINER_SRC}/requirements-runtime.lock || {{
                  echo "install: pip requirements install failed; retrying without optional tree-sitter code-intel deps (lazy runtime import, degrades gracefully)"
                  grep -ivE 'tree[-_]sitter' {_CONTAINER_SRC}/requirements-runtime.lock > /tmp/ouro_reqs_no_treesitter.txt
                  python -m pip install -r /tmp/ouro_reqs_no_treesitter.txt
                }}
              fi

              if [ "$UV_INSTALL_OK" = "1" ]; then
                uv pip install --python "$VENV_PY" -e {_CONTAINER_SRC} --no-deps
                # ffmpeg in the AGENT prefix (v6.56.0, P0-1): task images rarely ship
                # ffmpeg, so extract_video_frames was dead in TB tasks. The wheel binary
                # is found by media._resolve_ffmpeg via imageio_ffmpeg.get_ffmpeg_exe();
                # a mirror hiccup degrades gracefully (typed UNAVAILABLE + cv2 hint).
                uv pip install --python "$VENV_PY" imageio-ffmpeg || echo "install: imageio-ffmpeg failed (extract_video_frames degrades to the cv2 workaround)"
              else
                python -m pip install -e {_CONTAINER_SRC} --no-deps
                python -m pip install imageio-ffmpeg || echo "install: imageio-ffmpeg failed (extract_video_frames degrades to the cv2 workaround)"
              fi

              # ---- publish uv where the verifier bootstrap looks for it -------------
              # The verifier's injected test.sh reuses an existing uv instead of fetching
              # one. The mounted cache dir is its first probe and outlives the container,
              # so later trials skip the download entirely; the venv copy covers the
              # shared-venv verifier mode.
              if command -v uv >/dev/null 2>&1; then
                mkdir -p "$PIP_CACHE_DIR/uv-bin" 2>/dev/null || true
                cp -f "$(command -v uv)" "$PIP_CACHE_DIR/uv-bin/uv" 2>/dev/null || true
                if command -v uvx >/dev/null 2>&1; then
                  cp -f "$(command -v uvx)" "$PIP_CACHE_DIR/uv-bin/uvx" 2>/dev/null || true
                fi
                # Publish BOTH into the venv too. Task test.sh files in this cache put
                # /opt/ouroboros-venv/bin first on PATH and then call `uvx`; copying only
                # `uv` there produced "test.sh: line N: uvx: command not found" and a
                # reward of 0 on every task whose verifier shells out to uvx.
                cp -f "$(command -v uv)" {_CONTAINER_VENV}/bin/uv 2>/dev/null || true
                if command -v uvx >/dev/null 2>&1; then
                  cp -f "$(command -v uvx)" {_CONTAINER_VENV}/bin/uvx 2>/dev/null || true
                fi
                chmod -R a+rwX "$PIP_CACHE_DIR/uv-bin" 2>/dev/null || true
                chmod a+rX {_CONTAINER_VENV}/bin/uv {_CONTAINER_VENV}/bin/uvx 2>/dev/null || true
              fi
              chmod -R a+rX {_CONTAINER_SRC} {_CONTAINER_VENV} /logs/agent
              {_CONTAINER_VENV}/bin/python -c 'import importlib.metadata; print("ouroboros", importlib.metadata.version("ouroboros"))'
              echo "install: complete"
            }} 2>&1 | tee -a /logs/agent/ouroboros-install.log
            """
        ).strip()
        await self.exec_as_root(
            environment,
            command=install_cmd,
            timeout_sec=self.install_timeout_sec,
        )
        elapsed = time.monotonic() - started
        await self._append_log(environment, f"install: elapsed_sec={elapsed:.1f}")

        # Patch test.sh to use Chinese mirrors for faster package downloads
        await self._patch_test_sh_for_china(environment)

    async def _patch_test_sh_for_china(self, environment: BaseEnvironment) -> None:
        """Patch test.sh to use Chinese mirrors for uv package downloads.

        The verifier runs test.sh from the HOST package cache — harbor's
        ``Verifier.verify()`` uploads ``~/.cache/harbor/tasks/packages/<org>/<task>/
        <digest>/tests`` into the verifier environment (shared or separate) and
        overwrites the container copy — so the HOST cache copy is the authoritative
        injection point. The in-container copy is only a belt-and-braces for
        environments that skip the tests upload.

        Injected block (loaded from the module constant, single source of truth):
        1) PyPI + python-build-standalone downloads go through CN mirrors;
        2) an already-installed uv is reused (agent install leaves one at
           /opt/ouroboros-venv/bin/uv or $HOME/.local/bin/uv) — NEVER download when
           a usable uv exists;
        3) only when no uv exists anywhere does it fetch the binary via gh-proxy
           (astral's install.sh hardcodes a GitHub release URL, unreachable from CN,
           and burns ~300s on a blocked connect).
        """
        await self._patch_test_sh_host_cache(environment)
        await self._patch_test_sh_in_container(environment)

    async def _patch_test_sh_host_cache(self, environment: BaseEnvironment) -> None:
        """Patch the host harbor package cache copy of test.sh (verifier source)."""
        task_name = _task_name_from_trial_dir(self.logs_dir)
        if not task_name:
            return
        try:
            toml = self._cached_task_toml(task_name)
            if toml is None:
                # Loud, not silent. A skipped patch means the verifier runs the task's own
                # `curl -LsSf https://astral.sh/uv/... | sh`, which cannot reach GitHub from
                # here: it burns ~130s and then fails with "uvx: command not found", scoring
                # every trial 0 no matter what the agent delivered.
                await self._append_log(
                    environment,
                    f"patch: WARNING no cached task.toml for {task_name!r} -- "
                    f"test.sh left unpatched, the verifier may fail to find uv",
                )
                return
            test_sh = toml.parent / "tests" / "test.sh"
            if not test_sh.is_file():
                await self._append_log(
                    environment,
                    f"patch: WARNING {test_sh} not found -- test.sh left unpatched",
                )
                return
            original = test_sh.read_text(encoding="utf-8")
            patched = _inject_test_sh_mirror_block(original)
            if patched is not None and patched != original:
                test_sh.write_text(patched, encoding="utf-8")
                await self._append_log(
                    environment, f"patch: host cache test.sh updated ({test_sh})"
                )
        except Exception as exc:
            log.warning("patch: host cache test.sh update failed: %s", exc)

    async def _patch_test_sh_in_container(self, environment: BaseEnvironment) -> None:
        """Patch /tests/test.sh inside the task container (shared-verifier belt)."""
        # Both pieces and both markers are baked into the heredoc by the HOST (single
        # source: _TEST_SH_MIRROR_BLOCK / _APT_SHIM_BLOCK), so the container python needs
        # no repo import. They travel as ARGUMENTS rather than as names interpolated into
        # the python source: the previous version wrote the bare identifier
        # _TEST_SH_INJECTED_MARKER into the container-side script, which is a NameError,
        # so this fallback path could never patch anything -- it only looked healthy
        # because the host-cache path usually got there first and this one then exited
        # early.
        patch_cmd = (
            textwrap.dedent(
                """
                set -euo pipefail
                TEST_SH="/tests/test.sh"
                if [ ! -f "$TEST_SH" ]; then
                    echo "patch: test.sh not found, skipping"
                    exit 0
                fi
                BLOCK='@@MIRROR_BLOCK@@'
                SHIM='@@SHIM_BLOCK@@'
                BLOCK_MARKER='@@BLOCK_MARKER@@'
                SHIM_MARKER='@@SHIM_MARKER@@'
                python3 - "$TEST_SH" "$BLOCK" "$SHIM" "$BLOCK_MARKER" "$SHIM_MARKER" <<'PY'
                import sys
                from pathlib import Path

                path = Path(sys.argv[1])
                block, shim = sys.argv[2], sys.argv[3]
                block_marker, shim_marker = sys.argv[4], sys.argv[5]
                text = path.read_text(encoding="utf-8")
                need_block = block_marker not in text
                need_shim = shim_marker not in text
                if not (need_block or need_shim):
                    print("patch: in-container test.sh already patched")
                    raise SystemExit(0)
                lines = text.splitlines()
                if lines and lines[0].startswith("#!"):
                    head, rest = lines[0], lines[1:]
                    new_lines = [head]
                    if need_block:
                        new_lines.append(block_marker)
                        new_lines.extend(block.rstrip("\\n").splitlines())
                        new_lines.append("# Gate the original uv install line (uv already bootstrapped above):")
                        for line in rest:
                            if line.strip().startswith("curl -LsSf https://astral.sh/uv/") and "install.sh" in line:
                                stmt = line.strip()
                                # bash `{ list; }` needs a terminator before `}`.
                                new_lines.append('[ -n "$UV_ALREADY_AVAILABLE" ] || { ' + stmt + "; }")
                            else:
                                new_lines.append(line)
                    else:
                        new_lines.extend(rest)
                    if need_shim:
                        new_lines.extend(shim.rstrip("\\n").splitlines())
                    content = "\\n".join(new_lines) + "\\n"
                    # github -> gh-proxy (direct raw/release assets are blocked in CN);
                    # lines already carrying gh-proxy are left alone, so re-patching is a no-op.
                    content = "".join(
                        ln if "gh-proxy" in ln else ln.replace(
                            "https://github.com/", "https://gh-proxy.com/https://github.com/"
                        )
                        for ln in content.splitlines(keepends=True)
                    )
                    path.write_text(content, encoding="utf-8")
                    path.chmod(0o755)
                    print("patch: in-container test.sh updated")
                PY
                """
            )
            .replace("@@MIRROR_BLOCK@@", _TEST_SH_MIRROR_BLOCK.replace("'", "'\\''"))
            .replace("@@SHIM_BLOCK@@", _APT_SHIM_BLOCK.replace("'", "'\\''"))
            .replace("@@BLOCK_MARKER@@", _TEST_SH_INJECTED_MARKER.replace("'", "'\\''"))
            .replace("@@SHIM_MARKER@@", _APT_SHIM_MARKER.replace("'", "'\\''"))
            .strip()
        )

        result = await environment.exec(command=patch_cmd, user="root", timeout_sec=30)
        if result.return_code != 0:
            await self._append_log(environment, f"patch: warning - test.sh patch failed: {result.stderr}")
        else:
            await self._append_log(environment, "patch: test.sh optimized for China network")

    async def _ensure_workspace_git_root(self, environment: BaseEnvironment) -> None:
        workspace_dir = shlex.quote(self.workspace_dir)
        command = textwrap.dedent(
            f"""
            set -euo pipefail
            workspace_dir={workspace_dir}
            cd "$workspace_dir"
            if git rev-parse --show-toplevel >/tmp/ouroboros-git-root 2>/dev/null; then
              root="$(cat /tmp/ouroboros-git-root)"
              if [ "$root" != "$workspace_dir" ]; then
                echo "workspace git root is $root, expected $workspace_dir" >&2
                exit 2
              fi
            else
              git init
              git config user.email ouroboros-bench@example.invalid
              git config user.name "Ouroboros Bench"
            fi
            """
        ).strip()
        result = await environment.exec(command=command, cwd=self.workspace_dir, timeout_sec=60)
        if result.return_code != 0:
            raise RuntimeError(
                f"failed to prepare {self.workspace_dir} as git workspace: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )

    async def _resolve_workspace_dir(self, environment: BaseEnvironment) -> None:
        """Pick the agent's active workspace.

        The image's WORKDIR is the task author's intent — this is the directory
        the verifier runs in, and where task-provided files live. Read it via
        ``readlink /proc/1/cwd`` inside the container: PID 1 keeps the image's
        ``WorkingDir`` as its cwd, so this probe works regardless of whether
        ``docker inspect`` is reachable from inside the container.

        Fall back to the old ``/app`` (or ``/workspace``) heuristic only when
        the probe fails — that preserves the behavior for the bulk of tasks
        (86/89 of the dataset uses WORKDIR=/app) while fixing the handful of
        tasks whose image WORKDIR'd elsewhere. Without this, tasks like
        ``prove-plus-comm`` (WORKDIR=/workspace) end up with ``/app`` as the
        workspace because our ``/app/datasets`` bind-mount happens to *create*
        ``/app``, defeating the old "use /workspace only if /app is missing"
        fallback and forcing the agent to work in a phantom directory.
        """
        probe = await environment.exec(
            command="readlink /proc/1/cwd 2>/dev/null",
            timeout_sec=10,
        )
        image_workdir = probe.stdout.strip() if probe.return_code == 0 else ""
        if image_workdir:
            check = await environment.exec(
                command=f"test -d {shlex.quote(image_workdir)}",
                timeout_sec=10,
            )
            if check.return_code == 0 and image_workdir != self.workspace_dir:
                self.workspace_dir = image_workdir
                await self._append_log(
                    environment,
                    f"workspace: using image WORKDIR {image_workdir} (via readlink /proc/1/cwd)",
                )
                return

        requested = self.workspace_dir
        quoted_requested = shlex.quote(requested)
        result = await environment.exec(command=f"test -d {quoted_requested}", timeout_sec=10)
        if result.return_code == 0:
            return
        if requested == _CONTAINER_WORKSPACE:
            fallback = await environment.exec(command="test -d /workspace", timeout_sec=10)
            if fallback.return_code == 0:
                self.workspace_dir = "/workspace"
                await self._append_log(environment, "workspace: /app missing, using /workspace")
                return
        create = await environment.exec(command=f"mkdir -p {quoted_requested}", user="root", timeout_sec=10)
        if create.return_code != 0:
            raise RuntimeError(
                f"failed to create workspace {requested}: stdout={create.stdout!r} stderr={create.stderr!r}"
            )
        await self._append_log(environment, f"workspace: created {requested}")

    async def _start_server(self, environment: BaseEnvironment, env: dict[str, str]) -> None:
        start_cmd = textwrap.dedent(
            f"""
            set -euo pipefail
            mkdir -p {_CONTAINER_DATA}/logs {_CONTAINER_DATA}/state /logs/agent
            rm -f /logs/agent/ouroboros.pid
            cd {_CONTAINER_SRC}
            nohup {_CONTAINER_VENV}/bin/python server.py --host 127.0.0.1 --port 8765 \
              > /logs/agent/ouroboros-server.stdout.log \
              2> /logs/agent/ouroboros-server.stderr.log &
            echo "$!" > /logs/agent/ouroboros.pid
            """
        ).strip()
        result = await environment.exec(command=start_cmd, env=env, timeout_sec=30)
        if result.return_code != 0:
            raise RuntimeError(f"failed to start Ouroboros server: {result.stdout}\n{result.stderr}")

        wait_cmd = textwrap.dedent(
            f"""
            {_CONTAINER_VENV}/bin/python - <<'PY'
            import json
            import pathlib
            import sys
            import time
            import urllib.request

            deadline = time.time() + {self.server_start_timeout_sec}
            last_error = ""
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen("{_SERVER_URL}/api/state", timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    pathlib.Path("/logs/agent/ouroboros-state.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if data.get("supervisor_ready"):
                        print(json.dumps({{"ready": True, "state": data}}, ensure_ascii=False))
                        sys.exit(0)
                    last_error = "server responded but supervisor_ready=false"
                except Exception as exc:
                    last_error = repr(exc)
                time.sleep(2)
            print(json.dumps({{"ready": False, "error": last_error}}, ensure_ascii=False))
            sys.exit(1)
            PY
            """
        ).strip()
        result = await environment.exec(command=wait_cmd, env=env, timeout_sec=self.server_start_timeout_sec + 20)
        if result.return_code != 0:
            raise RuntimeError(f"Ouroboros server did not become ready: {result.stdout}\n{result.stderr}")

    async def _network_preflight(self, environment: BaseEnvironment, env: dict[str, str]) -> None:
        provider_url = ""
        provider_name = ""
        if env.get("OPENROUTER_API_KEY"):
            provider_url = "https://openrouter.ai/api/v1/models"
            provider_name = "openrouter"
        elif env.get("OPENAI_COMPATIBLE_API_KEY"):
            base_url = str(env.get("OPENAI_COMPATIBLE_BASE_URL") or env.get("OPENAI_BASE_URL") or "").strip()
            provider_name = "openai_compatible"
            if base_url:
                provider_url = base_url.rstrip("/") + "/models"
            else:
                (self.logs_dir / "network-preflight.txt").write_text(
                    "openai_compatible_preflight_error missing OPENAI_COMPATIBLE_BASE_URL\n",
                    encoding="utf-8",
                )
                raise RuntimeError("OPENAI_COMPATIBLE_API_KEY requires OPENAI_COMPATIBLE_BASE_URL for container preflight")
        elif env.get("OPENAI_API_KEY"):
            provider_url = "https://api.openai.com/v1/models"
            provider_name = "openai"
        elif env.get("ANTHROPIC_API_KEY"):
            provider_url = "https://api.anthropic.com/v1/models"
            provider_name = "anthropic"
        elif env.get("CLOUDRU_FOUNDATION_MODELS_API_KEY"):
            provider_url = (env.get("CLOUDRU_FOUNDATION_MODELS_BASE_URL") or "https://foundation-models.api.cloud.ru/v1").rstrip("/") + "/models"
            provider_name = "cloudru"
        elif env.get("GIGACHAT_CREDENTIALS") or (env.get("GIGACHAT_USER") and env.get("GIGACHAT_PASSWORD")):
            provider_url = (env.get("GIGACHAT_BASE_URL") or "https://gigachat.devices.sberbank.ru/api/v1").rstrip("/") + "/models"
            provider_name = "gigachat"
        if not provider_url:
            (self.logs_dir / "network-preflight.txt").write_text(
                "provider preflight skipped: no provider API key was injected; "
                "Ouroboros runtime will surface provider configuration errors.\n",
                encoding="utf-8",
            )
            return
        command = textwrap.dedent(
            f"""
            python3 - <<'PY'
            import sys
            import time
            import urllib.error
            import urllib.request
            attempts = 3
            last_exc = None
            for attempt in range(1, attempts + 1):
                # User-Agent matters: Cloudflare-fronted gateways (opencode.ai) answer
                # 403 "error code: 1010" to urllib's default UA while allowing the real
                # clients. Sending a curl UA makes this probe mean what it says instead
                # of relying on "4xx still counts as reachable".
                req = urllib.request.Request(
                    {provider_url!r}, method="GET", headers={{"User-Agent": "curl/8.5.0"}}
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        print({provider_name!r} + "_preflight_status", resp.status)
                        sys.exit(0 if 200 <= resp.status < 500 else 1)
                except urllib.error.HTTPError as exc:
                    # No Authorization header is sent on purpose: this only proves the
                    # endpoint is reachable, so 4xx (401 on a bare /models GET) is a PASS.
                    print({provider_name!r} + "_preflight_status attempt " + str(attempt) + "/" + str(attempts), exc.code)
                    sys.exit(0 if 200 <= exc.code < 500 else 1)
                except Exception as exc:
                    print({provider_name!r} + "_preflight_error attempt " + str(attempt) + "/" + str(attempts), type(exc).__name__)
                    last_exc = exc
                if attempt < attempts:
                    time.sleep(5)
            print("preflight_failed after " + str(attempts) + " attempts:", last_exc)
            sys.exit(1)
            PY
            """
        ).strip()
        result = await environment.exec(command=command, timeout_sec=90)
        (self.logs_dir / "network-preflight.txt").write_text(
            f"stdout:\n{result.stdout or ''}\nstderr:\n{result.stderr or ''}\nreturn_code={result.return_code}\n",
            encoding="utf-8",
        )
        if result.return_code != 0:
            raise RuntimeError(f"container cannot reach configured provider endpoint ({provider_name})")

    def _disabled_tools(self) -> list[str]:
        # Reward-hacking guard: faithful TB2.1 runs give the task FULL container network
        # (every task.toml declares allow_internet=true; tasks like build-cython-ext/caffe-cifar-10
        # require `git clone`), so we must NOT block shell egress. We only withhold the agent's OWN
        # LLM-powered web/search/browser/VLM tools (which a reference shell agent wouldn't have) via
        # the declarative `disabled_tools` tool-policy. This leaves allowed_resources at its permissive
        # default (network/git/pip available) and never trips the web<->network cross-implication in
        # the registry resource gate. (Previously this set allowed_resources.network=false, which
        # wrongly blocked `git clone` even though the container had working network.)
        # The web group mirrors the registry's `_WEB_TOOLS` set (web_search/
        # browse_page/browser_action/youtube_transcript — the transcript tool joined
        # `_WEB_TOOLS` in v6.52.1 and the adapter's list had silently drifted until
        # v6.55.0; a sync test now pins the mirror). On top of it, web-off runs also
        # withhold the DELEGATED-vision tools (analyze_screenshot/vlm_query): they
        # route through an LLM/VLM lookup a reference shell agent would not have.
        # `view_image` is intentionally NOT disabled: it is a LOCAL image-to-model
        # tool registered OUTSIDE `_WEB_TOOLS` (it injects a local file into the
        # agent's own model context, no web/second-model call), so local-image tasks
        # (e.g. financial-document/code-from-image) keep a legitimate vision
        # affordance a reference agent could also have.
        # v6.55.0: claude_code_edit is disabled in EVERY bench run regardless of the
        # web gate — benches measure Ouroboros as a single-model harness; the embedded
        # Claude-Code delegate is a separate future experiment.
        # Operator 2026-07-23: schedule_subagent disabled for the no-swarm submittable
        # campaign. The v6.81.0 runs had to disclose "no task delegation" rather than
        # "no subagents", because `plan_task` then ran pooled planning scouts that surfaced in
        # traces as `delegation_role=subagent`. Since the 2026-08-15 spec-gate redesign plan
        # review runs NO scouts: with this tool withheld a run spawns no subagents at all, and
        # a submission may say so — check the traces of the run you are actually disclosing.
        disabled = ["claude_code_edit", "schedule_subagent"]
        if getattr(self, "disable_agent_web", True):
            disabled = list(self._WEB_TOOLS_MIRROR) + list(self._DELEGATED_VISION_TOOLS) + disabled
        return disabled

    async def _run_ouroboros_task(self, environment: BaseEnvironment, env: dict[str, str]) -> dict[str, Any]:
        workspace_root = json.dumps(self.workspace_dir)
        disabled_tools_line = f'"disabled_tools": {json.dumps(self._disabled_tools())},'
        truncation_codes_literal = repr(tuple(sorted(RUNTIME_TRUNCATION_REASON_CODES)))

        runner = textwrap.dedent(
            f"""
            import json
            import os
            import pathlib
            import sys
            import time
            import urllib.parse
            import urllib.request

            instruction = pathlib.Path("/logs/agent/instruction.txt").read_text(encoding="utf-8")
            started = time.time()
            run_log = pathlib.Path("/logs/agent/ouroboros-run.jsonl")
            stderr_log = pathlib.Path("/logs/agent/ouroboros-run.stderr.log")
            task_id_path = pathlib.Path("/logs/agent/ouroboros-current-task-id.txt")

            def api(method, path, body=None, timeout=30):
                data = None
                headers = {{"Accept": "application/json"}}
                if body is not None:
                    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                req = urllib.request.Request("{_SERVER_URL}" + path, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw.strip() else {{}}

            def emit(event):
                with run_log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\\n")

            task_body = {{
                "description": instruction,
                "workspace_root": {workspace_root},
                "workspace_mode": "external",
                "memory_mode": "empty",
                "service_teardown": "keep",
                "actor_id": "harbor-terminal-bench",
                "source": "terminal-bench",
                "metadata": {{"source": "terminal-bench", "delegation_role": "root"}},
                {disabled_tools_line}
            }}
            task_timeout = {int(self._effective_task_timeout_sec())}
            if task_timeout > 0:
                task_body["timeout_sec"] = task_timeout
            created = api("POST", "/api/tasks", task_body)
            task_id = str(created.get("task_id") or "")
            if not task_id:
                stderr_log.write_text(f"task creation did not return task_id: {{created!r}}\\n", encoding="utf-8")
                print(json.dumps({{"return_code": 1, "elapsed_sec": round(time.time() - started, 3), "status": "create_failed"}}))
                sys.exit(1)
            task_id_path.write_text(task_id, encoding="utf-8")
            emit({{"type": "task_created", "task_id": task_id, "data": created}})

            latest = {{}}
            seen_events = set()
            final_statuses = {{"completed", "failed", "cancelled", "rejected_duplicate"}}
            while True:
                result = api("GET", "/api/tasks/" + urllib.parse.quote(task_id), timeout=30)
                for event in result.get("events") or []:
                    key = (str(event.get("type") or ""), str(event.get("ts") or event.get("seq") or ""))
                    if key in seen_events:
                        continue
                    seen_events.add(key)
                    emit({{"type": "task_event", "task_id": task_id, "data": event}})
                status = str(result.get("status") or "")
                if status in final_statuses:
                    latest = result
                    pathlib.Path("/logs/agent/ouroboros-task-result.json").write_text(
                        json.dumps(latest, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    emit({{"type": "final", "task_id": task_id, "result": latest}})
                    break
                time.sleep(2)

            status = str(latest.get("status") or "")
            reason_code = str(latest.get("reason_code") or "")
            axes = latest.get("outcome_axes") if isinstance(latest.get("outcome_axes"), dict) else {{}}
            execution = axes.get("execution") if isinstance(axes.get("execution"), dict) else {{}}
            infra_failed = (
                reason_code == "llm_api_error"
                or str(execution.get("status") or "") == "infra_failed"
                or str(execution.get("reason_code") or "") == "llm_api_error"
            )
            # The runtime can stop a task for a reason that is NOT "the task is finished" --
            # the per-task USD reservation rail (budget_exhausted), the round cap
            # (round_limit), the loop-local deadline (deadline_local). That is neither
            # infra_failed nor a fair-shot wrong answer, and without it a cost-truncated
            # trial is indistinguishable from an honest failure downstream. The vocabulary is
            # INTERPOLATED from result_index.RUNTIME_TRUNCATION_REASON_CODES on the host, not
            # restated here: this runner is a source template executed inside the task
            # container, so the literal below is generated, and a runtime code added upstream
            # cannot go missing from it.
            loop_outcome = latest.get("loop_outcome") if isinstance(latest.get("loop_outcome"), dict) else {{}}
            resource_limit = latest.get("resource_limit")
            if not isinstance(resource_limit, dict):
                resource_limit = loop_outcome.get("resource_limit")
            truncated = reason_code in {truncation_codes_literal}
            summary = {{
                "return_code": 2 if infra_failed else 0,
                "task_status_code": 0 if status == "completed" else 1,
                "elapsed_sec": round(time.time() - started, 3),
                "task_id": latest.get("task_id") or latest.get("id"),
                "status": status,
                "reason_code": reason_code,
                "infra_failed": infra_failed,
                "truncated": truncated,
                "resource_limit": resource_limit if isinstance(resource_limit, dict) else {{}},
                "degraded": bool(latest.get("degraded") or loop_outcome.get("degraded")),
                "degraded_reason": str(
                    latest.get("degraded_reason") or loop_outcome.get("degraded_reason") or ""
                ),
                "cost_usd": latest.get("cost_usd"),
                "prompt_tokens": latest.get("prompt_tokens"),
                "completion_tokens": latest.get("completion_tokens"),
                "total_rounds": latest.get("total_rounds"),
            }}
            pathlib.Path("/logs/agent/ouroboros-run-summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(json.dumps(summary, ensure_ascii=False))
            sys.exit(2 if infra_failed else 0)
            """
        ).strip()
        command = "cat > /tmp/run_ouroboros_task.py <<'PY'\n" + runner + "\nPY\n" + (
            f"{_CONTAINER_VENV}/bin/python /tmp/run_ouroboros_task.py"
        )
        result = await environment.exec(
            command=command,
            env=env,
            cwd=self.workspace_dir,
            timeout_sec=(self.task_timeout_sec + 60 if self.task_timeout_sec is not None else None),
        )
        parsed: dict[str, Any] | None = None
        try:
            candidate = json.loads((result.stdout or "").strip().splitlines()[-1])
            if isinstance(candidate, dict):
                parsed = candidate
        except Exception:
            parsed = None
        # The runner exits 2 (not 0) purely to SIGNAL a terminal `infra_failed` result — the task
        # still reached a terminal /api/tasks state (status completed/failed). That is a real terminal
        # outcome, NOT a Harbor wall-clock interruption, so treat it as a returned result (caller sets
        # reached_terminal_result=True and the captured summary is NOT mislabeled
        # captured_after_cancellation). Only a nonzero exit that produced NO terminal summary (e.g. a
        # genuine runner crash / create_failed) is a real failure to raise on.
        if parsed is not None and str(parsed.get("status") or "") in ("completed", "failed"):
            return parsed
        if result.return_code != 0:
            raise RuntimeError(f"Ouroboros task runner failed: {result.stdout}\n{result.stderr}")
        return parsed if parsed is not None else {"raw_stdout": result.stdout or "", "raw_stderr": result.stderr or ""}

    async def _emit_trajectory(
        self, environment: BaseEnvironment, env: dict[str, str]
    ) -> dict[str, Any]:
        """Build /logs/agent/trajectory.json in-container from the trial logs.

        Uses the stdlib-only builder shipped with the uploaded source tree, so
        the exact same mapping serves live runs and the offline backfill
        converter (build_atif_trajectories.py).
        """
        builder = f"{_CONTAINER_SRC}/devtools/benchmarks/terminal_bench/atif.py"
        model = json.dumps(self.ouroboros_model or "")
        result = await environment.exec(
            command=(
                f"{_CONTAINER_VENV}/bin/python {builder} /logs/agent --model {model}"
            ),
            env=env,
            timeout_sec=120,
        )
        if result.return_code != 0:
            raise RuntimeError(
                f"trajectory builder exited {result.return_code}: {result.stderr}"
            )
        try:
            payload = json.loads((result.stdout or "").strip().splitlines()[-1])
            metrics = payload.get("physical_metrics")
            return metrics if isinstance(metrics, dict) else {}
        except (IndexError, ValueError):
            return {}

    async def _stop_server(self, environment: BaseEnvironment) -> None:
        await environment.exec(
            command=(
                "if [ -s /logs/agent/ouroboros-current-task-id.txt ]; then "
                "TASK_ID=$(cat /logs/agent/ouroboros-current-task-id.txt); "
                "export TASK_ID; "
                f"{_CONTAINER_VENV}/bin/python - <<'PY' || true\n"
                "import os, urllib.parse, urllib.request\n"
                "task_id = os.environ.get('TASK_ID', '')\n"
                "if task_id:\n"
                f"    urllib.request.urlopen(urllib.request.Request('{_SERVER_URL}/api/tasks/' + urllib.parse.quote(task_id) + '/cancel', data=b'{{}}', method='POST'), timeout=5).read()\n"
                "PY\n"
                "fi; "
                "if [ -f /logs/agent/ouroboros.pid ]; then "
                "kill $(cat /logs/agent/ouroboros.pid) 2>/dev/null || true; "
                "fi; "
                "pkill -TERM -f '/opt/ouroboros-src|/opt/ouroboros-venv/bin/ouroboros' 2>/dev/null || true"
            ),
            timeout_sec=10,
        )

    async def _capture_current_task_summary(self, environment: BaseEnvironment, interrupted: bool = True) -> None:
        """Persist best-effort task state. ``interrupted`` records whether Harbor cancelled
        agent.run mid-exec (True) vs a routine post-terminal snapshot (False); it is written as
        ``captured_after_cancellation`` so the disclosure ledger can tell a real cancellation
        apart from a normal terminal finish."""
        captured_after_cancellation = "True" if interrupted else "False"
        command = textwrap.dedent(
            f"""
            if [ ! -s /logs/agent/ouroboros-current-task-id.txt ]; then
              exit 0
            fi
            {_CONTAINER_VENV}/bin/python - <<'PY'
            import json
            import pathlib
            import time
            import urllib.parse
            import urllib.request

            task_id = pathlib.Path("/logs/agent/ouroboros-current-task-id.txt").read_text(encoding="utf-8").strip()
            if not task_id:
                raise SystemExit(0)
            try:
                with urllib.request.urlopen("{_SERVER_URL}/api/tasks/" + urllib.parse.quote(task_id), timeout=10) as resp:
                    latest = json.loads(resp.read().decode("utf-8", errors="replace"))
            except Exception as exc:
                pathlib.Path("/logs/agent/ouroboros-run.stderr.log").open("a", encoding="utf-8").write(
                    "best-effort task summary failed: " + repr(exc) + "\\n"
                )
                raise SystemExit(0)

            pathlib.Path("/logs/agent/ouroboros-task-result.json").write_text(
                json.dumps(latest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            status = str(latest.get("status") or "")
            summary = {{
                "return_code": 0,
                "task_status_code": 0 if status == "completed" else 1,
                "elapsed_sec": None,
                "task_id": latest.get("task_id") or latest.get("id") or task_id,
                "status": status,
                "cost_usd": latest.get("cost_usd"),
                "prompt_tokens": latest.get("prompt_tokens"),
                "completion_tokens": latest.get("completion_tokens"),
                "total_rounds": latest.get("total_rounds"),
                "captured_after_cancellation": {captured_after_cancellation},
                "captured_at": time.time(),
            }}
            pathlib.Path("/logs/agent/ouroboros-run-summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with pathlib.Path("/logs/agent/ouroboros-run.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({{"type": "final", "task_id": task_id, "result": latest, "captured_after_cancellation": {captured_after_cancellation}}}, ensure_ascii=False) + "\\n")
            PY
            """
        ).strip()
        await environment.exec(command=command, timeout_sec=30)

    @staticmethod
    def _context_task_timeout_sec(context: Any) -> int | None:
        """Best-effort per-task timeout from the harbor AgentContext.

        Harbor's AgentContext does not currently expose the task.toml timeout
        (verified against harbor docs 2026-06: tokens/cost/rollout/metadata
        only), so this probe usually returns None today. If a future harbor
        adds a timeout field, the deadline pass-through (milestone nudges +
        run_command cap inside Ouroboros) lights up without an adapter change.
        """
        for attr in ("agent_timeout_sec", "task_timeout_sec", "timeout_sec", "max_agent_timeout_sec"):
            raw = getattr(context, attr, None)
            if raw is None and isinstance(getattr(context, "metadata", None), dict):
                raw = context.metadata.get(attr)
            try:
                value = int(raw) if raw is not None else 0
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    # Buffer between the agent's own deadline and Harbor's hard external kill, so the
    # loop's graceful self-finalize (which itself fires get_finalization_grace_sec before
    # the deadline) completes and the partial artifact is written before Harbor terminates.
    # v6.55.0: 30s let gpt2-codegolf overrun the deadline by 26.5s (a 351s
    # provider-recovery gap + a final round); 105s covers the measured
    # finalization overhead with margin (owner decision #15, range 90-120).
    _DEADLINE_SAFETY_SEC = 105

    # Mirror of ouroboros/tools/registry.py::_WEB_TOOLS (the adapter must stay
    # importable without the runtime package on the harbor host; a sync test in
    # tests/test_devtools_benchmarks.py pins this against the real set).
    _WEB_TOOLS_MIRROR = ("web_search", "browse_page", "browser_action", "youtube_transcript")
    _DELEGATED_VISION_TOOLS = ("analyze_screenshot", "vlm_query")

    # Harbor's package cache: <cache>/tasks/packages/<org>/<name>/<digest>/task.toml
    # (harbor.models.task.id:PackageTaskId.get_local_path, verified against harbor 0.18/0.20).
    _PACKAGE_CACHE_DIR = Path.home() / ".cache" / "harbor" / "tasks" / "packages"

    def _cached_task_toml(self, task_name: str) -> Path | None:
        """Resolve one cached ``task.toml`` for ``task_name`` — or None, never a guess.

        The org is NOT a constant: the cache already holds `terminal-bench/`, `gaia/` and
        `scale-ai/` side by side, and a dataset such as Harbor-Index ships tasks from several
        orgs at once, so the pre-v6.79.0 hardcoded `terminal-bench` literal simply missed every
        non-TB dataset. AgentContext carries no task identity (checked in harbor 0.18 and 0.20),
        so the org comes from the configured dataset.

        A configured org is AUTHORITATIVE: when `self.dataset` names one, only that org's cache
        is consulted, and a miss returns None. There is no cross-owner fallback in that case.
        Borrowing a same-named task from another org is not a lenient fallback, it is running
        the task under a different benchmark's parameters — and the parameter in question is the
        wall-clock cap, which decides pass or fail. `frontier-bench/frontier-bench` verifier
        caps are 600s against terminal-bench-2-1's 3600s, so a silent borrow between exactly
        those two orgs (the two most likely to be cached side by side here) misprices the
        deadline by 6x. Deadline-blind is the honest degradation.

        The name-only lookup remains only for a dataset with NO org (unqualified name), and
        even there it REFUSES an ambiguous name cached under two orgs."""
        base = self._PACKAGE_CACHE_DIR
        org = self.dataset.split("/", 1)[0] if "/" in self.dataset else ""
        if org:
            matches = sorted((base / org / task_name).glob("*/task.toml"))
        else:
            owners = sorted({
                path.parent.parent.parent.name
                for path in base.glob(f"*/{task_name}/*/task.toml")
            })
            if len(owners) != 1:
                return None
            matches = sorted((base / owners[0] / task_name).glob("*/task.toml"))
        # Newest matching package version (avoid a stale cached digest).
        return max(matches, key=lambda path: path.stat().st_mtime) if matches else None

    def _resolve_task_timeout_from_dataset(self, context: Any) -> int | None:
        """Read the per-task agent wall-clock cap from the cached task.toml.

        Harbor's AgentContext does not expose the task.toml timeout, so derive the task
        name from the trial path (logs_dir = .../<task>__<trialhash>/agent) or context, then
        read ``[agent].timeout_sec`` from the cached dataset task.toml. Best-effort: returns
        None on any failure (agent then runs deadline-blind, as before — safe fallback)."""
        task_name = ""
        try:
            parent = Path(self.logs_dir).resolve().parent.name  # "<task>__<trialhash>"
            if "__" in parent:
                task_name = parent.rsplit("__", 1)[0]
        except Exception:
            task_name = ""
        if not task_name:
            for attr in ("task_id", "task_name", "task", "name"):
                raw = getattr(context, attr, None)
                if isinstance(raw, str) and raw.strip():
                    task_name = raw.strip().split("/")[-1].rsplit("__", 1)[0]
                    break
        if not task_name:
            return None
        try:
            chosen = self._cached_task_toml(task_name)
            if chosen is None:
                return None
            text = chosen.read_text(encoding="utf-8")
        except Exception:
            return None
        # Parse [agent].timeout_sec without a toml dependency (the field is a simple float/int).
        import re as _re
        section = None
        cap = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                section = s[1:-1].strip()
                continue
            if section == "agent":
                m = _re.match(r"timeout_sec\s*=\s*([0-9]+(?:\.[0-9]+)?)", s)
                if m:
                    try:
                        cap = int(float(m.group(1)))
                    except (TypeError, ValueError):
                        cap = None
                    break
        return cap if (cap and cap > 0) else None

    def _effective_task_timeout_sec(self) -> int:
        """The deadline (sec from task creation) handed to the agent: the per-task Harbor cap
        minus the install/server time already consumed and a small safety buffer. 0 means no
        deadline (agent runs as before). The agent uses this to pace and self-finalize a partial
        result before Harbor's hard external kill."""
        cap = self.task_timeout_sec
        if not cap or int(cap) <= 0:
            return 0
        elapsed = 0.0
        if self._run_started_monotonic is not None:
            elapsed = max(0.0, time.monotonic() - self._run_started_monotonic)
        effective = float(int(cap)) - elapsed - float(self._DEADLINE_SAFETY_SEC)
        # Cap IS known here (guard above returned for unknown caps). If install/server already ate
        # the budget, hand the agent a 1s deadline so it enters graceful finalization immediately
        # rather than running blind into Harbor's hard kill with an empty result.
        return int(effective) if effective > 0 else 1

    def _append_capability_guidance(self, instruction: str) -> str:
        """Append the per-task annotation block to the instruction.

        Task annotations are the ONLY prompt-side capability this adapter injects.
        The global OUROBOROS_CAP_RULES block that once accompanied them is gone from
        this path on purpose: a 100+ KB system prompt (global rules + per-task notes)
        made mimo-v2.5 emit a single maxed-out 65536-token reply, which was
        length-truncated ~8 minutes in and then blew the deadline. The annotations
        are the only channel that tells the agent what past runs of THIS task died on.

        The enable flag and the task-name normalisation both live in
        exp/capabilities/task_annotations.py, so this method cannot drift from the
        module about what "enabled" means or which name shapes are accepted. Default
        OFF: the bodies are distilled from this benchmark's own failures, so an
        annotated run is not a clean measurement and must not be silently mixed into
        a baseline arm. Every failure here degrades to the plain instruction.
        """
        try:
            from devtools.benchmarks.terminal_bench.exp.capabilities import task_annotations as _ann
        except Exception as exc:  # best-effort only
            log.warning("task annotations unavailable: %s", exc)
            return instruction
        if not _ann.annotations_enabled():
            return instruction
        # From config.json, not from the dir name: a path-resolved task's dir is
        # "<taskhash>__<hash>", which resolves to nothing and silently drops the annotation.
        task_name = _task_name_from_trial_dir(self.logs_dir)
        rendered = _ann.render_task_annotations(task_name)
        # The effort directive is adapter config, not model-facing text.
        rendered = re.sub(r"(?m)^\s*reasoning[-_]effort\s*:.*$\n?", "", rendered)
        return f"{instruction}\n\n{rendered}" if rendered else instruction

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._run_started_monotonic = time.monotonic()
        if self.task_timeout_sec is None:
            probed = self._context_task_timeout_sec(context)
            if probed:
                self.task_timeout_sec = probed
        if self.task_timeout_sec is None:
            self.task_timeout_sec = self._resolve_task_timeout_from_dataset(context)
        instruction = (
            instruction
            + "\n\nIMPORTANT - integrity: do not fetch this benchmark's task "
            "definitions, solutions, tests, or reference materials from source "
            "repositories or mirrors on the internet. Solve the task using the "
            "environment you are given; downloading general-purpose software or "
            "data that the task itself requires is fine."
        )
        instruction = self._append_capability_guidance(instruction)
        (self.logs_dir / "instruction.txt").write_text(instruction, encoding="utf-8")
        await environment.upload_file(self.logs_dir / "instruction.txt", "/logs/agent/instruction.txt")

        env = self._container_env()

        # Global github rewrite -> gh-proxy: one git config in /root/.gitconfig covers
        # BOTH the agent's own clones (build-cython-ext's instruction demands one) and
        # the verifier's on-the-fly clones (fix-ocaml-gc re-clones a clean testsuite) —
        # the same channel the injected test.sh already uses to fetch uv. Idempotent;
        # images without git skip silently. Best effort: a failure must never block
        # the trial (direct github still works when gh-proxy is down, and vice versa).
        try:
            git_rewrite = await environment.exec(
                command=(
                    "command -v git >/dev/null 2>&1 || exit 0\n"
                    'git config --global --get url."https://gh-proxy.com/https://github.com/".insteadOf >/dev/null 2>&1 && exit 0\n'
                    'git config --global url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"\n'
                ),
                user="root",
                timeout_sec=15,
            )
            if getattr(git_rewrite, "return_code", 0) not in (0, None):
                log.warning("git gh-proxy rewrite returned %s: %s",
                            git_rewrite.return_code, getattr(git_rewrite, "stderr", ""))
        except Exception as exc:
            log.warning("git gh-proxy rewrite skipped: %s", exc)

        reached_terminal_result = False
        try:
            self._enforce_container_secret_policy(env)
            self._openrouter_credit_preflight(self._host_settings())
            await self._network_preflight(environment, env)
            await self._resolve_workspace_dir(environment)
            await self._ensure_workspace_git_root(environment)
            await self._start_server(environment, env)
            self._run_summary = await self._run_ouroboros_task(environment, env)
            reached_terminal_result = True
        finally:
            try:
                # Only mark the captured summary as a cancellation when run() did NOT reach a
                # terminal result (i.e. Harbor actually interrupted mid-exec). On a normal terminal
                # finish this is a routine post-run snapshot, not a cancellation — so the disclosure
                # ledger does not misread a genuine terminal `provider_unavailable` as a wall-clock
                # cancellation (run_tb._failure_category keys on captured_after_cancellation).
                await self._capture_current_task_summary(
                    environment, interrupted=not reached_terminal_result
                )
            except Exception as exc:
                (getattr(self, "logger", None) or log).warning("Failed to capture in-container Ouroboros task summary: %s", exc)
            try:
                # Leaderboard submissions require an ATIF trajectory for every
                # passing trial (harbor static validation); emit it while the
                # trial logs are still in the container.
                physical_metrics = await self._emit_trajectory(environment, env)
                if physical_metrics:
                    self._run_summary.update(physical_metrics)
            except Exception as exc:
                (getattr(self, "logger", None) or log).warning("Failed to emit ATIF trajectory: %s", exc)
            if not self.leave_server_running_for_verifier or not reached_terminal_result:
                try:
                    await self._stop_server(environment)
                except Exception as exc:
                    (getattr(self, "logger", None) or log).warning("Failed to stop in-container Ouroboros cleanly: %s", exc)

        cost = self._run_summary.get("cost_usd")
        prompt_tokens = self._run_summary.get("prompt_tokens")
        completion_tokens = self._run_summary.get("completion_tokens")
        cached_tokens = self._run_summary.get("cached_tokens")
        context.cost_usd = float(cost) if cost is not None else None
        context.n_input_tokens = int(prompt_tokens) if prompt_tokens is not None else None
        context.n_output_tokens = int(completion_tokens) if completion_tokens is not None else None
        context.n_cache_tokens = int(cached_tokens) if cached_tokens is not None else None
        context.metadata = {
            "adapter_mode": "installed_ouroboros",
            "workspace_dir": self.workspace_dir,
            "runtime_mode": self.runtime_mode,
            "review_enforcement": self.review_enforcement,
            "summary": self._run_summary,
        }


InstalledOuroborosTerminalBenchAgent = OuroborosTerminalBenchAgent

__all__ = ["OuroborosTerminalBenchAgent", "InstalledOuroborosTerminalBenchAgent"]
