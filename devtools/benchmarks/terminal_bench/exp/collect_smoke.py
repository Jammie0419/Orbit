#!/usr/bin/env python3
"""Collect per-task smoke runs into a leaderboard-shaped submission tree.

WHY THIS EXISTS

`run_harbor_smoke.py` is the convenient way to run one task at a time, but its
output cannot pass as a submission and does not look like one:

  * it launches harbor with a bare `--agent-import-path`, so the job config
    records `agents[0].name = null`. The leaderboard's static analysis joins
    `config.agents[].name` against the trials report, so a smoke tree fails with
    "no matching agent in job config" no matter how good the numbers are;
  * each invocation writes its own `<run_root>/<timestamp>/` job dir, so 89 tasks
    produce 89 job dirs instead of one submission-shaped job;
  * it writes no `metadata.yaml` and no `disclosure_ledger.json`.

This tool assembles those per-task runs into the shape an accepted submission
actually has:

    <out>/
    ├── assembly_manifest.json            (what went into this tree; NOT an admitted run manifest)
    ├── disclosure_ledger.json            (consolidated; run_tb's own taxonomy)
    └── submission/submissions/terminal-bench/2.1/<agent>__<model>/
        ├── metadata.yaml
        └── job/
            ├── agent_job_config.json     (NAMED - the piece smoke mode omits)
            └── <timestamp>/
                ├── config.json  lock.json  job.log
                ├── result.json            (aggregate over every merged trial)
                └── {task}__{hash}/...     (every task's trials, side by side)

REUSE, NOT REIMPLEMENTATION

The named job config, `metadata.yaml` and the disclosure ledger are produced by
`run_tb.py`'s own functions, so the merged artifact cannot drift from what a
native run writes: `_write_agent_job_config`, `leaderboard_metadata`, and
`write_disclosure_ledger`.

Usage:
  exp/collect_smoke.py --model "openai-compatible::mimo-v2.5" \
      --out ~/bench_runs/terminal_bench/exp/campaign \
      --runs ~/bench_runs/terminal_bench/smoke/regex-log \
             ~/bench_runs/terminal_bench/smoke/pypi-server
  exp/collect_smoke.py --model ... --out ... --scan ~/bench_runs/terminal_bench/smoke
  exp/collect_smoke.py --model ... --out ... --runs A B --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import shutil
import sys

if __package__ in {None, ""}:
    # .../<repo>/devtools/benchmarks/terminal_bench/exp/collect_smoke.py
    # parents[4] is the repo root. parents[3] is `devtools`, which is neither a package
    # root nor importable, so `import devtools...` fails. The sibling runners live one
    # level up (terminal_bench/) where parents[3] IS the repo root, which is why this
    # only bit the script run the way exp/README.md documents: without PYTHONPATH set.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from devtools.benchmarks.terminal_bench.run_tb import (
    HarborCommandConfig,
    _write_agent_job_config,
    leaderboard_metadata,
    write_disclosure_ledger,
)

AGENT_DIR_PREFIX = "ouroboros"  # matches run_tb.py's submission layout
DEFAULT_DATASET = "terminal-bench/terminal-bench-2-1"


# --------------------------------------------------------------------------- model


def model_slug(model: str) -> str:
    """Same flattening run_tb.py uses, so both tools name the slot identically.

    The existing submission tree is `ouroboros__openai-compatible__mimo-v2.5`, i.e.
    `/` -> `-` and `:` -> `_`. A raw `::` survives on Linux but breaks as a URL path
    segment and on Windows.
    """
    return model.replace("/", "-").replace(":", "_")


# ------------------------------------------------------------------------ discovery


def _is_trial_dir(path: pathlib.Path) -> bool:
    """A trial dir holds a result.json describing ONE trial.

    Naming alone is not enough to tell a trial dir from harbor's job dir: the job
    timestamp dir is also `<date>__<time>` (so it contains `__`) and also carries a
    job-level result.json. Discriminate on CONTENT instead -- a trial result.json has
    `task_name` / `verifier_result`, a job-level one has `stats.evals`. Same rule
    run_tb.py's ledger walker uses.
    """
    if not path.is_dir():
        return False
    result = path / "result.json"
    if not result.is_file():
        return False
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and ("task_name" in data or "verifier_result" in data)


def discover_trial_dirs(roots: list[pathlib.Path]) -> list[pathlib.Path]:
    """Every `<root>/<timestamp>/<task>__<hash>/` trial dir under the given roots.

    A root may also BE a job timestamp dir, so `--runs <root>/2026-01-01__00-00-00`
    works as well as `--runs <root>`.
    """
    found: dict[pathlib.Path, None] = {}
    for root in roots:
        if not root.is_dir():
            sys.exit(f"collect: run root not found: {root}")
        if _is_trial_dir(root):
            found[root] = None
            continue
        for candidate in sorted(root.iterdir()):
            if _is_trial_dir(candidate):
                found[candidate] = None
                continue
            if candidate.is_dir():
                for nested in sorted(candidate.iterdir()):
                    if _is_trial_dir(nested):
                        found[nested] = None
    return sorted(found)


def scan_for_roots(parent: pathlib.Path) -> list[pathlib.Path]:
    """Treat every immediate subdirectory of `parent` as a smoke run root."""
    if not parent.is_dir():
        sys.exit(f"collect: scan dir not found: {parent}")
    roots = [child for child in sorted(parent.iterdir()) if child.is_dir() and not _is_trial_dir(child)]
    if not roots:
        sys.exit(f"collect: no run roots under {parent}")
    return roots


def read_trial(trial_dir: pathlib.Path) -> dict:
    try:
        data = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"trial_name": trial_dir.name, "task_name": trial_dir.name.rsplit("__", 1)[0],
                "reward": None, "error": f"unreadable result.json: {exc}"}
    verifier = data.get("verifier_result") if isinstance(data.get("verifier_result"), dict) else {}
    rewards = verifier.get("rewards") if isinstance(verifier.get("rewards"), dict) else {}
    exc_info = data.get("exception_info") if isinstance(data.get("exception_info"), dict) else {}
    return {
        "trial_name": str(data.get("trial_name") or trial_dir.name),
        "task_name": str(data.get("task_name") or trial_dir.name.rsplit("__", 1)[0]),
        "reward": rewards.get("reward"),
        "exception_type": exc_info.get("exception_type"),
        "task_ref": ((data.get("task_id") or {}).get("ref") if isinstance(data.get("task_id"), dict) else None),
        # Pass@1 is defined as the task's FIRST attempt, so the collector has to carry the
        # per-trial start time: harbor's job-level result.json groups trials by reward value
        # and cannot say which one ran first.
        "started_at": str(data.get("started_at") or ""),
        "error": "",
        "dir": trial_dir,
    }


# ------------------------------------------------------------------- job artifacts


def build_job_result(trials: list[dict], *, eval_key: str, started: str, finished: str) -> dict:
    """Harbor-shaped job-level result.json for the merged trial set.

    Computed from the real trials rather than copied from one source job, so the
    aggregate describes what is actually in this job dir. Kept to harbor's own keys
    and value shapes; `pass_at_k` stays empty exactly as harbor leaves it.
    """
    reward_buckets: dict[str, list[str]] = {}
    exception_buckets: dict[str, list[str]] = {}
    rewards_numeric: list[float] = []
    for trial in trials:
        reward = trial.get("reward")
        reward_buckets.setdefault(str(reward), []).append(trial["trial_name"])
        if isinstance(reward, (int, float)) and not isinstance(reward, bool):
            rewards_numeric.append(float(reward))
        if trial.get("exception_type"):
            exception_buckets.setdefault(str(trial["exception_type"]), []).append(trial["trial_name"])
    for bucket in list(reward_buckets.values()) + list(exception_buckets.values()):
        bucket.sort()
    mean = sum(rewards_numeric) / len(rewards_numeric) if rewards_numeric else 0.0
    return {
        "id": "",  # no single harbor job backs an assembled tree; see assembly_manifest.json
        "started_at": started,
        "updated_at": finished,
        "finished_at": finished,
        "n_total_trials": len(trials),
        "stats": {
            "n_completed_trials": len(trials),
            "n_errored_trials": sum(1 for t in trials if t.get("exception_type")),
            "n_running_trials": 0,
            "n_pending_trials": 0,
            "n_cancelled_trials": 0,
            "n_retries": 0,
            "evals": {
                eval_key: {
                    "n_trials": len(trials),
                    "n_errors": sum(1 for t in trials if t.get("exception_type")),
                    "metrics": [{"mean": mean}],
                    "pass_at_k": {},
                    "reward_stats": {"reward": reward_buckets},
                    "exception_stats": exception_buckets,
                }
            },
            "n_input_tokens": None,
            "n_cache_tokens": None,
            "n_output_tokens": None,
            "cost_usd": None,
        },
    }


def _pass_at_k(n_trials: int, n_pass: int, k: int) -> float:
    """Unbiased pass@k over the trials actually run for one task.

    1 - C(n-c, k)/C(n, k): the probability that at least one of k samples passes,
    estimated without replacement from n trials of which c passed.
    """
    if n_trials <= 0:
        return 0.0
    if n_pass <= 0:
        return 0.0
    if n_trials - n_pass < k:
        return 1.0
    # product form keeps the numbers small for large n
    ratio = 1.0
    for i in range(k):
        ratio *= (n_trials - n_pass - i) / (n_trials - i)
    return 1.0 - ratio


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="measured model id, e.g. openai-compatible::mimo-v2.5")
    parser.add_argument("--light-model", default="", help="light lane model (default: same as --model)")
    parser.add_argument("--out", required=True, help="output run root (manifest/ledger beside submission/)")
    parser.add_argument("--runs", nargs="*", default=[], help="smoke run roots to collect")
    parser.add_argument("--scan", default="", help="parent dir whose subdirs are all run roots")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=5, help="trials per task the campaign intended (for reporting)")
    parser.add_argument("--agent-name", default="Ouroboros Installed")
    parser.add_argument("--org-name", default="Ouroboros")
    parser.add_argument("--job-timestamp", default="", help="job dir name; default: now")
    parser.add_argument("--settings-path", default="", help="host settings path recorded in the job config")
    parser.add_argument("--move", action="store_true", help="move instead of copy trial dirs")
    parser.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
    args = parser.parse_args()

    roots = [pathlib.Path(p).expanduser() for p in args.runs]
    if args.scan:
        roots.extend(scan_for_roots(pathlib.Path(args.scan).expanduser()))
    if not roots:
        parser.error("pass --runs and/or --scan")

    trial_dirs = discover_trial_dirs(roots)
    if not trial_dirs:
        sys.exit("collect: no trial dirs found under the given roots")
    trials = [read_trial(d) for d in trial_dirs]

    by_task: dict[str, list[dict]] = {}
    for trial in trials:
        by_task.setdefault(trial["task_name"], []).append(trial)

    out = pathlib.Path(args.out).expanduser()
    slug = model_slug(args.model)
    submission_root = out / "submission"
    job_dir = submission_root / "submissions" / "terminal-bench" / "2.1" / f"{AGENT_DIR_PREFIX}__{slug}" / "job"
    stamp = args.job_timestamp or _dt.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    merged_job_ts = job_dir / stamp

    print(f"collected trials : {len(trials)} across {len(by_task)} task(s)")
    print(f"source run roots : {len(roots)}")
    print(f"output job dir   : {merged_job_ts}")
    print()

    print("per-task trial counts vs k")
    shortfalls = []
    for task in sorted(by_task):
        n = len(by_task[task])
        flag = "" if n >= args.k else f"   <-- SHORT of k={args.k}"
        if n < args.k:
            shortfalls.append(task)
        print(f"  {n:3d}  {task}{flag}")
    print()

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    if merged_job_ts.exists():
        sys.exit(f"collect: refusing to overwrite existing job dir: {merged_job_ts}")
    merged_job_ts.mkdir(parents=True)
    job_dir.mkdir(parents=True, exist_ok=True)

    # ---- job-level config.json / lock.json: copied from a source job (real harbor output)
    source_jobs = {}
    for trial_dir in trial_dirs:
        source_job = trial_dir.parent
        source_jobs.setdefault(source_job, None)
    for source_job in sorted(source_jobs):
        for name in ("config.json", "lock.json"):
            src = source_job / name
            if src.is_file():
                shutil.copy2(src, merged_job_ts / name)
                break

    # ---- trial dirs
    for trial_dir in trial_dirs:
        target = merged_job_ts / trial_dir.name
        if target.exists():
            sys.exit(f"collect: duplicate trial dir name would collide: {target}")
        if args.move:
            shutil.move(str(trial_dir), str(target))
        else:
            shutil.copytree(trial_dir, target, symlinks=True)

    # ---- named job config (run_tb's own builder: this is the piece smoke mode omits)
    cfg = HarborCommandConfig(
        dataset=args.dataset,
        model=args.model,
        k=args.k,
        jobs_dir=job_dir,
        harbor_bin="harbor",
        n_concurrent=1,
        task_filters=sorted(by_task),
        settings_path=pathlib.Path(args.settings_path).expanduser() if args.settings_path else pathlib.Path(""),
        execute=True,
        light_model=args.light_model or args.model,
    )
    config_path = _write_agent_job_config(cfg)

    # ---- metadata.yaml in the official location (job_dir.parent)
    # `leaderboard_metadata` resolves the helper models from the CURRENT environment
    # (OUROBOROS_REVIEW_MODELS / _SCOPE_REVIEW_MODEL(S) / _WEBSEARCH_MODEL), falling back
    # to the shipped defaults. Those defaults are NOT what a run with a sourced .env
    # used, so collecting without that env would declare reviewers that never touched
    # the run -- a misrepresentation in exactly the field a reviewer reads first.
    env_review = (os.environ.get("OUROBOROS_REVIEW_MODELS") or "").strip()
    env_scope = (os.environ.get("OUROBOROS_SCOPE_REVIEW_MODELS")
                 or os.environ.get("OUROBOROS_SCOPE_REVIEW_MODEL") or "").strip()
    if not env_review and not env_scope:
        print("WARNING: neither OUROBOROS_REVIEW_MODELS nor OUROBOROS_SCOPE_REVIEW_MODEL(S) is set.")
        print("         metadata.yaml will declare the SHIPPED DEFAULT reviewers, which may not")
        print("         be the models the collected runs actually used. Re-run this collector")
        print("         with the same environment the runs were launched from (e.g. after")
        print("         `source .env.terminal_bench.linux`) before treating metadata.yaml as truthful.")
        print()
    metadata_path = job_dir.parent / "metadata.yaml"
    metadata_path.write_text(
        leaderboard_metadata(
            agent_name=args.agent_name,
            org_name=args.org_name,
            model=args.model,
            light_model=args.light_model or args.model,
            disable_agent_web=cfg.disable_agent_web,
        ),
        encoding="utf-8",
    )

    # ---- job-level result.json + job.log
    stamps = []
    for trial_dir in trial_dirs:
        try:
            data = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("started_at", "finished_at"):
            value = data.get(key)
            if isinstance(value, str) and value:
                stamps.append(value)
    started_at = min(stamps) if stamps else ""
    finished_at = max(stamps) if stamps else ""
    eval_key = f"{args.agent_name}__ouroboros-{args.model.replace('/', '-')}__{args.dataset}"
    (merged_job_ts / "result.json").write_text(
        json.dumps(build_job_result(trials, eval_key=eval_key, started=started_at, finished=finished_at), indent=2) + "\n",
        encoding="utf-8",
    )
    (merged_job_ts / "job.log").write_text(
        "assembled by exp/collect_smoke.py from per-task smoke runs\n"
        f"source run roots ({len(roots)}):\n" + "\n".join(f"  {r}" for r in roots) + "\n",
        encoding="utf-8",
    )

    # ---- assembly record + disclosure ledger
    # Deliberately NOT `ouroboros.benchmark.run_manifest.v1`, and deliberately not
    # named run_manifest.json. That schema is produced by `admit_benchmark_run`, and
    # its value comes from what admission PROVES: a clean-seed gate, repo provenance,
    # argv, credential disclosure, harness identity. Assembling already-finished runs
    # proves none of that, so reusing the name would hand a reader a document that
    # looks admitted and is not. This record says what it is: which source runs went
    # into this tree.
    assembly = {
        "schema": "ouroboros.benchmark.assembly_manifest.v1",
        "benchmark": "terminal_bench",
        "created_at_unix": _dt.datetime.now().timestamp(),
        "run_root": str(out),
        "assembled_by": "devtools/benchmarks/terminal_bench/exp/collect_smoke.py",
        "provenance_note": (
            "Assembled from completed per-task runs. This is NOT an admitted run "
            "manifest: it carries no clean-seed gate, no source provenance and no "
            "credential disclosure, because the assembly itself performed no run. "
            "Per-run provenance lives in each source root's own run_manifest.json."
        ),
        "requested_task_ids": sorted(by_task),
        "requested_count": len(by_task),
        "dataset": args.dataset,
        "model_slots": {"OUROBOROS_MODEL": args.model, "OUROBOROS_MODEL_LIGHT": args.light_model or args.model},
        "assembly": {
            "outcome": "assembled",
            "assembly_kind": "per-task smoke runs merged into one submission-shaped job",
            "source_run_roots": [str(r) for r in roots],
            "source_job_dirs": [str(p) for p in sorted(source_jobs)],
            "k": args.k,
            "model": args.model,
            "light_model": args.light_model or args.model,
            "job_timestamp": stamp,
            "merged_job_dir": str(merged_job_ts),
            "trials_short_of_k": shortfalls,
            "job_level_result_json": (
                "computed aggregate over the merged trials; no single harbor job backs this tree"
            ),
            "job_level_config_json": (
                "copied from one source job, so it describes that job's single task rather "
                "than every task in this tree"
            ),
        },
    }
    (out / "assembly_manifest.json").write_text(json.dumps(assembly, indent=2) + "\n", encoding="utf-8")

    ledger = write_disclosure_ledger(
        jobs_dir=job_dir,
        out_path=out / "disclosure_ledger.json",
        run_meta={
            "dataset": args.dataset,
            "k": args.k,
            "n_concurrent": 1,
            "model": args.model,
            "model_provider_prefix": (args.model.split("/", 1)[0] if "/" in args.model else ""),
            "assembled": True,
            "source_run_roots": [str(r) for r in roots],
        },
    )

    # ---- pass@k summary (honest: computed over the trials present)
    # Pass@1 is the task's FIRST attempt -- the reward of the earliest-started trial -- so it is
    # fixed the moment that trial finishes and is 0/1 per task; it only becomes a rate once
    # averaged over tasks. Pass@k keeps harbor's semantics over all n trials, so the two can
    # disagree in direction on one task (pass@1 = 0 with pass@5 > 0 means a later attempt
    # passed). Mean is the reward average over all n trials.
    print("pass@k over the collected trials")
    total_first = 0.0
    total_mean = 0.0
    total_pass_k = 0.0
    for task in sorted(by_task):
        rows = sorted(by_task[task], key=lambda r: str(r.get("started_at") or "\uffff"))
        n = len(rows)
        n_pass = sum(1 for r in rows if r.get("reward") in (1, 1.0, True))
        first = 1.0 if rows and rows[0].get("reward") in (1, 1.0, True) else 0.0
        mean = n_pass / n if n else 0.0
        value_k = _pass_at_k(n, n_pass, args.k)
        total_first += first
        total_mean += mean
        total_pass_k += value_k
        print(f"  pass@1 {first*100:6.1f}%   mean {mean*100:6.1f}%   "
              f"pass@{args.k} {value_k*100:6.1f}%   {n_pass}/{n}  {task}")
    tasks = len(by_task) or 1
    mean_task_pass_k = total_pass_k / tasks
    print()
    print(f"mean over {len(by_task)} task(s): pass@1 {total_first/tasks*100:.1f}%   "
          f"mean {total_mean/tasks*100:.1f}%   pass@{args.k} {mean_task_pass_k*100:.1f}%")
    if shortfalls:
        print(f"WARNING: {len(shortfalls)} task(s) have fewer than k={args.k} trials; "
              f"their pass@{args.k} is optimistic")
    print()
    print(f"job config  -> {config_path}")
    print(f"metadata    -> {metadata_path}")
    print(f"assembly    -> {out / 'assembly_manifest.json'}")
    print(f"ledger      -> {out / 'disclosure_ledger.json'}")
    if isinstance(ledger, dict):
        print(f"ledger says : n_trials={ledger.get('n_trials')} n_tasks={ledger.get('n_tasks')} "
              f"rewards={ledger.get('reward_distribution')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
