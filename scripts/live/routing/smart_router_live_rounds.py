"""Real-LLM MULTI-ROUND session walkthrough: one agent, several real model calls
conversations back-to-back with very different questions. Verifies the full
routing chain stays correct across rounds (no filter leak, each round routed
independently) AND that the model actually calls tools inside each round's
narrowed envelope.

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    Same category as ``scripts/claudexor_platform_smoke.py``: spends real money
    against a live model API and needs a real credential, so it CANNOT run in
    automated suites. Automated, deterministic routing regression lives in
    ``tests/test_smart_router.py`` and ``tests/test_harness_tree.py``.

    Run manually:
        python scripts/live/routing/smart_router_live_rounds.py
    Requires ``OPENAI_COMPATIBLE_API_KEY`` in ``.env.gaia`` (or the env) and costs a
    small budget per round.
"""
from __future__ import annotations

import os
import pathlib
import queue
import tempfile

def _make_env(repo_dir: pathlib.Path, drive_root: pathlib.Path):
    from ouroboros.agent import Env
    return Env(repo_dir=repo_dir, drive_root=drive_root)

ROUNDS = [
    {
        "id": "round-coding",
        "type": "api_task",
        "text": "Use the vcs_status tool to tell me the current git branch, in one line.",
        "description": "Check git status",
        "workspace_root": "REPO",  # filled below
        "expect_probe": ("vcs_status", True),  # (tool, must_be_in_envelope)
    },
    {
        "id": "round-research",
        "type": "api_task",
        "text": "Without using any tools, briefly name three RAG techniques.",
        "description": "Research RAG techniques",
        "workspace_root": None,
        "expect_probe": ("web_search", True),
    },
    {
        "id": "round-knowledge",
        "type": "api_task",
        "text": "Use the update_scratchpad tool to append a note: 'multi-round session ok'.",
        "description": "Save a note to memory",
        "workspace_root": None,
        "expect_probe": ("update_scratchpad", True),
    },
    {
        "id": "round-simple",
        "type": "chat",
        "text": "hi",
        "description": "greeting",
        "workspace_root": None,
        "expect_probe": ("chat_history", True),
    },
]

def main() -> None:
    from ouroboros.config import load_settings

    settings = load_settings()
    os.environ["OPENAI_COMPATIBLE_API_KEY"] = str(settings.get("OPENAI_COMPATIBLE_API_KEY") or "").strip()
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = str(settings.get("OPENAI_COMPATIBLE_BASE_URL") or "").strip()
    os.environ["OUROBOROS_MODEL"] = str(settings.get("OUROBOROS_MODEL") or "").strip()
    if not os.environ["OPENAI_COMPATIBLE_API_KEY"]:
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY not configured in settings.json; sync .env first")
    for _k in ("OUROBOROS_REVIEW_MODELS", "OUROBOROS_SCOPE_REVIEW_MODEL",
               "OUROBOROS_SCOPE_REVIEW_MODELS", "OUROBOROS_MODEL_DEEP_SELF_REVIEW"):
        if str(settings.get(_k) or "").strip():
            os.environ[_k] = str(settings.get(_k)).strip()
    os.environ["OUROBOROS_SMART_ROUTING"] = "true"

    repo_dir = pathlib.Path(__file__).resolve().parents[3]
    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    drive_root.mkdir()

    from ouroboros.agent import OuroborosAgent
    agent = OuroborosAgent(_make_env(repo_dir, drive_root))
    agent._log_worker_boot_once = lambda: None

    results = []
    for i, spec in enumerate(ROUNDS):
        task = dict(spec)
        if task.get("workspace_root") == "REPO":
            task["workspace_root"] = str(repo_dir)

        print(f"\n{'=' * 64}\n[round {i + 1}] {task['id']}: {task['text'][:70]}")
        ctx, messages, _cap = agent._prepare_task_context(task)
        names = {s["function"]["name"] for s in agent.tools.schemas()}
        probe_tool, probe_expected = spec["expect_probe"]
        probe_ok = probe_tool in names
        print(f"  branch={ctx.harness_branch.name:10} envelope={len(names):3} "
              f"probe[{probe_tool}]={'IN' if probe_ok else 'MISSING'}")

        from ouroboros.loop import run_llm_loop
        text, usage, trace = run_llm_loop(
            messages=messages,
            tools=agent.tools,
            llm=agent.llm,
            drive_logs=drive_root / "logs",
            emit_progress=lambda s: None,
            incoming_messages=queue.Queue(),
            task_type=str(task.get("type") or ""),
            task_id=str(task.get("id") or ""),
            budget_remaining_usd=1.0,
            event_queue=None,
            initial_effort="low",
            drive_root=drive_root,
        )
        calls = trace.get("tool_calls") or []
        print(f"  model : {str(text)[:90]}")
        print(f"  tools : {len(calls)}  -> {[c.get('name') for c in calls[:5]]}")
        results.append({"id": task["id"], "branch": ctx.harness_branch.name,
                        "envelope": len(names), "probe_ok": probe_ok, "calls": len(calls)})

    print(f"\n{'=' * 64}\nSUMMARY")
    all_ok = True
    for r in results:
        ok = r["probe_ok"]
        all_ok &= ok
        print(f"  {r['id']:18} branch={r['branch']:10} env={r['envelope']:3} "
              f"probe={'OK' if ok else 'FAIL'} calls={r['calls']}")
    print("\nRESULT:", "ALL ROUTES CORRECT ACROSS ROUNDS" if all_ok else "ROUTE FAILURE DETECTED")

if __name__ == "__main__":
    main()
