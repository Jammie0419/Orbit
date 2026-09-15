# Ouroboros Devtools

`devtools/` contains operator-side and benchmark support code that should be
versioned with Ouroboros without becoming part of the runtime core.

Rules:

- Generated logs, datasets, run outputs, Docker layers, and secrets do not live
  here.
- Default benchmark outputs go under `/Users/anton/Ouroboros/bench_runs/`.
- Runtime modules must not import `devtools`.
- This is not an immune-system bypass: touched files are reviewed normally.
- Promote code out of `devtools` only through a separate reviewed runtime plan.

---

# Evolution arm (`benchmarks/evolution/`)

Runs the LEAP evolution loop over a corpus: feed records → reflect → (cadence) promote →
campaign in an isolated clone → commit → restart → boot-verified absorption. One session
owns one throwaway clone plus one isolated data root:

```
<session>/clone/              git clone of this repo at the session's starting commit
<session>/data/               the isolated drive root (state/, logs/, skills/, …)
<session>/run_evolution_arm.log
<session>/server.stdout.log   the isolated server's + its workers' raw streams
<session>/server.stderr.log
<session>/feed_progress.json  resume point (last_index) + failures
<session>/session_ledger.json written at teardown (outcomes, absorbed shas, cost)
```

A session's clone is frozen at the commit it was created from, and `--resume` reuses that
same clone: **a fix lands in a session only if the session directory is new.**

## How the run log is organised

The log is grouped by the LEAP operators of the paper's Algorithm 1 (`docs/orbit/`), not by
the data source each line comes from. `devtools/benchmarks/evolution/leap_report.py` owns the
formatting (no IO, no metrics of its own); the runner collects the values and emits them.

| Line family | Meaning |
|---|---|
| `②执行 ③归因 ④记忆 ⑤触发 ⑥规划 ⑦变异 ⑧选择 ⑨遗传 ⑪沉淀` | the operator the line belongs to (Algorithm 1 step numbers) |
| `[战役] …` / `[战役#N] 开 · ⤷ commit · ⤷ absorbed` | the campaign namespace |
| `等待 · …` / `运行 · …` | operational lines (waits, heartbeats, teardown) — never operator chips |
| `[isolated-server] …` | restart-bounce notices from the harness's server helper. **Raw print: terminal only, never in the log file.** The same "busy" line is reported once per streak |

Two numbering systems coexist: `[战役] 第 N/M 个战役已提交请求` counts campaigns **within the
session** against `--max-absorbed` (a resume restarts that count from its own baseline), while
`战役#K` is the **campaign's cycle number**, continuous across sessions (one campaign document
carries successive cycles).

Each record is emitted in three phases so a slow provider never looks like a dead run —
`②执行`'s header lands right after corpus seeding, the reflection output plus the memory
writes follow the reflection call, and the attribution/decision tail follows the promotion
call. `⑪沉淀` is emitted when a **cycle resolves** (right after `⑨遗传 ⤷ absorbed/…`), because
Algorithm 1 step 12 is the write that follows the outcome — a record that merely *starts* a
campaign does not claim it.

Two tests hold this contract: one asserts every datum the flat log used to print still
appears across the phases, another asserts the runner's emission order (and that a record
never settles). `docs/orbit/EXPECTED_RUN_OUTPUT.md` holds rendered samples for
`--max-absorbed 1`, `--max-absorbed 2`, and `max=1` followed by `--resume --max-absorbed 2`.

## Review strength: two switches, both OFF by default

Corpus runs intentionally keep the defaults, so the loop turns and accumulates without the
selection layer aborting cycles. Two knobs change that — they alter the METHOD, so they must
be applied to every arm identically and the baseline re-run:

- `OUROBOROS_REVIEW_ENFORCEMENT=blocking` — makes the "selection" operator actually gate.
  Default is `advisory` (`config.py`), where every blocking signal is downgraded to a warning
  plus a durable `review_advisory_override` trace. Measured evidence for the difference: a
  `PREFLIGHT_BLOCKED: New files added in ouroboros/ or supervisor/ but docs/ARCHITECTURE.md is
  not staged` was downgraded and the commit landed without touching that doc. Expect the commit
  failure rate to rise — that is the selection pressure, not a regression.
- `OUROBOROS_ADVISORY_REVIEW_ROUTE=agent_session` — makes the advisory pre-review actually run.
  The default route is `api`, which requires `ANTHROPIC_API_KEY`; with a BYO
  `openai-compatible` provider every `advisory_review` call auto-bypasses and records
  `status=bypassed, reason="ANTHROPIC_API_KEY not set — auto-bypassed (advisory route=api)"`.
  `agent_session` is the keyless delegated route — **not yet verified against the
  xiaomi/openai-compatible setup**, so try it on a one-cycle run first.

What a commit in the default regime has actually passed: the triad + scope LLM reviews
(advisory findings, non-blocking), the attribution / evolution-authority / restart-receipt
checks (hard), and an *audited* advisory bypass. The bypass is not silent — it is recorded in
`state/advisory_review.json` (`attempts`: `no_advisory` → `advisory_review_required` →
`succeeded`) and `logs/events.jsonl` (`advisory_review_bypassed`, `review_advisory_override`),
so a write-up can report the review strength it had instead of claiming "reviewed".

The runner also forces two benchmark-appropriate settings into the isolated server's
environment: `OUROBOROS_PRE_PUSH_TESTS=0` (a corpus commit must not be gated by this repo's own
size-debt census, which is red at some baselines) and `OUROBOROS_REQUIRE_ADVISORY_REVIEW=1`
(the per-call `skip_advisory_review=True` shortcut is refused; the advisory tool must be
invoked, and its bypass is then audited). `OUROBOROS_DIE_WITH_PARENT=1` ties the isolated
server tree's life to the harness so a killed launcher cannot leave orphans writing to the
same drive root.

## What this pass changed (evolution arm)

Runner/loop:

- `--max-absorbed` now trips: the campaign count is read *after* waiting for the
  asynchronously created campaign (`account_promoted_campaign`), and the limit is re-checked
  on every record rather than only on a promotion decision.
- A campaign executes alone: the next block's reflection waits for the commit, then runs
  during absorption (`wait_for_campaign_execution`).
- Feeding stops for the stated reason (quota vs corpus exhausted); `_budget_reached` is bound
  before the `try` so a startup failure cannot turn the teardown message into a `NameError`.
- The run log is grouped by Algorithm 1 operators, emitted in three phases, with a session
  summary block at teardown; heartbeats only on change; the bounce "busy" notice once per
  streak.

Evolution accounting (product side):

- A commit-less cycle killed by infrastructure is recorded as `infra_failed` with
  `infra:<reason>` instead of `no_op`, and does **not** count against the objective's repeat
  tally or join `dropped_objective_fps`.
- A replayed terminal backfills the cycle's rounds/cost (boot reconciliation can absorb before
  the terminal arrives), and the ledger's outcome distribution reaches the digest with its
  reason.
- Reflection output survives one illegal JSON escape or raw control character instead of
  dropping the record's memory actions, and a still-unparseable block is marked
  `memory_actions_parse_failed` instead of looking like a deliberate empty.

Process/observability:

- The isolated server's and its workers' stdout/stderr go to files next to the session
  (previously `DEVNULL`: a worker traceback vanished with no artifact).
- An unpriceable model no longer banks `$0.00` as "available" in the campaign; the ledger-wide
  status is left alone because it also gates replay safety.
- Orphan prevention: the server has a graceful SIGTERM/SIGINT path that reaps its worker tree,
  forked workers reset the inherited handler, and the bench-spawned server arms
  `PR_SET_PDEATHSIG` (verified both ways: with the parent SIGKILLed the child dies; unarmed it
  survives).
- A review-wave budget event that had no supervisor handler (`review_wave_budget_partial_unknown`)
  is persisted as a typed row instead of an untyped repr.

