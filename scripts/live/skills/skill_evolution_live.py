"""Real-LLM smoke for the Hermes-Style Skill Evolution envelope
(PAPER Phase 3): stats ledger + trajectory -> self-authored skill generation +
GEPA genetic evolution + nudge cadence, against a real model.

⚠️ MANUAL OPERATOR SCRIPT — NOT a pytest test, and NOT part of CI.
    Spends real money against a live model API (main slot = OUROBOROS_MODEL,
    ~1 generation call + up to ~9 evolution calls here) and needs a real
    credential, so it CANNOT run in automated suites. Automated deterministic
    regression lives in ``tests/test_skill_evolution.py``.

    Run manually (activate .env first):
        set -a; source .env; set +a
        python scripts/live/skills/skill_evolution_live.py

Verifies end-to-end, against a real model, on a TEMP drive (the repo and the
real data dir are never touched):
  1. SkillStatsLedger.aggregate rebuilds state/skill_stats.json from the
     synthetic skill_exec rows (12 runs, 8 ok -> success rate 0.667).
  2. SkillAutoGenerator turns a successful self-repairing trace into a
     self-authored skill under skills/self/ (dual markers + scripts).
  3. SkillNudgeEngine cadence (first run -> due) + rule-based analysis.
  4. SkillEvolver runs the GEPA population cycle on the seeded failing skill
     and either accepts a fitter variant (version bump) or keeps the old one.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile


def _tool_row(task_id: str, tool: str, *, is_error: bool = False, status: str = "ok",
              args: dict | None = None, result: str = "") -> dict:
    return {
        "ts": "2026-09-03T00:00:00Z", "type": "tool_call", "tool": tool,
        "task_id": task_id, "args": args if args is not None else {},
        "result_preview": result or ("ok" if not is_error else "boom"),
        "is_error": is_error, "status": "error" if is_error else status,
    }


def main() -> None:
    from ouroboros.config import load_settings

    settings = load_settings()
    for _k in ("OPENAI_COMPATIBLE_API_KEY", "OPENAI_COMPATIBLE_BASE_URL", "OUROBOROS_MODEL"):
        _v = str(settings.get(_k) or "").strip()
        if _v:
            os.environ[_k] = _v  # settings.json wins only when non-empty; .env-provided values stay
    if not os.environ.get("OPENAI_COMPATIBLE_API_KEY"):
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY not configured; activate .env first (set -a; source .env; set +a)")
    os.environ["OUROBOROS_SKILL_EVOLUTION"] = "true"  # envelope is force-enabled for this run

    drive_root = pathlib.Path(tempfile.mkdtemp()) / "drive"
    (drive_root / "logs").mkdir(parents=True)
    (drive_root / "state").mkdir(parents=True)

    # --- synthetic data (realistic shapes) ---
    with (drive_root / "logs" / "tools.jsonl").open("a", encoding="utf-8") as fh:
        # current task trace: 7 steps, one error recovered -> generation-eligible
        for row in [
            _tool_row("live-skill-task", "read_file"),
            _tool_row("live-skill-task", "search_code"),
            _tool_row("live-skill-task", "run_command"),
            _tool_row("live-skill-task", "edit_text"),
            _tool_row("live-skill-task", "run_command", is_error=True, status="error"),
            _tool_row("live-skill-task", "edit_text"),
            _tool_row("live-skill-task", "run_command"),
        ]:
            fh.write(json.dumps(row) + "\n")
        # 12 skill_exec runs for the seeded skill: 8 ok + 4 failed -> 0.667.
        # The failed rows carry REAL error text so the reflective mutation (B2)
        # has concrete failure modes to eliminate.
        failure_results = [
            "tarfile.ReadError: file is not a tar archive",
            "PermissionError: [Errno 13] Permission denied: 'logs.tar'",
            "subprocess.TimeoutExpired: command 'tar -czf' timed out after 60s",
            "FileNotFoundError: [Errno 2] No such file or directory: 'archive.d'",
        ]
        for i in range(12):
            failed = i >= 8
            fh.write(json.dumps(_tool_row(
                f"live-task-{i % 3}", "skill_exec", is_error=failed,
                status="error" if failed else "ok",
                args={"skill": "live-demo-skill", "script": "main.py"},
                result=failure_results[i - 8] if failed else "compressed archives uploaded")) + "\n")

    # seed a self-authored skill that the evolver may improve
    from ouroboros.skill_evolution.auto_generation import write_skill_package

    write_skill_package(
        drive_root,
        {
            "name": "live-demo-skill",
            "description": "compress log archives before upload",
            "version": "1.0",
            "type": "script",
            "runtime": "python",
            "when_to_use": "whenever log archives must be compressed and uploaded",
            "tags": ["log", "archive", "upload"],
            "scripts": [{
                "name": "main.py",
                "code": "#!/usr/bin/env python3\n"
                        "import sys, tarfile\n"
                        "def main():\n"
                        "    path = sys.argv[1] if len(sys.argv) > 1 else 'logs.tar'\n"
                        "    with tarfile.open(path, 'w:gz') as tf:\n"
                        "        tf.add(path + '.d')\n"
                        "    print('compressed')\n"
                        "if __name__ == '__main__':\n"
                        "    main()\n",
            }],
        },
        task_id="live-seed",
        created_by_tool="live-smoke",
    )
    # a past review flagged this skill: the feedback loop must surface it in
    # the evolution prompts (failure analysis / fitness) so new variants avoid
    # repeating the flagged pattern.
    review_state = drive_root / "state" / "skills" / "live-demo-skill"
    review_state.mkdir(parents=True, exist_ok=True)
    (review_state / "review.json").write_text(json.dumps({
        "status": "blockers",
        "findings": [{
            "item": "network-egress", "verdict": "FAIL", "severity": "high",
            "reason": "script must not contact external endpoints",
        }],
        "reviewer_models": ["reviewer-one"],
        "timestamp": "2026-09-02T00:00:00Z",
    }), encoding="utf-8")

    from ouroboros.skill_evolution.auto_generation import recent_review_flags

    print("=== 0. review-feedback seed ===")
    print("  flags for live-demo-skill:", recent_review_flags(drive_root, skill_name="live-demo-skill"))

    from ouroboros.llm import LLMClient

    llm = LLMClient()

    print("=== 1. stats ledger ===")
    from ouroboros.skill_evolution.stats import SkillStatsLedger

    ledger = SkillStatsLedger(drive_root)
    stats = ledger.aggregate()
    entry = stats.get("live-demo-skill") or {}
    print("  live-demo-skill:", entry)

    print("=== 2. auto-generation from the current task ===")
    from ouroboros.skill_evolution.auto_generation import SkillAutoGenerator

    generator = SkillAutoGenerator(drive_root, llm_client=llm)
    record = generator.maybe_generate_for_task(
        "live-skill-task",
        goal="Fix flaky log-archive uploads by retrying on transient errors",
        outcome_hint="success",
    )
    if record:
        print("  created skill:", record["skill_name"], "| type:", record["type"])
        skill_dir = drive_root / "skills" / "self" / record["skill_name"]
        print("  package:", list(skill_dir.rglob("*"))[:8])
    else:
        print("  no skill generated (eligibility or LLM extraction failed)")

    print("=== 3. nudge (first run -> due) + analysis ===")
    from ouroboros.skill_evolution.nudge import SkillNudgeEngine

    nudge = SkillNudgeEngine(drive_root)
    print("  is_due:", nudge.is_due())
    analysis = nudge.analyze_recent()
    print("  failed_skills:", analysis["failed_skills"])
    print("  best_reusable_task:", analysis["best_reusable_task"])

    print("=== 4. GEPA evolution of the seeded failing skill ===")
    from ouroboros.skill_loader import discover_skills
    from ouroboros.skill_evolution.genetic_evolution import SkillEvolver

    skills = discover_skills(drive_root)
    records = SkillEvolver(drive_root, llm_client=llm).evolve_candidates(skills, stats)
    for rec in records:
        print("  record:", json.dumps(rec, ensure_ascii=False)[:300])
    nudge.record(analysis)

    print("=== 4.5 auto-rollback (evolved version failed re-review) ===")
    # Deterministic scenario: simulate an accepted evolution whose re-review
    # came back blockers. The backup (FULL pre-overwrite package, marker
    # included) + a historical CLEAN verdict bound to the backup hash let the
    # rollback also restore executability (A1: verdict-for-hash index).
    from ouroboros.skill_loader import compute_content_hash
    from ouroboros.skill_evolution.pipeline import rollback_failed_evolutions
    from ouroboros.skill_review_history import review_history_path

    live = drive_root / "skills" / "self" / "live-demo-skill"
    stamp = "20260903T000000"
    backup = drive_root / "skills" / "self" / f"live-demo-skill.replaced-{stamp}"
    shutil.copytree(live, backup)  # full pre-overwrite copy (SKILL.md + scripts + marker)
    old_hash = compute_content_hash(backup)
    review_state = drive_root / "state" / "skills" / "live-demo-skill"
    with review_history_path(drive_root, "live-demo-skill").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-09-02T00:00:00Z", "status": "clean",
                             "content_hash": old_hash,
                             "reviewer_models": ["reviewer-one"]}) + "\n")
    # "evolve" the live package (mutation marker), then a reviewer fails it
    (live / "scripts" / "main.py").write_text("print('evolved version')\n", encoding="utf-8")
    (live / "SKILL.md").write_text(
        (live / "SKILL.md").read_text(encoding="utf-8").replace("version: '1.0'", "version: '1.1'"),
        encoding="utf-8")
    (review_state / "review.json").write_text(json.dumps({
        "status": "blockers",
        "content_hash": compute_content_hash(live),
        "findings": [{"item": "network-egress", "verdict": "FAIL"}],
        "timestamp": "2026-09-03T02:00:00Z",
    }), encoding="utf-8")
    rollback_records = rollback_failed_evolutions(drive_root)
    print("  rollback records:", [json.dumps(r, ensure_ascii=False)[:220] for r in rollback_records])
    print("  restored main.py:", (live / "scripts" / "main.py").read_text(encoding="utf-8").strip())
    restored_review = json.loads((review_state / "review.json").read_text(encoding="utf-8"))
    print("  restored review.json:", {k: restored_review.get(k) for k in ("status", "content_hash")})
    backups_left = list((drive_root / "skills" / "self").glob("*.replaced-*"))
    print("  backups remaining:", [p.name for p in backups_left])

    print("=== 5. post-checks ===")
    from ouroboros.contracts.skill_manifest import parse_skill_manifest_text
    from ouroboros.skill_loader import is_self_authored_skill_dir

    for skill in discover_skills(drive_root):
        text = (pathlib.Path(skill.skill_dir) / "SKILL.md").read_text(encoding="utf-8")
        manifest = parse_skill_manifest_text(text)
        print(f"  {skill.name}: version={manifest.version} "
              f"self_authored={skill.is_self_authored} source={skill.source} "
              f"provenance_ok={is_self_authored_skill_dir(skill.skill_dir, drive_root=drive_root)}")
    backups = list((drive_root / "skills" / "self").glob("*.replaced-*")) if (drive_root / "skills" / "self").exists() else []
    print("  pre-overwrite backups (accepted evolution only):", [p.name for p in backups])

    print("\n=== summary ===")
    print("  stats file:", (drive_root / "state" / "skill_stats.json").exists())
    print("  generation history:", (drive_root / "state" / "skill_generation_history.jsonl").exists())
    print("  evolution history:", (drive_root / "state" / "skill_evolution_history.jsonl").exists())
    print("  nudges:", (drive_root / "state" / "skill_nudges.jsonl").exists())
    assert (drive_root / "state" / "skill_stats.json").exists()
    assert (drive_root / "state" / "skill_generation_history.jsonl").exists()
    assert (drive_root / "state" / "skill_nudges.jsonl").exists()


if __name__ == "__main__":
    main()