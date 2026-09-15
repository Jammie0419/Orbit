"""Trajectory-based experience learning with step-level credit assignment
(PAPER_INTEGRATION_ANALYSIS 不足 5).

Two trace sources, one scoring core:

* ``kind="task"`` — the just-finished ordinary task's tool trace (decision-time
  analysis: which task step patterns correlate with promotable work).
* ``kind="cycle"`` — a completed evolution cycle's tool trace (methodology
  lessons: which stage — analysis / build / verification — caused absorption
  or failure; this is what the paper calls "关键步骤识别").

Step rows come from ``logs/tools.jsonl`` (ts / tool / args / result_preview /
is_error / status); no observability-blob dependency. Every LLM call degrades
silently to a structured placeholder so the promotion chain can never break.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from ouroboros.utils import append_jsonl, utc_now_iso

log = logging.getLogger(__name__)

EXPERIENCES_REL = pathlib.Path("state") / "evolution_experiences.jsonl"
STEP_CREDITS_REL = pathlib.Path("state") / "step_credits.jsonl"
CONSUMED_CURSOR_REL = pathlib.Path("state") / "evolution_consumed.json"
TOOLS_LOG_REL = pathlib.Path("logs") / "tools.jsonl"
CHECKPOINTS_REL = pathlib.Path("state") / "evolution_checkpoints.jsonl"

# Credit formula (document 原案): base + success - error + fast.
# The document's token-thrifty term is NOT implemented: `logs/tools.jsonl` rows
# carry no per-step token count (ts / tool / task_id / args / result_preview /
# is_error / status / refs), so the term could never be awarded — it was dead
# weight that still read as if it scored something.
CREDIT_BASE = 0.5
CREDIT_SUCCESS = 0.2
CREDIT_ERROR = -0.3
CREDIT_FAST = 0.1  # step latency known and < 1000ms (see load_task_steps)

# Stage keywords that mark "verification-stage" failure signals in a cycle's
# extracted experience — the planner strengthens verification_plan on these.
_VERIFY_FAILURE_KEYWORDS = (
    "verif", "test", "restart", "build fail", "验证", "测试", "重启",
)

_OBJECTIVE_TYPE_KEYWORDS = {
    "bug_fix": ("bug", "fix", "error", "fail", "报错", "修复"),
    "performance": ("performance", "speed", "optimize", "性能", "优化", "加速"),
    "capability": ("feature", "capability", "add", "新功能", "能力"),
    "refactor": ("refactor", "cleanup", "improve", "重构", "清理"),
}


def _loose_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _parse_ts(value: Any) -> Optional[float]:
    """Epoch seconds for a tool-log ``ts``, or None when unparseable.

    Rows are written by ``utc_now_iso`` (``...+00:00``); a naive or malformed value
    yields None so the caller leaves the derived field absent instead of inventing
    a timing that was never observed.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def _truncate_repr(value: Any, limit: int) -> str:
    """Stable string form of a log field (args/result), bounded for prompts."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text[:limit]


def _default_main_model() -> str:
    """Explicit main-slot model (same resolution as the promotion chooser).

    The evolution layer must NEVER pass an empty model to ``llm.chat`` — an
    empty string resolves to provider ``openrouter`` with an empty model name
    and fails at request time. Single-model discipline (spec: mimo-v2.5 only,
    no external mix) means every layer call uses the main slot.
    """
    import os

    from ouroboros.config import SETTINGS_DEFAULTS

    return str(
        os.environ.get("OUROBOROS_MODEL", "") or SETTINGS_DEFAULTS["OUROBOROS_MODEL"]
    ).strip()


class TrajectoryExperienceLearner:
    """Step-level credit assignment + LLM experience extraction over traces.

    All methods are failure-tolerant: a missing trace, a broken file, or a
    failed LLM call yields an empty/placeholder result, never an exception.
    """

    def __init__(self, drive_root: pathlib.Path, llm_client: Any = None):
        self.drive_root = pathlib.Path(drive_root)
        self.llm_client = llm_client
        self.experiences_path = self.drive_root / EXPERIENCES_REL
        self.credits_path = self.drive_root / STEP_CREDITS_REL
        self.cursor_path = self.drive_root / CONSUMED_CURSOR_REL

    # ------------------------------------------------------------------ #
    # Trace loading
    # ------------------------------------------------------------------ #

    def load_task_steps(self, task_id: str) -> List[Dict[str, Any]]:
        """Rebuild the step list for ``task_id`` from the tool log.

        Matches rows where ``task_id`` equals the target (root task; evolution
        cycles are root tasks too). Unknown/missing fields are left absent so
        the credit formula skips only what is truly unknown.

        ``duration_ms`` is derived from the gap between consecutive rows of THIS
        task: it is the step's wall latency (the model turn that produced the call
        plus the call itself), which is the only timing signal the tool log
        carries — rows have no per-step duration field. It is an upper bound on the
        call's own execution time, and the first step has none. Without this the
        fast-credit term in ``assign_credits`` could never fire.
        """
        task_id = str(task_id or "").strip()
        if not task_id:
            return []
        path = self.drive_root / TOOLS_LOG_REL
        if not path.exists():
            return []
        steps: List[Dict[str, Any]] = []
        prev_ts: Optional[float] = None
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if str(row.get("task_id") or "") != task_id:
                        continue
                    if not str(row.get("tool") or "").strip():
                        continue
                    is_error = bool(row.get("is_error")) or str(
                        row.get("status") or ""
                    ).strip().lower() in {"error", "timeout"}
                    args = row.get("args")
                    step = {
                        "step_id": len(steps),
                        "tool": str(row.get("tool") or ""),
                        "is_error": is_error,
                        "status": str(row.get("status") or ""),
                        "result_preview": str(row.get("result_preview") or "")[:200],
                        # Backward-compatible passthrough (skill auto-generation
                        # consumes call arguments; secrets were scrubbed at write
                        # time by sanitize_tool_args_for_log).
                        "args": _truncate_repr(args, 400),
                    }
                    ts_value = _parse_ts(row.get("ts"))
                    if ts_value is None:
                        # An unreadable stamp leaves the NEXT step unmeasurable too:
                        # spanning it would attribute a multi-step interval to one
                        # step and can deny a fast step its credit.
                        prev_ts = None
                    else:
                        if prev_ts is not None:
                            gap_ms = (ts_value - prev_ts) * 1000.0
                            if gap_ms >= 0:
                                step["duration_ms"] = gap_ms
                        prev_ts = ts_value
                    steps.append(step)
        except Exception:
            log.debug("evolution layer: tools.jsonl read failed", exc_info=True)
            return []
        return steps

    # ------------------------------------------------------------------ #
    # Core scoring (shared by both trace kinds)
    # ------------------------------------------------------------------ #

    def assign_credits(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Per-step credit scores, normalized to sum 1.0 (document formula).

        Only signals the trace actually carries are rewarded/penalized:
        success +0.2, error -0.3, fast (<1000ms) +0.1. See ``load_task_steps`` for
        how ``duration_ms`` is derived and why no token term exists.
        """
        if not steps:
            return []
        credits = []
        for step in steps:
            credit = CREDIT_BASE
            if step.get("is_error"):
                credit += CREDIT_ERROR
            else:
                credit += CREDIT_SUCCESS
            duration = step.get("duration_ms")
            if isinstance(duration, (int, float)) and 0 <= duration < 1000:
                credit += CREDIT_FAST
            credits.append({
                "step_id": step.get("step_id", 0),
                "tool": str(step.get("tool") or ""),
                "credit": max(0.0, min(1.0, credit)),
            })
        total = sum(c["credit"] for c in credits)
        if total > 0:
            for c in credits:
                c["credit"] = round(c["credit"] / total, 4)
        return credits

    def identify_critical_steps(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Credit top-3 (the steps that carried the trace) + credit-lowest-2
        (the steps that dragged it down).

        Each returned step carries an explicit ``role`` ("key"/"drag") because
        consumers previously had to re-derive it by membership in the *unsorted*
        credit list — which mislabelled every step's role, since the top-3 is
        picked from the credit-sorted order. The two sets never overlap (a short
        trace yields fewer drags rather than duplicating a key step).
        """
        if not credits:
            return []
        ordered = sorted(credits, key=lambda c: c["credit"], reverse=True)
        n = len(ordered)
        key_n = min(3, n)
        drag_n = min(2, max(0, n - key_n))
        critical = [{**c, "role": "key"} for c in ordered[:key_n]]
        if drag_n:
            critical.extend({**c, "role": "drag"} for c in ordered[-drag_n:])
        return critical

    @staticmethod
    def classify_objective(objective: str) -> str:
        text = str(objective or "").lower()
        for kind, keywords in _OBJECTIVE_TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return kind
        return "other"

    @staticmethod
    def canonical_objective_type(label: Any, objective: str = "") -> str:
        """Coerce an arbitrary objective_type label into the classifier vocabulary.

        Stored rows MUST use the same vocabulary ``classify_objective`` produces:
        the similarity query re-derives the type from the objective TEXT, so a
        free-form label from the extraction LLM ("bugfix", "Optimization") would
        never match and the strategy digest would stay ``standard`` forever.
        Unknown labels fall back to the keyword classifier — the text is the
        ground truth, the model's label is only a hint.
        """
        raw = str(label or "").strip().lower()
        raw = raw.replace("-", "_").replace(" ", "_")
        aliases = {
            "bugfix": "bug_fix", "bug_fixing": "bug_fix", "bug": "bug_fix",
            "fix": "bug_fix", "fixes": "bug_fix", "error_fix": "bug_fix",
            "perf": "performance", "optimization": "performance",
            "optimisation": "performance", "speed": "performance", "perf_optimization": "performance",
            "feature": "capability", "features": "capability",
            "new_feature": "capability", "new_capability": "capability",
            "refactoring": "refactor", "cleanup": "refactor",
            "clean_up": "refactor", "improvement": "refactor",
        }
        if raw in _OBJECTIVE_TYPE_KEYWORDS:
            return raw
        if raw in aliases:
            return aliases[raw]
        if raw == "other":
            return "other"
        return TrajectoryExperienceLearner.classify_objective(objective)

    # ------------------------------------------------------------------ #
    # LLM experience extraction (degrades to placeholders on failure)
    # ------------------------------------------------------------------ #

    def _extract_overall(
        self,
        objective: str,
        outcome: str,
        steps: List[Dict[str, Any]],
        kind: str,
    ) -> Dict[str, Any]:
        """LLM extraction of the overall experience for one trace.

        ``kind`` is named in the prompt so the model analyzes the right object
        (a task trace vs an evolution-cycle trace) — this is the A/B 双轨 point.
        """
        placeholder = {
            "objective_type": self.classify_objective(objective),
            "objective_complexity": "unknown",
            "success_factors": [],
            "failure_factors": [],
            "reusable_pattern": "",
        }
        if self.llm_client is None or not steps:
            return placeholder
        step_lines = [
            f"- {s.get('tool')}: ok={not s.get('is_error')}"
            for s in steps[:40]
        ]
        subject = (
            "an EVOLUTION CYCLE's execution trace (this cycle's own steps — "
            "which stage, analysis/build/verification, contributed or failed)"
            if kind == "cycle" else
            "an ordinary task's execution trace (which steps made this task "
            "worth evolving)"
        )
        prompt = (
            f"Analyze {subject}.\n\n"
            f"[OUTCOME] {outcome}\n"
            f"[OBJECTIVE] {objective}\n"
            f"[STEPS]\n" + "\n".join(step_lines) + "\n\n"
            "Return ONLY JSON: {\"objective_type\": \"bug_fix|performance|capability|refactor|other\", "
            "\"objective_complexity\": \"low|medium|high\", "
            "\"success_factors\": [\"...\"], \"failure_factors\": [\"...\"], "
            "\"reusable_pattern\": \"...\"}"
        )
        try:
            from ouroboros.llm_observability import chat_observed

            llm = self.llm_client
            resp, _usage = chat_observed(
                llm,
                drive_root=self.drive_root,
                task_id="evolution_experience",
                call_type="evolution_experience_extraction",
                messages=[{"role": "user", "content": prompt}],
                model=_default_main_model(),
                reasoning_effort="low",
                max_tokens=2048,
            )
            obj = _loose_json((resp.get("content") or "") if isinstance(resp, dict) else "")
            if obj:
                # The model frequently ignores the requested enum (returning
                # "bugfix", "Bug Fix", "optimization", ...). Store the canonical
                # vocabulary so the similarity query — which re-derives the type
                # from the objective text — can actually match this row.
                obj["objective_type"] = self.canonical_objective_type(
                    obj.get("objective_type"), objective)
                obj.setdefault("success_factors", [])
                obj.setdefault("failure_factors", [])
                obj.setdefault("reusable_pattern", "")
                return obj
        except Exception:
            log.debug("evolution layer: experience extraction LLM failed", exc_info=True)
        return placeholder

    # ------------------------------------------------------------------ #
    # Storage + queries
    # ------------------------------------------------------------------ #

    def _task_experience_recorded(self, task_id: str) -> bool:
        """Has this task already contributed a Track-A experience row?

        Track B advances a cursor, so re-reading its ledger is idempotent; Track A
        had no such guard, and re-processing a record (a resume, or a retry after a
        partial failure) appended the same task's credits again. Every duplicate
        skewed the tool/success statistics that ``suggest_evolution_strategy``
        aggregates, and inflated the ledger count the runner reports.

        Fails open (False) on a read error: a duplicate row is better than
        silently dropping an experience.
        """
        tid = str(task_id or "").strip()
        if not tid:
            return False
        try:
            if not self.experiences_path.exists():
                return False
            with self.experiences_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if (
                        isinstance(row, dict)
                        and str(row.get("kind") or "") == "task"
                        and str(row.get("task_id") or "") == tid
                    ):
                        return True
        except Exception:
            log.debug("evolution layer: task experience dedup read failed", exc_info=True)
        return False

    def store_experience(
        self,
        *,
        kind: str,
        task_id: str,
        objective: str,
        outcome: str,
        steps: List[Dict[str, Any]],
        overall: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if kind == "task" and self._task_experience_recorded(task_id):
            log.debug(
                "evolution layer: task experience already recorded (task=%s) — skipping",
                task_id,
            )
            return None
        credits = self.assign_credits(steps)
        critical = self.identify_critical_steps(credits)
        record = {
            "ts": utc_now_iso(),
            "kind": kind,
            "task_id": str(task_id or ""),
            "objective": str(objective or ""),
            "outcome": str(outcome or ""),
            "overall": overall,
            "steps": [
                {
                    "step_id": s.get("step_id", i),
                    "tool": str(s.get("tool") or ""),
                    "is_error": bool(s.get("is_error")),
                }
                for i, s in enumerate(steps[:40])
            ],
            "credits": credits,
            "critical_steps": critical,
        }
        try:
            # append_jsonl returns False (it does not raise) when all write
            # retries fail — without this check the caller could not tell a lost
            # experience from a landed one, and Track B would advance its cursor
            # past the failed row and never retry it.
            if not append_jsonl(self.experiences_path, record):
                log.warning(
                    "evolution layer: experience append failed — record dropped "
                    "(kind=%s task=%s)", kind, task_id,
                )
                return None
            for c in critical:
                # Derived ledger: best-effort, never fails the experience itself.
                append_jsonl(self.credits_path, {
                    "ts": utc_now_iso(),
                    "kind": kind,
                    "task_id": str(task_id or ""),
                    "step_id": c.get("step_id", 0),
                    "tool": str(c.get("tool") or ""),
                    "credit": c.get("credit", 0.0),
                    "role": str(c.get("role") or "drag"),
                })
            return record
        except Exception:
            log.debug("evolution layer: experience store failed", exc_info=True)
            return None

    def load_experiences(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.experiences_path.exists():
            return []
        out = []
        try:
            with self.experiences_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if kind is None or str(rec.get("kind") or "") == kind:
                        out.append(rec)
        except Exception:
            log.debug("evolution layer: experiences read failed", exc_info=True)
        return out

    def query_similar_objectives(
        self,
        objective: str,
        *,
        kind: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        obj_type = self.classify_objective(objective)
        similar = [
            exp for exp in self.load_experiences(kind=kind)
            if self.canonical_objective_type(
                (exp.get("overall") or {}).get("objective_type"),
                str(exp.get("objective") or ""),
            ) == obj_type
        ]
        similar.sort(
            key=lambda exp: (
                1.0 if str(exp.get("outcome") or "").lower() == "absorbed" else 0.0
            ),
            reverse=True,
        )
        return similar[:top_k]

    def suggest_evolution_strategy(
        self,
        objective: str,
        *,
        kind: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Strategy digest for the promotion decision / planner.

        ``kind=None`` (default) draws on BOTH tracks: ``kind="task"`` (Track A —
        the per-task traces) and ``kind="cycle"`` (Track B — completed evolution
        cycles). Track A rows are stored under ``kind="task"``, so the old
        default of ``"cycle"`` silently discarded every per-task experience and
        pinned the digest at ``standard`` regardless of accumulated history.

        No similar history -> ``standard``; otherwise ``optimized`` with the
        accumulated success/failure patterns and the tools that carried
        critical steps across similar traces.
        """
        similar = self.query_similar_objectives(objective, kind=kind, top_k=top_k)
        if not similar:
            return {"strategy": "standard", "confidence": 0.5}
        success_patterns = [
            str((exp.get("overall") or {}).get("reusable_pattern") or "")
            for exp in similar
            if str(exp.get("outcome") or "").lower() == "absorbed"
        ]
        failure_patterns = []
        for exp in similar:
            ffs = (exp.get("overall") or {}).get("failure_factors") or []
            for ff in ffs:
                t = str(ff).strip()
                if t and t not in failure_patterns:
                    failure_patterns.append(t)
        tool_counts: Dict[str, int] = {}
        for exp in similar:
            for step in exp.get("critical_steps") or []:
                tool = str(step.get("tool") or "").strip()
                if tool:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1
        recommended = sorted(tool_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        absorbed = sum(1 for exp in similar
                       if str(exp.get("outcome") or "").lower() == "absorbed")
        return {
            "strategy": "optimized",
            "success_patterns": success_patterns[:5],
            "failure_patterns": failure_patterns[:5],
            "recommended_tools": [t for t, _ in recommended],
            "confidence": round(absorbed / len(similar), 3),
        }

    # ------------------------------------------------------------------ #
    # A entry: current task trace (decision-time analysis)
    # ------------------------------------------------------------------ #

    def extract_task_experience(
        self,
        task_id: str,
        reflection_entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        steps = self.load_task_steps(task_id)
        if not steps:
            return None
        objective = str((reflection_entry or {}).get("goal") or "") or task_id
        outcome = "task"
        overall = self._extract_overall(objective, outcome, steps, kind="task")
        return self.store_experience(
            kind="task", task_id=task_id,
            objective=objective, outcome=outcome,
            steps=steps, overall=overall,
        )

    # ------------------------------------------------------------------ #
    # B entry: completed evolution cycles (cursor-consumed, idempotent)
    # ------------------------------------------------------------------ #

    def _read_cursor(self) -> int:
        try:
            data = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            return int(data.get("last_seq") or 0)
        except Exception:
            return 0

    def _write_cursor(self, last_seq: int) -> None:
        try:
            from ouroboros.utils import atomic_write_json

            atomic_write_json(self.cursor_path, {"last_seq": last_seq})
        except Exception:
            log.debug("evolution layer: cursor write failed", exc_info=True)

    def _pending_cycle_rows(self) -> List[Tuple[int, Dict[str, Any]]]:
        if not (self.drive_root / CHECKPOINTS_REL).exists():
            return []
        cursor = self._read_cursor()
        rows: List[Tuple[int, Dict[str, Any]]] = []
        try:
            with (self.drive_root / CHECKPOINTS_REL).open(encoding="utf-8") as fh:
                for seq, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not str(row.get("kind") or "").startswith("cycle_outcome"):
                        # Legacy task-done rows (pre schema alignment): top-level
                        # kind/cycle_outcome absent — recover the outcome from the
                        # embedded transaction so no_op cycles still reach Track B
                        # instead of being silently skipped forever.
                        tx = row.get("transaction")
                        if isinstance(tx, str):
                            try:
                                tx = json.loads(tx)
                            except Exception:
                                tx = {}
                        legacy = str((tx or {}).get("cycle_outcome") or "") \
                            if isinstance(tx, dict) else ""
                        if legacy not in {"absorbed", "abandoned", "no_op"}:
                            continue
                        row = {**row, "kind": "cycle_outcome", "cycle_outcome": legacy}
                    if str(row.get("cycle_outcome") or "") not in {
                            "absorbed", "abandoned", "no_op"}:
                        continue
                    if seq > cursor:
                        rows.append((seq, row))
        except Exception:
            log.debug("evolution layer: checkpoint scan failed", exc_info=True)
        return rows

    def consume_pending_cycles(self, _limit: int = 5) -> int:
        """Credit-assign the traces of finished evolution cycles that were not
        yet analyzed (idempotent via the cursor). Returns how many were stored.

        ``_limit`` bounds per-call LLM spend; a high-traffic drive never burns
        the whole budget in one task's post-task pass.
        """
        pending = self._pending_cycle_rows()
        if not pending:
            return 0
        stored = 0
        for seq, row in pending[:_limit]:
            cycle_task_id = str(row.get("task_id") or "").strip()
            steps = self.load_task_steps(cycle_task_id) if cycle_task_id else []
            objective = str(row.get("campaign_objective") or "")
            outcome = str(row.get("cycle_outcome") or "no_op")
            # Only run LLM extraction when there is an actual trace to analyze.
            # An empty trace still STORES a record — it carries the cycle's
            # objective + outcome, which is the signal the strategy digest reads
            # ("objectives of this class got absorbed / kept failing").
            overall = {}
            if steps:
                overall = self._extract_overall(objective, outcome, steps, kind="cycle")
            record = self.store_experience(
                kind="cycle", task_id=cycle_task_id,
                objective=objective, outcome=outcome,
                steps=steps, overall=overall,
            )
            # A failed write must NOT advance the cursor: the cursor never
            # rewinds, so the cycle's experience would be lost permanently.
            if record is None:
                log.warning(
                    "evolution layer: cycle experience NOT stored (seq=%s task=%s) — "
                    "cursor held so the next pass retries",
                    seq, cycle_task_id,
                )
                break
            stored += 1
            self._write_cursor(seq)
        return stored


__all__ = ["TrajectoryExperienceLearner"]