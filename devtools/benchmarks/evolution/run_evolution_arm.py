#!/usr/bin/env python3
"""Mode-P offline-replay driver for the GAIA evolution experiment (spec §10.4).

Feeds an extracted evolution corpus (produced by
``devtools/benchmarks/gaia/extract_evolution_corpus.py``, e.g.
``bench_runs/evolution_corpus/gaia_corpus_<date>.jsonl``) into the post-task
evolution pipeline WITHOUT re-executing any GAIA task::

    for each record:
        llm_trace        = load_trace_from_path(rec["trace_ref"])   # §10.6
        reflection_entry = generate_reflection(task, llm_trace, trace_summary, ...)
        apply_memory_actions(env, MEMORY_ACTIONS_JSON)              # memory/scratchpad
        append_backlog_items(data_root, BACKLOG_CANDIDATES_JSON)    # improvement backlog
        maybe_promote(env, task, reflection_entry, llm_client)      # cadence every_n:5
        poll_campaign_progress(data_root)                           # supervisor runs campaign

Each arm gets ONE isolated session under ``bench_runs/evolution/<arm>/``
(throwaway clone + isolated data root + settings overrides, see §10.1-10.3).
The evolution machinery runs inside the isolated server; the live Ouroboros
installation and repo are never touched (clone has its origin removed).

All four arms are runnable: the evolution-layer switches (OUROBOROS_MULTI_AGENT_EVOLVER,
implemented 2026-09-02) and the skill-evolution switch (OUROBOROS_SKILL_EVOLUTION,
implemented 2026-09-03 — auto-generation + GEPA evolution + nudge, see docs/orbit/
PAPER_INTEGRATION_ANALYSIS.md Phase 3) gate everything behind opt-in keys.

Running this driver spends real LLM budget (reflection per record + promotion
decisions every ``cadence`` records + evolution campaigns). Use ``--dry-run``
first to validate the corpus wiring at zero cost.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from devtools.benchmarks.common.server_runner import (
    IsolatedServer,
    absorbed_cycles_done,
    build_isolated_settings,
    seed_owner_state,
)

REPO_DIR = pathlib.Path(__file__).resolve().parents[3]


def default_live_settings() -> pathlib.Path | None:
    """Locate a live settings.json to copy provider/model/budget keys from.

    Server-friendly resolution order: $OUROBOROS_DATA_DIR/settings.json,
    $OUROBOROS_SETTINGS_PATH, ~/Ouroboros/data/settings.json (Windows/dev),
    ~/.ouroboros/settings.json (typical Linux deployment).
    """
    candidates = []
    if os.environ.get("OUROBOROS_DATA_DIR"):
        candidates.append(pathlib.Path(os.environ["OUROBOROS_DATA_DIR"]) / "settings.json")
    if os.environ.get("OUROBOROS_SETTINGS_PATH"):
        candidates.append(pathlib.Path(os.environ["OUROBOROS_SETTINGS_PATH"]))
    candidates.append(pathlib.Path.home() / "Ouroboros" / "data" / "settings.json")
    candidates.append(pathlib.Path.home() / ".ouroboros" / "settings.json")
    for c in candidates:
        if c.is_file():
            return c
    return None

# spec §3.3
PERSISTENT_OBJECTIVE = (
    "改进通用执行策略：工具选择、错误恢复、上下文运用与结果验证；"
    "改进必须对任务难度和任务形态无关地成立（跨 coding/research/knowledge/simple 均有效），"
    "拒绝只对单一任务类型有效的特化技巧。"
)

# spec §10.2 — evolution-layer switches; both are implemented and opt-in
# (MULTI_AGENT_EVOLVER 2026-09-02, SKILL_EVOLUTION 2026-09-03 Phase 3).
ARM_SWITCHES = {
    "V0": {},
    "V1": {"OUROBOROS_SMART_ROUTING": "true", "OUROBOROS_SMART_MEMORY": "true"},
    "V2": {"OUROBOROS_MULTI_AGENT_EVOLVER": "true", "OUROBOROS_SKILL_EVOLUTION": "true"},
    "V3": {"OUROBOROS_SMART_ROUTING": "true", "OUROBOROS_SMART_MEMORY": "true",
           "OUROBOROS_MULTI_AGENT_EVOLVER": "true", "OUROBOROS_SKILL_EVOLUTION": "true"},
}

_REQUEST_FILE = "state/post_task_evolution_request.json"


_LOG_FH = None


def _log(msg: str) -> None:
    line = f"[run_evolution_arm] {msg}"
    print(line, flush=True)
    if _LOG_FH is not None:
        _LOG_FH.write(line + "\n")
        _LOG_FH.flush()


def _git(args: list[str], cwd: pathlib.Path) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------------------
# trace mapping (spec §10.6)
# ---------------------------------------------------------------------------

def load_trace_from_path(trace_ref: str, base_dir: pathlib.Path | None = None) -> dict:
    """Load a corpus trace_ref into the llm_trace dict expected by generate_reflection.

    Resolution order: absolute path → base_dir (the corpus JSONL's directory;
    trace_ref is written relative to it) → repo root (legacy corpora used
    ``bench_runs/evolution_corpus/traces/...``).

    Form (b): our extracted trace JSONs (``{"tool_calls": [...], ...}``) are
    returned as-is — the corpus extractor now emits production-grade traces
    (full-result views, real reasoning_notes, persisted trace_summary, meta.usage/
    meta.review_evidence), so no reshaping is needed here. Form (a): a raw
    Ouroboros ``tools.jsonl`` is mapped line by line (``result_preview`` is
    renamed to ``result`` — the field the reflection pipeline actually consumes).
    """
    p = pathlib.Path(trace_ref)
    if not p.is_absolute():
        candidates = []
        if base_dir is not None:
            candidates.append(base_dir / p)
        candidates.append(REPO_DIR / p)
        for cand in candidates:
            if cand.is_file():
                p = cand
                break
        else:
            p = candidates[0]
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if "tool_calls" in data:
        return data
    calls = []
    for line in p.open(encoding="utf-8-sig"):
        rec = json.loads(line)
        if rec.get("type") != "tool_call" or not rec.get("tool"):
            continue
        is_err = bool(rec.get("is_error"))
        status = rec.get("status") or ("error" if is_err else "ok")
        calls.append({
            "tool": rec.get("tool"),
            "args": rec.get("args") or {},
            "result": rec.get("result_preview") or rec.get("result") or "",
            "is_error": is_err,
            "status": status,
        })
    return {"tool_calls": calls, "reasoning_notes": [], "trace_summary": ""}


def trace_usage_dict(llm_trace: dict) -> dict:
    """Rebuild the usage_dict passed to generate_reflection from corpus trace meta.

    Production passes the loop's accumulated usage (rounds/cost/tokens,
    agent_task_pipeline.py:1362); without it the reflection entry records
    rounds=0/cost=None and the NONTRIVIAL reflection branch never triggers.
    The extractor persists cost fields in ``meta.usage`` (total_rounds,
    cost_usd, tokens from the headless task result)."""
    meta = llm_trace.get("meta") or {}
    usage = dict(meta.get("usage") or {})
    out: dict = {}
    if usage.get("total_rounds") is not None:
        out["rounds"] = int(usage["total_rounds"])
    if usage.get("cost_usd") is not None:
        out["cost"] = float(usage["cost_usd"])
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        if usage.get(key) is not None:
            out[key] = int(usage[key])
    if usage.get("cost_accounting_status"):
        out["cost_accounting_status"] = usage["cost_accounting_status"]
    return out


def trace_review_evidence(llm_trace: dict) -> dict:
    """Corpus trace meta.review_evidence (the persisted production review_state
    dict), or {} when the run had none."""
    meta = llm_trace.get("meta") or {}
    rv = meta.get("review_evidence")
    return rv if isinstance(rv, dict) else {}


def build_trace_summary(llm_trace: dict, max_len: int = 2000) -> str:
    """≤max_len tool-trace summary: reuse the extracted one, else synthesize."""
    summary = str(llm_trace.get("trace_summary") or "").strip()
    if not summary:
        calls = llm_trace.get("tool_calls") or []
        n_err = sum(1 for c in calls if c.get("is_error"))
        lines = [f"## Tool trace ({len(calls)} calls, {n_err} errors)"]
        for i, c in enumerate(calls[:40], 1):
            args = json.dumps(c.get("args") or {}, ensure_ascii=False)[:120]
            lines.append(f"{i}. {c.get('tool')}({args})")
        summary = "\n".join(lines)
    return summary[:max_len]


# ---------------------------------------------------------------------------
# campaign progress / checkpoint helpers
# ---------------------------------------------------------------------------

def checkpoint_rows(data_root: pathlib.Path) -> list[dict]:
    p = data_root / "state" / "evolution_checkpoints.jsonl"
    if not p.is_file():
        return []
    try:
        return [json.loads(l) for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def cycle_count(data_root: pathlib.Path) -> int:
    return sum(1 for r in checkpoint_rows(data_root) if r.get("kind") == "cycle_outcome")


def snapshot_checkpoint_summary(data_root: pathlib.Path) -> None:
    rows = checkpoint_rows(data_root)
    cycles = [r for r in rows if r.get("kind") == "cycle_outcome"]
    if not cycles:
        _log("checkpoints: （尚无周期记录）")
        return
    from collections import Counter
    dist = Counter(r.get("cycle_outcome") for r in cycles)
    cost = round(sum(r.get("cost_usd", 0) or 0 for r in cycles), 2)
    _log(f"checkpoints: 总条数={len(rows)} 周期={len(cycles)} 分布={dict(dist)} 成本=${cost}")
    for r in cycles:
        if r.get("cycle_outcome") == "absorbed":
            _log(f"  absorbed {r.get('commit_sha', '')[:12]} | {str(r.get('campaign_objective') or '')[:60]}")


def poll_campaign_progress(data_root: pathlib.Path, timeout_sec: float = 300) -> dict:
    """Wait for a promotion signal to be consumed into a campaign cycle.

    Returns {"campaign": bool, "cycles_before": n, "cycles_after": m}.
    """
    before = cycle_count(data_root)
    req = data_root / _REQUEST_FILE
    req_seen = req.is_file()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        after = cycle_count(data_root)
        if after > before:
            _log(f"campaign: 新周期已记录（{before} → {after}）")
            return {"campaign": True, "cycles_before": before, "cycles_after": after}
        if not req.is_file() and req_seen:
            _log("campaign: promote 信号已被 supervisor 消费")
            req_seen = False
        time.sleep(15)
    _log(f"campaign: 等待超时（{timeout_sec}s，无新周期；promote 可能被 cadence/决策拒绝）")
    return {"campaign": False, "cycles_before": before, "cycles_after": cycle_count(data_root)}


# ---------------------------------------------------------------------------
# session setup
# ---------------------------------------------------------------------------

def _seed_settings(data_root: pathlib.Path, arm: str, cadence: str, total_budget: float,
                   live_settings: pathlib.Path) -> pathlib.Path:
    settings_path = data_root / "settings.json"
    live_cfg: dict = {}
    if live_settings is not None and live_settings.is_file():
        try:
            live_cfg = json.loads(live_settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            live_cfg = {}
    overrides = {
        "OUROBOROS_RUNTIME_MODE": "advanced",
        "OUROBOROS_POST_TASK_EVOLUTION": "true",
        "OUROBOROS_POST_TASK_EVOLUTION_CADENCE": cadence,
        "OUROBOROS_EVOLUTION_PERSISTENT_OBJECTIVE": PERSISTENT_OBJECTIVE,
        "TOTAL_BUDGET": total_budget,
        **ARM_SWITCHES.get(arm.upper(), {}),
    }
    cfg = build_isolated_settings(live_cfg, **overrides)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path


def main() -> int:
    ap = argparse.ArgumentParser(description="GAIA evolution corpus offline-replay driver (spec §10.4).")
    ap.add_argument("--corpus", type=pathlib.Path, default=None,
                    help="Corpus JSONL (default: newest bench_runs/evolution_corpus/gaia_corpus_*.jsonl)")
    ap.add_argument("--session-dir", type=pathlib.Path,
                    default=REPO_DIR / "bench_runs" / "evolution" / "V0",
                    help="Persistent session dir: <session>/clone + <session>/data (spec §10.1)")
    ap.add_argument("--arm", default="V0", help="Arm label (V0-V3, controls arm switches)")
    ap.add_argument("--source-repo", type=pathlib.Path, default=REPO_DIR,
                    help="Repo to clone as the throwaway session clone")
    ap.add_argument("--live-settings", type=pathlib.Path, default=None,
                    help="Source of provider/model/budget keys for the isolated settings "
                         "(default: $OUROBOROS_DATA_DIR/settings.json, then ~/Ouroboros/data, then ~/.ouroboros)")
    ap.add_argument("--resume", action="store_true",
                    help="Resume an existing session dir (feeds only the records not yet processed)")
    ap.add_argument("--cadence", default="every_n:5", help="OUROBOROS_POST_TASK_EVOLUTION_CADENCE")
    ap.add_argument("--budget", type=float, default=200.0, help="Per-session TOTAL_BUDGET (USD)")
    ap.add_argument("--campaign-timeout", type=float, default=300.0,
                    help="Seconds to poll for one campaign cycle after each promote")
    ap.add_argument("--max-absorbed", type=int, default=10, help="Stop feeding after N absorbed cycles (spec §3.5)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate corpus→trace→pipeline wiring at zero LLM cost (no server, no LLM calls)")
    args = ap.parse_args()

    if args.corpus is None:
        candidates = sorted((REPO_DIR / "bench_runs" / "evolution_corpus").glob("gaia_corpus_*.jsonl"))
        args.corpus = candidates[-1] if candidates else None
    if not args.corpus or not args.corpus.is_file():
        _log(f"corpus not found: {args.corpus}（先用 extract_evolution_corpus.py 生成，或 --corpus 指定）")
        return 2
    corpus = [json.loads(l) for l in args.corpus.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    _log(f"corpus: {args.corpus}（{len(corpus)} 条）")
    if args.live_settings is None:
        args.live_settings = default_live_settings()
        if args.live_settings is None:
            _log("警告: 未找到 live settings.json，隔离 settings 将缺少 provider/model 键（可用 --live-settings 指定）")
        else:
            _log(f"live settings: {args.live_settings}")

    # dry-run: validate wiring only, no clone/server/LLM.
    if args.dry_run:
        ok = True
        notes_covered = 0
        usage_covered = 0
        for i, rec in enumerate(corpus, 1):
            try:
                trace = load_trace_from_path(rec["trace_ref"], base_dir=args.corpus.parent)
                n = len(trace.get("tool_calls") or [])
                n_notes = len(trace.get("reasoning_notes") or [])
                usage = trace_usage_dict(trace)
                summary = str(trace.get("trace_summary") or "").strip() or build_trace_summary(trace)
                status = "✓" if n else "✗ 空轨迹"
                if not n:
                    ok = False
                if n_notes:
                    notes_covered += 1
                if usage.get("rounds") is not None:
                    usage_covered += 1
                _log(f"dry-run {i:2d}/{len(corpus)} {rec['id']}: tool_calls={n} "
                     f"notes={n_notes} rounds={usage.get('rounds')} "
                     f"summary={len(summary)} 失败={not rec['outcome']['passed']} {status}")
            except Exception as exc:  # noqa: BLE001 - report any wiring error
                _log(f"dry-run {i:2d}/{len(corpus)} {rec['id']}: ✗ {exc}")
                ok = False
        _log(f"dry-run 完成（未启动服务器、未调用 LLM）: reasoning_notes 覆盖 {notes_covered}/{len(corpus)}，"
             f"usage(rounds) 覆盖 {usage_covered}/{len(corpus)}" + (" ✅" if ok else " ❌ 有失败项"))
        return 0 if ok else 1

    session_dir = args.session_dir.resolve()
    clone = session_dir / "clone"
    data_root = session_dir / "data"
    progress_path = session_dir / "feed_progress.json"
    session_exists = clone.exists() or data_root.exists()
    if session_exists and not args.resume:
        _log(f"session dir already exists: {session_dir}（续跑需 --resume；重跑请清理或换 --session-dir）")
        return 2
    resume = session_exists and args.resume
    if resume and not progress_path.is_file():
        _log(f"--resume 但找不到进度文件: {progress_path}")
        return 2

    global _LOG_FH
    _LOG_FH = (session_dir / "run_evolution_arm.log").open("a" if resume else "w", encoding="utf-8")
    _log(f"日志: {session_dir / 'run_evolution_arm.log'}")

    if resume:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress.get("arm") != args.arm or progress.get("corpus") != str(args.corpus):
            _log("警告: 进度文件与本次参数不一致（arm/corpus），继续将产生偏差")
    else:
        progress = {"arm": args.arm, "corpus": str(args.corpus), "sha_start": None,
                    "last_index": 0, "records_processed": 0, "failures": []}

    _log(f"session: {session_dir}  arm={args.arm}  cadence={args.cadence}  budget=${args.budget}"
         + ("  （resume 续跑）" if resume else ""))
    if not resume:
        clone.parent.mkdir(parents=True, exist_ok=True)
        rc, out = _git(["clone", "--no-hardlinks", "-q", str(args.source_repo), str(clone)], clone.parent)
        if rc != 0:
            _log(f"clone failed: {out}")
            return 2
        sha_start = _git(["rev-parse", "HEAD"], clone)[1].strip()
        progress["sha_start"] = sha_start
        # -B guarantees BRANCH_DEV 'ouroboros' exists (safe_restart depends on it, §10.8-2).
        rc, out = _git(["checkout", "-B", "ouroboros"], clone)
        if rc != 0:
            _log(f"checkout -B ouroboros failed: {out}")
            return 2
        # Isolation: drop origin so a self-mod _auto_push can never reach the live repo (§10.8-1).
        _git(["remote", "remove", "origin"], clone)

        data_root.mkdir(parents=True, exist_ok=True)
        settings_path = _seed_settings(data_root, args.arm, args.cadence, args.budget, args.live_settings)
        seed_owner_state(data_root)

        from supervisor import state as sstate
        (data_root / sstate.ISOLATED_BENCHMARK_SENTINEL).write_text("isolated benchmark data root\n", encoding="utf-8")
    else:
        settings_path = data_root / "settings.json"
        if not (clone / ".git").is_dir() or not settings_path.is_file():
            _log("resume 目录不完整: 缺 clone/.git 或 data/settings.json")
            return 2
        sha_start = progress.get("sha_start") or _git(["rev-parse", "HEAD"], clone)[1].strip()
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
    os.environ["OUROBOROS_DATA_DIR"] = str(data_root)
    os.environ["OUROBOROS_SETTINGS_PATH"] = str(settings_path)

    from ouroboros.agent import Env
    from ouroboros.improvement_backlog import append_backlog_items
    from ouroboros.llm import LLMClient
    from ouroboros.post_task_evolution import maybe_promote
    from ouroboros.reflection import apply_memory_actions, generate_reflection

    env = Env(repo_dir=clone, drive_root=data_root, branch_dev="ouroboros")
    llm_client = LLMClient()

    start_idx = int(progress.get("last_index", 0))
    remaining = corpus[start_idx:]
    if remaining:
        server = IsolatedServer(clone, data_root, settings_path)
        absorbed_before = absorbed_cycles_done(data_root)
        sha_before = server.current_sha()
        try:
            _log(f"starting isolated server on {server.base_url} …")
            server.start(ready_timeout=240)
            for pos, rec in enumerate(remaining, 1):
                i = start_idx + pos
                if absorbed_cycles_done(data_root) - absorbed_before >= args.max_absorbed:
                    _log(f"达到吸收周期上限 {args.max_absorbed}，提前停止喂料（剩余 {len(remaining) - pos + 1} 条）")
                    break
                try:
                    task_dict = {"id": rec["id"], "text": rec["task"], "drive_root": str(data_root)}
                    llm_trace = load_trace_from_path(rec["trace_ref"], base_dir=args.corpus.parent)
                    # 语料 trace 自带生产持久化的 trace_summary；空（旧语料）时才本地合成。
                    trace_summary = str(llm_trace.get("trace_summary") or "").strip()
                    if not trace_summary:
                        trace_summary = build_trace_summary(llm_trace)
                    usage_dict = trace_usage_dict(llm_trace)
                    reflection_entry = generate_reflection(
                        task=task_dict, llm_trace=llm_trace, trace_summary=trace_summary,
                        llm_client=llm_client, usage_dict=usage_dict,
                        review_evidence=trace_review_evidence(llm_trace),
                    )
                    # 生产 reflection 出参键是 memory_actions / backlog_candidates /
                    # reflection（MEMORY_ACTIONS_JSON/BACKLOG_CANDIDATES_JSON 只是
                    # prompt 里的行标记，不在 entry 上）。
                    mem_actions = reflection_entry.get("memory_actions") or []
                    if mem_actions:
                        apply_memory_actions(env, mem_actions)
                    backlog = reflection_entry.get("backlog_candidates") or []
                    if backlog:
                        append_backlog_items(data_root, backlog)
                    decision = maybe_promote(env, task_dict, reflection_entry, llm_client)
                    _log(f"record {i:2d}/{len(corpus)} {rec['id']}: "
                         f"reflection={len(str(reflection_entry.get('reflection', '')))}字 "
                         f"rounds={usage_dict.get('rounds')} mem={len(mem_actions)} "
                         f"backlog={len(backlog)} promote={bool(decision)}")
                    poll_campaign_progress(data_root, timeout_sec=args.campaign_timeout)
                    snapshot_checkpoint_summary(data_root)
                except Exception as exc:  # noqa: BLE001 - per-record fault isolation
                    _log(f"record {i:2d}/{len(corpus)} {rec['id']}: ✗ 失败: {exc}")
                    progress.setdefault("failures", []).append({"id": rec["id"], "error": str(exc)})
                progress["last_index"] = i
                progress["records_processed"] = i
                progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            # Wait for the in-flight campaign before stopping (§10.8-5: the server must
            # stay up across the whole corpus; stop only after the last campaign).
            try:
                server.wait_for_absorb(prev_sha=sha_before, prev_absorbed=absorbed_before, timeout=1800)
            except Exception as exc:  # noqa: BLE001
                _log(f"wait_for_absorb: {exc}")
            server.stop()
    else:
        _log("所有语料已在先前会话处理完毕（进度文件），跳过喂料直接收尾")

    # §10.7 snapshot + ledger
    rc, _ = _git(["tag", f"{args.arm}-evolved"], clone)
    rc2, commits = _git(["log", "--oneline", f"{progress.get('sha_start', sha_start)}..HEAD"], clone)
    rows = checkpoint_rows(data_root)
    cycles = [r for r in rows if r.get("kind") == "cycle_outcome"]
    from collections import Counter
    dist = Counter(r.get("cycle_outcome") for r in cycles)
    ledger = {
        "arm": args.arm,
        "tag": f"{args.arm}-evolved",
        "corpus": str(args.corpus),
        "corpus_completed": len(corpus),
        "records_processed": progress.get("records_processed", 0),
        "records_failed": progress.get("failures", []),
        "resumed": resume,
        "cycle_outcome_counts": dict(dist),
        "absorbed_count": dist.get("absorbed", 0),
        "abandoned_count": dist.get("abandoned", 0),
        "no_op_count": dist.get("no_op", 0),
        "total_cost_usd": round(sum(r.get("cost_usd", 0) or 0 for r in cycles), 2),
        "absorbed_commit_shas": [r.get("commit_sha") for r in cycles if r.get("cycle_outcome") == "absorbed"],
        "session_clone_head": _git(["rev-parse", "--short", "HEAD"], clone)[1].strip(),
        "log_file": str(session_dir / "run_evolution_arm.log"),
    }
    (session_dir / "session_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    if _LOG_FH is not None:
        _LOG_FH.close()
    _log(f"ledger: {session_dir / 'session_ledger.json'}")
    _log(f"吸收 commit（{args.arm}-evolved tag 相对起点）: {commits.strip() or '(无)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())