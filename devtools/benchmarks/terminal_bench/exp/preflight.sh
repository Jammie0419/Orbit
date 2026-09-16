#!/usr/bin/env bash
# Terminal-Bench pre-flight gate.
#
# Purpose: refuse to start a run when an EXTERNAL dependency is already broken.
# Every check here guards a failure class that costs a full trial and produces a
# reward-0 artifact that is not a capability signal (API outage, missing docker,
# unwritable cache mount, missing task image).
#
# Usage:
#   source .env.terminal_bench.linux
#   ./devtools/benchmarks/terminal_bench/exp/preflight.sh            # all checks
#   ./devtools/benchmarks/terminal_bench/exp/preflight.sh --quick    # skip image check
#   ./devtools/benchmarks/terminal_bench/exp/preflight.sh --tasks-file exp/all_tasks.txt
#
# Exit codes: 0 = clear to run, 1 = a blocking check failed.
set -uo pipefail

RETRIES="${TERMINAL_BENCH_PREFLIGHT_RETRIES:-3}"
WAIT_SEC="${TERMINAL_BENCH_PREFLIGHT_WAIT_SEC:-15}"
CHECK_IMAGES=1
TASKS_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --quick) CHECK_IMAGES=0 ;;
    --tasks-file) TASKS_FILE="${2:-}"; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "preflight: unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

FAIL=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }
skip() { printf '  \033[90mSKIP\033[0m  %s\n' "$1"; }

echo "Terminal-Bench pre-flight"
echo "-------------------------"

# ---------------------------------------------------------------- credentials
echo "[1/6] credentials"
if [ -n "${OPENAI_COMPATIBLE_API_KEY:-}" ]; then
  pass "OPENAI_COMPATIBLE_API_KEY is set"
else
  fail "OPENAI_COMPATIBLE_API_KEY is unset — every trial would fail auth"
fi
if [ -n "${OPENAI_COMPATIBLE_BASE_URL:-}" ]; then
  pass "OPENAI_COMPATIBLE_BASE_URL=${OPENAI_COMPATIBLE_BASE_URL}"
else
  fail "OPENAI_COMPATIBLE_BASE_URL is unset"
fi

# -------------------------------------------------------------- docker + harbor
echo "[2/6] docker and harbor CLI"
if docker info >/dev/null 2>&1; then
  pass "docker daemon reachable"
else
  fail "docker daemon not reachable — harbor cannot create task containers"
fi
# The harbor CLI lives in the venv, so a forgotten `source .venv/bin/activate` costs
# a whole invocation. Observed failure: harbor raises
# `PermissionError: [Errno 13] Permission denied: 'harbor'` (not FileNotFoundError),
# which reads like a broken binary rather than a missing PATH entry.
HARBOR_BIN="$(command -v harbor || true)"
if [ -n "$HARBOR_BIN" ]; then
  pass "harbor on PATH: $HARBOR_BIN"
else
  fail "harbor not on PATH — run 'source .venv/bin/activate' first (the CLI lives in .venv/bin)"
fi
RUNNING="$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
if [ "${RUNNING:-0}" -gt 0 ]; then
  warn "$RUNNING container(s) already running — leftovers can exhaust disk"
else
  pass "no leftover containers"
fi
# Every task whose image is not cached locally has to come from the registry, and a
# registry that is unreachable turns "first run of a task" into a failed trial rather
# than a slow one. /v2/ ALWAYS answers 401 to an unauthenticated request -- it is the
# auth challenge, not a failure: docker answers it by fetching an anonymous token and
# retrying, which works for public images. A real problem is an empty reply (000).
REG_CODE="$(curl -s -m 20 -o /dev/null -w '%{http_code}' https://registry-1.docker.io/v2/ 2>/dev/null)"
case "$REG_CODE" in
  401)     pass "image registry reachable (401 = the normal auth challenge, not an error)" ;;
  200)     pass "image registry reachable (HTTP 200)" ;;
  000|"")  fail "image registry unreachable — uncached task images cannot be pulled" ;;
  *)       warn "image registry answered HTTP $REG_CODE (unexpected; pulls may fail)" ;;
esac

# --------------------------------------------------------------- API liveness
echo "[3/6] API liveness"
if [ -z "${OPENAI_COMPATIBLE_BASE_URL:-}" ]; then
  skip "no base URL to probe"
else
  BASE="${OPENAI_COMPATIBLE_BASE_URL%/}"
  AUTH=(-H "Authorization: Bearer ${OPENAI_COMPATIBLE_API_KEY:-}")

  # /models only proves ROUTING. A zero-balance account answers 200 there and then
  # returns 401 CreditsError on the first real completion, so a /models-only gate
  # passes a run that cannot score a single trial. Probe an actual minimal
  # completion, and treat a billing/auth error type as a blocking failure.
  PROBE_MODEL="${PREFLIGHT_PROBE_MODEL:-}"
  if [ -z "$PROBE_MODEL" ]; then
    PROBE_MODEL="${TERMINAL_BENCH_MODEL:-}"
    PROBE_MODEL="${PROBE_MODEL##*::}"   # openai-compatible::mimo-v2.5 -> mimo-v2.5
  fi

  if [ -z "$PROBE_MODEL" ]; then
    skip "no probe model (set PREFLIGHT_PROBE_MODEL or TERMINAL_BENCH_MODEL)"
  else
    BODY="$(printf '{"model":"%s","messages":[{"role":"user","content":"ping"}],"max_tokens":5}' "$PROBE_MODEL")"
    RESP=""
    OK=0
    REPORTED=0   # local: a SPECIFIC verdict was already printed for this probe.
                 # Using the global $FAIL here instead would swallow the generic
                 # message whenever an earlier section had already failed, leaving
                 # "BLOCKED" with no explanation of the API failure.
    for i in $(seq 1 "$RETRIES"); do
      RESP="$(curl -s -m 30 -X POST "$BASE/chat/completions" "${AUTH[@]}" \
                -H "Content-Type: application/json" -d "$BODY" 2>/dev/null)"
      case "$RESP" in
        *CreditsError*|*"Insufficient balance"*|*insufficient_quota*)
          fail "account has NO CREDIT — a real completion was rejected"
          echo "        provider said: $(printf '%s' "$RESP" | head -c 240)"
          echo "        every trial would burn its setup time and score 0; top up before running"
          REPORTED=1
          break ;;
        *Invalid*key*|*invalid_api_key*|*Unauthorized*|*"401"*)
          fail "credentials rejected by the provider"
          echo "        provider said: $(printf '%s' "$RESP" | head -c 240)"
          REPORTED=1
          break ;;
        *'"content"'*|*'"choices"'*|*'"role"'*)
          OK=1; break ;;
        *)
          [ "$i" -lt "$RETRIES" ] && echo "        unusable response (attempt $i/$RETRIES), waiting ${WAIT_SEC}s..."
          [ "$i" -lt "$RETRIES" ] && sleep "$WAIT_SEC" ;;
      esac
    done
    if [ "$OK" = 1 ]; then
      pass "model '$PROBE_MODEL' answered a real completion"
    elif [ "$REPORTED" = 0 ]; then
      fail "no usable completion after $RETRIES attempts — last response: $(printf '%s' "$RESP" | head -c 200)"
    fi
  fi
fi

# ------------------------------------------------------- cache mounts + disk
echo "[4/6] cache mounts and disk"
for VAR in OBO_TB_PIP_CACHE OBO_TB_APT_CACHE OBO_TB_HF_CACHE; do
  DIR="${!VAR:-}"
  if [ -z "$DIR" ]; then
    warn "$VAR unset — container re-downloads on every trial"
    continue
  fi
  if [ ! -d "$DIR" ]; then
    fail "$VAR=$DIR does not exist — the bind mount would fail or silently degrade"
  elif [ ! -w "$DIR" ]; then
    fail "$VAR=$DIR is not writable"
  else
    pass "$VAR=$DIR"
  fi
done
# A cache directory that exists but was never populated looks identical to a warm one
# from the outside, and the difference is 200MB per trial. Name the two artifacts that
# actually have to be there for the caches to do anything.
UV_PROBE="${OBO_TB_PIP_CACHE:-}/uv-bin/uv"
if [ -n "${OBO_TB_PIP_CACHE:-}" ] && [ -x "$UV_PROBE" ]; then
  pass "uv binary staged for the verifier: $UV_PROBE"
elif [ -n "${OBO_TB_PIP_CACHE:-}" ]; then
  warn "no uv at $UV_PROBE — the verifier will try to download one (CN: slow, can fail)"
fi
if [ -n "${OBO_TB_APT_CACHE:-}" ] && [ -d "${OBO_TB_APT_CACHE:-}" ]; then
  DEB_COUNT="$(find "${OBO_TB_APT_CACHE}" -name '*.deb' 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${DEB_COUNT:-0}" -gt 0 ]; then
    pass "apt .deb cache holds $DEB_COUNT archive(s)"
  else
    warn "apt .deb cache is empty — the next apt install re-downloads ~33MB (check docker-clean)"
  fi
fi
# Check the filesystems a run actually fills, not a hardcoded path: the caches and
# docker's storage root can both live somewhere other than where they did the last
# time this was edited, and a check that looks at the wrong disk reports green while
# the real one is full. Container layers (docker root) are the larger consumer.
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)"
for TARGET in "${OBO_TB_PIP_CACHE:-}" "${DOCKER_ROOT:-}"; do
  [ -n "$TARGET" ] && [ -d "$TARGET" ] || continue
  FREE_GB="$(df -BG --output=avail "$TARGET" 2>/dev/null | tail -1 | tr -dc '0-9')"
  [ -n "$FREE_GB" ] || continue
  if [ "$FREE_GB" -lt 20 ]; then
    fail "only ${FREE_GB}G free on ${TARGET} — a k=5 run needs far more (layers + caches)"
  else
    pass "${FREE_GB}G free on ${TARGET}"
  fi
done

# --------------------------------------------------------- container egress
echo "[5/6] container egress"
# The agent runs INSIDE the container and calls the model API from there, so a probe
# from this host proves the wrong thing: host reachability and container reachability
# are different network namespaces. If container egress were broken, the host probe
# above would still pass and every trial would die on its first LLM call. This is the
# same failure the host probe exists to catch, one namespace over.
PROBE_IMAGE=""
for candidate in python:3.12-slim python:3.11-slim python:3.12-slim-bookworm python:3.12; do
  if docker image inspect "$candidate" >/dev/null 2>&1; then PROBE_IMAGE="$candidate"; break; fi
done
if [ -z "$PROBE_IMAGE" ]; then
  skip "no local python image to probe with (a python:3.12-slim exists on most hosts)"
elif [ -z "${OPENAI_COMPATIBLE_BASE_URL:-}" ] || [ -z "${OPENAI_COMPATIBLE_API_KEY:-}" ]; then
  skip "no credentials to probe the container with"
elif [ -z "${PROBE_MODEL:-}" ]; then
  skip "no probe model to name in the container request"
else
  PROBE_PY='
import json, os, socket, sys, urllib.request
base = os.environ["__URL"].rstrip("/")
host = base.split("//", 1)[-1].split("/", 1)[0]
try:
    socket.getaddrinfo(host, 443)
    print("dns=ok")
except Exception as exc:
    print("dns=fail", type(exc).__name__)
try:
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({"model": os.environ["__MODEL"],
                         "messages": [{"role": "user", "content": "hi"}],
                         "max_tokens": 3}).encode(),
        headers={"Authorization": "Bearer " + os.environ["__KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    print("api=ok" if body.get("choices") else "api=fail:empty-body")
except Exception as exc:
    print("api=fail:%s:%s" % (type(exc).__name__, str(exc)[:110]))
'
  # Credentials go in as env vars, exactly as a real trial's container receives them.
  NET_OUT="$(printf '%s' "$PROBE_PY" | docker run --rm -i \
      -e __URL="$OPENAI_COMPATIBLE_BASE_URL" \
      -e __KEY="$OPENAI_COMPATIBLE_API_KEY" \
      -e __MODEL="$PROBE_MODEL" \
      "$PROBE_IMAGE" python3 - 2>&1)"
  case "$NET_OUT" in
    *dns=ok*)   pass "container DNS resolves the API host" ;;
    *)          fail "container DNS cannot resolve the API host — every trial would fail" ;;
  esac
  case "$NET_OUT" in
    *api=ok*)   pass "container reached the model API and got a real completion" ;;
    *)          fail "container could NOT reach the model API — a trial would burn its setup then score 0"
                echo "        probe said: $(printf '%s' "$NET_OUT" | tr '\n' ' ' | tail -c 240)" ;;
  esac
fi

# ------------------------------------------------------------- task images
echo "[6/6] task images"
if [ "$CHECK_IMAGES" = 0 ]; then
  skip "image check disabled (--quick)"
elif [ -z "$TASKS_FILE" ]; then
  skip "no --tasks-file given (pass one to verify its images are cached)"
elif [ ! -f "$TASKS_FILE" ]; then
  fail "tasks file not found: $TASKS_FILE"
else
  CACHE_ROOT="${HOME}/.cache/harbor/tasks/packages/terminal-bench"
  MISSING=0
  TOTAL=0
  MISSING_LIST=""
  while IFS= read -r raw; do
    NAME="$(echo "$raw" | sed 's/^terminal-bench\///' | tr -d '[:space:]')"
    [ -z "$NAME" ] && continue
    case "$NAME" in \#*) continue ;; esac
    TOTAL=$((TOTAL + 1))
    TOML="$(find "$CACHE_ROOT/$NAME" -name task.toml 2>/dev/null | head -1)"
    if [ -z "$TOML" ]; then
      warn "$NAME: no cached task.toml"
      continue
    fi
    IMAGE="$(grep -oP '^docker_image = "\K[^"]+' "$TOML" | head -1)"
    [ -z "$IMAGE" ] && continue
    if docker image inspect "$IMAGE" >/dev/null 2>&1; then
      :
    else
      MISSING=$((MISSING + 1))
      MISSING_LIST="${MISSING_LIST}        ${NAME}\n"
    fi
  done < "$TASKS_FILE"
  if [ "$MISSING" -eq 0 ]; then
    pass "all $TOTAL task images present locally"
  else
    # NOT a blocker: an absent image is pulled (or built, for the tasks that ship a
    # Dockerfile) on first use and cached from then on. Do NOT suggest --force-build
    # here -- that rebuilds even a perfectly good cached image, which is the opposite
    # of what this warning is about, and it is not how the accepted submissions run
    # (8/10 pin environment.force_build=false).
    warn "$MISSING/$TOTAL task images not cached yet"
    printf "%b" "$MISSING_LIST"
    echo "        not a blocker: each is pulled/built once on first use, then reused."
    echo "        to pay that cost up front instead, run one throwaway trial per image."
  fi
fi

echo "-------------------------"
if [ "$FAIL" -eq 0 ]; then
  echo "clear to run"
  exit 0
fi
echo "BLOCKED — fix the failures above before starting a run"
exit 1
