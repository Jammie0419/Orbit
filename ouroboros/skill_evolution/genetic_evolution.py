"""GEPA-style genetic evolution of failing self-authored skills (Phase 3).

Only skills that (a) carry the self-authored provenance marker, (b) logged at
least ``EVOLUTION_MIN_EXECUTIONS`` skill_exec runs, and (c) sit below
``EVOLUTION_MAX_SUCCESS_RATE`` are candidates — community/native skills are
never touched (paper core principle).

Per candidate:

1. rebuild the recent failure rows for that skill from ``logs/tools.jsonl``;
2. LLM failure analysis -> improvement suggestions;
3. build a population of variants (original + suggestion-driven mutations +
   random strategy mutations, capped at ``POPULATION_SIZE``);
4. LLM fitness per variant; original's baseline is the current success rate;
5. accept only when the best variant is fitter than the current rate AND
   structurally valid (render -> re-parse round trip). Acceptance bumps the
   manifest minor version, rewrites the package in place (markers re-stamped
   consistently), bumps ``evolution_version`` in the stats ledger and records
   ``state/skill_evolution_history.jsonl``. Rejection keeps the old package.

Every LLM call degrades to the safe path (keep the old version). Never raises.
"""

from __future__ import annotations

import json
import logging
import pathlib
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from ouroboros.contracts.skill_manifest import canonical_skill_name, parse_skill_manifest_text
from ouroboros.contracts.skill_manifest import SkillManifestError
from ouroboros.skill_evolution.auto_generation import (
    _default_main_model,
    _loose_json,
    recent_review_flags,
    render_skill_manifest,
    write_skill_package,
)
from ouroboros.skill_evolution.stats import EVOLUTION_MAX_SUCCESS_RATE, EVOLUTION_MIN_EXECUTIONS
from ouroboros.utils import append_jsonl, utc_now_iso

log = logging.getLogger(__name__)

# GEPA hyper-parameters (paper spec); population size is the operative bound.
POPULATION_SIZE = 5
MAX_CANDIDATES_PER_RUN = 2
MAX_SUGGESTIONS = 2
MAX_RECENT_ERRORS = 8
# After an auto-rollback (review blockers), a skill is not re-evolved for this
# window — prevents accept -> review-fail -> rollback -> re-accept flip-flops.
ROLLBACK_COOLDOWN_HOURS = 24

# B3 (multi-case evaluation): per-variant eval cases drawn from the skill's own
# execution history (success rubrics + failure rows), capped to bound LLM cost.
MAX_EVAL_CASES = 5
MAX_EVAL_SUCCESS_CASES = 2

# B4 (holdout calibration): when the evaluated fitness has been systematically
# optimistic vs the realized success rate, tighten the acceptance gate.
CALIBRATION_MIN_ACCEPTS = 3
CALIBRATION_OPTIMISM_THRESHOLD = 0.1
CALIBRATION_DISCOUNT = 0.9


def _variant_fingerprint(variant: Dict[str, Any]) -> str:
    """Content hash of a variant's written form (canonical keys only, so the
    internal ``_mutation`` marker never affects dedupe)."""
    try:
        import hashlib

        payload = {
            "name": str(variant.get("name") or ""),
            "description": str(variant.get("description") or ""),
            "type": str(variant.get("type") or ""),
            "runtime": str(variant.get("runtime") or ""),
            "when_to_use": str(variant.get("when_to_use") or ""),
            "body": str(variant.get("body") or ""),
            "scripts": [
                [str(s.get("name") or ""), str(s.get("code") or "")]
                for s in (variant.get("scripts") or [])
                if isinstance(s, dict)
            ],
        }
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return ""

EVOLUTION_HISTORY_REL = pathlib.Path("state") / "skill_evolution_history.jsonl"
TOOLS_LOG_REL = pathlib.Path("logs") / "tools.jsonl"

_CALL_TYPE_ANALYSIS = "skill_evolution_failure_analysis"
_CALL_TYPE_MUTATE = "skill_evolution_mutate"
_CALL_TYPE_FITNESS = "skill_evolution_fitness"
_REASONING = "medium"

_MUTATION_STRATEGIES = (
    "add_error_handling",
    "improve_description",
    "optimize_parameters",
)


def _bump_version(version: str) -> str:
    """Minor-version bump for "N" / "N.M" strings; fallback appends ".1"."""
    text = str(version or "").strip()
    match = re.match(r"^(\d+)(?:\.(\d+))?", text)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0) + 1
        return f"{major}.{minor}"
    return f"{text}.1" if text else "1.1"


class SkillEvolver:
    """Genetic (population -> fitness -> accept-or-keep) evolution of skills."""

    def __init__(self, drive_root: pathlib.Path, llm_client: Any = None):
        self.drive_root = pathlib.Path(drive_root)
        self.llm_client = llm_client
        self.history_path = self.drive_root / EVOLUTION_HISTORY_REL

    # -- gates ------------------------------------------------------------- #

    @staticmethod
    def is_evolution_candidate(skill: Any, stats: Dict[str, Any]) -> bool:
        """Paper gate: self-authored + >=10 executions + success rate < 0.8."""
        if not bool(getattr(skill, "is_self_authored", False)):
            return False
        count = int(stats.get("execution_count") or 0)
        if count < EVOLUTION_MIN_EXECUTIONS:
            return False
        rate = float(stats.get("success_rate") or 0.0)
        return rate < EVOLUTION_MAX_SUCCESS_RATE

    # -- entry ------------------------------------------------------------- #

    def evolve_candidates(
        self,
        skills: List[Any],
        stats: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Evolve up to ``MAX_CANDIDATES_PER_RUN`` failing self-authored
        skills (worst success rate first). Returns the history records."""
        candidates: List[Tuple[Any, Dict[str, Any]]] = []
        seen_names: set = set()
        for skill in skills:
            name = str(getattr(skill, "name", "") or "")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            entry = stats.get(name) or {}
            if not self.is_evolution_candidate(skill, entry):
                continue
            if self._recent_rollback(name):
                continue  # cooldown after an auto-rollback (flip-flop guard)
            candidates.append((skill, entry))
        candidates.sort(key=lambda pair: float(pair[1].get("success_rate") or 0.0))
        records: List[Dict[str, Any]] = []
        for skill, entry in candidates[:MAX_CANDIDATES_PER_RUN]:
            try:
                records.append(self._evolve_one(skill, entry))
            except Exception:
                log.debug("skill evolution: evolve failed for %s", skill.name, exc_info=True)
                records.append({
                    "ts": utc_now_iso(),
                    "skill": str(getattr(skill, "name", "") or ""),
                    "accepted": False,
                    "reason": "internal_error",
                })
        return records

    def _recent_rollback(self, skill_name: str) -> bool:
        """True when this skill was auto-rolled-back within the cooldown
        window (``action == "rolled_back"`` in the evolution history)."""
        from datetime import datetime, timezone

        horizon = 3600.0 * ROLLBACK_COOLDOWN_HOURS
        now = datetime.now(timezone.utc)
        for row in self._history_rows()[-50:]:
            if str(row.get("action") or "") != "rolled_back":
                continue
            if str(row.get("skill") or "") != skill_name:
                continue
            try:
                ts = str(row.get("ts") or "").replace("Z", "+00:00")
                when = datetime.fromisoformat(ts)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if (now - when).total_seconds() < horizon:
                return True
        return False

    def _history_rows(self) -> List[Dict[str, Any]]:
        """All evolution-history rows (bounded read; never raises)."""
        if not self.history_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with self.history_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except Exception:
            log.debug("skill evolution: history read failed", exc_info=True)
        return rows

    def _fitness_discount(self, skill_name: str, stats: Dict[str, Any]) -> float:
        """B4 calibration: when >= CALIBRATION_MIN_ACCEPTS accepted evolutions
        were evaluated, on average, >= 0.1 above the realized success rate, the
        gate is tightened (evaluated fitness is discounted). Data-driven, no
        prompt change. Returns 1.0 (no discount) by default."""
        accepts = [
            row for row in self._history_rows()
            if str(row.get("skill") or "") == skill_name and bool(row.get("accepted"))
        ]
        if len(accepts) < CALIBRATION_MIN_ACCEPTS:
            return 1.0
        evaluated = [
            float(row.get("new_success_rate") or 0.0)
            for row in accepts
            if row.get("new_success_rate") is not None
        ]
        if not evaluated:
            return 1.0
        realized = float(stats.get("success_rate") or 0.0) if stats else 0.0
        optimism = (sum(evaluated) / len(evaluated)) - realized
        return CALIBRATION_DISCOUNT if optimism >= CALIBRATION_OPTIMISM_THRESHOLD else 1.0

    # -- internals --------------------------------------------------------- #

    def _evolve_one(self, skill: Any, stats: Dict[str, Any]) -> Dict[str, Any]:
        original = self._load_skill_dict(skill)
        baseline = float(stats.get("success_rate") or 0.0)
        failures = self._recent_failures(str(skill.name))
        successes = self._recent_successes(str(skill.name))
        eval_cases = self._build_eval_cases(successes, failures)
        analysis = self._analyze_failures(original, failures)
        suggestions = [str(s) for s in (analysis.get("suggestions") or [])][:MAX_SUGGESTIONS]
        variants = self._build_population(original, suggestions, failures)
        fitness: Dict[int, float] = {0: baseline}  # original baseline = current rate
        for idx, variant in enumerate(variants[1:], start=1):
            fitness[idx] = self._evaluate(variant, original, stats, eval_cases)

        discount = self._fitness_discount(str(skill.name), stats)
        best_idx = max(range(len(variants)), key=lambda i: fitness.get(i, 0.0))
        best_fitness = fitness.get(best_idx, 0.0)
        scored = best_fitness * discount
        if best_idx == 0 or scored <= max(baseline, 0.5):
            return self._record(
                skill=original, stats=stats, accepted=False, fitness=best_fitness,
                mutation_type="none", reason="no_better_variant",
                fitness_discount=discount,
            )
        best = variants[best_idx]
        reason = self._validate_variant(original, best)
        if reason is not None:
            return self._record(
                skill=original, stats=stats, accepted=False, fitness=best_fitness,
                mutation_type=str(best.get("_mutation") or "unknown"),
                reason=reason,
            )
        mutation_type = str(best.get("_mutation") or "unknown")
        # Strip the internal marker before writing; carry the bumped version.
        best = {k: v for k, v in best.items() if not k.startswith("_")}
        best["version"] = _bump_version(str(original.get("version") or ""))
        # 兜底: keep the pre-overwrite package under the skill system's orphan
        # backup convention (".replaced-"), so a failed re-review can roll back.
        backup_dir = self._backup_skill(skill)
        write_skill_package(
            self.drive_root, best, task_id="",
            created_by_tool="skill_evolution",
        )
        new_version = _bump_ledger_version(self.drive_root, str(skill.name))
        return self._record(
            skill=original, stats=stats, accepted=True, fitness=best_fitness,
            mutation_type=mutation_type, reason="",
            version_to=best["version"], evolution_version=new_version,
            backup_dir=backup_dir, fitness_discount=discount,
        )

    # -- population -------------------------------------------------------- #

    def _load_skill_dict(self, skill: Any) -> Dict[str, Any]:
        """Rebuild the skill as a dict from its manifest + script files."""
        manifest = getattr(skill, "manifest", None)
        skill_dir = pathlib.Path(getattr(skill, "skill_dir", ""))
        body = ""
        try:
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            parsed = parse_skill_manifest_text(text)
            body = str(getattr(parsed, "body", "") or "")
        except Exception:
            text = ""
        manifests: List[Dict[str, str]] = []
        for entry in (getattr(manifest, "scripts", None) or []):
            sname = str(entry.get("name") or "") if isinstance(entry, dict) else str(entry or "")
            if not sname:
                continue
            code = ""
            try:
                code = (skill_dir / "scripts" / sname).read_text(encoding="utf-8")
            except Exception:
                pass
            manifests.append({"name": sname, "code": code})
        tags = []
        try:
            extras = getattr(manifest, "raw_extra", None) or {}
            tags = [str(t) for t in (extras.get("tags") or [])]
        except Exception:
            pass
        return {
            "name": canonical_skill_name(getattr(skill, "name", "") or ""),
            "description": str(getattr(manifest, "description", "") or ""),
            "version": str(getattr(manifest, "version", "") or "1.0"),
            "type": str(getattr(manifest, "type", "") or "script"),
            "runtime": str(getattr(manifest, "runtime", "") or "python"),
            "when_to_use": str(getattr(manifest, "when_to_use", "") or ""),
            "body": body,
            "tags": tags,
            "scripts": manifests,
        }

    def _recent_failures(self, skill_name: str) -> List[Dict[str, Any]]:
        try:
            path = self.drive_root / TOOLS_LOG_REL
            if not path.exists():
                return []
            out: List[Dict[str, Any]] = []
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if str(row.get("tool") or "") != "skill_exec":
                        continue
                    args = row.get("args")
                    name = args.get("skill") if isinstance(args, dict) else ""
                    if str(name or "") != skill_name:
                        continue
                    is_error = bool(row.get("is_error")) or str(
                        row.get("status") or "").strip().lower() in {"error", "timeout"}
                    if is_error:
                        out.append({
                            "status": str(row.get("status") or ""),
                            "result": str(row.get("result_preview") or "")[:200],
                        })
            return out[-MAX_RECENT_ERRORS:]
        except Exception:
            log.debug("skill evolution: failure scan failed", exc_info=True)
            return []

    def _backup_skill(self, skill: Any) -> str:
        """Copy the pre-overwrite package to ``<name>.replaced-<ts>/`` (the
        skill system's orphan backup convention: discovery skips such dirs).
        Returns the backup dir's str, or "" when the copy failed."""
        try:
            import shutil

            source = pathlib.Path(getattr(skill, "skill_dir", "") or "")
            if not source.is_dir():
                return ""
            stamp = utc_now_iso().replace(":", "").replace("-", "").replace("+", "T")[:15]
            target = source.parent / f"{source.name}.replaced-{stamp}"
            shutil.copytree(source, target, dirs_exist_ok=False)
            return str(target)
        except Exception:
            log.debug("skill evolution: pre-overwrite backup failed", exc_info=True)
            return ""

    def _analyze_failures(
        self,
        skill: Dict[str, Any],
        failures: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        placeholder = {"common_errors": [], "suggestions": []}
        if self.llm_client is None or not failures:
            return placeholder
        review_flags = recent_review_flags(self.drive_root, skill_name=str(skill.get("name") or ""))
        review_block = ""
        if review_flags:
            review_block = (
                "\n[Recent reviewer findings for THIS skill — the variant MUST avoid them]"
                "\n- " + "\n- ".join(review_flags) + "\n"
            )
        prompt = f"""Analyze why this skill keeps failing, then give concrete improvement suggestions.

[Skill]
{self._compact_skill(skill, max_chars=2500)}

[Recent failures (skill_exec error rows)]
{json.dumps(failures, ensure_ascii=False)[:2500]}
{review_block}
Return ONLY JSON:
{{"common_errors": ["..."], "suggestions": ["concrete changes to description/steps/error handling/parameters"]}}
"""
        data = self._call(prompt, _CALL_TYPE_ANALYSIS, max_tokens=2048)
        if not isinstance(data, dict):
            return placeholder
        return {
            "common_errors": [str(e) for e in (data.get("common_errors") or [])][:5],
            "suggestions": [str(s) for s in (data.get("suggestions") or [])][:MAX_SUGGESTIONS],
        }

    def _recent_successes(self, skill_name: str) -> List[Dict[str, Any]]:
        """Recent non-error skill_exec rows for this skill (eval-case rubrics)."""
        try:
            path = self.drive_root / TOOLS_LOG_REL
            if not path.exists():
                return []
            out: List[Dict[str, Any]] = []
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if str(row.get("tool") or "") != "skill_exec":
                        continue
                    args = row.get("args")
                    name = args.get("skill") if isinstance(args, dict) else ""
                    if str(name or "") != skill_name:
                        continue
                    is_error = bool(row.get("is_error")) or str(
                        row.get("status") or "").strip().lower() in {"error", "timeout"}
                    if not is_error:
                        out.append({
                            "status": str(row.get("status") or ""),
                            "result": str(row.get("result_preview") or "")[:200],
                        })
            return out[-MAX_EVAL_SUCCESS_CASES * 3:]
        except Exception:
            log.debug("skill evolution: success scan failed", exc_info=True)
            return []

    def _build_eval_cases(
        self,
        successes: List[Dict[str, Any]],
        failures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Mini eval set (B3, GEPA metric-over-valset analog): recent success
        rubrics + failure rows, bounded by MAX_EVAL_CASES."""
        cases: List[Dict[str, Any]] = [
            {"kind": "success", "result": str(row.get("result") or "")[:200]}
            for row in successes[-MAX_EVAL_SUCCESS_CASES:]
        ]
        cases.extend(
            {"kind": "failure", "result": str(row.get("result") or "")[:200]}
            for row in failures[- (MAX_EVAL_CASES - len(cases)):]
        )
        return cases[:MAX_EVAL_CASES]

    def _build_population(
        self,
        original: Dict[str, Any],
        suggestions: List[str],
        failures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        variants: List[Dict[str, Any]] = [dict(original)]
        seen: set = {_variant_fingerprint(original)}
        variant_types: List[str] = []
        for suggestion in suggestions:
            if len(variants) >= POPULATION_SIZE:
                break
            variant = self._mutate(original, prompt_kind="suggestion",
                                   suggestion=suggestion, failures=failures)
            if variant is not None and _variant_fingerprint(variant) not in seen:
                variants.append(variant)
                seen.add(_variant_fingerprint(variant))
                variant_types.append("suggested")
        strategies = list(_MUTATION_STRATEGIES)
        random.shuffle(strategies)
        for strategy in strategies:
            if len(variants) >= POPULATION_SIZE:
                break
            variant = self._mutate(original, prompt_kind="strategy",
                                   strategy=strategy, failures=failures)
            if variant is not None and _variant_fingerprint(variant) not in seen:
                variants.append(variant)
                seen.add(_variant_fingerprint(variant))
                variant_types.append(strategy)
        return variants

    def _mutate(
        self,
        original: Dict[str, Any],
        *,
        prompt_kind: str,
        suggestion: str = "",
        strategy: str = "",
        failures: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.llm_client is None:
            return None
        if prompt_kind == "suggestion":
            instruction = f"Apply this improvement suggestion:\n{suggestion}"
        elif strategy == "add_error_handling":
            instruction = ("Add robust error handling and clear failure messages "
                           "(skip gracefully on missing inputs, non-zero exits, timeouts).")
        elif strategy == "improve_description":
            instruction = ("Rewrite description/when_to_use to be clearer and more "
                           "precise about inputs, outputs and edge cases.")
        else:  # optimize_parameters
            instruction = ("Optimize the parameters (and their handling in the code) "
                           "for simpler, more robust invocation.")
        # B2 (GEPA reflection analog): the mutation prompt carries the skill's
        # OWN failing executions (real error text from the tool log), so the
        # rewrite targets the actual failure modes instead of generic advice.
        failure_block = ""
        if failures:
            failure_lines = [
                f"- status={str(row.get('status') or 'error')}: {str(row.get('result') or '')[:220]}"
                for row in failures[-6:]
            ]
            failure_block = (
                "\n[Recent failing executions of THIS skill — the rewrite MUST "
                "make the script handle these cases]"
                "\n" + "\n".join(failure_lines) + "\n"
            )
        prompt = f"""{instruction}

[Current skill]
{self._compact_skill(original, max_chars=3000)}
{failure_block}
Return the COMPLETE modified skill as ONLY JSON:
{{"name": ..., "description": ..., "type": ..., "runtime": ...,
  "when_to_use": ..., "parameters": {{...}}, "tags": [...],
  "scripts": [{{"name": "main.py", "code": "..."}}]}}
Keep the same name unless the change truly requires a new one. Scripts must be complete runnable code.
"""
        data = self._call(prompt, _CALL_TYPE_MUTATE, max_tokens=4096)
        if not data or not isinstance(data, dict):
            return None  # empty/absent proposal = failed mutation (no-op dedupe)
        data["_mutation"] = strategy or "suggested"
        return data

    def _evaluate(
        self,
        variant: Dict[str, Any],
        original: Dict[str, Any],
        stats: Dict[str, Any],
        eval_cases: List[Dict[str, Any]],
    ) -> float:
        if self.llm_client is None:
            return 0.0
        if not eval_cases:
            return 0.0
        review_flags = recent_review_flags(self.drive_root, skill_name=str(original.get("name") or ""))
        review_block = ""
        if review_flags:
            review_block = (
                "\n- Reviewer-flagged problems (a variant repeating any of these "
                "must score LOW): " + "; ".join(review_flags[:3])
            )
        case_lines = [
            f"{i + 1}. [{row.get('kind')}] {str(row.get('result') or '')[:200]}"
            for i, row in enumerate(eval_cases)
        ]
        prompt = f"""Score this skill variant against each execution case below (0.0-1.0 per case).

[Variant]
{self._compact_skill(variant, max_chars=3000)}

[Historical context]
- executions: {stats.get('execution_count', 0)}
- current success rate: {stats.get('success_rate', 0.0)}
{review_block}

[Cases (from this skill's real executions)]
{chr(10).join(case_lines)}

For every case return a per-case score: a variant that genuinely fixes a
failure case must score that case clearly above the current success rate;
repeating a reviewer-flagged problem must score LOW.

Return ONLY JSON: {{"case_scores": [0.0-1.0, ...]}}  (one per case, same order)
"""
        data = self._call(prompt, _CALL_TYPE_FITNESS, max_tokens=1024)
        if not isinstance(data, dict):
            return 0.0
        scores = data.get("case_scores")
        if isinstance(scores, list) and scores:
            try:
                numeric = [max(0.0, min(1.0, float(s))) for s in scores]
            except (TypeError, ValueError):
                numeric = []
            if numeric:
                return sum(numeric) / len(numeric)
        try:
            return max(0.0, min(1.0, float(data.get("fitness") or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def _validate_variant(self, original: Dict[str, Any], variant: Dict[str, Any]) -> Optional[str]:
        """Accept only structurally sound same-name variants (render -> parse)."""
        candidate = {k: v for k, v in variant.items() if not k.startswith("_")}
        candidate["name"] = str(original.get("name") or "")
        from ouroboros.skill_evolution.auto_generation import validate_generated_skill

        reason = validate_generated_skill(candidate)
        if reason is not None:
            return reason
        try:
            text = render_skill_manifest(candidate)
            parsed = parse_skill_manifest_text(text)
            if str(parsed.name or "") != str(original.get("name") or ""):
                return "name_mismatch"
        except SkillManifestError:
            return "manifest_unparseable"
        except Exception:
            return "manifest_render_failed"
        return None

    # -- records ----------------------------------------------------------- #

    def _record(
        self,
        *,
        skill: Dict[str, Any],
        stats: Dict[str, Any],
        accepted: bool,
        fitness: float,
        mutation_type: str,
        reason: str,
        version_to: str = "",
        evolution_version: int = 0,
        backup_dir: str = "",
        fitness_discount: float = 1.0,
    ) -> Dict[str, Any]:
        record = {
            "ts": utc_now_iso(),
            "skill": str(skill.get("name") or ""),
            "old_success_rate": float(stats.get("success_rate") or 0.0),
            "new_success_rate": round(fitness, 4),
            "mutation_type": str(mutation_type or ""),
            "accepted": bool(accepted),
            "reason": str(reason or ""),
            "version_from": str(skill.get("version") or ""),
            "version_to": str(version_to or ""),
            "evolution_version": int(evolution_version or 0),
            "backup_dir": str(backup_dir or ""),
            "fitness_discount": round(float(fitness_discount or 1.0), 4),
        }
        try:
            append_jsonl(self.history_path, record)
        except Exception:
            log.debug("skill evolution: history write failed", exc_info=True)
        return record

    # -- plumbing ---------------------------------------------------------- #

    def _call(self, prompt: str, call_type: str, *, max_tokens: int) -> Optional[Dict[str, Any]]:
        if self.llm_client is None:
            return None
        try:
            from ouroboros.llm_observability import chat_observed

            resp, _usage = chat_observed(
                self.llm_client,
                drive_root=self.drive_root,
                task_id="skill_evolution",
                call_type=call_type,
                messages=[{"role": "user", "content": prompt}],
                model=_default_main_model(),
                reasoning_effort=_REASONING,
                max_tokens=max_tokens,
            )
            content = (resp.get("content") or "") if isinstance(resp, dict) else ""
        except Exception:
            log.debug("skill evolution: %s LLM call failed", call_type, exc_info=True)
            return None
        return _loose_json(str(content))

    @staticmethod
    def _compact_skill(skill: Dict[str, Any], *, max_chars: int) -> str:
        compact = {
            "name": skill.get("name"),
            "description": skill.get("description"),
            "type": skill.get("type"),
            "runtime": skill.get("runtime"),
            "when_to_use": skill.get("when_to_use"),
            "parameters": skill.get("parameters"),
            "tags": skill.get("tags"),
            "scripts": [
                {"name": s.get("name"), "code": (s.get("code") or "")[:1200]}
                for s in (skill.get("scripts") or [])
            ],
        }
        text = json.dumps(compact, ensure_ascii=False)[:max_chars]
        return text


def _bump_ledger_version(drive_root: pathlib.Path, name: str) -> int:
    from ouroboros.skill_evolution.stats import SkillStatsLedger
    return SkillStatsLedger(drive_root).bump_evolution_version(name)