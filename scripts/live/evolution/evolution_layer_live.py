"""Real-LLM smoke for the evolution layer (PAPER 不足 4 + 5 + 7):
TrajectoryExperienceLearner (dual-track credit assignment) + MultiAgentEvolver
(planner) against a real model.

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    Same category as ``scripts/claudexor_platform_smoke.py``: spends real money
    against a live model API and needs a real credential, so it CANNOT run in
    automated suites. Automated deterministic regression lives in
    ``tests/test_evolution_layer.py``.

    Run manually (activate .env first):
        set -a; source .env; set +a
        python scripts/live/evolution/evolution_layer_live.py

Verifies end-to-end, against a real model:
  1. Track-A: task-trace experience extraction (credit assignment + LLM overall).
  2. Track-B: evolution-cycle trace consumption via the cursor (kind=cycle).
  3. suggest_evolution_strategy produces a strategy digest from the cycle depot.
  4. MultiAgentEvolver produces a full structured evolution plan
     (objective/root_causes/approach/steps/verification).
This is NOT a full campaign run (server + reviewed commit + restart verify live
in ``devtools/benchmarks/evolution/run_evolution_arm.py``) — it validates the
layer's cognitive products with a real model at minimal cost.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile


def main() -> None:
    from ouroboros.config import load_settings

    settings = load_settings()
    for _k in ("OPENAI_COMPATIBLE_API_KEY", "OPENAI_COMPATIBLE_BASE_URL", "OUROBOROS_MODEL"):
        _v = str(settings.get(_k) or "").strip()
        if _v:
            os.environ[_k] = _v  # settings.json wins only when non-empty; .env-provided values stay
    if not os.environ.get("OPENAI_COMPATIBLE_API_KEY"):
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY not configured; activate .env first (set -a; source .env; set +a)")
    # The layer under test is force-enabled for this run (consume_pending_cycles
    # and the planner only run — even at low level — under this switch).
    os.environ["OUROBOROS_MULTI_AGENT_EVOLVER"] = "true"

    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    (drive_root / "logs").mkdir(parents=True)
    (drive_root / "state").mkdir(parents=True)

    # --- synthetic traces (realistic shapes from logs/tools.jsonl) ---
    def _tool_row(task_id: str, tool: str, *, is_error: bool = False, status: str = "ok") -> dict:
        return {
            "ts": "2026-09-02T00:00:00Z", "type": "tool_call", "tool": tool,
            "task_id": task_id, "args": {}, "result_preview": "ok",
            "is_error": is_error, "status": status,
        }

    with (drive_root / "logs" / "tools.jsonl").open("a", encoding="utf-8") as fh:
        for row in [
            _tool_row("live-task-1", "read_file"),
            _tool_row("live-task-1", "query_code"),
            _tool_row("live-task-1", "run_command", is_error=True, status="error"),
            _tool_row("live-task-1", "edit_text"),
            _tool_row("live-cycle-1", "search_code"),
            _tool_row("live-cycle-1", "edit_batch"),
            _tool_row("live-cycle-1", "run_command", is_error=True, status="error"),
            _tool_row("live-cycle-1", "vcs_diff"),
        ]:
            fh.write(json.dumps(row) + "\n")

    checkpoint = {
        "schema_version": 1, "kind": "cycle_outcome", "source": "live-smoke",
        "ts": "2026-09-02T00:00:00Z", "task_id": "live-cycle-1",
        "campaign_id": "live-c1", "campaign_objective": "Improve error recovery on command timeouts",
        "cycle_outcome": "abandoned", "commit_sha": "",
    }
    with (drive_root / "state" / "evolution_checkpoints.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(checkpoint) + "\n")

    reflection = {
        "task_id": "live-task-1", "task_type": "api_task",
        "goal": "Fix the failing login flow",
        "rounds": 18, "cost_usd": 0.02, "error_count": 3,
        "key_markers": ["TOOL_ERROR", "review"], "reflection": "Retry logic timeouts.",
    }

    from ouroboros.llm import LLMClient

    llm = LLMClient()

    print("=== Track-A: task trace experience (kind=task) ===")
    from ouroboros.evolution.trajectory_experience_learner import TrajectoryExperienceLearner

    learner = TrajectoryExperienceLearner(drive_root, llm_client=llm)
    exp_a = learner.extract_task_experience("live-task-1", reflection)
    print("  steps:", [(s["tool"], s["is_error"]) for s in (exp_a or {}).get("steps") or []])
    print("  credits:", [(c["tool"], c["credit"]) for c in (exp_a or {}).get("credits") or []])
    print("  overall:", json.dumps((exp_a or {}).get("overall") or {}, ensure_ascii=False)[:400])

    print("=== Track-B: evolution-cycle trace (kind=cycle, cursor) ===")
    consumed = learner.consume_pending_cycles()
    print("  consumed:", consumed)
    recs = learner.load_experiences(kind="cycle")
    for rec in recs:
        print("  cycle:", rec.get("task_id"), rec.get("outcome"),
              "| critical:", [(c.get("tool"), c.get("credit")) for c in rec.get("critical_steps") or []])
    print("  cursor:", json.loads((drive_root / "state" / "evolution_consumed.json").read_text(encoding="utf-8")))

    print("=== strategy digest ===")
    strategy = learner.suggest_evolution_strategy("Improve error recovery on command timeouts")
    print("  ", json.dumps(strategy, ensure_ascii=False)[:400])

    print("=== MultiAgentEvolver plan ===")
    from ouroboros.evolution.multi_agent_evolver import MultiAgentEvolver

    evolver = MultiAgentEvolver(drive_root, llm_client=llm)
    plan = evolver.run_evolution_cycle(
        steps=list((exp_a or {}).get("steps") or []),
        reflection_entry=reflection,
        experience=(exp_a or {}).get("overall"),
        objective_hint="Improve error recovery on command timeouts",
    )
    for key in ("objective", "root_causes", "approach", "files_to_modify",
                "implementation_steps", "risks", "verification_plan"):
        print(f"  {key}: {str(plan.get(key))[:300]}")

    print("\n=== layer summary ===")
    print("  experiences stored:", len(learner.load_experiences()))
    print("  plan schema_version:", plan.get("schema_version"))


if __name__ == "__main__":
    main()