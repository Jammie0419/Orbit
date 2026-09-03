"""Post-task orchestration for the skill-evolution envelope (Phase 3).

``run_skill_evolution_step`` is invoked from ``maybe_promote`` ONLY when
``OUROBOROS_SKILL_EVOLUTION`` is on. Order inside one post-task boundary:

0. auto-rollback: evolved versions whose fresh review verdict is ``blockers``
   (verdict hash == current payload hash) are restored from the pre-overwrite
   ``.replaced-`` backup, so a failed re-review never strands the skill;
1. rebuild the stats ledger (``logs/tools.jsonl`` -> ``state/skill_stats.json``);
2. generation for the CURRENT task (gates + dedupe are inside the generator);
3. if the nudge cadence is due: analyze recent work, evolve the failing
   self-authored skills (evolver's own gates bound candidates), and generate
   from the best reusable recent task when the current one did not qualify;
4. record the nudge.

Never raises — this runs inside the post-task daemon thread and any failure
must not disturb the promotion path.
"""

from __future__ import annotations

import json
import logging
import pathlib
import shutil
from typing import Any, Dict, List, Optional

from ouroboros.utils import append_jsonl, read_json_dict, utc_now_iso

log = logging.getLogger(__name__)

# Backups created by the evolver before an accepted overwrite follow the skill
# system's orphan convention ("<name>.replaced-<ts>/"), which discovery skips.
ROLLBACK_BACKUP_GLOB = "*.replaced-*"


def rollback_failed_evolutions(drive_root: Any) -> List[Dict[str, Any]]:
    """Auto-rollback of evolved versions whose re-review came back blockers.

    Trigger: a ``.replaced-`` evolution backup exists AND the live skill's
    ``review.json`` verdict is ``blockers`` AND its ``content_hash`` equals the
    CURRENT payload hash (i.e. the reviewer actually judged the evolved bytes —
    a stale verdict for an older hash never triggers).

    Restore: the live payload (SKILL.md + scripts) is replaced with the backup
    copy; the live self-authored markers are kept (they stay consistent with
    the state-side marker). The backup is consumed (deleted) and a
    ``action: rolled_back`` record is appended to the evolution history. After
    the restore the review verdict no longer matches the payload hash, so the
    skill needs its normal re-review/attestation before execution, exactly like
    any other content change. Returns the rollback records. Never raises.
    """
    drive_root = pathlib.Path(str(drive_root))
    self_root = drive_root / "skills" / "self"
    outcomes: List[Dict[str, Any]] = []
    if not self_root.is_dir():
        return outcomes
    for backup in sorted(self_root.glob(ROLLBACK_BACKUP_GLOB)):
        try:
            record = _maybe_rollback_one(drive_root, self_root, backup)
            if record:
                outcomes.append(record)
        except Exception:
            log.debug("skill evolution: rollback failed for %s", backup.name, exc_info=True)
    return outcomes


def _maybe_rollback_one(
    drive_root: pathlib.Path,
    self_root: pathlib.Path,
    backup: pathlib.Path,
) -> Optional[Dict[str, Any]]:
    marker_fragment = ".replaced-"
    idx = backup.name.find(marker_fragment)
    if idx <= 0:
        return None
    live_name = backup.name[:idx]
    live = self_root / live_name
    if not live.is_dir():
        return None  # orphan backup without a live skill: nothing to restore
    try:
        from ouroboros.skill_loader import compute_content_hash

        current_hash = compute_content_hash(live)
    except Exception:
        log.debug("skill evolution: hash compute failed for %s", live_name, exc_info=True)
        return None
    review = read_json_dict(drive_root / "state" / "skills" / live_name / "review.json") or {}
    if str(review.get("status") or "").lower() != "blockers":
        return None
    if str(review.get("content_hash") or "") != current_hash:
        return None  # the blockers verdict is not about the current payload
    restored_version = _read_package_version(backup)
    _restore_from_backup(live, backup)
    _sync_state_marker(drive_root, live)
    # A1 upgrade (GEPA 对照): when the restored bytes match a hash that
    # previously received an executable verdict (review.json or the append-only
    # history), re-apply it — the rollback then also restores executability,
    # like a git revert. No fresh review is needed because the hash binding is
    # satisfied by the historical verdict.
    restored_verdict = _restore_executable_verdict(drive_root, live_name, live)
    try:
        shutil.rmtree(backup)
    except Exception:
        log.debug("skill evolution: backup cleanup failed for %s", backup.name, exc_info=True)
    record = {
        "ts": utc_now_iso(),
        "action": "rolled_back",
        "skill": live_name,
        "reason": "review_blockers",
        "backup_dir": str(backup),
        "restored_version": restored_version,
        "restored_verdict": restored_verdict,
    }
    try:
        history_path = drive_root / "state" / "skill_evolution_history.jsonl"
        append_jsonl(history_path, record)
    except Exception:
        log.debug("skill evolution: rollback history write failed", exc_info=True)
    return record


def _restore_from_backup(live: pathlib.Path, backup: pathlib.Path) -> None:
    """Swap the live payload for the backup copy — INCLUDING the provenance
    marker, so the restored bytes are byte-identical to the pre-evolution
    package (the marker contributes to the content hash). The state-side
    marker is re-synced to the same payload afterwards."""
    for item in list(live.iterdir()):
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except OSError:
                pass
    for item in backup.iterdir():
        target = live / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _sync_state_marker(drive_root: pathlib.Path, live: pathlib.Path) -> None:
    """Re-write the state-side self-authored marker from the restored payload
    marker so both sides carry the identical task_id/created_at payload."""
    try:
        from ouroboros.utils import atomic_write_json, read_json_dict

        marker = read_json_dict(live / ".self_authored.json")
        if not isinstance(marker, dict):
            return
        state_marker = drive_root / "state" / "skills" / live.name / "self_authored.json"
        state_marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(state_marker, marker, trailing_newline=True)
    except Exception:
        log.debug("skill evolution: state marker sync failed", exc_info=True)


def _read_package_version(pkg: pathlib.Path) -> str:
    try:
        from ouroboros.contracts.skill_manifest import parse_skill_manifest_text

        manifest = pkg / "SKILL.md"
        if manifest.exists():
            return str(parse_skill_manifest_text(manifest.read_text(encoding="utf-8")).version or "")
    except Exception:
        pass
    return ""


def _restore_executable_verdict(
    drive_root: pathlib.Path,
    skill_name: str,
    live: pathlib.Path,
) -> str:
    """Re-apply a historical executable verdict bound to the restored hash.

    Returns the restored verdict status ("" when none was found). Never
    raises — a restore without a historical verdict stays stale and simply
    waits for its normal re-review, exactly like any other content change.
    """
    try:
        from ouroboros.skill_loader import SkillReviewState, compute_content_hash, save_review_state
        from ouroboros.skill_review_history import verdict_for_hash

        restored_hash = compute_content_hash(live)
        verdict = verdict_for_hash(drive_root, skill_name, restored_hash)
        if not verdict:
            return ""
        save_review_state(
            drive_root,
            skill_name,
            SkillReviewState(
                status=str(verdict.get("status") or ""),
                content_hash=str(verdict.get("content_hash") or ""),
                findings=list(verdict.get("findings") or []),
                reviewer_models=list(verdict.get("reviewer_models") or []),
                timestamp=str(verdict.get("timestamp") or ""),
                review_profile=str(verdict.get("review_profile") or ""),
            ),
        )
        return str(verdict.get("status") or "")
    except Exception:
        log.debug("skill evolution: verdict restore failed", exc_info=True)
        return ""


def run_skill_evolution_step(
    env: Any,
    task: Dict[str, Any],
    reflection_entry: Optional[Dict[str, Any]],
    llm_client: Any = None,
) -> None:
    """Skill-evolution work for one finished task. Never raises."""
    try:
        drive_root = pathlib.Path(str(env.drive_root))
        # Step 0: auto-rollback before anything else — a failed re-review of an
        # evolved version is restored from its .replaced- backup first, so the
        # stats/evolution pass below never reasons about a stranding payload.
        rollback_failed_evolutions(drive_root)

        from ouroboros.skill_evolution.stats import SkillStatsLedger

        stats = SkillStatsLedger(drive_root).aggregate()

        task_id = str(task.get("id") or "")
        goal = (
            str((reflection_entry or {}).get("goal") or "")
            or str(task.get("description") or "")
            or str(task.get("text") or "")
        )
        outcome_hint = (
            str((reflection_entry or {}).get("outcome") or "")
            or str(task.get("outcome") or "")
            or str((reflection_entry or {}).get("status") or "")
        )

        from ouroboros.evolution.trajectory_experience_learner import (
            TrajectoryExperienceLearner,
        )
        from ouroboros.skill_evolution.auto_generation import SkillAutoGenerator

        learner = TrajectoryExperienceLearner(drive_root)
        generator = SkillAutoGenerator(drive_root, llm_client=llm_client)
        steps = learner.load_task_steps(task_id) if task_id else []
        generator.maybe_generate_for_task(
            task_id, goal=goal, outcome_hint=outcome_hint, steps=steps)

        from ouroboros.skill_evolution.nudge import SkillNudgeEngine

        nudge = SkillNudgeEngine(drive_root)
        if not nudge.is_due():
            return
        analysis = nudge.analyze_recent()

        from ouroboros.skill_evolution.genetic_evolution import SkillEvolver
        from ouroboros.skill_loader import discover_skills

        skills = discover_skills(drive_root)
        SkillEvolver(drive_root, llm_client=llm_client).evolve_candidates(skills, stats)

        recent = analysis.get("best_reusable_task")
        if isinstance(recent, dict) and str(recent.get("task_id") or "") != task_id:
            recent_id = str(recent.get("task_id") or "")
            generator.maybe_generate_for_task(
                recent_id, goal="", outcome_hint="",
                steps=learner.load_task_steps(recent_id))

        nudge.record(analysis)
    except Exception:
        log.debug("skill evolution: post-task step failed", exc_info=True)