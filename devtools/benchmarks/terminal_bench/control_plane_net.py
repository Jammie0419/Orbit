"""Keep harbor's control plane reachable no matter which shell launched the run.

harbor resolves task-package metadata from Supabase — ``ofhuhcpkvzjlejydnvyd.supabase.co``,
the default in ``harbor.auth.constants`` (note: *not* the ``hlqxx…supabase.co`` host that
``harbor.registry.client.harbor.config`` defaults to, which is the one our NO_PROXY lists
carry). Measured 2026-09-22 from this host:

* direct: ``code=000`` after a 10s timeout — not reachable from CN;
* through a healthy Clash core (7899): ``401`` in 0.4s;
* through a core whose node is dead (7897 that day): ``SSL routines::unexpected eof``.

So the whole run depends on the proxy env pointing at a core with a live node, and a dead
node turns ``harbor run`` into a 400-line ConnectError traceback before the first trial
starts. This module probes the control plane through the env's proxy first, then the local
cores, then direct, and writes the winner into the harbor child env. The first candidate
normally answers in under a second; only a broken one costs the probe timeout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

_HARBOR_CONTROL_PLANE_URL = "https://ofhuhcpkvzjlejydnvyd.supabase.co/rest/v1/"
# Clash cores on this host: 7899 is lzm's own (manual mihomo), 7897 is rzr's
# (clash-verge-service). Order matters only as a preference between two live cores.
_LOCAL_CORE_CANDIDATES = ("http://127.0.0.1:7899", "http://127.0.0.1:7897")
_PROBE_TIMEOUT_SEC = 8.0
_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
_SOCKS_ENV_KEYS = ("ALL_PROXY", "all_proxy")


def probe_control_plane(proxy: str | None, timeout: float = _PROBE_TIMEOUT_SEC) -> bool:
    """True when the control plane answers through ``proxy`` (or directly when None).

    Any HTTP status counts: the endpoint is public-read, so 401/404 still prove the
    request reached Supabase. Only a transport failure (curl's ``000``) is a miss.
    """
    cmd = ["curl", "-sS", "-m", str(timeout), "-o", "/dev/null", "-w", "%{http_code}"]
    cmd += ["-x", proxy] if proxy else ["--noproxy", "*"]
    cmd.append(_HARBOR_CONTROL_PLANE_URL)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    except Exception:
        return False
    return proc.stdout.strip() not in ("", "000")


def ensure_control_plane_reachable(
    env: dict[str, str],
    *,
    probe: Callable[[str | None], bool] = probe_control_plane,
) -> str:
    """Pick a route to harbor's control plane and write it into ``env`` in place.

    Candidates in order: the proxy already in ``env``, the two local cores, then direct.
    Returns a short description of the winner (``"http://127.0.0.1:7899"``, ``"direct"``)
    or ``"unreachable"`` when every candidate failed — in that case ``env`` is left
    untouched so the failure surfaces from harbor itself, with the real error.
    """
    current = (env.get("HTTPS_PROXY") or env.get("https_proxy") or "").strip() or None
    candidates: list[str | None] = []
    for candidate in (current, *_LOCAL_CORE_CANDIDATES, None):
        if candidate not in candidates:
            candidates.append(candidate)

    # Two passes: a probe miss can be a transient blip (observed 2026-09-22 while 3 GB of
    # wheels were downloading — the same host answered 401 seconds later), and a spurious
    # "unreachable" would leave the child env with the very proxy we just proved dead.
    for attempt in range(2):
        for candidate in candidates:
            if not probe(candidate):
                continue
            if candidate is None:
                for key in (*_PROXY_ENV_KEYS, *_SOCKS_ENV_KEYS):
                    env.pop(key, None)
                return "direct"
            for key in _PROXY_ENV_KEYS:
                env[key] = candidate
            # A stale socks entry would mount httpx's ``all://`` at a dead core; the
            # http(s) mounts we just set are strictly more specific, but dropping it
            # keeps the child env honest about the route actually in use.
            for key in _SOCKS_ENV_KEYS:
                env.pop(key, None)
            return candidate
    return "unreachable"
