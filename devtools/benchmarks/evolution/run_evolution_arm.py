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
import datetime as _dt
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

# spec §3.3 + 战役执行契约（实验适配：战役任务在无项目作用域的隔离环境运行）
PERSISTENT_OBJECTIVE = (
    "改进通用执行策略：工具选择、错误恢复、上下文运用与结果验证；"
    "改进必须对任务难度和任务形态无关地成立（跨 coding/research/knowledge/simple 均有效），"
    "拒绝只对单一任务类型有效的特化技巧。"
    "（战役执行契约：你的任务必须落地为本仓库的实际代码修改并 git 提交——"
    "用 edit_batch/write_file 实施改动，运行相关测试验证，最后提交；"
    "仅调研、写知识或记录里程碑不构成完成。"
    "本任务运行在无项目作用域的实验环境：不要调用 journal_write/journal_read/"
    "workpad_read 等需要 project scope 的工具；里程碑记录改用 knowledge_write "
    "或 scratchpad_write。）"
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

# 战役执行契约（实验适配）：追加到 promote 请求的 objective 文本里，战役 agent
# 的任务描述由此携带契约。持久目标里的同名文案只进决策 prompt，不会进 objective。
_CAMPAIGN_CONTRACT_SUFFIX = (
    "\n\n（战役执行契约：你的任务必须落地为本仓库的实际代码修改并 git 提交——"
    "用 edit_batch/write_file 实施改动，运行相关测试验证，最后提交；"
    "仅调研、写知识或记录里程碑不构成完成。"
    "本任务运行在无项目作用域的实验环境：不要调用 journal_write/journal_read/"
    "workpad_read 等需要 project scope 的工具；里程碑记录改用 knowledge_write "
    "或 scratchpad_write。）"
)


def _augment_request_contract(data_root: pathlib.Path) -> None:
    """给 durable promote 请求追加执行契约（supervisor 消费前调用，幂等）。"""
    p = data_root / _REQUEST_FILE
    if not p.is_file():
        return
    try:
        req = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    obj = str(req.get("objective") or "")
    if not obj or "战役执行契约" in obj:
        return
    req["objective"] = obj + _CAMPAIGN_CONTRACT_SUFFIX
    try:
        from ouroboros.utils import atomic_write_json
        atomic_write_json(p, req)
    except Exception:  # noqa: BLE001 - best-effort; supervisor tick may already consume
        pass


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


# ---------------------------------------------------------------------------
# seeding + deployment plan (PAPER Phase 3, skill evolution in offline arms)
# ---------------------------------------------------------------------------

_SEED_STATE_FILE = "state/seeded_tasks.json"


def _seed_trace_rows(data_root: pathlib.Path, rec: dict, trace: dict, *, dry: bool = False) -> int:
    """把语料 trace 的 tool_calls 以生产行 schema 写进会话 drive 的
    ``logs/tools.jsonl``（task_id = rec["id"]）。

    离线回放不重跑 GAIA 任务，会话 tools.jsonl 本为空——Track A 经验学习
    （load_task_steps by task_id）与技能自动生成（≥5 步 + 自修复 + 成功）
    读的都是这个文件；不种子化则 V2/V3 的技能板块在离线臂里是死代码。
    幂等：按 state/seeded_tasks.json 记录已 seed 的 task_id（resume 兼容）。
    ``dry=True`` 只返回行数不写盘。返回写入/应写行数。
    """
    calls = trace.get("tool_calls") or []
    n = len(calls)
    if dry:
        return n
    seeded_state_path = data_root / _SEED_STATE_FILE
    seeded = {}
    if seeded_state_path.is_file():
        try:
            seeded = json.loads(seeded_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            seeded = {}
    if rec["id"] in seeded:
        return int(seeded[rec["id"]].get("n", n))
    base_ts = str(rec.get("started_at") or "")
    lines = []
    for i, c in enumerate(calls):
        is_err = bool(c.get("is_error"))
        status = str(c.get("status") or ("error" if is_err else "ok"))
        preview = str(c.get("result") or c.get("result_preview") or "")
        if len(preview) > 2000:
            preview = preview[:2000] + f"\n...(truncated from {len(str(c.get('result') or ''))} chars)"
        row = {
            "ts": base_ts,
            "type": "tool_call",
            "tool": str(c.get("tool") or ""),
            "task_id": rec["id"],
            "args": c.get("args") or {},
            "result_preview": preview,
            "result_ref": c.get("trace_ref") or {},
            "is_error": is_err,
            "status": status,
            "tool_call_id": str(c.get("tool_call_id") or ""),
            "round_id": i + 1,
            "task_depth": 0,
        }
        lines.append(json.dumps(row, ensure_ascii=False))
    logs_path = data_root / "logs" / "tools.jsonl"
    logs_path.parent.mkdir(parents=True, exist_ok=True)
    with logs_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    seeded[rec["id"]] = {"ts": base_ts, "n": n}
    seeded_state_path.parent.mkdir(parents=True, exist_ok=True)
    seeded_state_path.write_text(json.dumps(seeded, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


def _deploy_plan(data_root: pathlib.Path, deploy_tasks_path: pathlib.Path, *, dry: bool = True) -> dict:
    """部署期计划预检：加载固定部署任务集（V2/V3 同集同序），检查工作区
    资产（make_assets.py 产物 + manifest），扫描会话内已生成/待背书的技能，
    打印部署编排信息。dry=True 不做任何真实执行。"""
    plan = {"deploy_tasks": str(deploy_tasks_path), "loadable": False, "tasks": 0, "hard_cases": 0,
            "pending_skills": 0, "skills": [], "assets_ready": False,
            "asset_files": 0, "note": ""}
    if not deploy_tasks_path.is_file():
        plan["note"] = f"deploy_tasks.json 不存在（{deploy_tasks_path}），部署期跳过（不影响回放）"
        return plan
    try:
        data = json.loads(deploy_tasks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        plan["note"] = f"deploy_tasks.json 解析失败: {exc}"
        return plan
    plan["loadable"] = True
    shared = data.get("shared") or []
    plan["tasks"] = len(shared)
    plan["hard_cases"] = sum(1 for t in shared if str(t.get("difficulty", "")).lower().startswith("hard"))
    assets_dir = deploy_tasks_path.parent / "assets"
    manifest = assets_dir / "manifest.json"
    if manifest.is_file():
        try:
            mf = json.loads(manifest.read_text(encoding="utf-8"))
            plan["assets_ready"] = True
            plan["asset_files"] = len(mf.get("files") or {})
        except (json.JSONDecodeError, OSError):
            plan["note"] = "assets/manifest.json 存在但解析失败（先跑 make_assets.py）"
    else:
        plan["note"] = "工作区资产未生成（先跑 deploy_tasks/make_assets.py）；将降级为极简示例输入"
    skills_root = data_root / "skills" / "self" if data_root is not None else None
    if skills_root is not None and skills_root.is_dir():
        for d in sorted(skills_root.iterdir()):
            if d.is_dir() and (d / ".self_authored.json").is_file():
                attested = (data_root / "state" / "skills" / d.name / "owner_attestation.json").is_file()
                plan["skills"].append({"name": d.name, "attested": attested})
                plan["pending_skills"] += 1 if not attested else 0
    return plan


_DEPLOY_FIXTURES = {
    # 部署任务预置的最小输入（工作区示例文件）。任务文本假设输入存在，
    # 执行前按 task id 建好，保证真实文件操作可发生。
    "deploy-01": {"fixtures": {"a.txt": "line1\n\nline3\n\n", "b.txt": "x\n\ny\n"}, "dirs": []},
    "deploy-02": {"fixtures": {"data.csv": "name,count\nAlice,3\nbob,7\n\nCarol,2\n"}, "dirs": []},
    "deploy-05": {"fixtures": {"a.jpg": b"\xff\xd8\xff\xe0", "b.jpg": b"\xff\xd8\xff\xe1"}, "dirs": ["images"]},
    "deploy-06": {"fixtures": {"app.log": "INFO ok\nERROR 503\nERROR 404\nINFO fine\nERROR 503\n"}, "dirs": []},
    "deploy-08": {"fixtures": {"d1.json": '{"n": 1}', "d2.json": '{"n": 2}'}, "dirs": ["data"]},
    "deploy-09": {"fixtures": {"sentences.txt": "hello world\nsecond line\n"}, "dirs": []},
    "deploy-11": {"fixtures": {}, "dirs": ["arch"]},
    "deploy-12": {"fixtures": {"url_links.txt": "https://a.com/x\nhttps://b.com/y\nhttps://a.com/z\n"}, "dirs": []},
}


_HARD_VARIANTS = {
    # 刁钻用例 = 对应 shared 资产的变换：None=空工作区；(base_id, extra)=拷贝该资产并追加特殊文件
    "deploy-hard-empty": None,
    "deploy-hard-oversize": ("deploy-03", "oversize.bin"),
    "deploy-hard-illformed": ("deploy-08", "entry_broken.json"),
}


def _copy_asset(src_dir: pathlib.Path, ws_dir: pathlib.Path) -> None:
    """把资产目录内容原样拷入工作区（保持相对结构）。"""
    for p in src_dir.rglob("*"):
        if p.is_file():
            dst = ws_dir / p.relative_to(src_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(p.read_bytes())


def _gen_fallback_fixtures(ws_dir: pathlib.Path, task_id: str) -> None:
    """资产缺失时的降级：极简示例输入（保证任务委托成立）。"""
    spec = _DEPLOY_FIXTURES.get(task_id)
    if not spec:
        return
    for d in spec["dirs"]:
        (ws_dir / d).mkdir(parents=True, exist_ok=True)
    for fname, content in spec["fixtures"].items():
        p = ws_dir / fname
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")


def _deploy_ws_setup(ws_dir: pathlib.Path, task_id: str, assets_dir: pathlib.Path | None = None) -> None:
    """为部署任务建工作区：优先拷贝 assets/<task_id>/ 的逼真输入（中等复杂度档，
    由 make_assets.py 确定性生成）；hard 变体在对应资产上做空/超长/坏编码变换；
    资产缺失时降级为极简示例输入。"""
    ws_dir.mkdir(parents=True, exist_ok=True)
    # workspace_admission 要求任务工作区必须是 git worktree 根（否则 POST /api/tasks
    # 返回 400）：对专用部署工作区 git init，使其成为合法 worktree（实验会话内
    # 目录，不影响其他任何仓库）。
    try:
        subprocess.run(["git", "init", "-q"], cwd=str(ws_dir), capture_output=True, timeout=15)
    except Exception:  # noqa: BLE001 - 若 git init 失败，提交时 400 会如实记录
        pass
    if task_id in _HARD_VARIANTS:
        variant = _HARD_VARIANTS[task_id]
        if variant is None:
            return  # 空工作区（输入目录不存在场景）
        base_id, extra = variant
        if assets_dir is not None and (assets_dir / base_id).is_dir():
            _copy_asset(assets_dir / base_id, ws_dir)
        else:
            _gen_fallback_fixtures(ws_dir, base_id)
        if extra == "oversize.bin":
            (ws_dir / extra).write_bytes(b"0" * (21 * 1024 * 1024))           # >20MB
        elif extra == "entry_broken.json":
            (ws_dir / extra).write_bytes(b"\xff\xfe\x00\x01" * 8 + b"{broken json")  # 非 UTF-8 损坏编码
        return
    if assets_dir is not None and (assets_dir / task_id).is_dir():
        _copy_asset(assets_dir / task_id, ws_dir)
        return
    _gen_fallback_fixtures(ws_dir, task_id)


def _attest_skill(data_root: pathlib.Path, skill_dir: pathlib.Path) -> bool:
    """owner 背书：写 owner_attestation.json + review.json（owner_attested、
    status=clean、绑定当前内容哈希）。复用产品既有背书路径（skill_loader
    校验：marker 存在即 verdict 有效；内容哈希保证审查与内容一致）。"""
    from ouroboros.skill_loader import (SkillReviewState, compute_content_hash,
                                        save_review_state, skill_state_dir)
    name = skill_dir.name
    st_dir = skill_state_dir(data_root, name)
    if (st_dir / "owner_attestation.json").is_file():
        return False
    h = compute_content_hash(skill_dir)
    save_review_state(data_root, name, SkillReviewState(
        status="clean",
        content_hash=h,
        reviewer_models=["experiment-operator"],
        review_profile="owner_attested",
    ))
    st_dir.mkdir(parents=True, exist_ok=True)
    (st_dir / "owner_attestation.json").write_text(json.dumps({
        "attested_by": "experiment_operator",
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "note": "deploy-phase owner attestation (experiment)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _run_deploy_phase(server, data_root: pathlib.Path, deploy_tasks_path: pathlib.Path,
                      work_root: pathlib.Path, *, phase: str) -> dict:
    """部署期执行（V2/V3 进化期；V0/V1 无技能自动跳过）。

    phase="baseline"：背书新生成技能 → 用原始版本跑固定部署任务集（前测）；
    phase="post"：技能 evolution_version 提升后对变异版 rerun 同一任务集（后测）。
    执行经 server.submit 在隔离服务器内真实运行，产出真实 skill_exec 行 →
    会话 tools.jsonl → skill_stats 账本；前后测对比与 GEPA 决策记录到
    <data_root>/state/deploy_log.jsonl。GEPA 变异本身沿用管线 nudge 节律，
    本函数不直接调用进化器。
    """
    plan = _deploy_plan(data_root, deploy_tasks_path, dry=False)
    summary = {"phase": phase, "skills": [], "runs": 0, "note": ""}
    if not plan["loadable"]:
        summary["note"] = plan["note"]
        return summary
    data = json.loads(deploy_tasks_path.read_text(encoding="utf-8")) or {}
    shared = data.get("shared") or []
    skills_root = data_root / "skills" / "self"
    if not skills_root.is_dir():
        summary["note"] = "无自写技能，部署期跳过"
        return summary
    deployable = []
    for d in sorted(skills_root.iterdir()):
        if d.is_dir() and (d / ".self_authored.json").is_file():
            deployable.append(d)
    if not deployable:
        summary["note"] = "无自写技能，部署期跳过"
        return summary
    if phase == "baseline":
        attested = [_attest_skill(data_root, d) for d in deployable]
        summary["skills"] = [d.name for d, ok in zip(deployable, attested)]
    else:
        summary["skills"] = [d.name for d in deployable]
    summary["note"] = f"skills={summary['skills']}"
    log_entries = []
    for d in deployable:
        name = d.name
        for t in shared:
            text = str(t["text"]).replace("<name>", name)
            ws = work_root / f"{phase}-{name}-{t['id']}"
            _deploy_ws_setup(ws, str(t["id"]), assets_dir=deploy_tasks_path.parent / "assets")
            try:
                tid = server.submit(text, workspace_root=str(ws), timeout_sec=1500)
                res = server.wait_task(tid, timeout=1500)
                summary["runs"] += 1
                status = str(res.get("status") or "")
                log_entries.append({"phase": phase, "skill": name, "task": t["id"],
                                    "status": status, "task_id": str(tid)})
            except Exception as exc:  # noqa: BLE001 - per-task fault isolation
                log_entries.append({"phase": phase, "skill": name, "task": t["id"],
                                    "status": "driver_error", "error": str(exc)})
    deploy_log = data_root / "state" / "deploy_log.jsonl"
    deploy_log.parent.mkdir(parents=True, exist_ok=True)
    with deploy_log.open("a", encoding="utf-8", newline="\n") as fh:
        for e in log_entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return summary




def _run_deploy_window(server, data_root: pathlib.Path, deploy_tasks_path: pathlib.Path,
                       work_root: pathlib.Path) -> dict:
    """统一部署窗口（语料喂完 + 最后一个战役落账后执行；幂等）。

    状态机（state/deploy_state.json）：
      phase=none    → baseline：背书全部未背书技能 + 前测任务集，记录初始版本；
      phase=baseline→ post：检测到技能 evolution_version 提升后，对变异版 rerun 同一任务集；
      phase=post    → 不再动作。
    GEPA 变异由 nudge 节律驱动（不在本窗口直接调用）；变异若发生在窗口执行之后，
    post 段由下一次 --resume 会话的窗口补做（每次会话收尾都会调用本窗口）。
    """
    dep_state_path = data_root / "state" / "deploy_state.json"
    dep_state = {}
    if dep_state_path.is_file():
        try:
            dep_state = json.loads(dep_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dep_state = {}
    phase = dep_state.get("phase", "none")
    versions = dep_state.get("versions", {})
    if phase == "none":
        dep = _run_deploy_phase(server, data_root, deploy_tasks_path, work_root, phase="baseline")
        _log(f"部署窗口 baseline: {dep['note']} runs={dep['runs']}")
        if dep["skills"]:
            stats_path = data_root / "state" / "skill_stats.json"
            stats = {}
            if stats_path.is_file():
                try:
                    stats = json.loads(stats_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    stats = {}
            initial = {name: int((stats.get(name) or {}).get("evolution_version", 0))
                       for name in dep["skills"]}
            dep_state = {"phase": "baseline", "versions": initial}
    elif phase == "baseline":
        stats_path = data_root / "state" / "skill_stats.json"
        stats = {}
        if stats_path.is_file():
            try:
                stats = json.loads(stats_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                stats = {}
        evolved = {name: int(s.get("evolution_version", 0))
                   for name, s in stats.items()
                   if isinstance(s, dict) and s.get("evolution_version") != versions.get(name)}
        if evolved:
            dep = _run_deploy_phase(server, data_root, deploy_tasks_path, work_root, phase="post")
            _log(f"部署窗口 post: skills={sorted(evolved)} runs={dep['runs']}")
            dep_state = {"phase": "post", "versions": versions}
    dep_state_path.parent.mkdir(parents=True, exist_ok=True)
    dep_state_path.write_text(json.dumps(dep_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return dep_state


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
    ap.add_argument("--campaign-timeout", type=float, default=600.0,
                    help="Seconds to poll for one campaign cycle after each promote")
    ap.add_argument("--max-absorbed", type=int, default=10, help="Stop feeding after N absorbed cycles (spec §3.5)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate corpus→trace→pipeline wiring at zero LLM cost (no server, no LLM calls)")
    ap.add_argument("--deploy-tasks", type=pathlib.Path,
                    default=REPO_DIR / "devtools" / "benchmarks" / "evolution" / "deploy_tasks" / "deploy_tasks.json",
                    help="(V2/V3) 部署期固定任务集清单（同集同序；spec 部署期设计）")
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
        seeded_total = 0
        zero_tool = 0
        for i, rec in enumerate(corpus, 1):
            try:
                trace = load_trace_from_path(rec["trace_ref"], base_dir=args.corpus.parent)
                n = len(trace.get("tool_calls") or [])
                n_seed = _seed_trace_rows(args.session_dir / "data", rec, trace, dry=True)
                n_notes = len(trace.get("reasoning_notes") or [])
                usage = trace_usage_dict(trace)
                summary = str(trace.get("trace_summary") or "").strip() or build_trace_summary(trace)
                if n == 0:
                    # 零工具直接作答任务：合法（无工具轨迹但保留反思文本），标注而非失败
                    status = "✓ zero-tool"
                    zero_tool += 1
                else:
                    status = "✓"
                seeded_total += n_seed
                if n_notes:
                    notes_covered += 1
                if usage.get("rounds") is not None:
                    usage_covered += 1
                _log(f"dry-run {i:2d}/{len(corpus)} {rec['id']}: tool_calls={n} "
                     f"notes={n_notes} rounds={usage.get('rounds')} "
                     f"summary={len(summary)} seed={n_seed} 失败={not rec['outcome']['passed']} {status}")
            except Exception as exc:  # noqa: BLE001 - report any wiring error
                _log(f"dry-run {i:2d}/{len(corpus)} {rec['id']}: ✗ {exc}")
                ok = False
        plan = _deploy_plan(args.session_dir / "data", args.deploy_tasks, dry=True)
        _log(f"部署期预检: tasks={plan['tasks']}（hard={plan['hard_cases']}）loadable={plan['loadable']} "
             f"assets={plan['assets_ready']}（{plan['asset_files']} 文件）"
             + (f"；{plan['note']}" if plan["note"] else ""))
        _log(f"dry-run 完成（未启动服务器、未调用 LLM）: reasoning_notes 覆盖 {notes_covered}/{len(corpus)}，"
             f"usage(rounds) 覆盖 {usage_covered}/{len(corpus)}，seed 应写 {seeded_total} 行，"
             f"zero-tool 标注 {zero_tool}" + (" ✅" if ok else " ❌ 有失败项"))
        return 0 if ok else 1

    session_dir = args.session_dir.resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
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
    # Driver 进程的开关 getter（get_post_task_evolution_enabled / get_runtime_mode /
    # *ARM* switches）读的是环境变量而非 settings 文件 —— 不注入则 maybe_promote
    # 在第一道门就短路，promote 决策与技能进化块整场不执行。外部显式环境变量优先。
    os.environ.setdefault("OUROBOROS_POST_TASK_EVOLUTION", "true")
    os.environ.setdefault("OUROBOROS_RUNTIME_MODE", "advanced")
    for _env_key, _env_val in ARM_SWITCHES.get(args.arm.upper(), {}).items():
        os.environ.setdefault(_env_key, _env_val)
    # 旁模型一致性：ouroboros 的模型 getter 只读环境变量（缺失回退默认 grok-4.5），
    # 而隔离服务器读 settings 文件。两者必须指向同一模型（实验全程单模型约束），
    # 否则 driver 侧反思/决策/技能与服务器侧战役/部署会混用模型。
    _live_cfg_ref = {}
    if args.live_settings is not None and args.live_settings.is_file():
        try:
            _live_cfg_ref = json.loads(args.live_settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _live_cfg_ref = {}
    _model_keys = ("OUROBOROS_MODEL", "OUROBOROS_MODEL_LIGHT", "OUROBOROS_MODEL_HEAVY",
                   "OUROBOROS_MODEL_FALLBACK", "OUROBOROS_MODEL_REVIEW")
    for _k in _model_keys:
        if not os.environ.get(_k) and _live_cfg_ref.get(_k):
            os.environ[_k] = str(_live_cfg_ref[_k])
    from ouroboros.config import _main_model, get_light_model, get_heavy_model

    _m_main, _m_light, _m_heavy = _main_model(), get_light_model(), get_heavy_model()
    _m_cfg = str(_live_cfg_ref.get("OUROBOROS_MODEL") or "")
    if _m_cfg and _m_main != _m_cfg:
        _log(f"警告: driver 主模型 {_m_main} 与 live settings 的 {_m_cfg} 不一致，"
             f"请通过 .env/环境变量显式设置 OUROBOROS_MODEL 后重跑")
    _log(f"模型槽位: main={_m_main} light={_m_light} heavy={_m_heavy}")

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
                    # 种子化：把语料轨迹行写入会话 tools.jsonl（Track A 经验学习
                    # 与技能生成读此文件；幂等、resume 安全）。
                    try:
                        seeded = _seed_trace_rows(data_root, rec, llm_trace)
                    except Exception as exc:  # noqa: BLE001 - seeding must not kill the record
                        _log(f"record {i:2d}/{len(corpus)} {rec['id']}: 种子化失败（不影响回放）: {exc}")
                        seeded = 0
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
                    if decision:
                        _augment_request_contract(data_root)  # 战役执行契约注入 objective
                    _log(f"record {i:2d}/{len(corpus)} {rec['id']}: "
                         f"reflection={len(str(reflection_entry.get('reflection', '')))}字 "
                         f"rounds={usage_dict.get('rounds')} mem={len(mem_actions)} "
                         f"backlog={len(backlog)} seed={seeded} promote={bool(decision)}")
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
            # 统一部署窗口（V2/V3）：语料喂完 + 最后一个战役落账后执行
            # （含 max-absorbed / 预算触发提前停机的收尾路径）。幂等：phase=post 后不再动作。
            if args.arm in ("V2", "V3"):
                try:
                    _run_deploy_window(server, data_root, args.deploy_tasks, session_dir / "deploy_ws")
                except Exception as exc:  # noqa: BLE001 - deploy window must not kill teardown
                    _log(f"部署窗口失败（不影响收尾）: {exc}")
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