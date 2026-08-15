"""Real-LLM multi-task walkthrough: drives the real smart-router + harness wiring
against a real model (DeepSeek via the openai-compatible stack) for one task of
each type.

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    This is the same category as ``scripts/claudexor_platform_smoke.py``: it
    spends real money against a live model API and requires a real credential,
    so it CANNOT run in automated suites. It lives in ``scripts/`` on purpose.
    Automated, deterministic routing regression lives in
    ``tests/test_smart_router.py`` and ``tests/test_harness_tree.py``.

    Run manually:
        python scripts/smart_router_live_multi.py
    Requires ``DEEPSEEK_API_KEY`` in ``.env.gaia`` (or the env) and costs a
    small budget per task.

For each task it reports the FULL chain:
  1. classification -> harness branch
  2. round-one tool envelope (size + spot-check routed/not-routed tools)
  3. recommended skills (if any)
  4. the model's real final text and the real tool calls it made
  5. the routing-history record

This is the owner-facing sanity check that the 不足 1 + 不足 3 + 不足 8 wiring is
reasonable end-to-end, not just unit-correct.
"""
from __future__ import annotations

import json
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


# One task per task-type. Each is designed to be answerable in ~1 tool round so
# the budget stays tiny; the point is the routing chain, not the answer.
TASKS = [
    {
        "label": "coding",
        "task": {
            "id": "multi-coding",
            "chat_id": 1,
            "type": "api_task",
            "workspace_root": None,  # set below to repo root
            "text": "Use the vcs_status tool to tell me the current git branch, in one line.",
            "description": "Check git status",
        },
        "expect": {"branch": "coding", "has_tool": "vcs_status", "lacks_tool": "web_search"},
    },
    {
        "label": "research",
        "task": {
            "id": "multi-research",
            "chat_id": 2,
            "type": "api_task",
            "workspace_root": None,
            "text": "Without using any tools, briefly list three well-known retrieval-augmented generation (RAG) techniques.",
            "description": "Research RAG techniques",
        },
        "expect": {"branch": "research", "has_tool": "web_search", "lacks_tool": "vcs_status"},
    },
    {
        "label": "knowledge",
        "task": {
            "id": "multi-knowledge",
            "chat_id": 3,
            "type": "api_task",
            "workspace_root": None,
            "text": "Use the update_scratchpad tool to append a short note that the smart-router audit is done.",
            "description": "Save a note to memory",
        },
        "expect": {"branch": "knowledge", "has_tool": "update_scratchpad", "lacks_tool": "vcs_status"},
    },
    {
        "label": "simple",
        "task": {
            "id": "multi-simple",
            "chat_id": 4,
            "type": "chat",
            "workspace_root": None,
            "text": "hi",
            "description": "Simple greeting",
        },
        "expect": {"branch": "main", "has_tool": "chat_history", "lacks_tool": "web_search"},
    },
]


def _run_task(agent, drive_root: pathlib.Path, label: str, entry: dict, task: dict) -> None:
    print(f"\n{'=' * 60}\n>>> [{label}] {task['text'][:70]}")
    ctx, messages, _cap = agent._prepare_task_context(task)
    branch = ctx.harness_branch
    names = {s["function"]["name"] for s in agent.tools.schemas()}
    system = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")

    # 1-3. routing facts
    print(f"  classification branch : {branch.name}  (task_type={getattr(branch, 'task_type', '?')})")
    print(f"  envelope size         : {len(names)}/108")
    spot = entry["expect"]
    print(f"  spot-check            : expected branch={spot['branch']}")
    for key in ("has_tool", "lacks_tool"):
        tool = spot[key]
        print(f"    {tool:18} {'IN envelope' if tool in names else 'NOT routed'} ({key})")
    prompt_extra = (getattr(branch, "system_prompt_extra", "") or "").strip()
    print(f"  harness prompt extra  : {'in system prompt' if prompt_extra and prompt_extra.splitlines()[0] in system else 'n/a'}")

    # 4. real LLM loop
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
    print(f"  model reply           : {str(text)[:110]}")
    calls = trace.get("tool_calls") or []
    print(f"  tool calls            : {len(calls)}")
    for tc in calls[:5]:
        print(f"      {tc.get('name')}({str(tc.get('arguments'))[:80]})")


def main() -> None:
    key = _load_key()
    os.environ["OPENAI_COMPATIBLE_API_KEY"] = key
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = "https://api.deepseek.com"
    os.environ["OUROBOROS_SMART_ROUTING"] = "true"
    os.environ["OUROBOROS_MODEL"] = "openai-compatible::deepseek-chat"

    repo_dir = pathlib.Path(__file__).resolve().parents[1]
    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    drive_root.mkdir()

    from ouroboros.agent import OuroborosAgent
    agent = OuroborosAgent(_make_env(repo_dir, drive_root))
    agent._log_worker_boot_once = lambda: None

    for entry in TASKS:
        task = dict(entry["task"])
        if task.get("workspace_root") is None and entry["label"] == "coding":
            task["workspace_root"] = str(repo_dir)
        _run_task(agent, drive_root, entry["label"], entry, task)

    history = drive_root / "state" / "routing_history.jsonl"
    print(f"\n{'=' * 60}\nRouting history ({history.name}):")
    for line in history.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        print(f"  {rec['task_id']:16} type={rec['task_type']:9} branch={rec['branch']:9} tools={rec['tools_count']:3} skills={rec['skills_count']}")


if __name__ == "__main__":
    main()
