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

# Verifier-side tooling/environment failures.
#
# A reward 0 whose VERIFIER never ran is infrastructure, not capability -- and nothing
# in the ledger distinguishes it from the model answering wrong. Observed in practice:
# every task's test.sh reaching for `uvx` while the agent venv had only `uv`, giving
# "/tests/test.sh: line 28: uvx: command not found" and a reward of 0.
#
# Choosing these markers is a trade, and the two errors are NOT equally bad. Calling a
# genuine failure "infra" removes a real failure from the capability numbers and
# INFLATES the score -- the dishonest direction. So the auto-classify set is narrow:
# it contains only things the verifier's OWN toolchain produces.
#
# Rejected candidates, with the false positive each one produced on real data:
#   "ModuleNotFoundError: No module named"  -> feal-differential-cryptanalysis prints
#      "No module named 'attack'" because the TASK asks the agent to write attack.py.
#      That is the agent failing to deliver, i.e. a genuine failure.
#   "Failed to establish a new connection"  -> appears inside urllib3 "Retrying"
#      warnings that precede a SUCCESSFUL request, and can follow the agent's own
#      broken network code.
#   "ImportError: cannot import name"       -> same ambiguity as ModuleNotFoundError.
# Those are surfaced for review instead; see VERIFIER_REVIEW_MARKERS.

# Tools a terminal-bench task never asks the agent to BUILD, so their absence is the
# harness's problem and not the agent's deliverable.
HARNESS_ONLY_TOOLS = ("uv", "uvx", "pytest", "pip", "pip3")

VERIFIER_INFRA_MARKERS: tuple[tuple[str, str], ...] = (
    *((f": {tool}: command not found", f"verifier toolchain missing '{tool}'")
      for tool in HARNESS_ONLY_TOOLS),
    ("error: externally-managed-environment", "pip refused to run in the verifier"),
    ("Cannot connect to the Docker daemon", "docker unavailable inside the verifier"),
    ("Could not find a version that satisfies the requirement",
     "verifier could not install a package it needs"),
    ("No matching distribution found", "verifier could not install a package it needs"),
)

# Real signals of a broken verifier environment that could ALSO be the agent's own
# failure, so they are reported rather than auto-classified.
VERIFIER_REVIEW_MARKERS: tuple[tuple[str, str], ...] = (
    ("ModuleNotFoundError: No module named", "a module was missing"),
    ("ImportError: cannot import name", "an import failed"),
    ("Temporary failure in name resolution", "DNS lookup failed"),
    ("Could not resolve host", "DNS lookup failed"),
)


def _scan_markers(text: str, markers) -> tuple[str, str] | None:
    for marker, meaning in markers:
        for line in text.splitlines():
            if marker not in line:
                continue
            # A retry warning precedes the same request being retried and often
            # succeeding; it is not evidence the verifier failed.
            if "Retrying" in line:
                continue
            return meaning, line.strip()[:200]
    return None


def scan_verifier_stdout(trial_dir: Path, markers=None) -> tuple[str, str] | None:
    """Return (what it means, the offending line), or None when nothing matches.

    `markers` defaults to VERIFIER_INFRA_MARKERS; pass VERIFIER_REVIEW_MARKERS for the
    advisory pass. None means either no verifier output was found or it contains no
    marker, i.e. the verifier ran and its verdict stands.
    """
    markers = VERIFIER_INFRA_MARKERS if markers is None else markers
    for rel in ("verifier/test-stdout.txt", "verifier/test-stderr.txt", "trial.log"):
        path = trial_dir / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = _scan_markers(text, markers)
        if hit is not None:
            return hit
    return None


def classify(trial: dict, trial_dir: Path | None = None) -> tuple[str, str]:
    """Return (bucket, reason). `reason` explains the assignment in one phrase.

    `trial_dir` is optional but should be supplied when available: without it a
    verifier that failed to run is indistinguishable from a wrong answer.
    """
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

    # Last gate before calling it a capability failure: a reward 0 that looks like a
    # wrong answer but whose verifier never actually ran is infrastructure, not
    # capability. This is the only place the difference is visible at all.
    if trial_dir is not None:
        hit = scan_verifier_stdout(trial_dir)
        if hit is not None:
            meaning, line = hit
            return INFRA, f"verifier did not run: {meaning} | {line}"

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


def find_trial_dirs(ledger_path: Path, extra_roots: list[Path]) -> dict[str, Path]:
    """Map trial_name -> trial dir, searched under the ledger's own directory.

    Both layouts put the trial dirs below wherever the ledger lives: a smoke run root
    has `<root>/<timestamp>/<trial>/`, and an assembled campaign has
    `<out>/submission/submissions/<...>/<timestamp>/<trial>/`. Searching the ledger's
    parent therefore covers both without the caller having to say which it is.
    """
    roots = [ledger_path.parent, *extra_roots]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for verifier in root.rglob("verifier"):
            if not verifier.is_dir():
                continue
            trial = verifier.parent
            if (verifier / "reward.txt").is_file() or (verifier / "test-stdout.txt").is_file():
                found.setdefault(trial.name, trial)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", help="path to disclosure_ledger.json")
    parser.add_argument("--run-root", help="run root; the ledger is located inside it")
    parser.add_argument("--verifier-root", action="append", default=[],
                        help="extra dir to search for trial verifier output; repeatable")
    parser.add_argument("--infra-out", help="write the rerun task list here")
    parser.add_argument("--show-evidence", action="store_true",
                        help="print the verifier line that made an infra call")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    path = resolve_ledger(args)
    ledger = load_ledger(path)
    trials = ledger.get("trials") or []
    if not trials:
        sys.exit(f"triage: {path} contains no trials")

    trial_dirs = find_trial_dirs(path, [Path(r).expanduser() for r in args.verifier_root])
    scanned = sum(1 for t in trials if t.get("trial_name") in trial_dirs)

    results = []
    for trial in trials:
        trial_dir = trial_dirs.get(str(trial.get("trial_name")))
        bucket, reason = classify(trial, trial_dir)
        # Advisory only: markers that could equally be the agent's own failure, so
        # they are shown to the operator instead of silently moving the trial. See
        # VERIFIER_REVIEW_MARKERS for the false positive behind each one.
        hint = scan_verifier_stdout(trial_dir, VERIFIER_REVIEW_MARKERS) if trial_dir else None
        results.append({
            "task_name": trial.get("task_name", "?"),
            "trial_name": trial.get("trial_name", "?"),
            "reward": trial.get("reward"),
            "bucket": bucket,
            "reason": reason,
            "reason_code": trial.get("reason_code"),
            "exception_type": trial.get("exception_type"),
            "verifier_scanned": trial_dir is not None,
            "review_hint": f"{hint[0]}: {hint[1]}" if hint else "",
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
            "n_trials_verifier_scanned": scanned,
            "buckets": dict(buckets),
            "rerun_tasks": rerun,
            "trials": results,
        }, ensure_ascii=False, indent=2))
        return 0

    total = len(results)
    print(f"ledger   {path}")
    print(f"trials   {total}   tasks {len(by_task)}")
    # Say how much of the evidence base was actually inspectable: a trial whose
    # verifier output could not be found is classified on the ledger alone, and a
    # "genuine" verdict there is less trustworthy than one backed by the output.
    print(f"verifier output found for {scanned}/{total} trial(s)"
          + ("" if scanned == total else "   <- the rest were judged on the ledger only"))
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
            print(f"  {count:4d}  {reason[:150]}")
        print()

    # The trials this run rescued from a "genuine failure" misread deserve naming:
    # they are the reason to trust the capability numbers at all.
    rescued = [r for r in results
               if r["bucket"] == INFRA and str(r["reason"]).startswith("verifier did not run")]
    if rescued:
        print(f"NOTE: {len(rescued)} trial(s) had a reward 0 that looks like a wrong answer")
        print("      but whose VERIFIER never ran. Counted as infra, not capability.")
        if args.show_evidence:
            for row in rescued:
                print(f"        {row['trial_name']}: {row['reason']}")
        print()

    # Advisory, deliberately not acted on. Every one of these cost a real false
    # positive when it was tried as an automatic rule.
    hinted = [r for r in results if r["review_hint"]]
    if hinted:
        print(f"REVIEW: {len(hinted)} trial(s) show a failure signature that could be either")
        print("        the verifier's environment or the agent's own failure, so they were")
        print("        NOT reclassified. Check these by hand before trusting their verdicts:")
        for row in hinted[:10]:
            mark = "PASS" if row["bucket"] == PASS else row["bucket"]
            print(f"        [{mark}] {row['trial_name']}: {row['review_hint'][:120]}")
        if len(hinted) > 10:
            print(f"        ... and {len(hinted) - 10} more (use --json for all)")
        print()

    print(f"rerun list: {len(rerun)} task(s) failed only for infra reasons")
    if args.infra_out and rerun:
        print(f"written -> {Path(args.infra_out).expanduser()}")
    if not rerun:
        print("(nothing to rerun — every failure was a fair shot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
