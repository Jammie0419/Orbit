#!/usr/bin/env python3
"""Build and optionally run a Harbor Terminal-Bench smoke command."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from devtools.benchmarks.common.manifests import (
    admit_benchmark_run,
    finalize_run_manifest,
    write_json,
)
from devtools.benchmarks.common.model_slots import (
    fixed_model_actor_snapshot,
)
from devtools.benchmarks.common.result_index import task_result_row, write_result_index
from devtools.benchmarks.common.run_roots import (
    default_settings_path,
    assert_file_output_outside_repo,
    assert_outside_repo,
    repo_root_from_devtools,
    run_root as default_run_root,
)
from devtools.benchmarks.terminal_bench.cache_mounts import extend_with_cache_mounts


AGENT_IMPORT = "devtools.benchmarks.terminal_bench.harbor_installed_agent:OuroborosTerminalBenchAgent"


def harbor_command(
    *,
    task_names: list[str],
    model: str,
    run_root: pathlib.Path,
    dataset: str = "terminal-bench/terminal-bench-2-1",
    harbor_bin: str = "harbor",
    n_tasks: int = 1,
    n_concurrent: int = 1,
    k: int = 1,
    agent_setup_timeout_multiplier: float = 1.0,
    environment_build_timeout_multiplier: float = 1.0,
    light_model: str = "",
    force_build: bool = False,
    options: dict[str, Any] | None = None,
) -> list[str]:
    opts = dict(options or {})
    host_settings_path = str(opts.get("host_settings_path") or "")
    # Keep the light model pinned to the main model by default; v6.27.0 otherwise
    # defaults it to google/gemini-3.5-flash, which would diverge from a pure-model run.
    effective_light_model = light_model or model
    cmd = [
        harbor_bin,
        "run",
        "--dataset",
        dataset,
        "--agent-import-path",
        AGENT_IMPORT,
        "--model",
        f"ouroboros-{model.replace('/', '-')}",
        "--agent-kwarg",
        f"ouroboros_model={model}",
        "--agent-kwarg",
        f"ouroboros_light_model={effective_light_model}",
        "--agent-kwarg",
        "install_timeout_sec=1200",
        "--agent-kwarg",
        "server_start_timeout_sec=240",
        # Dataset identity for the adapter's per-task cache lookup (org is not a constant).
        "--agent-kwarg",
        f"dataset={dataset}",
    ]
    if host_settings_path:
        cmd.extend(["--agent-kwarg", f"host_settings_path={host_settings_path}"])
    cmd.extend(
        [
            "--agent-setup-timeout-multiplier",
            str(float(agent_setup_timeout_multiplier)),
            "--environment-build-timeout-multiplier",
            str(float(environment_build_timeout_multiplier)),
            "-k",
            str(int(k)),
            "--n-concurrent",
            str(int(n_concurrent)),
            "--n-tasks",
            str(int(n_tasks)),
            "--jobs-dir",
            str(run_root),
            "--yes",
        ]
    )
    for task_name in task_names:
        cmd.extend(["--include-task-name", task_name])
    # Host cache mounts (pip/uv wheels, apt debs + index, HF artifacts). Smoke mode used to
    # emit NONE, so every trial re-downloaded ~200MB of large wheels inside harbor's 360s
    # agent-setup budget and routinely died with AgentSetupTimeoutError. The mount set is
    # shared with run_tb via cache_mounts.py so the two cannot drift.
    extend_with_cache_mounts(cmd, repo_root_from_devtools())
    # Cached images are the default: a task image that is already present is reused,
    # which is both faster and closer to the accepted-submission shape (8/10 accepted
    # submissions pin environment.force_build=false). Rebuilding is opt-in because it
    # turns a ~15 minute trial into a multi-minute image build every single time.
    if force_build:
        cmd.append("--force-build")
    return cmd


def _harbor_results(run_root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path.resolve(strict=False) for path in run_root.glob("*/result.json") if path.is_file())


def _new_harbor_result(run_root: pathlib.Path, before: set[pathlib.Path]) -> pathlib.Path:
    new_results = [path for path in _harbor_results(run_root) if path not in before]
    if len(new_results) != 1:
        raise RuntimeError(f"expected exactly one new Harbor result.json, found {len(new_results)}")
    return new_results[0]


def _task_key(instance_id: object) -> str:
    """Reduce an id to its bare task name so the two id shapes Harbor uses can be compared.

    The CLI filters are written `org/name` (`terminal-bench/regex-log`) but harbor reports
    outcomes keyed by TRIAL name (`regex-log__rYVxmUv`), so an unnormalized set comparison
    never matches: every smoke run -- including clean ones -- was stamped
    harness_failed/harbor_result_unresolved, discarding the fact that harbor exited 0.
    """
    name = str(instance_id or "").strip()
    if not name:
        return ""
    name = name.rsplit("/", 1)[-1]
    return name.rsplit("__", 1)[0] if "__" in name else name


def _pass_at_k(n_trials: int, n_pass: int, k: int) -> float:
    """Probability that at least one of k samples passes, estimated without replacement:
    ``1 - C(n-c, k)/C(n, k)`` -- harbor's formula, and the one Chen et al. 2021 defines.

    At k=1 it degenerates to c/n, which is what the literature calls pass@1. Reproduced
    here so this launcher need not import harbor to print a score.
    """
    if n_trials <= 0 or n_pass <= 0:
        return 0.0
    if n_trials - n_pass < k:
        return 1.0
    ratio = 1.0
    for i in range(k):
        ratio *= (n_trials - n_pass - i) / (n_trials - i)
    return 1.0 - ratio


def _harbor_trial_rows(result_path: pathlib.Path) -> list[dict[str, object]]:
    """Per-TRIAL rows ``(task, reward, started_at)`` from the trial dirs beside the job result.

    The job-level result.json groups trials by reward VALUE, so it cannot say which trial ran
    first -- and "ran first" is exactly what Pass@1 means here. Each trial dir keeps its own
    result.json carrying a started_at, so the execution order is read from there.
    """
    rows: list[dict[str, object]] = []
    for trial_result in sorted(result_path.parent.glob("*/result.json")):
        try:
            data = json.loads(trial_result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "task_name" not in data:
            continue  # not a trial result.json
        verifier = data.get("verifier_result") if isinstance(data.get("verifier_result"), dict) else {}
        rewards = verifier.get("rewards") if isinstance(verifier.get("rewards"), dict) else {}
        rows.append({
            "task": _task_key(data.get("trial_name") or trial_result.parent.name),
            "reward": rewards.get("reward"),
            "started_at": str(data.get("started_at") or ""),
        })
    return rows


def _score_summary(rows: list[dict[str, object]]) -> list[tuple[str, int, int, float]]:
    """``(task, n_trials, n_passing, first_reward)`` per task, sorted.

    An unscored trial counts as 0, matching harbor, which treats a missing verifier_result as
    a zero rather than as grounds to drop the task. ``first_reward`` is the reward of the
    trial with the earliest started_at -- the task's FIRST attempt.
    """
    by_task: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        task = str(row.get("task") or "")
        if task:
            by_task.setdefault(task, []).append(row)
    summary: list[tuple[str, int, int, float]] = []
    for task, task_rows in sorted(by_task.items()):
        # Empty started_at sorts last: an unknown time must not be crowned "first".
        ordered = sorted(task_rows, key=lambda row: str(row.get("started_at") or "\uffff"))
        passes = [1 if row.get("reward") in (1, 1.0, True) else 0 for row in ordered]
        summary.append((task, len(passes), sum(passes), float(passes[0])))
    return summary


def _print_score_summary(rows: list[dict[str, object]]) -> None:
    """Print our own score table under Harbor's, carrying the two Pass@1 readings side by side.

    ``pass@1`` is the official number: Chen et al. 2021's ``1 - C(n-c,k)/C(n,k)`` evaluated at
    k=1, which reduces to c/n -- the single-attempt success rate. It is therefore always equal
    to the reward mean, so there is no separate Mean column; both names are on this one.

    ``first@1`` is the reward of the task's FIRST trial (earliest started_at), a 0/1 "passed on
    the first attempt" indicator. It is NOT the official pass@1: it is a single observation,
    not an estimate, and only becomes a rate once averaged over tasks. Printed because a
    reported "first-try success rate" has to come from somewhere explicit.

    Harbor prints Pass@2/4/5 in the table directly above, so those are not repeated here.
    """
    summary = _score_summary(rows)
    if not summary:
        return
    widest = max(len(task) for task, _, _, _ in summary) + 2
    print()
    print("scores -- pass@1: official (Chen et al. 2021) 1-C(n-c,k)/C(n,k) at k=1 = c/n, the "
          "single-attempt success rate; it equals the reward mean")
    print("          first@1: reward of the FIRST trial started (0/1) -- an observation, "
          "not the official pass@1")
    print("  " + f"{'task':<{widest}}" + f"{'n':>3}" + f"{'pass@1':>10}" + f"{'first@1':>10}")
    totals = [0.0, 0.0]
    for task, n, n_pass, first in summary:
        values = [_pass_at_k(n, n_pass, 1), first]
        totals = [total + value for total, value in zip(totals, values)]
        print(f"  {task:<{widest}}{n:>3}" + "".join(f"{value:>10.3f}" for value in values))
    label = f"mean over {len(summary)} task(s)"
    print(f"  {label:<{widest}}{'':>3}"
          + "".join(f"{total / len(summary):>10.3f}" for total in totals))
    if any(not str(row.get("started_at") or "") for row in rows):
        print("  NOTE: at least one trial has no started_at, so which trial counts as "
              "first@1 is not fully determined for that task")


def _harbor_task_outcomes(result_path: pathlib.Path) -> list[dict[str, object]]:
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    evals = stats.get("evals") if isinstance(stats.get("evals"), dict) else {}
    outcomes: list[dict[str, object]] = []
    seen: set[str] = set()
    for eval_summary in evals.values():
        if not isinstance(eval_summary, dict):
            continue
        reward_stats = eval_summary.get("reward_stats") if isinstance(eval_summary.get("reward_stats"), dict) else {}
        rewards = reward_stats.get("reward") if isinstance(reward_stats.get("reward"), dict) else {}
        for reward_text, task_ids in rewards.items():
            if not isinstance(task_ids, list):
                continue
            try:
                reward_value = float(str(reward_text))
            except ValueError:
                reward_value = None
            for task_id in task_ids:
                instance_id = str(task_id or "").strip()
                if not instance_id or instance_id in seen:
                    continue
                seen.add(instance_id)
                outcomes.append({"instance_id": instance_id, "reward": reward_value})
    return sorted(outcomes, key=lambda item: str(item["instance_id"]))


def _harbor_child_env(repo_root: pathlib.Path,
                      pinned_env: dict[str, str]) -> dict[str, str]:
    env = dict(pinned_env)
    existing = env.get("PYTHONPATH", "")
    entries = [str(repo_root)]
    if existing:
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", action="append", default=[], help="task name; repeat for a deterministic subset")
    parser.add_argument("--model", default="google/gemini-3.5-flash")
    parser.add_argument("--dataset", default="terminal-bench/terminal-bench-2-1")
    parser.add_argument("--harbor-bin", default="harbor")
    parser.add_argument("--n-tasks", type=int, default=5)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("-k", "--k", type=int, default=1, dest="k", help="trials per task (harbor -k); default 1")
    parser.add_argument("--agent-setup-timeout-multiplier", type=float, default=1.0, help="harbor agent-setup timeout multiplier; default 1.0 (official)")
    parser.add_argument("--environment-build-timeout-multiplier", type=float, default=1.0, help="harbor environment-build timeout multiplier; default 1.0 (official)")
    parser.add_argument("--ouroboros-light-model", default="", help="light model kwarg; default = main --model (avoids v6.27.0 gemini-3.5-flash default)")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--settings-path", default="")
    parser.add_argument("--isolated-data-root", default="")
    parser.add_argument("--ledger-output", default="", help="denominator-preserving JSONL result ledger")
    parser.add_argument(
        "--allow-dirty-seed",
        action="store_true",
        help="record and proceed with an unclean/unidentifiable seed checkout instead of refusing",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--force-build",
        action="store_true",
        help="rebuild the task image even when a cached one exists (default: reuse cache)",
    )
    args = parser.parse_args()

    repo_root = repo_root_from_devtools()
    effective_light = str(args.ouroboros_light_model or "").strip() or args.model
    child_env = dict(os.environ)
    fixed_actor = fixed_model_actor_snapshot(
        args.model,
        light_model=effective_light,
        target=child_env,
    )
    actor_slots = fixed_actor["model_slots"]
    settings_path = pathlib.Path(args.settings_path).expanduser() if args.settings_path else default_settings_path()
    run_root = assert_outside_repo(
        pathlib.Path(args.run_root).expanduser() if args.run_root else default_run_root("terminal_bench"),
        repo_root,
    )
    # The shared seed gate below (benchmark_run_manifest, fail-closed since v6.75.0) is now the
    # single authority on source cleanliness; the old opt-in --require-clean-source check was a
    # weaker duplicate of it.
    actual_include_filters = args.task or []
    effective_n_tasks = len(actual_include_filters) if actual_include_filters else int(args.n_tasks)
    task_names = actual_include_filters or [f"selection-slot-{idx + 1}" for idx in range(effective_n_tasks)]
    cmd = harbor_command(
        task_names=actual_include_filters,
        model=actor_slots["OUROBOROS_MODEL"],
        run_root=run_root,
        dataset=args.dataset,
        harbor_bin=args.harbor_bin,
        n_tasks=effective_n_tasks,
        n_concurrent=args.n_concurrent,
        k=args.k,
        agent_setup_timeout_multiplier=args.agent_setup_timeout_multiplier,
        environment_build_timeout_multiplier=args.environment_build_timeout_multiplier,
        light_model=actor_slots["OUROBOROS_MODEL_LIGHT"],
        force_build=bool(args.force_build),
        options={"execute": args.execute, "host_settings_path": str(settings_path)},
    )
    ledger_output = (
        assert_file_output_outside_repo(pathlib.Path(args.ledger_output), repo_root)
        if args.ledger_output
        else run_root / "result_index.jsonl"
    )
    manifest_path = run_root / "run_manifest.json"
    # Admission is the outermost REFUSAL point, not the outermost side effect: `ensure_outside_repo`
    # above already created `run_root` (it mkdirs). So a refused run leaves that directory holding
    # nothing but the persisted refusal — no harbor invocation, no ledger, no settings render.
    manifest = admit_benchmark_run(
        manifest_path,
        benchmark="terminal_bench",
        run_root=run_root,
        repo_dir=repo_root,
        requested_task_ids=list(actual_include_filters),
        require_clean=not args.allow_dirty_seed,
        argv=sys.argv,
        output_paths={"harbor_output_dir": str(run_root)},
        dataset=args.dataset,
        harness={"agent_import": AGENT_IMPORT, "harbor_bin": args.harbor_bin},
        official_command=cmd,
        timeout_sec=None,
        isolated_data_root=args.isolated_data_root,
        settings_path=settings_path,
        extra={
            "outcome": "started",
            "n_tasks": effective_n_tasks,
            "requested_n_tasks_arg": int(args.n_tasks),
            "n_concurrent": int(args.n_concurrent),
            "source_dirty_allowed": bool(args.allow_dirty_seed),
            "selection": {
                "mode": "explicit_task_ids" if actual_include_filters else "deterministic_first_n",
                "requested_slots": task_names,
                "include_filters": actual_include_filters,
            },
        },
    )
    manifest["model_slots"] = {
        key: actor_slots[key]
        for key in (
            "OUROBOROS_MODEL",
            "OUROBOROS_MODEL_LIGHT",
            "OUROBOROS_MODEL_FALLBACKS",
        )
    }
    manifest["available_subagents"] = fixed_actor["available_subagents"]
    manifest["harness"]["fixed_model_actor"] = fixed_actor
    # Durable before Harbor can spend: no ambient settings model/Heavy can survive.
    write_json(manifest_path, manifest)
    if not actual_include_filters:
        manifest["requested_count"] = effective_n_tasks
    with finalize_run_manifest(manifest_path, manifest) as final:
        (run_root / "harbor_command.json").write_text(json.dumps({"run_root": str(run_root), "cmd": cmd, "agent_import": AGENT_IMPORT}, indent=2), encoding="utf-8")
        status = "planned"
        reason = "command_generated"
        official_eval_status = "not_run"
        print(shlex.join(cmd))
        returncode = 0
        harbor_result: pathlib.Path | None = None
        harbor_result_error = ""
        observed_outcomes: list[dict[str, object]] = []
        if args.execute:
            before_results = set(_harbor_results(run_root))
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=repo_root,
                    env=_harbor_child_env(repo_root, child_env),
                )
            except Exception as exc:
                harbor_result_error = f"{type(exc).__name__}: {exc}"
                status = "harness_failed"
                reason = "harbor_invocation_failed"
                official_eval_status = "failed"
                returncode = 2
            else:
                returncode = completed.returncode
                status = "harness_completed" if returncode == 0 else "harness_failed"
                reason = "harbor_returncode_0" if returncode == 0 else "harbor_returncode_nonzero"
                official_eval_status = "completed" if returncode == 0 else "failed"
                try:
                    harbor_result = _new_harbor_result(run_root, before_results)
                except Exception as exc:
                    harbor_result_error = str(exc)
                    status = "harness_failed"
                    reason = "harbor_result_unresolved"
                    official_eval_status = "failed"
                    returncode = returncode or 2
            if harbor_result is not None:
                observed_outcomes = _harbor_task_outcomes(harbor_result)
                observed_ids = {_task_key(item.get("instance_id")) for item in observed_outcomes}
                expected_ids = {_task_key(name) for name in actual_include_filters}
                if not observed_outcomes and effective_n_tasks > 0:
                    harbor_result_error = "Harbor result contained no parseable task outcomes"
                elif expected_ids and not observed_ids.issubset(expected_ids):
                    extras = sorted(observed_ids - expected_ids)
                    harbor_result_error = f"Harbor result included unexpected task ids: {extras}"
                elif expected_ids:
                    missing = sorted(expected_ids - observed_ids)
                    if missing:
                        harbor_result_error = f"Harbor result omitted requested task ids: {missing}"
                elif len(observed_ids) != effective_n_tasks:
                    # Distinct task keys, not raw outcome count: one task at k=5 yields five
                    # outcome rows, which against `--n-tasks 1` read as a mismatch.
                    harbor_result_error = (
                        f"Harbor result completed {len(observed_ids)} tasks, expected {effective_n_tasks}"
                    )
                if harbor_result_error:
                    status = "harness_failed"
                    reason = "harbor_result_unresolved"
                    official_eval_status = "failed"
                    returncode = returncode or 2
                # The finalization seam rewrites the manifest on EVERY exit path, so these
                # observed-result fields need no separate write here.
                manifest["output_paths"]["harbor_result"] = str(harbor_result)
                manifest["observed_task_ids"] = [str(item["instance_id"]) for item in observed_outcomes]
                manifest["official_result_summary"] = {
                    "result_path": str(harbor_result),
                    "completed_outcomes": len(observed_outcomes),
                }
        ledger_tasks: list[dict[str, object]] = []
        if observed_outcomes and not harbor_result_error:
            ledger_tasks.extend(observed_outcomes)
            recorded_ids = {str(item.get("instance_id") or "") for item in ledger_tasks}
            if actual_include_filters:
                for task in task_names:
                    if task not in recorded_ids:
                        ledger_tasks.append({"instance_id": task, "reward": None})
            while not actual_include_filters and len(ledger_tasks) < effective_n_tasks:
                ledger_tasks.append({"instance_id": f"selection-slot-missing-{len(ledger_tasks) + 1}", "reward": None})
        else:
            ledger_tasks.extend({"instance_id": task, "reward": None} for task in task_names)
        write_result_index(
            ledger_output,
            [
                task_result_row(
                    benchmark="terminal_bench",
                    instance_id=str(task["instance_id"]),
                    status=status,
                    metadata={
                        "reason_code": reason,
                        "official_eval_status": official_eval_status,
                        "output_paths": {
                            "harbor_output_dir": str(run_root),
                            "manifest": str(run_root / "run_manifest.json"),
                            "harbor_result": str(harbor_result) if harbor_result is not None else "",
                        },
                        "error": harbor_result_error,
                        "details": {
                            "returncode": returncode,
                            "include_filters": actual_include_filters,
                            "n_tasks": effective_n_tasks,
                            "official_reward": task.get("reward"),
                        },
                    },
                )
                for task in ledger_tasks
            ],
        )
        if not args.execute:
            final.update({"outcome": "command_generated", "exit_code": 0})
            return 0
        if observed_outcomes and not harbor_result_error and harbor_result is not None:
            _print_score_summary(_harbor_trial_rows(harbor_result))
        final.update({"outcome": status, "exit_code": int(returncode)})
        return returncode


if __name__ == "__main__":
    raise SystemExit(main())
