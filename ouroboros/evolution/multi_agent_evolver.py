"""Multi-agent evolution planner (PAPER_INTEGRATION_ANALYSIS 不足 4 + 7).

Worker-side planner: turns a promotion decision into a structured
``evolution_plan`` through three LLM stages:

* Analyzer — root causes from the just-finished task's trace + reflection;
* Researcher — approach / files / steps / risks for the top improvement;
* Verifier-advice — a pre-verification checklist, strengthened when cycle
  experience shows verification-stage failures historically.

Builder/Verifier EXECUTION stays on the existing gated evolution-task
machinery (reviewed commit + restart verify); this module only plans. The plan
rides on the promotion request and the supervisor injects it into the cycle
task text (``[EVOLUTION PLAN]`` section).

Every LLM call degrades to a placeholder so the promotion chain never breaks.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List, Optional

from ouroboros.evolution.trajectory_experience_learner import (
    _default_main_model as _main_model_slot,
    _loose_json,
)

log = logging.getLogger(__name__)

PLAN_SCHEMA_VERSION = 1

_VERIFY_FAILURE_KEYWORDS = (
    "verif", "test", "restart", "build fail", "验证", "测试", "重启",
)


class MultiAgentEvolver:
    """Planner producing the evolution plan for one promoted objective."""

    def __init__(self, drive_root: pathlib.Path, llm_client: Any = None):
        self.drive_root = pathlib.Path(drive_root)
        self.llm_client = llm_client

    # ------------------------------------------------------------------ #
    # Public entry
    # ------------------------------------------------------------------ #

    def run_evolution_cycle(
        self,
        steps: List[Dict[str, Any]],
        reflection_entry: Optional[Dict[str, Any]] = None,
        experience: Optional[Dict[str, Any]] = None,
        objective_hint: str = "",
        experience_digest: str = "",
    ) -> Dict[str, Any]:
        """Produce the structured plan for one cycle. Never raises.

        ``experience`` is the corresponding learned experience (may carry
        failure patterns that tune the verification stage).
        ``experience_digest`` is the prose strategy digest (success/failure
        patterns + critical-step tools from the accumulated depot) consumed by
        the Analyzer and Researcher prompts — this is the "失败回环" feedback
        path: plans are generated AWAY from historically failing patterns.
        """
        plan: Dict[str, Any] = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "objective": str(objective_hint or "").strip(),
            "root_causes": [],
            "approach": "",
            "files_to_modify": [],
            "implementation_steps": [],
            "risks": [],
            "verification_plan": [],
        }
        reflection = reflection_entry if isinstance(reflection_entry, dict) else {}

        # Stage 1: Analyzer — what went wrong / what to improve.
        analyzed = self._analyze(steps, reflection, objective_hint,
                                 experience_digest=experience_digest)
        objective = str(analyzed.get("objective") or "").strip() or plan["objective"]
        improvement = None
        improvements = analyzed.get("improvements") or []
        if improvements and isinstance(improvements[0], dict):
            improvement = improvements[0]
        elif not objective:
            objective = str((reflection.get("goal") or "") or "")[:120]
        plan["objective"] = objective or "Autonomously improve Ouroboros."
        plan["root_causes"] = [
            str(c) for c in (analyzed.get("root_causes") or [])
            if str(c or "").strip()
        ][:5]

        # Stage 2: Researcher — how to implement the improvement.
        if improvement:
            researched = self._research(improvement, reflection, objective,
                                        experience_digest=experience_digest)
            plan["approach"] = str(researched.get("approach") or "").strip()
            plan["files_to_modify"] = [
                str(f) for f in (researched.get("files_to_modify") or [])
                if str(f or "").strip()
            ][:10]
            plan["implementation_steps"] = [
                str(s) for s in (researched.get("implementation_steps") or [])
                if str(s or "").strip()
            ][:12]
            plan["risks"] = [
                str(r) for r in (researched.get("risks") or [])
                if str(r or "").strip()
            ][:8]

        # Stage 3: Verifier advice — the pre-verification checklist.
        plan["verification_plan"] = self._verification_advice(
            plan, experience
        )
        return plan

    # ------------------------------------------------------------------ #
    # Stages
    # ------------------------------------------------------------------ #

    def _analyze(
        self,
        steps: List[Dict[str, Any]],
        reflection: Dict[str, Any],
        objective_hint: str,
        *,
        experience_digest: str = "",
    ) -> Dict[str, Any]:
        step_lines = [
            f"- {s.get('tool')}: ok={not s.get('is_error')}"
            for s in steps[:40]
        ]
        marker_summary = ", ".join(
            str(m) for m in (reflection.get("key_markers") or [])[:8]
        ) or "(none)"
        goal = str(reflection.get("goal") or "")[:200] or "(none)"
        history_block = ""
        if str(experience_digest or "").strip():
            history_block = (
                "\n[HISTORICAL PATTERNS — how past task/evolution-cycle traces "
                "went; avoid the failure patterns and reuse the success ones]\n"
                + str(experience_digest)[:1200]
            )
        prompt = (
            "You are the ANALYZER stage of an evolution planner for Ouroboros "
            "(a self-improving agent). Analyze why the just-finished task "
            "warrants evolution and what the highest-value improvement is.\n\n"
            f"[TASK GOAL] {goal}\n"
            f"[MARKERS] {marker_summary}\n"
            f"[HINT OBJECTIVE (may be empty)] {objective_hint}\n"
            f"[TASK STEPS]\n" + "\n".join(step_lines)
            + history_block + "\n\n"
            "Return ONLY JSON: {\"root_causes\": [\"...\"], "
            "\"improvements\": [{\"objective\": \"one concrete, self-contained "
            "improvement to Ouroboros's own code/process\", \"rationale\": \"...\", "
            "\"estimated_impact\": \"low|medium|high\"}]}"
        )
        resp = self._call(prompt, call_type="evolution_plan_analyze", max_tokens=4096)
        if resp:
            return resp
        return {"root_causes": [], "improvements": []}

    def _research(
        self,
        improvement: Dict[str, Any],
        reflection: Dict[str, Any],
        objective: str,
        *,
        experience_digest: str = "",
    ) -> Dict[str, Any]:
        objective_text = str(
            improvement.get("objective") or objective or ""
        )[:300]
        history_block = ""
        if str(experience_digest or "").strip():
            history_block = (
                "\n[HISTORICAL PATTERNS — past traces failed in these ways; "
                "shape the approach to avoid them]\n"
                + str(experience_digest)[:1200]
            )
        prompt = (
            "You are the RESEARCHER stage of an evolution planner. Produce a "
            "concrete implementation plan for ONE improvement. Keep it small "
            "and targeted — Ouroboros evolution cycles absorb small wins; "
            "sprawling refactors die as no_op.\n\n"
            f"[OBJECTIVE] {objective_text}\n"
            f"[RATIONALE] {str(improvement.get('rationale') or '')[:300]}\n"
            + history_block + "\n\n"
            "Return ONLY JSON: {\"approach\": \"<2-4 sentences>\", "
            "\"files_to_modify\": [\"<repo-relative paths>\"], "
            "\"implementation_steps\": [\"<ordered, verifiable steps>\"], "
            "\"risks\": [\"<what could go wrong>\"]}"
        )
        resp = self._call(prompt, call_type="evolution_plan_research", max_tokens=4096)
        if resp:
            return resp
        return {"approach": "", "files_to_modify": [],
                "implementation_steps": [], "risks": []}

    def _verification_advice(
        self,
        plan: Dict[str, Any],
        experience: Optional[Dict[str, Any]],
    ) -> List[str]:
        failures = (experience or {}).get("failure_factors") if isinstance(experience, dict) else []
        verify_history_hint = ""
        if any(
            any(kw in str(f).lower() for kw in _VERIFY_FAILURE_KEYWORDS)
            for f in failures
        ):
            verify_history_hint = (
                "\nHistorical cycle experience shows verification-stage "
                "failures. Make the verification checklist EXPLICIT and "
                "mandatory: build + targeted tests + restart verify."
            )
        objective = str(plan.get("objective") or "")[:300]
        steps = "\n".join(f"- {s}" for s in (plan.get("implementation_steps") or [])[:10])
        prompt = (
            "You are the VERIFIER-ADVICE stage of an evolution planner. Produce "
            "the pre-verification checklist an evolution cycle must satisfy "
            "before its change is accepted (build, targeted tests, diff review, "
            "restart-safety).\n\n"
            f"[OBJECTIVE] {objective}\n"
            f"[PLANNED STEPS]\n{steps}\n" + verify_history_hint + "\n\n"
            "Return ONLY JSON: {\"verification_plan\": [\"<checklist items>\"]}"
        )
        resp = self._call(prompt, call_type="evolution_plan_verify", max_tokens=2048)
        if resp:
            items = resp.get("verification_plan") or []
            return [str(i) for i in items if str(i or "").strip()][:8]
        return []

    # ------------------------------------------------------------------ #
    # LLM plumbing
    # ------------------------------------------------------------------ #

    def _call(
        self,
        prompt: str,
        *,
        call_type: str,
        max_tokens: int,
    ) -> Optional[Dict[str, Any]]:
        if self.llm_client is None:
            return None
        try:
            from ouroboros.llm_observability import chat_observed

            resp, _usage = chat_observed(
                self.llm_client,
                drive_root=self.drive_root,
                task_id="evolution_plan",
                call_type=call_type,
                messages=[{"role": "user", "content": prompt}],
                model=_main_model_slot(),
                reasoning_effort="medium",
                max_tokens=max_tokens,
            )
            content = (resp.get("content") or "") if isinstance(resp, dict) else ""
            return _loose_json(str(content))
        except Exception:
            log.debug("evolution layer: planner LLM call %s failed", call_type, exc_info=True)
            return None


__all__ = ["MultiAgentEvolver"]