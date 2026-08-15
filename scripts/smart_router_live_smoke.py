"""Real-LLM smoke: drives the real smart-router + harness wiring against a real
model (DeepSeek via the openai-compatible stack).

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    Same category as ``scripts/claudexor_platform_smoke.py``: spends real money
    against a live model API and needs a real credential, so it CANNOT run in
    automated suites. Automated, deterministic routing regression lives in
    ``tests/test_smart_router.py`` and ``tests/test_harness_tree.py``.

    Run manually:
        $env:OUROBOROS_SMART_ROUTING="true"
        python scripts/smart_router_live_smoke.py
    Requires ``DEEPSEEK_API_KEY`` in ``.env.gaia`` (or the env) and costs a
    small budget.

Verifies end-to-end, against a real model:
  1. Task classification picks the right harness branch.
  2. The round-one tool envelope is narrowed (schemas served to the loop).
  3. The model is able to call the routed tools (a real tool call happens).
  4. The routing history record carries task_type/branch.
"""
from __future__ import annotations

import os
import pathlib
import queue
import tempfile

import dotenv  # type: ignore


def _load_key() -> str:
    dotenv.load_dotenv(".env.gaia")
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not found in .env.gaia")
    return key


def _make_env(repo_dir: pathlib.Path, drive_root: pathlib.Path):
    from ouroboros.agent import Env
    return Env(repo_dir=repo_dir, drive_root=drive_root)


def main() -> None:
    key = _load_key()
    os.environ["OPENAI_COMPATIBLE_API_KEY"] = key
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = "https://api.deepseek.com"
    os.environ["OUROBOROS_SMART_ROUTING"] = "true"
    # Pin the routed model to the OpenAI-compatible DeepSeek lane.
    os.environ["OUROBOROS_MODEL"] = "openai-compatible::deepseek-chat"

    repo_dir = pathlib.Path(__file__).resolve().parents[1]
    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    drive_root.mkdir()

    from ouroboros.agent import OuroborosAgent
    agent = OuroborosAgent(_make_env(repo_dir, drive_root))
    agent._log_worker_boot_once = lambda: None

    task = {
        "id": "live1",
        "chat_id": 1,
        "type": "api_task",
        "workspace_root": str(repo_dir),
        "text": "Use the vcs_status tool to check the current git state, then say in one line what branch you are on.",
        "description": "Check git status",
    }

    ctx, messages, cap_info = agent._prepare_task_context(task)
    branch = ctx.harness_branch
    names = {s["function"]["name"] for s in agent.tools.schemas()}
    print("=== routing facts ===")
    print("branch:", branch.name)
    print("envelope size:", len(names), "| vcs_status routed:", "vcs_status" in names,
          "| web_search routed:", "web_search" in names)
    print("system prompt has coding extra:", "Coding Task Focus" in " ".join(
        str(m.get("content") or "") for m in messages if m.get("role") == "system"))

    print("\n=== real LLM loop (budget-capped) ===")
    from ouroboros.loop import run_llm_loop
    text, usage, trace = run_llm_loop(
        messages=messages,
        tools=agent.tools,
        llm=agent.llm,
        drive_logs=drive_root / "logs",
        emit_progress=lambda s: print("  progress:", s),
        incoming_messages=queue.Queue(),
        task_type="api_task",
        task_id="live1",
        budget_remaining_usd=1.0,
        event_queue=None,
        initial_effort="low",
        drive_root=drive_root,
    )
    print("\n=== result ===")
    print("final text:", text[:300])
    print("tool calls made:", len(trace.get("tool_calls") or []))
    for tc in (trace.get("tool_calls") or [])[:10]:
        print("  tool:", tc.get("name"), "| args:", str(tc.get("arguments"))[:120])

    history = drive_root / "state" / "routing_history.jsonl"
    print("\n=== routing history ===")
    if history.exists():
        import json
        rec = json.loads(history.read_text(encoding="utf-8").splitlines()[-1])
        print("task_type:", rec.get("task_type"), "| branch:", rec.get("branch"),
              "| tools:", len(rec.get("tools") or []))
    print("\nusage cost_usd:", usage.get("cost_usd"), "| status:", usage.get("execution_status"))


if __name__ == "__main__":
    main()
