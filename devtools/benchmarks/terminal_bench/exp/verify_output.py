#!/usr/bin/env python3
"""Check a collected submission tree against the Terminal-Bench 2.1 layout rules.

This reports what it finds and never claims more than the evidence supports: a
failing check is printed as a gap with the reason, and the exit code is non-zero
when a SUBMISSION-BLOCKING gap exists. Checks marked ADVISORY do not change the
exit code because the rule they encode is a convention rather than a validator
rejection.

The rules encoded here come from devtools/benchmarks/terminal_bench/README.md
("Leaderboard Validity Rules" + "Submitting to the leaderboard") and
METHODOLOGY.md, which were read against the upstream validator and real accepted
submissions. Re-read those before treating this as authoritative.

Usage:
  exp/verify_output.py --submission ~/bench_runs/terminal_bench/exp/campaign/submission \
      --agent-name "Ouroboros Installed" --k 5
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict

BLOCKING = "BLOCKING"
ADVISORY = "ADVISORY"

REQUIRED_TRIAL_FILES = ("result.json",)
REQUIRED_TRIAL_FILES_ADVISORY = ("verifier/reward.txt", "agent/instruction.txt")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []  # (severity, ok, title, detail)

    def check(self, severity: str, ok: bool, title: str, detail: str = "") -> None:
        self.rows.append((severity, "PASS" if ok else "FAIL", title, detail))

    def note(self, title: str, detail: str = "") -> None:
        self.rows.append(("INFO", "INFO", title, detail))

    @property
    def blocking_failures(self) -> int:
        return sum(1 for sev, state, _, _ in self.rows if sev == BLOCKING and state == "FAIL")

    @property
    def advisory_failures(self) -> int:
        return sum(1 for sev, state, _, _ in self.rows if sev == ADVISORY and state == "FAIL")

    def render(self) -> None:
        for severity, state, title, detail in self.rows:
            tag = f"{state:<4}"
            sev = f"[{severity}]" if severity in (BLOCKING, ADVISORY) else "      "
            print(f"  {tag} {sev:<11} {title}")
            if detail and state != "PASS":
                for line in detail.splitlines():
                    print(f"           {line}")


def find_slot_dirs(submission: pathlib.Path) -> list[pathlib.Path]:
    """The `<agent>__<model>/` dirs that hold a `job/`, accepting either
    `<root>/submissions/<family>/<version>/<slot>` or the slot dir itself."""
    if (submission / "job").is_dir():
        return [submission]
    slots = []
    for job in sorted(submission.rglob("job")):
        if job.is_dir() and "submissions" in job.parts:
            slots.append(job.parent)
    return slots


def load_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--submission", required=True, help="submission root (the dir holding job/) or its parent")
    parser.add_argument("--agent-name", default="Ouroboros Installed")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="also emit machine-readable results")
    args = parser.parse_args()

    root = pathlib.Path(args.submission).expanduser()
    report = Report()

    slot_dirs = find_slot_dirs(root)
    report.check(BLOCKING, bool(slot_dirs), "submission slot dir found",
                 f"no `job/` directory under {root}")
    if not slot_dirs:
        report.render()
        return 1
    if len(slot_dirs) > 1:
        report.note(f"{len(slot_dirs)} slot dirs will each be checked")

    for slot in slot_dirs:
        report.note(f"slot: {slot}")
        job_dir = slot / "job"

        # ---- metadata.yaml in the official location (parent of job/)
        metadata = slot / "metadata.yaml"
        report.check(BLOCKING, metadata.is_file(), f"{slot.name}: metadata.yaml present",
                     f"expected {metadata}")

        # ---- named job config: the validator joins config.agents[].name against the
        # trials report, and a null name can never match.
        config_path = job_dir / "agent_job_config.json"
        config = load_json(config_path)
        if config is None:
            report.check(BLOCKING, False, f"{slot.name}: agent_job_config.json readable",
                         f"missing or invalid: {config_path}")
        else:
            agents = config.get("agents") or []
            names = [str(a.get("name") or "") for a in agents if isinstance(a, dict)]
            report.check(BLOCKING, bool(names) and all(names),
                         f"{slot.name}: job config names every agent",
                         f"agents[].name = {names!r}; a null/empty name can never match the "
                         f"trials report ('no matching agent in job config')")
            if names and args.agent_name:
                report.check(BLOCKING, args.agent_name in names,
                             f"{slot.name}: job config declares --agent-name",
                             f"expected {args.agent_name!r} among {names!r}")

        # ---- trial dirs
        ts_dirs = [d for d in sorted(job_dir.iterdir()) if d.is_dir()]
        all_trials: list[pathlib.Path] = []
        for ts in ts_dirs:
            all_trials.extend(sorted(d for d in ts.iterdir() if d.is_dir() and "__" in d.name))
        report.check(BLOCKING, bool(all_trials), f"{slot.name}: trial dirs present",
                     f"no {{task}}__{{hash}} dirs under {job_dir}")

        if not all_trials:
            continue

        per_task: dict[str, list[pathlib.Path]] = defaultdict(list)
        for trial in all_trials:
            per_task[trial.name.rsplit("__", 1)[0]].append(trial)

        # ---- k >= 5 per task
        short = {task: len(rows) for task, rows in per_task.items() if len(rows) < args.k}
        report.check(BLOCKING, not short, f"{slot.name}: every task has >= k={args.k} trials",
                     "\n".join(f"{task}: {n} trial(s)" for task, n in sorted(short.items())))

        # ---- per-trial required files
        missing_required: list[str] = []
        missing_advisory: list[str] = []
        rewarded: list[pathlib.Path] = []
        missing_trajectory: list[str] = []
        missing_task_ref: list[str] = []
        no_reward = 0

        for trial in all_trials:
            for rel in REQUIRED_TRIAL_FILES:
                if not (trial / rel).is_file():
                    missing_required.append(f"{trial.name}: {rel}")
            for rel in REQUIRED_TRIAL_FILES_ADVISORY:
                if not (trial / rel).is_file():
                    missing_advisory.append(f"{trial.name}: {rel}")

            data = load_json(trial / "result.json")
            if not isinstance(data, dict):
                continue
            ref = None
            task_id = data.get("task_id")
            if isinstance(task_id, dict):
                ref = task_id.get("ref")
            if not ref:
                missing_task_ref.append(trial.name)

            verifier = data.get("verifier_result")
            rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
            reward = rewards.get("reward") if isinstance(rewards, dict) else None
            if reward is None:
                no_reward += 1
            elif reward in (1, 1.0, True):
                rewarded.append(trial)
                if not (trial / "agent" / "trajectory.json").is_file():
                    missing_trajectory.append(trial.name)

        report.check(BLOCKING, not missing_required, f"{slot.name}: every trial has result.json",
                     "\n".join(missing_required[:20]))
        report.check(ADVISORY, not missing_advisory,
                     f"{slot.name}: every trial has verifier/reward.txt + agent/instruction.txt",
                     "\n".join(missing_advisory[:20]))

        # ---- ATIF trajectory for every REWARDED trial: README records that it must
        # exist BEFORE the first upload, because a re-upload skips existing trials and
        # a failed trajectory PUT degrades silently to archive-only (unrepairable).
        report.check(BLOCKING, not missing_trajectory,
                     f"{slot.name}: every rewarded trial has an ATIF trajectory",
                     "\n".join(missing_trajectory[:20]) +
                     "\nbackfill with build_atif_trajectories.py --job-dir <job> --validate BEFORE uploading")

        report.check(ADVISORY, not missing_task_ref,
                     f"{slot.name}: every trial records task_id.ref (content hash)",
                     "\n".join(missing_task_ref[:20]) +
                     "\nCI checks task versions by content hash; a missing ref cannot be verified")

        # ---- honest per-task summary (never hides shortfalls)
        passed = len(rewarded)
        total = len(all_trials)
        report.note(f"{slot.name}: {total} trial(s) over {len(per_task)} task(s); "
                    f"{passed} rewarded ({passed / total * 100:.1f}%)"
                    + (f"; {no_reward} unscored" if no_reward else ""))

        dist = Counter()
        for trial in all_trials:
            data = load_json(trial / "result.json")
            verifier = data.get("verifier_result") if isinstance(data, dict) else None
            rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
            dist[str(rewards.get("reward") if isinstance(rewards, dict) else None)] += 1
        report.note(f"{slot.name}: reward distribution {dict(sorted(dist.items()))}")

    report.render()
    print()
    if report.blocking_failures:
        print(f"RESULT: {report.blocking_failures} submission-blocking gap(s); "
              f"{report.advisory_failures} advisory gap(s)")
        print("This tree is NOT submission-ready as inspected.")
    elif report.advisory_failures:
        print(f"RESULT: 0 blocking gaps; {report.advisory_failures} advisory gap(s) worth reviewing")
    else:
        print("RESULT: no gaps found by the checks encoded here")
        print("Note: this verifier encodes the local reading of the published rules. It is not "
              "the upstream validator, and passing here does not guarantee CI acceptance.")

    if args.json:
        print()
        print(json.dumps(
            [{"severity": s, "state": st, "title": t, "detail": d} for s, st, t, d in report.rows],
            ensure_ascii=False, indent=2))

    return 1 if report.blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
