# LEAP: Operator-Complete Self-Evolution for Agentic Systems

## Abstract

Self-evolution — an agent improving itself from its own execution experience — is widely seen as a path toward stronger agents. Systems that rewrite their own scaffolding have shown that agents *can* modify their own code, but whether such loops can keep running depends on an unanswered question: **whether the evolution operators are complete**. We diagnose three structural gaps in existing loops — feedback black boxes (no attribution for what failed where), blind variation (no guidance or division of labor), and history loss (validated improvements vanish with the session) — and trace them to an incomplete operator set. We propose LEAP (Long-term Evolution with Attribution and Propagation), a complete loop of five operators over an importance-ordered memory substrate: **expression** routes inherited assets into the task at hand; **attribution** converts task and evolution trajectories into fitness evidence; **directed variation** produces candidate improvements through divided multi-agent labor; **selection** gates every change behind a referee branch and a graded review chain; **heredity** fixes survivors as absorbable commits and versioned skills. We instantiate LEAP on a self-evolving coding agent, build a 130-task evolution corpus with full provenance, test the necessity of attribution and heredity with a four-arm ablation, accept the whole-frame gain on Terminal-Bench (89 tasks × pass@5, 890 trials), and measure cross-generational gain by pre/post-mutation comparison on a fixed task set. Removing attribution reduces evolution to repeated trial and error; removing heredity zeroes accumulation — the operators are jointly necessary, and completeness is the line between "a few steps" and sustained operation.

## 1 Introduction

### 1.1 From capability to sustainability

An LLM agent factors into a fixed model $\theta$ and an evolvable scaffold $\Sigma$: prompts, memory, tools, and ultimately code. Self-evolution that holds $\theta$ fixed and updates $\Sigma$ is the more robust surface — text, data, and code can be inspected and rolled back, while a corrupted weight matrix cannot. Within this surface, the deepest intervention is the **full-scaffolding update**: the agent reads its own source, proposes patches, and lands them through validators. Because the improver is embedded in the improved, this paradigm is the most direct route to recursive self-improvement, and the most active frontier (Sec. 2). This paper accepts that paradigm and asks the next question: **how can such a loop keep running**. A loop that cannot sustain itself is easy to recognize: budget burned on near-identical rewrites, the same failure recurring under new names, and every session starting from zero memory of what was tried and why it failed.

### 1.2 Three structural gaps

Existing systems share three gaps. **Feedback black boxes.** Candidate selection rests on whole trajectories or scalar scores — STOP picks by a utility scalar [1], Darwin/Huxley–Gödel Machine by benchmark scores [2,3]. They see *which version is better* but not *which step, tool, or decision failed*; selection pressure is near-random. **Blind variation.** Candidates come from a single agent on a single path, unguided by task shape or history, with planning, research, implementation, and verification fused into one shot. Even archive-based systems diversify across paths while each update within a path stays monolithic. **History loss.** Validated improvements vanish with the session: archives record *who scored high*, not *why anything succeeded or failed at which step*; behavioral know-how has no cross-session carrier at all. The gaps reinforce each other — no attribution, hence blind direction; blind variation, hence wasted budget; wasted trials, hence nothing worth keeping — and together explain why existing loops walk a few steps but never sustain. Sec. 3.1 restates them as operator incompleteness.

### 1.3 LEAP in brief

We propose **LEAP (Long-term Evolution with Attribution and Propagation)**, a loop of five operators on an importance-ordered memory substrate. **Attribution** replays each task trajectory and each evolution cycle itself into step-level credit, producing fitness evidence. **Directed variation** turns evidence into real code patches through divided agent labor in isolated clones. **Selection** stages every patch on a referee branch and admits it only through a fail-closed graded gate chain. **Heredity** fixes survivors in two genotypes — absorbable commits (what the agent *can do*) and versioned skills (how it *does things well*). **Expression** routes inherited assets back into task execution. Any missing operator degrades the loop predictably (Table 3-1), which is also the theory behind our ablations.

We instantiate LEAP on a self-evolving coding agent [4] — a real, runnable system with tools and a task loop, whose native evolution is a single reviewed-commit point. It belongs to research line (i) of Sec. 2.2 in review-hardened form: single lineage, no archive population, no external evaluator search; its runtime loop is short (reflection → candidates → structured go/no-go decision → supervised campaign), and its gaps — no step-level evidence for decisions, no behavioral carrier for survivors, no task-side scheduling for assets — are exactly LEAP's starting point.

**Contributions.** (1) The LEAP framework: five operators plus a memory substrate, with the degradation signature of each missing operator. (2) Each of the three gaps meets its countering mechanism. Dual-track attribution closes the feedback black box — task replay covers task outcomes, evolution self-replay covers evolution's own, so selection acts on evidence. Smart routing plus multi-role campaigns jointly cure blind direction — routing sets the execution view by task classification, campaigns implement directed variation and selection together through multi-agent divided labor, isolated clones, and four-gate merged admission. Dual-genotype heredity plus a three-layer memory substrate jointly cure history loss — commits record what changed, lineages record what was learned; memory orders by importance, sessions stay retrievable, stable context stays reusable. (3) A reusable evaluation package: a 130-record provenance-complete evolution corpus, a four-arm operator ablation, pre/post-mutation skill comparison, and cross-domain acceptance on Terminal-Bench — all evidence auditable from persisted ledgers.

## 2 Related Work

Self-evolution splits by *what changes*: model weights vs. scaffolding [5]. Weight updates pay directly but resist tracing and rollback once polluted; scaffolding edits, carried by text, data, and code, are inspectable and reversible — the steadier surface given a fixed model, and the reason this paper never touches $\theta$. Within scaffolding, component-level work polishes one part; system-level work rewrites the whole program.

### 2.1 Component-level improvements: prompts, memory, tools

**Prompt optimization** iterates system prompts under fixed weights, in four flavors by feedback shape. Scalar methods rewrite to scores: OPRO[6] uses the model itself as the optimizer over past prompt–score trajectories. Self-critique methods let the model play critic: Self-Refine [7] has one model serve as generator, critic, and reviser over multiple rounds; Reflexion [8] verbalizes feedback into reflections kept in episodic memory for later trials, changing decisions without touching weights. Population methods treat prompts as genes: EvoPrompt [9] uses a language model as the evolutionary operator over discrete prompts; Promptbreeder [10] co-evolves the mutation prompts themselves for two-level self-reference; GEPA [11] reflects on trajectories into high-level rules merged along a Pareto frontier, beating RL at far higher sample efficiency; DEEVO [12] settles candidates by structured debate with Elo selection where no explicit numeric objective exists. Textual-gradient methods simulate backpropagation in language: TextGrad [13] casts prompt updates as differentiable steps. The direction proves language-carried iteration works, but stays inside prompt text and mostly on single-optimizer, single-path search.

**Memory and long-term learning** treat experience as the evolvable asset. Generative Agents [14] store full histories in language, distill higher-level reflections over time, and retrieve dynamically for planning. MemoryBank [15] forgets and reinforces along a forgetting curve by elapsed time and relative importance. ExpeL [16] gathers experience and extracts language knowledge without parameter updates, recalling insights and precedents at inference. Mem0 [17] extracts, consolidates, and retrieves salient dialogue content in a scalable architecture, with a graph variant over memory relations. A-MEM [18] files each memory as a structured note (context, keywords, tags) in Zettelkasten fashion, links it to history, and lets memories evolve as new ones arrive. FORGE [19] evolves memory with no weight updates by population broadcast: an inner reflection loop converts failed trajectories into rules, examples, or both, while an outer loop propagates the best instance's memory across stages. The shared dilemma is write density — too dense amplifies retrieval noise, too sparse sacrifices long-term capacity. Our substrate orders and evicts all experience by importance and extends the memorized object from task history to the history of evolution itself: attribution records, campaign ledgers, and skill lineages coexist under one importance semantics, with session history full-text indexed, reflections semantically recallable across sessions, and stable context cached.

**Tools and skills** widen the action space. Voyager [20] maximizes exploration by automatic curriculum, banks complex behaviors in a growing executable library, and improves programs with feedback-fused iterative prompting, reusing the library in new worlds. SkillWeaver [21] discovers skills on new websites, drills them, and distills lightweight plug-and-play interfaces transferable from strong to weak agents. PyVision [22] has multimodal models generate, execute, and refine Python tools per task, moving from tool use to tool invention. SkillOpt [23] trains the skill as a frozen agent's external state through bounded edits gated on held-out validation. Skill work is closest to ours; we add three missing properties — **heritability** (content hash plus version lineage), **reviewability** (unreviewed skills cannot execute), and **evolvability** (reflection-driven mutation under real execution pressure, Sec. 3.5). Component work proves each part *can* improve, but leaves coordination, direction, and cross-component sedimentation to system-level answers — the starting point of full-scaffolding updates.

### 2.2 Full-scaffolding updates: agents whose substrate is their own code

The deepest intervention takes the agent's program as the evolvable object. Two signatures mark it. **Self-reference** — the improver is embedded in the current scaffold: the present agent reads its code, proposes and applies patches, improver and improved co-evolving. Formally, with $\langle \Sigma_t \rangle$ the serializable encoding, one update is $\langle \tilde{\Sigma}_{t+1} \rangle = \mathrm{exec}(\langle \Sigma_t \rangle; S_t)$ with isolated execution and trajectory-derived signal $S_t$. **Validator gating** — candidates land as patches admitted only through tests, regressions, and safety checks; failures roll back wholesale. Unbounded in principle, all existing systems run bounded and verifiable — inside human-set goals, benchmarks, and safety protocols. By how candidates arise, what selects them, and what the population looks like, the literature forms four lines; *when* evolution fires — interleaved with execution or batched between tasks — is an orthogonal timing axis:

**(i) Single-lineage self-rewriting.** STOP [1] starts from a seed improver: query the model repeatedly under a utility function, keep the best, then turn the improved improver on itself, verifying gains on downstream tasks. Gödel Agent [26] drops fixed routines and optimizers entirely, letting the model rewrite its own logic and behavior from high-level objective prompts alone. Contribution: the self-referential loop is feasible; cost: one path, one agent, one shot — no division of labor, no history.

**(ii) Archival open-ended evolution.** Darwin Gödel Machine [2] samples agents from an archive, generates novel variants with a foundation model, and empirically validates each change on coding benchmarks, growing a diverse variant tree. Huxley–Gödel Machine [3] observes benchmark scores misalign with self-improvement potential and instead estimates potential from descendant performance aggregates to guide tree search. Hyperagents [33] packs task and meta agents into one editable program so the modification procedure itself is editable — improvement extends from task behavior to the improvement-generating mechanism. Contribution: population structure and diversity; limit: each within-path update stays monolithic, and archives record *who scored high*, not *why anything failed*.

**(iii) Evaluator-driven program evolution.** AlphaEvolve [28] edits code directly through model pipelines under continuous evaluator feedback, with discoveries in datacenter scheduling, circuit simplification, and open science. ShinkaEvolve [29] balances exploration and exploitation in parent sampling with novelty rejection and bandit-based model selection, finding a new circle-packing optimum within hundreds of samples. Meta-Harness [34] searches harness code itself through an agentic proposer that reads all prior candidates' source, scores, and traces from the filesystem. Contribution: selection anchored on external evaluators; limit: feedback is mostly whole-trajectory scalars that never localize failure to a step or stage.

**(iv) Design-space search and symbolic optimization.** ADAS [30] defines agents as code and has a meta agent program ever-better agents in a Turing-complete design space over a growing archive. GPTSwarm [31] unifies prompting tricks as computation graphs — nodes process data or query models, edges carry flow — optimized separately at node prompts and edge connectivity. Agent Symbolic Learning [32] treats prompts, tools, and their stacking as a symbolic network's learnable weights, optimized autonomously from data. Contribution: an explicit, optimizable "what to change" space; limit: search stays at design level with no reusable carrier for the evolution process itself.

On timing, all four lines can run batched or interleaved, and the interleaved form now has three independent witnesses: Live-SWE-Agent [27] rewriting its own scaffold while solving real software tasks; Continual Harness [34] alternating acting and self-refinement inside single embodied long-horizon runs without episode resets; Prime Agent [35] productizing the same mechanism as an open-source RLM harness with a persistent REPL and cross-trajectory memory for long-horizon evaluation and coding workflows. LEAP in this paper belongs to the same online form — evolution driven directly by task-completion events, with the Ch. 4 corpus replay only re-feeding already-occurred trajectories in fixed order for fair comparison. The online form demands more of attribution latency and selection safety. SIA [37] adds an external observation on the whole spectrum: scaffold edits concentrate on parsing, retries, and dispatch hygiene, rarely delivering domain reasoning no prompt could elicit — the manners of working, not its substance.

These lines jointly affirm that agents can rewrite their own code, contributing closed-loop selection (STOP, Gödel Agent), archival structure (DGM, Huxley, Hyperagents), evaluator-anchored selection (AlphaEvolve, ShinkaEvolve, Meta-Harness), explicit design optimization (ADAS, GPTSwarm, symbolic learning), and three independent witnesses for the online form (Live-SWE-Agent, Continual Harness, Prime Agent). Yet all carry the Sec. 1.2 gaps: **feedback black boxes** — whole-trajectory signals drive the next rewrite without localizing failing steps or stages; **blind direction** — candidate generation lacks task-shape and historical guidance, each within-path update still single-agent and one-shot; **history loss** — the evolution process itself (candidates, outcomes, lineage) is never preserved as replayable, retrievable experience. LEAP's mechanisms target exactly these (Ch. 3).

### 2.3 Positioning

Component work proves parts *can* improve; full-scaffolding systems prove the *whole program* can change — but neither answers systematically *where to change, whether the change is right, and how it persists*. LEAP answers with attribution, selection, and heredity plus memory: attribution supplies selection pressure, directed variation plus selection implements and gates each change, heredity and expression transmit and redeem capability, memory sustains continuity. The five operators span component and system levels as one loop, not a stack. Concretely, LEAP takes full-scaffolding updates as its substrate: selected products are written back into the agent as absorbable commits and skill lineages, upgrading the self-referential loop from one-shot rewriting into directed, attributed, heritable evolution.

## 3 The LEAP Framework

### 3.1 Principle: completing the operator set

**Thesis.** Sec. 2.2 systems prove agents *can* modify their code; what they cannot do is keep the modification process *sustainable*. Evolutionary biology reduces sustainable evolution to cooperating operators: variation produces candidates, differential fitness selects, heredity transmits survivors [38]. Ported to agents, two more links are needed. First, selection's precondition: biology assumes measurable fitness, but agent feedback arrives as whole-trajectory scalars with no evidential basis — attribution converts task and evolution history into fitness evidence so selection has something to act on. Second, heredity's redemption path: inherited capability without task-side invocation sleeps through execution — expression schedules inherited assets back into tasks. The complete loop is thus five operators: attribution produces evidence for selection, variation generates candidates under evidence, selection gates each change, heredity fixes survivors, expression redeems them. From this angle, full-scaffolding systems evolve a **population of one** — no redundant individuals to sacrifice (a polluted mainline has no retreat), no gene pool to inherit (every generation cold-starts from the same code). What decides sustainability is therefore not population size but **operator completeness**: existing systems hold rudiments of variation (candidate generation) and selection (validator gating) but systematically lack attribution (selection pressure without evidence — the black box), cross-generational heredity (validated improvements never assetized — cleared each session), and task-side expression (no invocation path for inherited capability; never exposed before, since no heritable asset ever existed — heredity and expression must be added as a pair).

**Framework.** LEAP organizes self-evolution as an operator-complete loop. With agent state $A_t = (\theta, \Sigma_t)$ ($\theta$ fixed and never updated here; $\Sigma_t$ the evolvable scaffold) and trajectory $\tau_t$, round $t$ over task $t$, scaffold $\Sigma_t$, memory $M_t$, campaign ledger $H_t$, and skill population $S_t$ composes as:

$$
\begin{aligned}
(T_t, R_t, \pi_t) &= \mathrm{Express}(t; M_t, S_t), \\
\tau_t &= \mathrm{Execute}(t; T_t, R_t, \pi_t), \\
E_t &= \mathrm{Attribute}(\tau_t; H_t), \\
\Delta_t &= \mathrm{Variate}(E_t; M_t), \\
s_t &= \mathrm{Select}(\Delta_t) \in \{0, 1\}, \\
(\Sigma_{t+1}, S_{t+1}) &= \mathrm{Inherit}(\Sigma_t, S_t; \Delta_t, s_t, \tau_t), \\
M_{t+1} &= \mathrm{MemWrite}(M_t; E_t, \Delta_t, s_t).
\end{aligned}
$$

Here $T_t$ is the tool envelope (Sec. 3.2), $R_t$ the recommended skill Top-K (Sec. 3.2), and $\pi_t$ the branch execution policy; $\tau_t$ the execution trace; $E_t$ fitness evidence; $\Delta_t$ the candidate patch; $s_t$ the selection bit, $1$ iff every gate of Sec. 3.4 passes; $\mathrm{Inherit}$ covers both code-level absorption and behavioral skill evolution:

- **Expression**: one task classification sequentially drives longitudinal adaptation (execution-strategy configuration) and lateral routing (tool-envelope construction, skill recommendation), deciding which inherited assets fire this round — the analogue of environmentally regulated gene expression (Sec. 3.2);
- **Attribution**: step- and stage-level credit from the task trace and the evolution ledger $H_t$, yielding the round's fitness signal — which behavior to reinforce, which to retire (Sec. 3.3);
- **Directed variation**: candidate generation guided by evidence and $M_t$. Variation is not random perturbation: direction is explicitly chosen over attribution summaries and the campaign ledger, implementation divided across roles (Sec. 3.4);
- **Selection**: candidate $\Delta_t$ staged on an isolated referee branch, merged to mainline only through preflight, scope, and hash-bound review gates ($s_t = 1$ iff all pass); failures roll back and are journaled as next-round attribution input (Sec. 3.4);
- **Heredity**: survivors fixed in two genotypes — **code-level** (absorbed commits: revertible, traceable) and **behavioral** (skill packages with version lineage, cross-session) (Sec. 3.5).

The memory substrate $M$ stores all evidence, decisions, and assets importance-ordered, with session indexing and semantic recall for long-range retrieval (Sec. 3.6). The genotypes divide labor: code heredity changes what the agent *can do*, behavioral heredity how it *does things well* — the former the only form prior full-scaffolding systems cover, the latter LEAP's answer to history loss. Algorithm 1 gives the per-record loop.

**Algorithm 1 (LEAP loop, one corpus record).**

```
Input: task t; scaffold Σ; memory M; ledger H; skill population S
 1: (envelope, TopK, policy) ← Express(t, M, S)   ▷ expression
 2: τ ← Execute(t; envelope, TopK, policy)        ▷ execution
 3: E ← Attribute(τ, H)                           ▷ attribution
 4: M ← MemWrite(M, E)
 5: if PromoteDue(every-N) and LLMDecide(reflection, backlog, capability, closed, experience):
 6:     plan ← Plan(E, H)                         ▷ divided planning
 7:     Δ    ← Implement(plan; isolated clone)    ▷ directed variation
 8:     if Preflight(Δ) and ReviewChain(hash(Δ)): ▷ selection
 9:         Absorb(Δ → H, Σ)                      ▷ code-level heredity
10:     else: Record(H; abandoned / no_op)        ▷ journaled failure
11: S ← SkillEvolve(τ, Stats(S))                  ▷ behavioral heredity
12: M ← MemWrite(M, Δ, S, outcome)                ▷ sedimentation
```

**Operator completeness.** Table 3-1 maps each of the five operators and the memory substrate to its degradation signature — both the operator form of Sec. 2.2's gaps and the theory behind the Sec. 4.5 ablations. The gaps↔operators mapping is not one-to-one: blind direction is repaired jointly by attribution (evidence) with expression/variation (guidance and labor); history loss jointly by heredity and memory — which is why the ablations remove attribution and heredity (Sec. 4.2).

| Missing item | Degraded loop | How tested |
|---|---|---|
| Attribution | randomized selection pressure, feedback stays black-box | Sec. 4.5 ablation (V3 vs V1) |
| Directed variation (labor) | back to single-agent single-path guessing | Process evidence (Sec. 4.3 rates and costs) |
| Selection | unverified changes pollute mainline, self-reference loses its safety floor | Sec. 4.6 blocked case plus gate block rates |
| Heredity | validated gains cleared each session | Sec. 4.5 ablation (V3 vs V2) |
| Expression | inherited assets sleep, never redeemed as capability | Process evidence (Table 4-2, row 4) |
| Memory | loop loses cross-session continuity | Process evidence (Table 4-2, row 4) |

Memory is the substrate, not a sixth operator: operators act on state, memory records everything — but its absence breaks the loop all the same. The rest of this chapter follows loop time: expression (3.2), attribution (3.3), variation + selection (3.4, one pipeline, two operators), heredity (3.5), substrate (3.6).

### 3.2 Expression: task-shape adaptation and genetic-asset scheduling

Each round must answer: **in what shape should this task run, and which inherited assets fire**. LEAP's expression operator is implemented by smart routing in a **single-classification dual-path scheduling** architecture: a purely rule-based classifier resolves task $t$ down a signal priority chain — explicit type hints, then workspace facts (a nonempty workspace means coding), then memory-mode signals, then bilingual keyword scan; total miss yields (simple, no-signal). Zero LLM cost, deterministic and reproducible. The classification result sequentially drives two scheduling decisions — first execution strategy (longitudinal adaptation), then resource visibility (lateral routing):

**Tool envelope.** The visible tool set narrows per task shape: take the tool subset matched by the classification, intersect with currently available tools, then subtract those explicitly removed by the branch. Control-plane tools are never hidden. Formally:

$$$$T_{\mathrm{env}}(t) = \big(\mathcal{T}(y) \cap A_{\mathrm{unfiltered}}\big) \setminus \big(\mathrm{Avoid}(b) \cup T_{\mathrm{ctrl}}\big)$$$$

where $y$ is the classification result, $\mathcal{T}(y)$ is the tool subset for the matched task type, $A_{\mathrm{unfiltered}}$ is the unfiltered available-tool universe (judgment always runs over the unfiltered set, preventing envelope shrinkage across tasks), $\mathrm{Avoid}(b)$ is branch $b$'s explicit exclusion preference, and $T_{\mathrm{ctrl}}$ is the control-plane tool set. **Routing narrows the initial view; it never removes capability.**

**Skill recommendation.** Each candidate skill $s$ scores as:

$$\mathrm{rel}(s,t) = \min\!\big\{1,\; w_{\mathrm{base}} + w_{\mathrm{tag}}\,\mathbf{1}[\mathrm{tag}(s,t)] + w_{\mathrm{name}}\,\mathbf{1}[\mathrm{name}(s,t)] + w_{\mathrm{text}} \min(K_{\mathrm{text}}, n_{\mathrm{text}}(s,t))\big\}$$

$$\mathrm{rel}'(s,t) = \mathrm{rel}(s,t) + \beta_b(s) - \delta_b(s), \qquad R(t) = \mathrm{Top}_{K}\{s : \mathrm{rel}'(s,t) \ge \theta_{\mathrm{rel}}\},\; K \le K_{\max}$$

With $w_{\mathrm{base}}=0.5$ as base, $w_{\mathrm{tag}}=0.3$, $w_{\mathrm{name}}=0.2$, $w_{\mathrm{text}}=0.1$ as hit weights, $K_{\mathrm{text}}=2$ as text hit cap, $\theta_{\mathrm{rel}}=0.6$ as recommendation threshold (exactly $w_{\mathrm{base}} + w_{\mathrm{text}}$, meaning "at least one field hit"), and $K_{\max}=10$ as recommendation cap. Branch bias is **dominated by negative construction**: relevance is capped at $1.0$ *before* bias, and demotion $\delta = 0.5$, so a vetoed skill scores at most $0.5 < \theta_{\mathrm{rel}}$ no matter its relevance; only an explicit always-pin survives. A branch's "no" cannot be overturned by high relevance.

**Table 3-2: Routing and attribution hyperparameters**

| Symbol | Meaning | Default | Section |
|---|---|---|---|
| $w_{\mathrm{base}}$ | Base score / credit base | 0.5 | 3.2 / 3.3 |
| $w_{\mathrm{tag}}$ | Tag hit weight | 0.3 | 3.2 |
| $w_{\mathrm{name}}$ | Name hit weight | 0.2 | 3.2 |
| $w_{\mathrm{text}}$ | Text hit weight | 0.1 | 3.2 |
| $K_{\mathrm{text}}$ | Text hit cap | 2 | 3.2 |
| $\theta_{\mathrm{rel}}$ | Recommendation threshold | 0.6 | 3.2 |
| $K_{\max}$ | Recommendation cap | 10 | 3.2 |
| $w_{\mathrm{ok}}$ | Success bonus | 0.2 | 3.3 |
| $w_{\mathrm{err}}$ | Error penalty | 0.3 | 3.3 |
| $w_{\mathrm{fast}}$ | Fast execution bonus | 0.1 | 3.3 |
| $w_{\mathrm{lean}}$ | Lean execution bonus | 0.1 | 3.3 |

**Longitudinal adaptation (execution-strategy configuration).** Different task shapes impose different boundary requirements: coding tasks demand strict code review and build verification, research tasks require open information gathering and multi-source synthesis. Branch configuration allows the system to automatically adjust four layers — system prompt, memory injection, skill bias, and tool exclusion — according to task type, achieving alignment between task shape and execution strategy.

The adaptation follows an **append-only, non-replacing** principle: branch configuration is layered on top of base configuration without overwriting it. This ensures backward compatibility — base configuration provides generic capability, branch configuration provides domain specialization, and the two compose rather than replace. Three fault-tolerance guarantees hold: the branch never triggers reclassification (reuses the initial classification result); missing or corrupted branches degrade to empty adjustments (fall back to base configuration); configuration errors do not contaminate execution (errors are isolated).

### 3.3 Attribution: fitness signals with receipts

Each round must answer: **what happened in the last task and the last evolution round, and why**. Selection needs pressure; pressure needs evidence. The trajectory learner keeps two replay tracks over one shared credit pipeline.

**Track A: task replay.** Right after each task, the learner rebuilds the step sequence from the tool-call log (error = call error or timeout) and scores each step $i$:

$$c_i = w_{\mathrm{base}} + w_{\mathrm{ok}}\,\mathbb{1}[\mathrm{ok}_i] - w_{\mathrm{err}}\,\mathbb{1}[\mathrm{err}_i] + w_{\mathrm{fast}}\,\mathbb{1}[\mathrm{fast}_i] + w_{\mathrm{lean}}\,\mathbb{1}[\mathrm{lean}_i]$$

Hyperparameters are defined in Table 3-2. The design principle is **penalty exceeds reward**: $w_{\mathrm{err}} > w_{\mathrm{ok}}$ ensures failure steps sink, $w_{\mathrm{base}}$ provides a non-negative base, and $w_{\mathrm{fast}}$, $w_{\mathrm{lean}}$ are supplementary bonuses (counted only when logged). Ranking yields **key steps** $K(\tau) = \mathrm{Top\text{-}3}\{c_i\}$ (reusable success patterns) and **drag steps** $D(\tau) = \mathrm{Bottom\text{-}2}\{c_i\}$ (failure patterns to avoid) — the raw material of Sec. 3.5 skill generation. Above the step detail, one lightweight LLM call extracts a structured record $e$: objective type, complexity, success/failure factors, reusable patterns — persisted with the per-step credits as task experience.

**Track B: cycle replay.** Evolution campaigns (analyze/build/verify stages) leave trajectories too. The learner scans the campaign ledger with a **monotone cursor**: each checkpoint past the cursor with settled outcome (absorbed/abandoned/no-op) rebuilds that evolution round's own step sequence through the same credit pipeline; the LLM extraction question switches subject to "which analysis/build/verify stages worked and which failed", persisted as cycle experience, cursor written back — each cycle trajectory **consumed exactly once**. Track B is empty before the first campaign — from the second replay on, *where an evolution round failed* is on record. This is LEAP's distinguishing property: not only task outcomes are attributable, **evolution's own outcomes are attributable** — selection pressure acts on the product and the process alike.

**Strategy digest (pure statistics, no LLM).** Before each evolution decision, the learner classifies the candidate objective, retrieves same-class records (absorbed first, top 5), and assembles {tier (standard/optimized), success/failure patterns, recommended tools (Top-5 tools by key-step counts), confidence (absorbed share)} into decision context. Three consumers take this evidence: Sec. 3.4 direction and planning, Sec. 3.4 failure reflux into Track B, Sec. 3.5 skill generation.

### 3.4 Directed variation and selection: from evidence to absorbed commits

Each round must answer: **what is the next improvement, who implements it, and what earns acceptance**. Two operators, one pipeline: variation produces candidates, selection gates them — two operators with distinct degradation signatures (Table 3-1).

**Direction and trigger.** Triggering runs on an every-N cadence: a persisted counter fires one "worth an evolution round?" judgment per $N$ consumed records — per-task evolution is costly and noisy, every-N batches attention into rhythm. The decider works over attribution summaries (Sec. 3.3) and the campaign ledger, with task-shape context and policy constraints from Sec. 3.2 routing; candidates come preferentially from the improvement backlog — attribution supplies evidence, the backlog supplies the candidate pool.

**Divided implementation (variation).** The planner emits structured plans: **analyzer** decomposes the objective with acceptance criteria, **researcher** gathers facts and existing implementations, **builder** implements minimal changes in an isolated clone, **verifier** holds build/test/regression gates. Candidates queue for the supervisor's isolated execution. Every implementation lands as revertible, traceable, countable commits — never one-shot self-rewriting.

**Verified absorption (selection).** Two phases: **stage**, then **gate**. Staging commits each implementation to a **referee branch** in the isolated clone — mainline never touches a change before full review, so absorption is "stage first, merge later". Gating admits patches through a graded chain:

$$\Sigma_{t+1} = \begin{cases} \Sigma_t \oplus \Delta_t, & \text{if } G(\Delta_t) = 1, \\ \Sigma_t, & \text{otherwise,} \end{cases}, \qquad G(\Delta_t) = g_{\mathrm{pre}} \land g_{\mathrm{scope}} \land g_{\mathrm{preflight}} \land g_{\mathrm{review}}$$

Gates define the **selection function** $G(\Delta_t)$ as the conjunction of four stages: **advisory pre-review** ($g_{\mathrm{pre}}$, cheap early filter) → **scope review** ($g_{\mathrm{scope}}$, no files or topics beyond the declared objective) → **preflight** ($g_{\mathrm{preflight}}$, build plus regression first) → **hash-bound review** ($g_{\mathrm{review}}$: verdicts bound to $h(\Delta)$; any byte change voids them). The chain is **fail-closed**: any gate evaluates to 0 then $G(\Delta_t) = 0$ — the default of evolution is *not absorbing*. Each rejection also books **readiness debt** suspending further absorption until cleared. Outcomes journal in three states — **absorbed** / **abandoned** / **no-op** — to the campaign ledger; failed candidates roll back automatically and reflux as Track-B evidence. Campaigns run on the instance's supervisor scheduler under owner binding, budget floors, and re-entrancy exclusion; the review chain is one gate among these, not the whole of safety.

### 3.5 Heredity: skill populations that outlive sessions

Each round must answer: **how do selected improvements survive into the next generation**. Code-level heredity is the absorbed commit (Sec. 3.4); behavioral heredity is the skill population — LEAP's "genes": independently executable, reviewable, mutable, selectable capability units. Commits record *what changed*; skill lineages record *what was learned*: how a task class is done well, which steps once dragged success down. Skills and memory both persist across sessions with different roles: memory is evolution's **ledger** — declarative, read and retrieved, never executed, mutated, or selected; skills are its **genes** — procedural, executed for real, mutated and selected on measured performance. The former approximates declarative memory, the latter procedural: the substrate keeps the loop continuous (Sec. 3.6), skills carry heritable capability.

**(i) Generation (trajectory → gene).** A trajectory $\tau$ qualifies iff

$$|T_\tau| \ge 8 \;\wedge\; \mathrm{Repair}(\tau) \;\wedge\; \mathrm{Success}(\tau)$$

— enough tool calls (threshold calibrated to the corpus median), a self-repair episode, task success. The generator distills a skill package from key/drag steps ($K(\tau)$, $D(\tau)$) with provenance markers and content hashes as review and lineage anchors. Generation lands **pending review** — write and run are separated: unreviewed (or unattested) skills cannot execute.

**(ii) Mutation (reflective directed mutation).** The skill ledger tracks real executions $n_s$ and success rate $r_s$; a self-authored skill becomes a mutation candidate iff

$$n_s \ge n_{\min} \;\wedge\; r_s < r_{\mathrm{min}}$$

— used, and not good enough. Rewriting injects the skill's recent **real failure text** into the mutation prompt, demanding the listed failure modes be eliminated; the candidate pool is bounded (original + mutants + fixed-strategy fallbacks) with fingerprint dedup against inbreeding. Each variant scores on a ≤5-case mini eval set $D_s$ (success traces → behavioral rubrics, failure traces → known-bad outputs) with fitness

$$F(\tilde s) = \frac{|\{x \in D_s : \mathrm{pass}(x)\}|}{|D_s|}$$

gated with a **calibration discount** against evaluator drift: with $d$ the moving average of evaluated-minus-realized success ($d > 0$ = systematic optimism), the bar rises as $\theta_F \gets \theta_F + \max(0, \lambda\cdot d)$ — the more history over-promised, the harder the gate.

**(iii) Selection and versioning (lineage).** Each mutant's review verdict binds to its content hash: pass overwrites, fail restores the backup automatically with its historical executable verdict re-applied ("rolled back and immediately runnable"), then a cooldown against churn. Survivors bump versions ($v_1 \to v_2 \to \cdots$) with success rates, fitness, and discounts recorded — skills gain **lineage**, and acquired capability transmits across generations.

**(iv) Redemption (measuring transmitted gain).** Heredity pays off task-side: evolved skills return to execution through Sec. 3.2 Top-K routing, and real gain is measured as same-task-set contrast $\Delta = r_{\mathrm{post}} - r_{\mathrm{baseline}}$ (Sec. 4.3); rejections and rollbacks journaled honestly. The "task → skill → task" positive loop is Propagation's micro-mechanism. Skill and campaign lines share task boundaries but trigger independently — usage statistics for the former, LLM judgment for the latter.

### 3.6 Substrate: importance-ordered memory

Each round must answer: **where did everything this round — evidence, decisions, outcomes, assets — go**. Without sedimentation the loop breaks each session. The substrate organizes on a single axis, **importance**: campaign ledgers, attribution records, skill histories, and task reflections coexist, rank, evict, and recall under one semantics.

**Mechanism, three layers.** **Importance ordering**: each new experience $m$ is rule-scored $w(m)$, LLM-arbitrated only in the ambiguous band, tagged; under capacity the minimum $\arg\min\, w(m)$ evicts first — low value yields, while short-but-critical records ("found a critical bug") escape length penalties. **Session indexing and semantic recall**: dialogue summaries, reflections, and evolution milestones enter an append-only full-text index immune to log rotation, guaranteeing retrievability; reflections sync to external semantic memory, recalled by task semantics at context build, reusing cross-session experience. **Stable-context caching**: identity, environment profile, and knowledge index reuse within-session, sustaining long-range continuity and cache hits on stable prefixes. Retrieval filters jointly on tags and importance for task and decision contexts. The instance's background loop reads backlog digests as a read-only observer and never writes this substrate.

## 4 Experiments

Three questions in order: **(1) does the loop run** — sustained, auditable evolution products on real trajectories (4.1–4.3); **(2) does the gain transfer** — overall lift on never-seen task domains (4.4); **(3) do the fixes come from the claimed operators** — predicted degradation under attribution/heredity removal (4.5). Sec. 4.6 adds qualitative mechanism evidence. Every metric comes from auto-persisted auditable files; decision rules are fixed upfront; negative results reported as measured.

### 4.1 Evolution corpus: source and construction

**(1) Real execution.** From the 165 GAIA validation tasks [39], the Sec. 1.3 base instance executed all tasks consecutively in a controlled server environment, preserving full results, per-task tool-call trajectories (arguments, result digests, error flags, full observation payloads), and run manifests.

**(2) Merge and distill.** One-shot dedup per task kept the **latest scored instance** (correct > incorrect > unscored; ties by recency) with full provenance: 165 unique records = **130 correct + 35 incorrect**, difficulty L1 53 / L2 86 / L3 26.

**(3) Why only the 130 correct.** Skill generation requires success plus self-repair, so incorrect tasks cannot enter the generation path; failure signal is not discarded — correct trajectories widely contain error→repair episodes whose error lines attribution preserves in full as mutation and decision material. All 130 feed the pipeline by **trajectory replay** (replaying already-occurred online trajectories in fixed order for fair four-arm comparison): no re-execution, zero execution cost; all evolution products (commits, skills, experience) genuinely produced by replay-driven reflection, decisions, and campaigns.

**(4) Fairness.** Terminal-Bench [40] (89 tasks) is disjoint in source and wording from GAIA with zero overlap; evaluation runs in fresh environments with memory and skills unmigrated — only code-level products take effect, strictly separating transfer gain from task-layer capability.

### 4.2 Setup: four arms around operator integrity

The Ch. 3 claim is "complete operators sustain the loop" (Table 3-1). The arms test exactly this: V0 and V3 bound "all off" vs "all on"; each ablation removes one operator.

**Table 4-1: arms and switch mapping.**

| Arm | Configuration | Switches | Claim tested |
|---|---|---|---|
| V0 (baseline) | all operators off | evolution master off; routing/memory off | — |

V0 is the instance's factory configuration: the evolution master switch stays at its shipped default (off), with no extra crippling.

| V1 (−attribution) | dual-track replay + strategy digest off; rest on | evolution/campaign/skill/routing/memory on; experience ablation off | Table 3-1 row 1: no attribution → randomized pressure |
| V2 (−heredity) | skill generate/mutate/deploy chain off (routing Top-K naturally empty); code heredity kept; rest on | as V3 with skill-evolution off | Table 3-1 row 4: no behavioral heredity → no accumulation |
| V3 (full) | all operators on | all on | — |

**Why these two.** They map to the two diagnosed gaps — black box and history loss — directly testing the causal claim; blind direction is jointly repaired by attribution with expression/variation (Sec. 3.1), so removing attribution also covers its degradation path. Selection cannot ablate (merging unverified changes is engineering-unacceptable); its role is characterized by tri-state rates, per-gate pass/block distributions, and rollback rates. Variation cannot ablate alone (no variation = no candidates = V0). Expression and memory are always-on substrate — ablating them would sever the evolution layer's inputs and outputs together; their value is covered by the V3−V0 delta plus process evidence (Table 4-2, row 4).

**Layout.** Ablations are judged in the evolution phase: ablated products (experience, skills) never migrate to evaluation, where V1/V2 would be indistinguishable from V3. So: evolution phase runs all four arms (4.3, 4.5); **Terminal acceptance runs V0 vs V3 only** (89 × pass@5, 445 trials per arm, 890 total [41]). **Fairness:** same corpus, same fixed order, same template (unified model slots, same budget, same every-N); one isolated session per arm; resumable across days; one repeat on V0/V3 only if the gap is large.

**Table 4-2: claim–evidence mapping (all from auto-persisted auditable files).**

| Block | Claim | Primary metric | Supporting metrics | Source |
|---|---|---|---|---|
| Multi-agent campaigns (variation+selection) | attributed campaigns outproduce unattributed (V1) at lower cost | absorption rate = absorbed/campaigns (V3 vs V1) | cost per absorption; generic-layer share; tri-state distribution; per-gate pass/block | campaign + session ledgers |
| Experience attribution | history measurably joins and improves decisions | digest injection rate at decision; objective repeat rate (defined Sec. 4.3, ablation core) | credit separation (error- vs success-step mean credit — the formula demonstrably sinks failures); experience accumulation vs absorption correlation | experience ledger + decision records + trajectories |
| Skill heredity | mutation measurably improves skills on the same tasks | same-set pre/post success Δ | generation rate; accept/rollback events; lineage depth | skill stats/generation/evolution histories |
| Expression + memory (substrate) | task-layer operators genuinely join execution without side effects | skill Top-K hit/adoption rates; envelope narrowing with hidden-tool call rate | branch coverage; importance distribution of evicted vs kept memories | routing history + trajectories + memory store |

Scale expectation (130 records, every-N = 5, absorption cap 10, ~15 executions per skill on the deployment set): ~26 decision points; V0 zero campaigns zero products; V3 on the order of 6–10 absorbed commits, mostly tool/prompt-layer (generic mechanisms); skills in the tens (gated by threshold pass rates and dedup), with really-used underperformers entering mutation; V3 costlier overall but cheaper per absorption. Magnitude estimates only; measured values rule, negatives reported.

### 4.3 Evolution-phase observations: does the loop run and run well (four arms)

The thesis is cumulative sustained evolution, so **charts lead** (Fig. 4-1; x-axis: consumed record order 1–130; four arms overlaid; all data auto-persisted):

- **(a) Cumulative absorbed commits** (V3 vs V0 main line; V1/V2 reference): V3 climbs in steps, V0 flat at zero — loop on vs off at a glance; unattributed V1 expected shallower and lower-quality; V2 (no behavioral heredity) tracks V3 here — its difference belongs to (b)(c);
- **(b) Skill lifecycle with pre/post Δ** (V3 vs V2): V3's generate→enable→deploy→mutate→rollback/overwrite event timeline overlaid with per-skill baseline→post lines; V2 identically zero — the behavioral-heredity output gap, directly visible;
- **(c) Decision quality and cost** (V1 core observable + four-arm cost): **objective repeat rate** — share of late-phase proposed objectives restating earlier ones by normalized-text similarity — with cost per absorption. Unattributed V1 should repeat more and earn less per dollar: the direct quantification of the black-box gap — seeing *that the last round failed* without *why*, it re-proposes the same target under new wording;
- **(d) Mechanism self-checks** (zero-cost automatic): ① credit separation — mean-credit gap between error and success steps (the Sec. 3.3 formula demonstrably sinks failures); ② per-gate pass/block distributions with readiness-debt clearance (selection's fail-closed semantics); ③ hidden-tool call rate (near zero — narrowing costs no capability, escape hatches nearly unused); ④ importance distribution of evicted vs kept memories (short-but-valuable records survive length pressure).

A summary table (Table 4-3) gives four-arm headline numbers: campaigns/absorptions (rate), repeat rate, cost per absorption, generic-layer share, skills generated/enabled, skill Δ, digest injection rate ($0\%$ under V1 ablation and V0 by construction), credit separation.

**Skill contrast protocol (full Δ spec).** The heredity claim is "mutation measurably improves skills on the same tasks", with core metric **same-set pre/post success Δ**. Since skills and memory never migrate to evaluation (fresh environments), it is measured directly on a fixed deployment set disjoint from evolution material and eval items: **pre** runs original skills to baseline; **mutation** fires at $\ge 10$ real uses with rate $< 0.8$, reflecting on the skill's real failure text; **post** re-runs the same set on the reviewed covering version; GEPA decisions (accept/reject/rollback) and lineage ($v_1 \to v_2 \to \cdots$) all recorded. **Rule:** $\Delta > 0$ (with post $\ge$ pre) counts as positive heredity evidence; $\Delta \le 0$ reported as measured with attribution (wrong mutation direction, calibration discount binding, …) — no fabricated lift.

### 4.4 Terminal-Bench acceptance: full frame vs baseline (V0 vs V3)

Fresh containers and data roots (memory and skills unmigrated; only code-level products and task-layer operators take effect), all 89 Terminal-Bench tasks × pass@5 [41] (445 attempts per arm, 890 total). The harshest question: **do improvements accumulated on a wholly different-source corpus transfer to never-seen domains** — transfer, if present, belongs to the mechanism, not to corpus memory. V1/V2 stay out of Terminal: their ablated products (experience, skills) never migrate, so they are unmeasurable-or-identical there; measuring them would add only uninformed variance. Table 4-4 reports pass@1, pass@5, cost per solved task, tokens per task, tool calls per task, tool failure rate — V0, V3, delta.

### 4.5 Evolution-phase ablations: attribution and heredity contributions (Fig. 4-2)

- **(a) Attribution (V3 vs V1):** absorption rate, repeat rate, and cost-per-absorption twin curves over record order, with credit-separation checks (both arms should separate — the ablation removes experience *use*, not credit *computation*). Higher V1 repeat rates at lower unit yield quantify the black-box gap;
- **(b) Heredity (V3 vs V2):** skill event timelines (V2 identically zero) with late-phase efficiency contrasts — quantifying history loss;
- **(c) Summary:** V3−V0 (whole), V3−V1 (attribution), V3−V2 (heredity) delta bars with honest magnitudes. Task-layer (expression/memory) contributions appear as process evidence — branch coverage, narrowing rates, hidden-tool call rates, Top-K hit/adoption, high-value memory retention (Table 4-2 row 4; routing history, trajectories, memory store) — no standalone arms, per Sec. 4.2.

**Rule:** directions and magnitudes reported as measured; a null ablation difference is reported and discussed (redundant operator, or a domain that never reaches its surface) — no fabricated significance.

### 4.6 Mechanism cases and product portrait (qualitative)

Four cases plus one portrait from auto-persisted files, no extra experiments: **(i) one blocked candidate**, replayed gate by gate (pre-review notes, scope-violating files, preflight failures, or review verdict) with debt booking and clearance — selection's conservative semantics made visible: **the default of evolution is *not absorbing***. **(ii) one self-attributed evolution failure**, localized by Track B to a stage (analyze/build/verify) with its failure mode entering the next same-class campaign context — "last round died at verification, this round's verification checklist is reinforced": **evolution improves task capability and itself**. **(iii) one skill's life**, end to end — threshold-passing generation (with key/drag steps) → review enablement → real usage statistics → rewrite trigger (with injected failure text) → mini-eval plus calibration discount → reviewed overwrite (or rollback) → same-set Δ: every Sec. 3.5 mechanism on one traceable timeline. **(iv) absorbed-commit portrait**: layer distribution (tool/prompt/process; generic vs task-specific) with 1–2 representative diffs and before/after behavior — expected generic-heavy, cross-checking the Sec. 4.4 transfer gain.

## 5 Conclusion

**Summary.** LEAP — an importance-substrated, five-operator loop for agent self-evolution — moves the question from "can an agent change its code" to "can the change loop keep running": attribution makes every outcome localizable to steps (including evolution's own); directed variation turns evidence into real code and skill changes with explicitly chosen direction and divided labor; selection holds every change on referee branches behind graded fail-closed review with *not absorbing* as default; heredity fixes validated gains as commits and versioned skills; expression schedules stored capability back into tasks. The operators are jointly necessary — the theoretical basis of the four-arm design.

**Empirically**, phase observations test sustained auditable output with stepwise accumulation; the two ablations test attribution and heredity necessity (the black-box and history-loss repairs); Terminal-Bench acceptance tests cross-domain transfer; same-set skill contrast measures transmitted gain directly; cases and portraits witness the loop's interior. All evidence comes from auto-persisted auditable files.

**Limitations and future work.** **Single model, instance, and domain pair** — one model family, one base instance, one GAIA→Terminal-Bench transfer edge; generality across stronger/weaker models, other bases, and other domains (web, scientific computing) awaits validation. **Hand-calibrated parameters** — credit weights, generation gates ($|T_\tau| \ge \theta_{\mathrm{steps}}$), mutation triggers ($n_s \ge n_{\min}$, $r_s < r_{\min}$), fitness discounts; the Sec. 3.2 L3 (statistics-generated configs) and L4 (result-fed self-tuning) route would bring expression's own parameters under evolution. **Safety boundary** — hash-bound graded review and validator gating inherit reviewer-model and suite quality; reviewer-weaker-than-generator or thin-coverage regimes leave self-confirmation risk beyond "review A, merge B" unclosed; evolving the reviewers themselves is next. **Cost and cadence** — every-N rhythm, campaign concurrency, and mini-eval sizing are fixed hyperparameters today; budget-aware adaptive cadence (dense evidence → faster evolution, sparse → dormancy) is worth exploring. **Bounded open-endedness** — the loop deliberately runs inside human-set goals, benchmarks, and safety protocols (Sec. 2.2); genuinely open-ended recursive self-improvement with generated goals remains a horizon problem.

**Closing.** Self-evolution is not one-shot rewriting of one's source but an operator-complete, evidence-driven, heritable loop. LEAP exists to keep that loop turning: every validated round fixed as revertible commits and lineaged skills, the curve a staircase, not a flat line — **each round's end is the next round's start**.

## References

1. Zelikman E., Lorch E., Mackey L., Kalai A. Self-Taught Optimizer (STOP): Recursively Self-Improving Code Generation. 2024.
2. Zhang J., et al. Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents. arXiv:2505.22954, 2025.
3. Wang W., et al. Huxley-Gödel Machine: Human-Level Coding Agent Development by an Approximation of the Optimal Self-Improving Machine. arXiv:2510.21614, 2025.
4. Razzhigaev A., Gritsaev A., Kaznacheev A., Dragunov N., Yampolskiy R., Kuznetsov A. Ouroboros: A Self-Developing Frontier Coding Agent with Reviewed Core Evolution. arXiv:2608.08311, 2026.
5. Ren Z., Chen Y., Guo D., et al. Self-Improvements in Modern Agentic Systems: A Survey. arXiv:2607.13104, 2026.
6. Yang C., et al. Large Language Models as Optimizers. arXiv:2309.03409, 2023.
7. Madaan A., et al. Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS, 2023.
8. Shinn N., Cassano F., Gopinath A., et al. Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS, 2023.
9. Guo Q., et al. EvoPrompt: Connecting LLMs with Evolutionary Algorithms Yields Powerful Prompt Optimizers. arXiv:2309.08532, 2023.
10. Fernando C., et al. Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution. arXiv:2309.16797, 2023.
11. Agrawal L., et al. GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning. arXiv:2507.19457, 2025.
12. Nair A., et al. Tournament of Prompts: Evolving LLM Instructions Through Structured Debates and Elo Ratings (DEEVO). arXiv:2506.00178, 2025.
13. Yuksekgonul M., et al. TextGrad: Automatic "Differentiation" via Text. arXiv:2406.07496, 2024.
14. Park J.S., O'Brien J., Cai C., et al. Generative Agents: Interactive Simulacra of Human Behavior. UIST, 2023.
15. Zhong W., et al. MemoryBank: Enhancing Large Language Models with Long-Term Memory. AAAI, 2024.
16. Zhao A., et al. ExpeL: LLM Agents Are Experiential Learners. AAAI, 2024.
17. Chhikara P., et al. Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. 2025.
18. Xu W., et al. A-MEM: Agentic Memory for LLM Agents. arXiv:2502.12110, 2025.
19. Bogdanov I., et al. FORGE: Self-Evolving Agent Memory with No Weight Updates via Population Broadcast. arXiv:2605.16233, 2026.
20. Wang G., Xie Y., Jiang Y., et al. Voyager: An Open-Ended Embodied Agent with Large Language Models. TMLR, 2023.
21. Zheng B., et al. SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills. arXiv:2504.07079, 2025.
22. Zhao S., et al. PyVision: Agentic Vision with Dynamic Tooling. arXiv:2507.07998, 2025.
23. Yang Y., et al. SkillOpt: Executive Strategy for Self-Evolving Agent Skills. arXiv:2605.23904, 2026.
24. Lenat D. EURISKO: A Program That Learns New Heuristics and Domain Concepts. Artificial Intelligence, 1983.
25. Schmidhuber J. Beyond Genetic Programming: Incremental Self-Improvement. 1995.
26. Yin X., et al. Gödel Agent: A Self-Referential Agent Framework for Recursive Self-Improvement. arXiv:2410.04444, 2024.
27. Xia C., et al. Live-SWE-agent: Can Software Engineering Agents Self-Evolve on the Fly? arXiv:2511.13646, 2025.
28. Novikov A., et al. AlphaEvolve: A Coding Agent for Scientific and Algorithmic Discovery. arXiv:2506.13131, 2025.
29. Lange R., et al. ShinkaEvolve: Towards Open-Ended and Sample-Efficient Program Evolution. arXiv:2509.19349, 2025.
30. Hu S., Lu C., Clune J. Automated Design of Agentic Systems. arXiv:2408.08435, 2024.
31. Zhuge M., et al. Language Agents as Optimizable Graphs. arXiv:2402.16823, 2024.
32. Zhou W., et al. Symbolic Learning Enables Self-Evolving Agents. arXiv:2406.18532, 2024.
33. Zhang J., et al. Hyperagents. arXiv:2603.19461, 2026.
34. Lee Y., et al. Meta-Harness: End-to-End Optimization of Model Harnesses. arXiv:2603.28052, 2026.
35. Karten S., et al. Continual Harness: Online Adaptation for Self-Improving Foundation Agents. arXiv:2605.09998, 2025.
36. Karten S., et al. Prime Agent: A Self-Improving RLM Harness. arXiv:2608.23552, 2026.
37. Hebbar P., et al. SIA: Self Improving AI with Harness & Weight Updates. arXiv:2605.27276, 2026.
38. Lewontin R. C. The Units of Selection. Annual Review of Ecology and Systematics, 1:1–18, 1970.
39. Mialon G., Fourrier C., Swift C., Wolf T., LeCun Y., Scialom T. GAIA: A Benchmark for General AI Assistants. arXiv:2311.12983, 2023.
40. Merrill M.A., Shaw P., et al. Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces. arXiv:2601.11868, 2026.
41. Chen M., Tworek J., Jun H., et al. Evaluating Large Language Models Trained on Code. arXiv:2107.03374, 2021.
