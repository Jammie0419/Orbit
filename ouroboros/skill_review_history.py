"""Read/write helpers for the existing append-only Skill Review history."""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

from ouroboros.platform_layer import acquire_exclusive_file_lock, release_exclusive_file_lock
from ouroboros.tools.review_helpers import format_obligation_excerpt
from ouroboros.utils import append_jsonl, iter_jsonl_objects, jsonl_append_lock_path, utc_now_iso

log = logging.getLogger(__name__)


def review_history_path(drive_root: pathlib.Path, skill_name: str) -> pathlib.Path:
    return drive_root / "state" / "skills" / skill_name / "review_history.jsonl"


def finding_signature(findings: List[Dict[str, Any]]) -> List[str]:
    return sorted({
        f"{finding.get('item')}:{finding.get('verdict')}:{finding.get('severity')}"
        for finding in findings
        if isinstance(finding, dict) and str(finding.get("verdict") or "").upper() == "FAIL"
    })


def extract_fail_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, dict) or str(finding.get("verdict") or "").upper() != "FAIL":
            continue
        entry = {
            "item": str(finding.get("item") or "?"),
            "severity": str(finding.get("severity") or ""),
            "reason_excerpt": format_obligation_excerpt(str(finding.get("reason") or "")),
        }
        if finding.get("model"):
            entry["model"] = str(finding["model"])
        out.append(entry)
    return out


def _ordinal(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def normalize_history(entries: List[Dict[str, Any]], skill_name: str) -> List[Dict[str, Any]]:
    """Add read-time ordinals to legacy rows without rewriting the audit log."""
    group_rounds: Dict[str, int] = {}
    snapshot_attempts: Dict[tuple[str, str], int] = {}
    last_hash: Dict[str, str] = {}
    out: List[Dict[str, Any]] = []
    for source in entries:
        entry = dict(source)
        group_id = str(entry.get("group_id") or f"manual:{skill_name}")
        content_hash = str(entry.get("content_hash") or "")
        review_round = max(
            group_rounds.get(group_id, 0) + 1,
            _ordinal(entry.get("review_round")),
        )
        group_rounds[group_id] = review_round
        attempt_key = (group_id, content_hash)
        snapshot_attempt = max(
            snapshot_attempts.get(attempt_key, 0) + 1,
            _ordinal(entry.get("snapshot_attempt")),
        )
        snapshot_attempts[attempt_key] = snapshot_attempt
        revised = bool(last_hash.get(group_id) and last_hash[group_id] != content_hash)
        if content_hash:
            last_hash[group_id] = content_hash
        entry.update(
            group_id=group_id,
            review_round=review_round,
            snapshot_attempt=snapshot_attempt,
            snapshot_revised=bool(entry.get("snapshot_revised", revised)),
        )
        out.append(entry)
    return out


def load_history(
    drive_root: pathlib.Path,
    skill_name: str,
    limit: int = 3,
    *,
    group_id: str = "",
) -> List[Dict[str, Any]]:
    try:
        entries = normalize_history(
            list(iter_jsonl_objects(review_history_path(drive_root, skill_name))),
            skill_name,
        )
    except OSError:
        return []
    if group_id:
        entries = [entry for entry in entries if entry.get("group_id") == group_id]
    return entries[-limit:] if limit > 0 else entries


def allocate_ordinals(
    drive_root: pathlib.Path,
    skill_name: str,
    group_id: str,
    content_hash: str,
) -> tuple[int, int, bool]:
    history = load_history(drive_root, skill_name, limit=0, group_id=group_id)
    review_round = max(
        (_ordinal(row.get("review_round")) for row in history), default=0,
    ) + 1
    snapshot_attempt = max(
        (
            _ordinal(row.get("snapshot_attempt"))
            for row in history
            if str(row.get("content_hash") or "") == content_hash
        ),
        default=0,
    ) + 1
    previous_hash = str(history[-1].get("content_hash") or "") if history else ""
    return review_round, snapshot_attempt, bool(previous_hash and previous_hash != content_hash)


def count_attempts(
    drive_root: pathlib.Path,
    skill_name: str,
    content_hash: str,
    *,
    group_id: str = "",
) -> int:
    history = load_history(drive_root, skill_name, limit=0, group_id=group_id)
    return sum(1 for row in history if str(row.get("content_hash") or "") == content_hash)


def verdict_for_hash(
    drive_root: pathlib.Path,
    skill_name: str,
    content_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return the most recent EXECUTABLE review verdict bound to a payload hash.

    Consulted after a content restore (e.g. the skill-evolution auto-rollback):
    when the restored bytes match a hash that previously received a
    ``clean``/``warnings`` verdict, that verdict can be re-applied without a
    fresh review — the hash binding is satisfied. ``review.json`` (current
    verdict) is checked first; otherwise the append-only review history is
    scanned for the latest executable row with the same ``content_hash``.

    Returns ``{"status", "content_hash", "findings", "timestamp",
    "reviewer_models", "review_profile"}`` or None. Never raises.
    """
    from ouroboros.skill_review_status import STATUS_CLEAN, STATUS_WARNINGS, normalize_skill_review_status
    from ouroboros.utils import read_json_dict

    executable = {STATUS_CLEAN, STATUS_WARNINGS}
    target = str(content_hash or "").strip()
    if not target:
        return None
    drive_root = pathlib.Path(drive_root)
    safe_name = str(skill_name or "")
    if not safe_name:
        return None

    def _shape(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        status = str(row.get("status") or "").lower()
        try:
            status = normalize_skill_review_status(status)
        except Exception:
            status = status.lower()
        if status not in executable:
            return None
        return {
            "status": status,
            "content_hash": target,
            "findings": row.get("findings") or row.get("fail_findings") or [],
            "timestamp": str(row.get("timestamp") or row.get("ts") or ""),
            "reviewer_models": row.get("reviewer_models") or [],
            "review_profile": str(row.get("review_profile") or ""),
        }

    # 1. The current verdict, when it already covers this hash.
    current = read_json_dict(drive_root / "state" / "skills" / safe_name / "review.json") or {}
    if str(current.get("content_hash") or "") == target:
        shaped = _shape(current)
        if shaped is not None:
            return shaped
    # 2. The append-only history (latest executable row for this hash).
    best: Optional[Dict[str, Any]] = None
    try:
        for row in iter_jsonl_objects(review_history_path(drive_root, safe_name)):
            if str(row.get("content_hash") or "") != target:
                continue
            shaped = _shape(row)
            if shaped is not None:
                best = shaped  # rows are appended in order; keep the latest
    except Exception:
        log.debug("skill review history scan failed", exc_info=True)
    return best


def append_history(
    drive_root: pathlib.Path,
    skill_name: str,
    *,
    status: str,
    content_hash: str,
    findings: List[Dict[str, Any]],
    raw_actor_records: Optional[List[Dict[str, Any]]] = None,
    single_reviewer_no_diversity: bool = False,
) -> None:
    try:
        payload: Dict[str, Any] = {
            "ts": utc_now_iso(),
            "status": status,
            "content_hash": content_hash,
            "failure_signature": finding_signature(findings),
            "fail_findings": extract_fail_findings(findings),
        }
        if single_reviewer_no_diversity:
            payload["single_reviewer_no_diversity"] = True
        if raw_actor_records:
            payload["raw_actor_records"] = list(raw_actor_records)
        append_jsonl(review_history_path(drive_root, skill_name), payload)
    except Exception:
        log.debug("skill review history append failed", exc_info=True)


def append_history_once(
    drive_root: pathlib.Path,
    skill_name: str,
    payload: Dict[str, Any],
) -> bool:
    """Append one lifecycle terminal row, idempotently keyed by ``job_id``."""
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return False
    path = review_history_path(drive_root, skill_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = jsonl_append_lock_path(path)
    lock_fd = acquire_exclusive_file_lock(lock_path, timeout_sec=2.0, stale_sec=10.0)
    if lock_fd is None:
        return False
    try:
        try:
            if any(str(row.get("job_id") or "") == job_id for row in iter_jsonl_objects(path)):
                return True
            data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            return True
        except OSError:
            log.warning("skill review terminal history append failed for %s", skill_name, exc_info=True)
            return False
    finally:
        release_exclusive_file_lock(lock_path, lock_fd)
