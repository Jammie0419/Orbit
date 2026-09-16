#!/usr/bin/env python3
"""Three-way triage of a Terminal-Bench run.

Every non-passing trial is sorted into exactly one bucket, because the three
buckets demand opposite treatment when you want a measurement that reflects
capability rather than infrastructure:

  infra       the trial never got a fair shot (provider outage, transport drop,
              setup/verify blow-up, unscored teardown).  RERUN these.
  truncation  a fair shot that ran out of budget (AgentTimeout, deadline_local,
              budget/round cap).  The dataset's own limits are part of the
              benchmark; rerunning does not make the model better.  KEEP as fail.
  genuine     a fair shot, enough budget, wrong answer.  KEEP as fail.

The point of the split is that only `infra` may be rerun without inflating the
score.  Treating truncation as "an external problem" is the classic way to make
a pass@k look better than it is.

Usage:
  exp/triage_run.py --ledger <run-root>/disclosure_ledger.json
  exp/triage_run.py --run-root ~/bench_runs/terminal_bench/valid\\ results/ouroboros_v0
  exp/triage_run.py --ledger ... --infra-out exp/remaining_tasks.txt
  exp/triage_run.py --ledger ... --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Kept in sync with run_tb.py's own taxonomy (see its _failure_category).
PROVIDER_REASONS = {"provider_unavailable", "llm_api_error"}
CAPABILITY_TRUNCATION_REASONS = {"deadline_local", "budget_exhausted", "round_limit"}
TIMEOUT_EXCEPTIONS = {"AgentTimeoutError", "VerifierTimeoutError"}

INFRA = "infra"
TRUNCATION = "truncation"
GENUINE = "genuine"
PASS = "pass"


def classify(trial: dict) -> tuple[str, str]:
    """Return (bucket, reason). `reason` explains the assignment in one phrase."""
    reward = trial.get("reward")
    if reward in (1, 1.0, True):
        return PASS, "rewarded"

    exception = trial.get("exception_type")
    reason_code = str(trial.get("reason_code") or "")
    truncated = bool(trial.get("truncated"))
    infra_failed = bool(trial.get("infra_failed"))
    after_cancel = bool(trial.get("captured_after_cancellation"))

    # A harness wall-clock cut is not the model's fault: the trial was killed
    # mid-flight, so it is rerunnable. Kept as its own reason so the caller can
    # see how much of the rerun list is this rather than a real provider outage.
    if after_cancel:
        return INFRA, "captured_after_cancellation (harness cut the trial)"

    # Dataset-declared agent/verifier timeout: a fair shot that ran out of budget.
    if exception in TIMEOUT_EXCEPTIONS:
        return TRUNCATION, f"{exception} (ran out of the task's own budget)"

    # Any other exception is a setup / verify / harness blow-up -> no fair shot.
    if exception:
        return INFRA, f"exception {exception}"

    if infra_failed:
        return INFRA, "runtime flagged infra_failed"

    if reward is None:
        return INFRA, "unscored trial (no reward produced)"

    if reason_code in PROVIDER_REASONS:
        return INFRA, f"provider reason {reason_code}"

    if truncated and reason_code in CAPABILITY_TRUNCATION_REASONS:
        return TRUNCATION, f"budget cap {reason_code}"

    if truncated:
        return TRUNCATION, f"truncated ({reason_code or 'unstated reason'})"

    if reason_code in CAPABILITY_TRUNCATION_REASONS:
        return TRUNCATION, f"budget cap {reason_code}"

    return GENUINE, f"wrong answer ({reason_code or 'unstated reason'})"


def load_ledger(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"triage: ledger not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"triage: {path} is not valid JSON: {exc}")


def resolve_ledger(args) -> Path:
    if args.ledger:
        return Path(args.ledger).expanduser()
    if args.run_root:
        root = Path(args.run_root).expanduser()
        direct = root / "disclosure_ledger.json"
        if direct.is_file():
            return direct
        found = sorted(root.rglob("disclosure_ledger.json"))
        if not found:
            sys.exit(f"triage: no disclosure_ledger.json under {root}")
        return found[-1]
    sys.exit("triage: pass --ledger or --run-root")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", help="path to disclosure_ledger.json")
    parser.add_argument("--run-root", help="run root; the ledger is located inside it")
    parser.add_argument("--infra-out", help="write the rerun task list here")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    path = resolve_ledger(args)
    ledger = load_ledger(path)
    trials = ledger.get("trials") or []
    if not trials:
        sys.exit(f"triage: {path} contains no trials")

    results = []
    for trial in trials:
        bucket, reason = classify(trial)
        results.append({
            "task_name": trial.get("task_name", "?"),
            "trial_name": trial.get("trial_name", "?"),
            "reward": trial.get("reward"),
            "bucket": bucket,
            "reason": reason,
            "reason_code": trial.get("reason_code"),
            "exception_type": trial.get("exception_type"),
        })

    buckets = Counter(r["bucket"] for r in results)
    # One task may have several trials; a task is rerunnable only if it has no
    # passing trial AND at least one infra trial.
    by_task: dict[str, list[dict]] = {}
    for r in results:
        by_task.setdefault(r["task_name"], []).append(r)

    rerun: list[str] = []
    for task, rows in sorted(by_task.items()):
        if any(r["bucket"] == PASS for r in rows):
            continue
        if any(r["bucket"] == INFRA for r in rows):
            rerun.append(task)

    if args.infra_out:
        dest = Path(args.infra_out).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("\n".join(rerun) + ("\n" if rerun else ""), encoding="utf-8")

    if args.json:
        print(json.dumps({
            "ledger": str(path),
            "n_trials": len(results),
            "n_tasks": len(by_task),
            "buckets": dict(buckets),
            "rerun_tasks": rerun,
            "trials": results,
        }, ensure_ascii=False, indent=2))
        return 0

    total = len(results)
    print(f"ledger   {path}")
    print(f"trials   {total}   tasks {len(by_task)}")
    print()
    print("buckets")
    for name, blurb in (
        (PASS, "keep"),
        (INFRA, "RERUN — no fair shot"),
        (TRUNCATION, "keep as failure — out of budget"),
        (GENUINE, "keep as failure — wrong answer"),
    ):
        count = buckets.get(name, 0)
        share = f"{count / total * 100:5.1f}%" if total else "  n/a"
        print(f"  {name:11s} {count:4d}  {share}  {blurb}")
    print()

    infra_rows = [r for r in results if r["bucket"] == INFRA]
    if infra_rows:
        print("infra detail (the only rerunnable bucket)")
        for reason, count in Counter(r["reason"] for r in infra_rows).most_common():
            print(f"  {count:4d}  {reason}")
        print()

    print(f"rerun list: {len(rerun)} task(s) failed only for infra reasons")
    if args.infra_out and rerun:
        print(f"written -> {Path(args.infra_out).expanduser()}")
    if not rerun:
        print("(nothing to rerun — every failure was a fair shot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
