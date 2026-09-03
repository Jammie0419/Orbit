"""Hermes-Style Skill Evolution (PAPER_INTEGRATION_ANALYSIS Phase 3).

Four capabilities behind one opt-in switch (``OUROBOROS_SKILL_EVOLUTION``,
default OFF):

* ``stats`` — per-skill execution ledger aggregated from ``logs/tools.jsonl``
  (the GEPA gate and the router's quality weighting read this).
* ``auto_generation`` — turn a successful, self-repairing task trace into a
  self-authored skill package under the data-plane ``skills/self/`` tree.
* ``genetic_evolution`` — GEPA-style genetic improvement of failing
  self-authored skills (population -> LLM fitness -> accept only when better).
* ``nudge`` — task-boundary review cadence that decides when periodic
  evolution work is due.
* ``pipeline`` — the post-task orchestration entry used by ``maybe_promote``.

Safety contract (same as the rest of the skill system): generated/evolved
skills land as ``pending`` review + ``disabled``; only the existing
review/owner-attestation/auto-grant gates can make them executable. The repo's
tracked ``skills/`` seed tree is never written.
"""