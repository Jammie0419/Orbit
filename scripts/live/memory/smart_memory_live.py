"""Real-LLM Smart Memory smoke (不足 2): drives the real SmartMemory wiring
against a real model (opencode zen/go gateway via the openai-compatible stack).

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    Same category as ``scripts/live/routing/smart_router_live_smoke.py``:
    spends real money against a live model API and needs a real credential,
    so it CANNOT run in automated suites. Automated, deterministic Smart
    Memory regression lives in ``tests/test_smart_memory.py``.

    Run manually:
        $env:OUROBOROS_SMART_MEMORY="true"
        python scripts/live/memory/smart_memory_live.py
    Uses the configured ``settings.json`` (OPENAI_COMPATIBLE_API_KEY /
    OPENAI_COMPATIBLE_BASE_URL / OUROBOROS_MODEL — sync from .env via
    ``scripts/sync_env_settings.py``) and costs a small budget.

Verifies end-to-end, against a real model:
  1. SmartMemory is actually used when OUROBOROS_SMART_MEMORY=true.
  2. A rule-ambiguous block (rule 0.5) gets a real LLM importance verdict
     instead of a plain rule score.
  3. Real LLM tag extraction lands on the block.
  4. Importance-based eviction keeps high-value blocks over routine ones.
"""
from __future__ import annotations

import os
import pathlib
import tempfile


def _make_env(repo_dir: pathlib.Path, drive_root: pathlib.Path):
    from ouroboros.agent import Env
    return Env(repo_dir=repo_dir, drive_root=drive_root)


def main() -> None:
    from ouroboros.config import load_settings

    settings = load_settings()
    os.environ["OPENAI_COMPATIBLE_API_KEY"] = str(settings.get("OPENAI_COMPATIBLE_API_KEY") or "").strip()
    os.environ["OPENAI_COMPATIBLE_BASE_URL"] = str(settings.get("OPENAI_COMPATIBLE_BASE_URL") or "").strip()
    os.environ["OUROBOROS_MODEL"] = str(settings.get("OUROBOROS_MODEL") or "").strip()
    if not os.environ["OPENAI_COMPATIBLE_API_KEY"]:
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY not configured in settings.json (run scripts/sync_env_settings.py first)")
    for _k in ("OUROBOROS_REVIEW_MODELS", "OUROBOROS_SCOPE_REVIEW_MODEL",
               "OUROBOROS_SCOPE_REVIEW_MODELS", "OUROBOROS_MODEL_DEEP_SELF_REVIEW"):
        if str(settings.get(_k) or "").strip():
            os.environ[_k] = str(settings.get(_k)).strip()
    os.environ["OUROBOROS_SMART_MEMORY"] = "true"

    repo_dir = pathlib.Path(__file__).resolve().parents[3]
    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    drive_root.mkdir()

    from ouroboros.agent import OuroborosAgent
    agent = OuroborosAgent(_make_env(repo_dir, drive_root))
    agent._log_worker_boot_once = lambda: None

    print("=== memory type ===")
    from ouroboros.memory_ext.smart_memory import SmartMemory
    print("smart memory active:", isinstance(agent.memory, SmartMemory))

    print("\n=== append rule-ambiguous block (real LLM arbitrates) ===")
    # Rule score for this neutral sentence is 0.5 -> ambiguous band -> LLM.
    b1 = agent.memory.append_scratchpad_block(
        "The worker pool uses a per-task snapshot directory to isolate delegated runs.",
        source="task",
    )
    print("importance:", round(float(b1.get("importance", -1)), 3))
    print("tags:", b1.get("tags"))
    print("rule-only would be exactly 0.5:", "expected" if abs(float(b1.get("importance", 0)) - 0.5) > 0.05 else "got plain 0.5 (LLM did not move it)")

    print("\n=== append high-value block (rule 0.7, no LLM needed) ===")
    b2 = agent.memory.append_scratchpad_block(
        "discovered a critical deadlock bug in the delegation snapshot handoff",
        source="error",
    )
    print("importance:", round(float(b2.get("importance", -1)), 3))

    print("\n=== fill past max and verify importance-based eviction ===")
    for i in range(12):
        agent.memory.append_scratchpad_block(f"routine status update number {i}", source="task")
    blocks = agent.memory.load_scratchpad_blocks()
    print("surviving blocks:", len(blocks))
    high_survived = any("deadlock" in b.get("content", "") for b in blocks)
    print("high-value block survived:", high_survived)

    print("\n=== rendered scratchpad (first 400 chars) ===")
    print(agent.memory.load_scratchpad()[:400])

    print("\n=== search_by_tags (real extracted tags) ===")
    if b1.get("tags"):
        hits = agent.memory.search_by_tags(b1["tags"][:1])
        print("tag:", b1["tags"][0], "| hits:", len(hits))
        for h in hits:
            print("  -", str(h.get("content", ""))[:80])

    print("\n=== search_by_importance(>= 0.6) ===")
    for h in agent.memory.search_by_importance(min_importance=0.6, limit=3):
        print(f"  imp={float(h.get('importance', 0)):.2f}", str(h.get("content", ""))[:70])

    print("\ndone")


if __name__ == "__main__":
    main()
