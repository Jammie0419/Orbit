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
echo "[1/5] credentials"
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

# ------------------------------------------------------------------- docker
echo "[2/5] docker"
if docker info >/dev/null 2>&1; then
  pass "docker daemon reachable"
else
  fail "docker daemon not reachable — harbor cannot create task containers"
fi
RUNNING="$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
if [ "${RUNNING:-0}" -gt 0 ]; then
  warn "$RUNNING container(s) already running — leftovers can exhaust disk"
else
  pass "no leftover containers"
fi

# --------------------------------------------------------------- API liveness
echo "[3/5] API liveness"
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
    for i in $(seq 1 "$RETRIES"); do
      RESP="$(curl -s -m 30 -X POST "$BASE/chat/completions" "${AUTH[@]}" \
                -H "Content-Type: application/json" -d "$BODY" 2>/dev/null)"
      case "$RESP" in
        *CreditsError*|*"Insufficient balance"*|*insufficient_quota*)
          fail "account has NO CREDIT — a real completion was rejected"
          echo "        provider said: $(printf '%s' "$RESP" | head -c 240)"
          echo "        every trial would burn its setup time and score 0; top up before running"
          break ;;
        *Invalid*key*|*invalid_api_key*|*Unauthorized*|*"401"*)
          fail "credentials rejected by the provider"
          echo "        provider said: $(printf '%s' "$RESP" | head -c 240)"
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
    elif [ "$FAIL" = 0 ]; then
      fail "no usable completion after $RETRIES attempts — last response: $(printf '%s' "$RESP" | head -c 200)"
    fi
  fi
fi

# ------------------------------------------------------- cache mounts + disk
echo "[4/5] cache mounts and disk"
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
FREE_GB="$(df -BG --output=avail /mnt/disk2/lzm 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt 20 ]; then
  fail "only ${FREE_GB}G free on /mnt/disk2 — a full k=5 run needs far more"
elif [ -n "$FREE_GB" ]; then
  pass "${FREE_GB}G free on /mnt/disk2"
fi

# ------------------------------------------------------------- task images
echo "[5/5] task images"
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
    fi
  done < "$TASKS_FILE"
  if [ "$MISSING" -eq 0 ]; then
    pass "all $TOTAL task images present locally"
  else
    warn "$MISSING/$TOTAL task images not cached — first run pays the build/pull"
    echo "        run once with --force-build, or let setup absorb it"
  fi
fi

echo "-------------------------"
if [ "$FAIL" -eq 0 ]; then
  echo "clear to run"
  exit 0
fi
echo "BLOCKED — fix the failures above before starting a run"
exit 1
