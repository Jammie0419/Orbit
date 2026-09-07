#!/usr/bin/env python3
"""进化产物三层分析器（只读，不修改 session）。

三层：
  ① 通用对比 —— V0 与 V3 共有层面的指标（任务执行遥测：工具调用/失败率/
      模型调用/上下文量），两者都跑任务故都产出，可直接算差值；
  ② V3 特有产物 —— 仅进化开启才有的产物（吸收提交、技能生成/变异、信用、
      经验、路由分支、战役、评审闸门）；
  ③ 按轮次递增 —— 以语料记录序为轮次轴，逐轮累积输出：
        通用面：V0(V3) 累积工具调用/失败；
        V3 特有：累积吸收提交/技能/信用/经验/战役/模型调用。

用法：
  python analyze_evolution_products.py --v3-dir <smoke_test> [--v0-dir <v0_session>] [--out md]
V0 缺省时，通用面对比列与按轮次 V0 列标注"需 V0 跑"。
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter

# ---------- 基础 IO ----------
def _load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]

def _load_json(p: pathlib.Path):
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def _state(d: pathlib.Path) -> pathlib.Path:
    return d / "data" / "state"

def _logs(d: pathlib.Path) -> pathlib.Path:
    return d / "data" / "logs"


# ---------- 通用面（V0/V3 共有：任务执行遥测） ----------
def common_metrics(d: pathlib.Path) -> dict:
    tools = _load_jsonl(_logs(d) / "tools.jsonl")
    usage = _load_jsonl(_state(d) / "usage_attempts.jsonl")
    calls = len(tools)
    errs = sum(1 for t in tools if str(t.get("is_error")) == "True")
    ctx_list = [int(t.get("candidate_context_size_bytes") or 0) for t in usage]
    ctx = sum(ctx_list)
    # 工具信封 / 自恢复 / 步数
    distinct_tools = len({t.get("tool") for t in tools})
    task_ids = {t.get("task_id") for t in tools if t.get("task_id")}
    steps_per_task = round(calls / len(task_ids), 2) if task_ids else None
    # 自恢复：同 (task,tool) 先错后成功
    last_err = {}
    recovered = 0
    for t in sorted(tools, key=lambda r: r.get("ts", "")):
        key = (t.get("task_id"), t.get("tool"))
        is_err = str(t.get("is_error")) == "True"
        if is_err:
            last_err[key] = True
        elif last_err.get(key):
            recovered += 1
            last_err[key] = False
    recovery_rate = round(recovered / errs, 3) if errs else None
    # 技能调用次数（桥接：V0=0，V3>0 表示技能在任务侧生效）
    skill_names = {r.get("skill_name") for r in _load_jsonl(_state(d) / "skill_generation_history.jsonl")
                   if r.get("outcome") == "created" and r.get("skill_name")}
    skill_invocations = sum(1 for t in tools if t.get("tool") in skill_names)
    # C/D 层：经验内错误步率、自修复次数/任务、反思条数
    ee = _load_jsonl(_state(d) / "evolution_experiences.jsonl")
    est = eerr = 0
    for r in ee:
        st = r.get("steps")
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except (json.JSONDecodeError, TypeError):
                st = []
        if isinstance(st, list):
            est += len(st)
            eerr += sum(1 for s in st if s.get("is_error"))
    error_step_rate = round(eerr / est, 3) if est else None
    corpus_tools = [t for t in tools if str(t.get("task_id", "")).startswith("2023_")]
    per_corpus_task_calls = (round(len(corpus_tools) / max(1, len({t["task_id"] for t in corpus_tools})), 1)
                             if corpus_tools else None)
    self_repair_per_task = round(recovered / len(task_ids), 3) if task_ids else None
    reflection_count = len(_load_jsonl(_state(d) / "task_reflections.jsonl"))
    model_by_category = dict(Counter(t.get("category") for t in usage))
    return {
        "tool_calls": calls,
        "tool_errors": errs,
        "tool_failure_rate": round(errs / calls, 3) if calls else None,
        "tool_error_recovery_rate": recovery_rate,
        "distinct_tools": distinct_tools,
        "steps_per_task": steps_per_task,
        "per_corpus_task_calls": per_corpus_task_calls,
        "skill_invocations": skill_invocations,
        "model_calls": len(usage),
        "model_by_category": model_by_category,
        "context_mb": round(ctx / 1024 / 1024, 1),
        "avg_context_kb": round(sum(ctx_list) / len(ctx_list) / 1024, 1) if ctx_list else None,
        "error_step_rate": error_step_rate,
        "self_repair_per_task": self_repair_per_task,
        "reflection_count": reflection_count,
    }


# ---------- V3 特有产物 ----------
def v3_unique(d: pathlib.Path) -> dict:
    st = _state(d)
    sg = _load_jsonl(st / "skill_generation_history.jsonl")
    sc = _load_jsonl(st / "step_credits.jsonl")
    ee = _load_jsonl(st / "evolution_experiences.jsonl")
    rh = _load_jsonl(st / "routing_history.jsonl")
    cp = _load_jsonl(st / "evolution_checkpoints.jsonl")
    ec = _load_json(st / "evolution_campaign.json")
    ar = _load_json(st / "advisory_review.json")
    # 吸收提交：campaign 的 absorbed_cycles_done + checkpoint cycle_outcome=absorbed
    absorbed = int(ec.get("absorbed_cycles_done") or 0)
    absorbed += sum(1 for r in cp if _cycle_outcome(r) == "absorbed")
    cycles = int(ec.get("cycles_done") or 0) or len(cp)
    runs = ar.get("advisory_runs") or []
    adv = dict(Counter(r.get("status") for r in runs)) if isinstance(runs, list) else None
    return {
        "absorbed_commits": absorbed,
        "cycles_done": cycles,
        "absorption_rate": round(absorbed / cycles, 3) if cycles else None,
        "skills_generated": sum(1 for r in sg if r.get("outcome") == "created"),
        "skills_failed": sum(1 for r in sg if r.get("outcome") != "created"),
        "skill_fail_reasons": [{"task_id": r.get("task_id"), "reason": r.get("reason")}
                                for r in sg if r.get("outcome") != "created"],
        "credits": len(sc),
        "credit_roles": dict(Counter(r.get("role") for r in sc)),
        "experiences": len(ee),
        "routing_branches": dict(Counter(r.get("branch") for r in rh)),
        "advisory_status": adv,
        "commit_readiness_debts": len(ar.get("commit_readiness_debts") or []),
    }


def _cycle_outcome(r: dict) -> str | None:
    tx = r.get("transaction")
    if isinstance(tx, str):
        try:
            tx = json.loads(tx)
        except (json.JSONDecodeError, TypeError):
            return None
    return tx.get("cycle_outcome") if isinstance(tx, dict) else None


# ---------- 按轮次递增 ----------
def _ordered_corpus_tasks(d: pathlib.Path) -> list[str]:
    """V3 特有产物里带语料 task_id（2023_*）的文件，按最早 ts 排序。"""
    st = _state(d)
    tasks: dict[str, str] = {}
    for name in ("evolution_experiences.jsonl", "step_credits.jsonl", "skill_generation_history.jsonl"):
        for r in _load_jsonl(st / name):
            tid = r.get("task_id")
            if not tid or not str(tid).startswith("2023_"):
                continue
            ts = r.get("ts", "")
            if tid not in tasks or ts < tasks[tid]:
                tasks[tid] = ts
    return sorted(tasks, key=lambda t: tasks[t])


def per_round(d: pathlib.Path, every_n: int = 5) -> list[dict]:
    """按 cadence 分组：每 every_n 条记录为一轮，输出累积值与本轮增量 Δ。"""
    st = _state(d)
    lg = _logs(d)
    tasks = _ordered_corpus_tasks(d)
    skills_by = Counter()
    skillfail_by = Counter()
    cred_by = Counter()
    exp_by = Counter()
    for r in _load_jsonl(st / "skill_generation_history.jsonl"):
        if not str(r.get("task_id", "")).startswith("2023_"):
            continue
        if r.get("outcome") == "created":
            skills_by[r["task_id"]] += 1
        else:
            skillfail_by[r["task_id"]] += 1
    for r in _load_jsonl(st / "step_credits.jsonl"):
        if str(r.get("task_id", "")).startswith("2023_"):
            cred_by[r["task_id"]] += 1
    for r in _load_jsonl(st / "evolution_experiences.jsonl"):
        if str(r.get("task_id", "")).startswith("2023_"):
            exp_by[r["task_id"]] += 1
    cps = sorted(_load_jsonl(st / "evolution_checkpoints.jsonl"), key=lambda r: r.get("ts", ""))
    rhs = sorted(_load_jsonl(st / "routing_history.jsonl"), key=lambda r: r.get("ts", ""))
    usage = sorted(_load_jsonl(st / "usage_attempts.jsonl"), key=lambda r: r.get("ts", ""))
    tools = sorted(_load_jsonl(lg / "tools.jsonl"), key=lambda r: r.get("ts", ""))
    _adv_raw = _load_json(st / "advisory_review.json").get("advisory_runs") or []
    adv = sorted(_adv_raw, key=lambda r: r.get("ts", "")) if isinstance(_adv_raw, list) else []

    # 逐条累积
    recs = []
    cum = {"skills": 0, "skillfail": 0, "cred": 0, "exp": 0, "cyc": 0, "abs": 0,
           "branches": set(), "model": 0, "tool": 0, "tool_err": 0, "adv_stale": 0}
    i_cp = i_rh = i_us = i_tl = i_ad = 0
    for idx, tid in enumerate(tasks, 1):
        cum["skills"] += skills_by.get(tid, 0)
        cum["skillfail"] += skillfail_by.get(tid, 0)
        cum["cred"] += cred_by.get(tid, 0)
        cum["exp"] += exp_by.get(tid, 0)
        cur_ts = _min_ts_for(d, tid)
        def _le(ev, ts):
            return ev.get("ts", "") <= ts
        while i_cp < len(cps) and _le(cps[i_cp], cur_ts):
            cum["cyc"] += 1
            if _cycle_outcome(cps[i_cp]) == "absorbed":
                cum["abs"] += 1
            i_cp += 1
        while i_rh < len(rhs) and _le(rhs[i_rh], cur_ts):
            cum["branches"].add(rhs[i_rh].get("branch"))
            i_rh += 1
        while i_us < len(usage) and _le(usage[i_us], cur_ts):
            cum["model"] += 1
            i_us += 1
        while i_tl < len(tools) and _le(tools[i_tl], cur_ts):
            cum["tool"] += 1
            if str(tools[i_tl].get("is_error")) == "True":
                cum["tool_err"] += 1
            i_tl += 1
        while i_ad < len(adv) and _le(adv[i_ad], cur_ts):
            if adv[i_ad].get("status") == "stale":
                cum["adv_stale"] += 1
            i_ad += 1
        recs.append({"skills": cum["skills"], "skillfail": cum["skillfail"],
                      "cred": cum["cred"], "exp": cum["exp"], "cyc": cum["cyc"],
                      "abs": cum["abs"], "branches": len(cum["branches"]),
                      "model": cum["model"], "tool": cum["tool"],
                      "tool_err": cum["tool_err"], "adv_stale": cum["adv_stale"]})

    # 按 every_n 分组：每组末尾快照为累积，差值为 Δ
    keys = ["skills", "skillfail", "cred", "exp", "cyc", "abs", "branches",
            "model", "tool", "tool_err", "adv_stale"]
    rounds = []
    prev = {k: 0 for k in keys}
    for i in range(0, len(recs), every_n):
        chunk = recs[i:i + every_n]
        end = chunk[-1]
        delta = {k: end.get(k, 0) - prev.get(k, 0) for k in keys}
        rounds.append({
            "round": len(rounds) + 1,
            "records": f"{i + 1}-{i + len(chunk)}",
            "cum": {k: end.get(k, 0) for k in keys},
            "delta": delta,
        })
        prev = {k: end.get(k, 0) for k in keys}
    return rounds


def _min_ts_for(d: pathlib.Path, tid: str) -> str:
    st = _state(d)
    best = ""
    for name in ("evolution_experiences.jsonl", "step_credits.jsonl", "skill_generation_history.jsonl"):
        for r in _load_jsonl(st / name):
            if r.get("task_id") == tid:
                best = r.get("ts", "") if (not best or r.get("ts", "") < best) else best
    return best


# ---------- 渲染 ----------
def render(v3: pathlib.Path, v0: pathlib.Path | None, every_n: int = 5) -> str:
    L = []; A = L.append
    cm3 = common_metrics(v3); uv3 = v3_unique(v3)
    cm0 = common_metrics(v0) if v0 else None
    A("# 进化过程指标分析\n")
    # ① V0 基础进化指标（V0 ∩ V3 都有，两边共有的进化产物 + 质量）
    A("## ① V0 基础进化指标（V0 ∩ V3 共有）\n")
    A("| 指标 | V0 | V3 | 说明 |")
    A("|---|---|---|---|")
    def row(name, v0_val, v3_val, note=""):
        a = v0_val if v0_val is not None else "—"
        b = v3_val if v3_val is not None else "—"
        A(f"| {name} | {a} | {b} | {note} |")
    # promotion 信号
    _ec = _load_json(_state(v3) / "evolution_campaign.json")
    _cps = _load_jsonl(_state(v3) / "evolution_checkpoints.jsonl")
    _n_cps = len(_cps)
    _n_absorbed = sum(1 for r in _cps if _cycle_outcome(r) == "absorbed")
    _n_ok = sum(1 for r in _cps if (r.get("outcome_axes") or {}).get("execution",{}).get("status") == "ok")
    _n_degraded = sum(1 for r in _cps if (r.get("outcome_axes") or {}).get("execution",{}).get("status") == "degraded")
    row("promotion 信号数", "—", _n_cps, "V0 基础进化也产出，需V0会话填")
    row("信号消费率", "—", f"{round(_n_cps/max(1,_n_cps)*100)}%", "是否被战役消费")
    row("战役成功率", "—", f"{round(_n_absorbed/max(1,_n_cps)*100)}%", "吸收/总战役")
    row("执行 ok 率", "—", f"{round(_n_ok/max(1,_n_cps)*100)}%", "执行未降级的比例")
    row("执行 degraded 率", "—", f"{round(_n_degraded/max(1,_n_cps)*100)}%", "工具错误导致降级")
    row("战役平均轮数", "—", round(sum(int(r.get("rounds") or 0) for r in _cps)/max(1,_n_cps),1), "每战平均 agent 轮数")
    row("战役自恢复次数", "—", sum(len((r.get("outcome_axes") or {}).get("execution",{}).get("recoveries") or []) for r in _cps), "出错后自动恢复")
    # 任务反思
    row("任务反思条数", "—", cm3.get("reflection_count"), "V0/V3 都产出反思")
    # 代码变更
    row("代码变更提交数", "—", int(_ec.get("absorbed_cycles_done") or 0), "V0 基础进化也可产出少量")
    if not v0:
        A("\n> V0 列空缺：需一次全关开关的 V0 会话才能填。")
    A("")
    # ② V3 特有进化指标
    A("## ② V3 特有进化指标（仅进化开启才产生）\n")
    A(f"- 吸收提交数（代码文件变更）: **{uv3['absorbed_commits']}**（战役 {uv3['cycles_done']} 战，吸收率 {uv3['absorption_rate']}）")
    A(f"- 技能生成: **{uv3['skills_generated']}** 成功 / {uv3['skills_failed']} 失败"
      + (f"；失败原因 {uv3['skill_fail_reasons']}" if uv3['skill_fail_reasons'] else ""))
    A(f"- 信用条目: {uv3['credits']}（role={uv3['credit_roles']}）")
    A(f"- 经验条目: {uv3['experiences']}")
    A(f"- 路由分支覆盖: {uv3['routing_branches']}")
    A(f"- 评审闸门: status={uv3['advisory_status']}，commit_readiness_debts={uv3['commit_readiness_debts']}")
    # ③ 按 cadence 轮次
    A(f"\n## ③ 按轮次递增（每 {every_n} 条记录为一轮）\n")
    A("| 轮 | 记录范围 | [代码]吸收 Δ/cum | [技能]生成 Δ/cum | [技能]失败 Δ | "
      "[归因]信用 Δ/cum | [经验]经验 Δ | [路由]分支 | "
      "[多智]战役 Δ | [安全]stale Δ | [开销]模型 Δ/cum |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in per_round(v3, every_n=every_n):
        c, d = r["cum"], r["delta"]
        def _cc(key):
            dv, cv = d[key], c[key]
            return f"{dv}/{cv}" if dv else f"—/{cv}"
        A(f"| {r['round']} | {r['records']} | "
          f"{_cc('abs')} | {_cc('skills')} | {d['skillfail']} | "
          f"{_cc('cred')} | {d['exp']} | {d['branches']} | "
          f"{d['cyc']} | {d['adv_stale']} | {_cc('model')} |")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Three-layer evolution-product analysis (common / V3-unique / per-round).")
    ap.add_argument("--v3-dir", type=pathlib.Path, required=True)
    ap.add_argument("--v0-dir", type=pathlib.Path, default=None)
    ap.add_argument("--every-n", type=int, default=2, help="Cadence: 每 N 条记录为一轮（默认 2，匹配 smoke cadence）")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()
    if args.v0_dir and not args.v0_dir.is_dir():
        print("V0 目录不存在"); return 2
    rep = render(args.v3_dir, args.v0_dir, every_n=args.every_n)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rep, encoding="utf-8")
        print(f"report: {args.out}")
    else:
        print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
