"""Evolution layer (PAPER_INTEGRATION_ANALYSIS 不足 4 + 5 + 7).

``trajectory_experience_learner`` (不足 5): trajectory-based experience learning
with step-level credit assignment over execution traces — BOTH ordinary task
traces (``kind="task"``, decision-time analysis of "what task patterns are worth
evolving") and evolution-cycle traces (``kind="cycle"``, methodology lessons
about "which stage of the cycle caused absorption/failure", consumed by later
cycle planning). Records live in ``state/evolution_experiences.jsonl`` and
``state/step_credits.jsonl``; a cursor (``state/evolution_consumed.json``) makes
cycle consumption idempotent.

``multi_agent_evolver`` (不足 4 + 7): the worker-side planner that turns a
promotion decision into a structured ``evolution_plan`` (Analyzer /
Researcher / Verifier-advice stages, all LLM calls routed through
``chat_observed``). The plan rides on the promotion request and is injected
into the cycle task text by the supervisor; Builder/Verifier execution stays on
the existing gated evolution-task machinery (reviewed commit + restart verify).

Both are gated by the single ``OUROBOROS_MULTI_AGENT_EVOLVER`` switch
(default off). Disabled means the V4 post-task pipeline behaves exactly as
before — nothing in this package runs and no prompt/request field changes.
"""