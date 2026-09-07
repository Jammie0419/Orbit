#!/usr/bin/env python3
"""四臂会话观测汇总器：把一次进化会话的所有观测文件汇总为对比实验输出。

输入：--session-dir（一个臂的 session 目录，含 clone/ data/ session_ledger.json），
可多次传入（如 V0 与 V3）→ 输出逐臂报告 + 两臂对比表（Markdown/JSON）。

产出（论文表 4-3 / 图 4-1 的数据源）：
  1. 战役统计：cycle 终态分布、吸收数、总成本、每吸收提交成本；
  2. 吸收提交落点分类：按文件路径规则分 {工具, 循环, 提示/上下文, 路由/机制, 特化, 测试/其他}，
     输出"通用层占比"（表 4-3 核心指标之一）；
  3. 技能事件：生成/启用/变异/回滚/版本演进（skill_generation/evolution_history）；
  4. 技能前测/后测：deploy_log.jsonl + skill_stats.json 的成功率对照；
  5. 进化期间 silent 记录的路由/经验/记忆观测文件存在性盘点。

只读：不修改 session 目录。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
from collections import Counter, defaultdict

# 落点分类规则：吸收提交涉及的文件路径 → 类别（通用层组分）
_COMMON_PATTERNS = [
    ("工具实现/注册", ("ouroboros/tools", "tools/registry", "tool_policy", "skill_exec")),
    ("执行循环", ("loop_tool_execution", "tool_runner", "execution")),
    ("提示/上下文", ("context.py", "prompt", "sys_prompt", "context_layout")),
    ("路由/机制", ("smart_router", "harness_tree", "harness_configs", "memory_ext", "reflection.py")),
    ("任务循环", ("agent.py", "agent_task_pipeline", "post_task_evolution")),
]
_OTHER_PATTERNS = [("测试/工具", ("tests/", "devtools/", "benchmark", "docs/"))]


def classify_file(rel: str) -> str:
    for label, pats in _COMMON_PATTERNS:
        if any(p in rel for p in pats):
            return label
    for label, pats in _OTHER_PATTERNS:
        if any(p in rel for p in pats):
            return label
    return "特化/未分类"


def git_log_files(clone: pathlib.Path, sha_start: str) -> list[str]:
    """sha_start..HEAD 吸收提交涉及的文件清单（--name-only）。"""
    p = subprocess.run(["git", "log", "--name-only", "--format=%H %s",
                        f"{sha_start}..HEAD"], cwd=str(clone),
                       capture_output=True, text=True, timeout=60)
    out = p.stdout or ""
    files = []
    for line in out.splitlines():
        line = line.strip()
        # --name-only 输出：提交头是 "hash message"，文件行是路径
        if line and "/" in line:
            files.append(line)
    return list(dict.fromkeys(files))  # 去重保序


def _load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]


def _cycle_outcome(r: dict) -> str | None:
    tx = r.get("transaction")
    if isinstance(tx, str):
        try:
            tx = json.loads(tx)
        except (json.JSONDecodeError, TypeError):
            return None
    return tx.get("cycle_outcome") if isinstance(tx, dict) else None


def _deep_metrics(data_root: pathlib.Path) -> dict:
    """原始观测文件的深度指标：模型调用口径、战役执行失败模式、评审闸门、
    信用分配、路由分支、经验复杂度/错误步率、技能生成失败原因。
    这些是论文机制证据与排障的核心，session_ledger 不覆盖。"""
    st = data_root / "state"
    out: dict = {}
    # 1. 模型调用口径
    ua = _load_jsonl(st / "usage_attempts.jsonl")
    if ua:
        out["model_usage"] = {
            "total_calls": len(ua),
            "by_category": dict(Counter(r.get("category") for r in ua)),
            "by_model": dict(Counter(r.get("model") for r in ua)),
            "pricing_known": dict(Counter(str(r.get("pricing_known")) for r in ua)),
            "context_bytes": sum(int(r.get("candidate_context_size_bytes") or 0) for r in ua),
        }
    # 2. 战役执行失败模式
    cps = _load_jsonl(st / "evolution_checkpoints.jsonl")
    camp = []
    for r in cps:
        ax = r.get("outcome_axes", {}) or {}
        exe = ax.get("execution", {}) or {}
        fails = exe.get("failure") or {}
        tools = [f.get("tool") for f in (fails.get("tool_errors") or [])]
        tx = r.get("transaction")
        if isinstance(tx, str):
            try:
                tx = json.loads(tx)
            except (json.JSONDecodeError, TypeError):
                tx = {}
        camp.append({
            "task_id": r.get("task_id"),
            "exec": exe.get("status"),
            "failure_kind": fails.get("kind"),
            "tool_errors": tools,
            "recoveries": len(exe.get("recoveries") or []),
            "rounds": r.get("rounds"),
            "cycle_outcome": (tx.get("cycle_outcome") if isinstance(tx, dict) else None),
        })
    out["campaign_exec"] = camp
    out["campaign_degraded_rate"] = (round(sum(1 for c in camp if c["exec"] == "degraded") / len(camp), 3)
                                     if camp else None)
    # 3. 评审闸门（解释 no_op 的根因）
    arp = st / "advisory_review.json"
    if arp.is_file():
        ar = json.loads(arp.read_text(encoding="utf-8"))
        runs = ar.get("advisory_runs") or []
        out["advisory"] = {
            "runs": len(runs) if isinstance(runs, list) else 0,
            "status_dist": dict(Counter(r.get("status") for r in runs)) if isinstance(runs, list) else None,
            "commit_readiness_debts": len(ar.get("commit_readiness_debts") or []),
            "open_obligations": len(ar.get("open_obligations") or []),
        }
    # 4. 技能生成失败原因
    sg = _load_jsonl(st / "skill_generation_history.jsonl")
    out["skill_gen"] = {
        "total": len(sg),
        "created": sum(1 for r in sg if r.get("outcome") == "created"),
        "failed": [{"task_id": r.get("task_id"), "reason": r.get("reason")}
                   for r in sg if r.get("outcome") != "created"],
    }
    # 5. 信用分配
    sc = _load_jsonl(st / "step_credits.jsonl")
    creds = [float(r.get("credit") or 0) for r in sc]
    out["credits"] = {
        "total": len(sc),
        "role_dist": dict(Counter(r.get("role") for r in sc)),
        "positive": sum(1 for c in creds if c > 0),
        "negative": sum(1 for c in creds if c < 0),
        "sum": round(sum(creds), 3),
    }
    # 6. 路由分支覆盖
    rh = _load_jsonl(st / "routing_history.jsonl")
    out["routing"] = {
        "branch_dist": dict(Counter(r.get("branch") for r in rh)),
        "skills_count_dist": dict(Counter(r.get("skills_count") for r in rh)),
        "tools_count_dist": dict(Counter(r.get("tools_count") for r in rh)),
    }
    # 7. 经验复杂度 / 错误步率
    ee = _load_jsonl(st / "evolution_experiences.jsonl")
    compl, otype = Counter(), Counter()
    esteps = eerr = 0
    for r in ee:
        ov = r.get("overall")
        if isinstance(ov, str):
            try:
                ov = json.loads(ov)
            except (json.JSONDecodeError, TypeError):
                ov = {}
        ov = ov if isinstance(ov, dict) else {}
        compl[ov.get("objective_complexity")] += 1
        otype[ov.get("objective_type")] += 1
        stp = r.get("steps")
        if isinstance(stp, str):
            try:
                stp = json.loads(stp)
            except (json.JSONDecodeError, TypeError):
                stp = []
        if isinstance(stp, list):
            esteps += len(stp)
            eerr += sum(1 for s in stp if s.get("is_error"))
    out["experiences"] = {
        "total": len(ee),
        "complexity": dict(compl),
        "objective_type": dict(otype),
        "steps_total": esteps,
        "error_steps": eerr,
        "error_rate": round(eerr / esteps, 3) if esteps else None,
    }
    return out


def summarize_session(session_dir: pathlib.Path) -> dict:
    ledger_path = session_dir / "session_ledger.json"
    data_root = session_dir / "data"
    sum_ = {"session": str(session_dir), "error": None, "campaign": {}, "files": {},
            "skills": {}, "deploy": {}, "observables": {}}
    if not ledger_path.is_file():
        sum_["error"] = "无 session_ledger.json（会话未完成？）"
        return sum_
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    sum_["campaign"] = {
        "arm": ledger.get("arm"),
        "cycle_counts": ledger.get("cycle_outcome_counts"),
        "absorbed_count": ledger.get("absorbed_count", 0),
        "abandoned_count": ledger.get("abandoned_count", 0),
        "no_op_count": ledger.get("no_op_count", 0),
        "total_cost_usd": ledger.get("total_cost_usd", 0),
        "absorbed_commit_shas": ledger.get("absorbed_commit_shas", []),
    }
    # ledger 未最终化时回退读原始文件（evolution_campaign.json + checkpoints）
    if not sum_["campaign"]["cycle_counts"] and not sum_["campaign"]["absorbed_count"]:
        ecp = data_root / "state" / "evolution_campaign.json"
        if ecp.is_file():
            ec = json.loads(ecp.read_text(encoding="utf-8"))
            cps = _load_jsonl(data_root / "state" / "evolution_checkpoints.jsonl")
            cc = Counter(_cycle_outcome(r) for r in cps)
            sum_["campaign"]["cycle_counts"] = dict(cc)
            sum_["campaign"]["absorbed_count"] = int(ec.get("absorbed_cycles_done") or 0) + (cc.get("absorbed") or 0)
            sum_["campaign"]["cycles_done"] = int(ec.get("cycles_done") or 0) or len(cps)
            sum_["campaign"]["no_op_count"] = cc.get("no_op") or 0
            sum_["campaign"]["abandoned_count"] = cc.get("abandoned") or 0
            sum_["campaign"]["total_cost_usd"] = ec.get("budget_spent_usd", 0)
    absorbed = sum_["campaign"]["absorbed_count"]
    cost = sum_["campaign"]["total_cost_usd"] or 0
    sum_["campaign"]["cost_per_absorbed"] = round(cost / absorbed, 4) if absorbed else None
    # 吸收提交落点分类
    clone = session_dir / "clone"
    sha_start = ""
    progress_path = session_dir / "feed_progress.json"
    if progress_path.is_file():
        try:
            sha_start = str((json.loads(progress_path.read_text(encoding="utf-8")) or {}).get("sha_start") or "")
        except (json.JSONDecodeError, OSError):
            sha_start = ""
    files = git_log_files(clone, sha_start) if (clone / ".git").is_dir() and sha_start else []
    classified = Counter(classify_file(f) for f in files)
    classify_total = sum(classified.values())
    common = sum(v for k, v in classified.items() if k not in ("特化/未分类", "测试/工具"))
    sum_["files"] = {"count": len(files),
                     "classified": dict(classified),
                     "common_layer_ratio": round(common / classify_total, 4) if classify_total else None}
    # 技能事件
    for fname, key in (("skill_generation_history.jsonl", "generation"),
                       ("skill_evolution_history.jsonl", "evolution")):
        p = data_root / "state" / fname
        rows = []
        if p.is_file():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        sum_["skills"][key] = {"count": len(rows), "rows": rows[-12:]}
    stats_path = data_root / "state" / "skill_stats.json"
    if stats_path.is_file():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        sum_["skills"]["stats"] = {name: {k: v for k, v in s.items()
                                          if k in ("execution_count", "success_count", "success_rate",
                                                   "evolution_version")}
                                   for name, s in stats.items() if isinstance(s, dict)}
    # 部署前后测（deploy_log 按 skill+task 聚合，phase=baseline/post）
    deploy_log = data_root / "state" / "deploy_log.jsonl"
    deploy = {"baseline": {}, "post": {}, "runs": 0}
    if deploy_log.is_file():
        for line in deploy_log.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            phase = row.get("phase")
            skill = row.get("skill")
            deploy.setdefault(phase, {}).setdefault(skill, Counter())[row.get("status")] += 1
            deploy["runs"] += 1
    sum_["deploy"] = deploy
    # 观测文件存在性盘点（图 4-1 数据源）
    obs = {
        "evolution_checkpoints.jsonl": data_root / "state" / "evolution_checkpoints.jsonl",
        "skill_stats.json": data_root / "state" / "skill_stats.json",
        "routing_history.jsonl": data_root / "state" / "routing_history.jsonl",
        "evolution_experiences.jsonl": data_root / "state" / "evolution_experiences.jsonl",
        "deploy_log.jsonl": data_root / "state" / "deploy_log.jsonl",
        "tools.jsonl": data_root / "logs" / "tools.jsonl",
        "task_reflections.jsonl": data_root / "logs" / "task_reflections.jsonl",
    }
    sum_["observables"] = {name: {"exists": p.exists(),
                                  "lines": sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0}
                           for name, p in obs.items()}
    sum_["deep"] = _deep_metrics(data_root)
    return sum_


def render(sessions: list[dict]) -> str:
    L = []
    A = L.append
    A("# 进化会话观测汇总\n")
    for s in sessions:
        A(f"## {s.get('campaign', {}).get('arm', s['session'])}")
        if s.get("error"):
            A(f"- ❌ {s['error']}")
            continue
        c = s["campaign"]
        A(f"- 战役: absorbed={c['absorbed_count']} abandoned={c['abandoned_count']} "
          f"no_op={c['no_op_count']}，总成本=${c['total_cost_usd']}，"
          f"每吸收提交成本=${c['cost_per_absorbed']}")
        f = s["files"]
        A(f"- 吸收提交涉及文件: {f['count']} 个；落点: {f['classified']}；"
          f"通用层占比={f['common_layer_ratio']}")
        sk = s["skills"]
        A(f"- 技能生成事件 {sk.get('generation', {}).get('count', 0)}、"
          f"进化事件 {sk.get('evolution', {}).get('count', 0)}")
        st = sk.get("stats") or {}
        if st:
            A("- 技能统计: " + "; ".join(f"{n}(v{vv}): 执行{e} 成功{s_} 率{r}"
                                         for n, d in st.items()
                                         for e, s_, r, vv in [(d.get('execution_count'), d.get('success_count'),
                                                               d.get('success_rate'), d.get('evolution_version'))]))
        dep = s["deploy"]
        base = dep.get("baseline", {})
        post = dep.get("post", {})
        def _rate(counter: Counter) -> float | None:
            ok = counter.get("completed", 0)
            total = sum(counter.values())
            return round(ok / total, 3) if total else None
        skill_names = sorted(set(base) | set(post))
        deltas = {}
        for sn in skill_names:
            rb, rp = _rate(base.get(sn, Counter())), _rate(post.get(sn, Counter()))
            deltas[sn] = {"baseline_rate": rb, "post_rate": rp,
                          "delta": round(rp - rb, 3) if (rb is not None and rp is not None) else None}
        A(f"- 部署期执行 {dep['runs']} 次；前后测 Δ: " + "; ".join(
            f"{sn}: {d['baseline_rate']} → {d['post_rate']} (Δ={d['delta']})"
            for sn, d in deltas.items()) or "（无部署记录）")
        obs = s["observables"]
        A("- 观测文件: " + ", ".join(f"{n}={'✓' if o['exists'] else '✗'}({o['lines']}行)"
                                     for n, o in obs.items()))
        d = s.get("deep") or {}
        if d.get("model_usage"):
            mu = d["model_usage"]
            mb = mu["context_bytes"]
            A(f"- 模型调用: {mu['total_calls']} 次（category={mu['by_category']}；"
              f"pricing_known={mu['pricing_known']} → 系统计成本为 0，真实成本≈调用数×单价）；"
              f"context 累计 {mb/1024/1024:.1f} MB")
        if d.get("campaign_exec"):
            ce = d["campaign_exec"]
            A(f"- 战役执行: {len(ce)} 战，degraded 率={d.get('campaign_degraded_rate')}；"
              + "; ".join(f"{c['task_id']}:{c['exec']}"
                          + (f"(tools={','.join(c['tool_errors'])})" if c['tool_errors'] else "")
                          + f"→{c['cycle_outcome']}" for c in ce))
        if d.get("advisory"):
            ad = d["advisory"]
            A(f"- 评审闸门: runs={ad['runs']} status={ad['status_dist']} "
              f"commit_readiness_debts={ad['commit_readiness_debts']} open_obligations={ad['open_obligations']}")
        if d.get("skill_gen"):
            sg = d["skill_gen"]
            A(f"- 技能生成: {sg['created']}/{sg['total']} created；"
              + ("失败: " + ", ".join(f"{f['task_id']}({f['reason']})" for f in sg['failed']) if sg['failed'] else "无失败"))
        if d.get("credits"):
            cr = d["credits"]
            A(f"- 信用分配: {cr['total']} 条 role={cr['role_dist']} 正{cr['positive']}/负{cr['negative']} 和={cr['sum']}")
        if d.get("routing"):
            rt = d["routing"]
            A(f"- 路由: branch={rt['branch_dist']} skills_count={rt['skills_count_dist']} tools_count={rt['tools_count_dist']}")
        if d.get("experiences"):
            ex = d["experiences"]
            A(f"- 经验: {ex['total']} 条 complexity={ex['complexity']} type={ex['objective_type']} "
              f"步{'-'.join(map(str,[ex['steps_total'],ex['error_steps']]))} 错误步率={ex['error_rate']}")
        A("")
    if len(sessions) == 2:
        a, b = sessions
        if not a.get("error") and not b.get("error"):
            A("## 对比（表格 4-3 口径）")
            A("| 指标 | " + " | ".join(s["campaign"]["arm"] for s in sessions) + " |")
            A("|---|---|---|")
            for key, fmt in (("absorbed_count", "{}"), ("abandoned_count", "{}"), ("no_op_count", "{}"),
                             ("total_cost_usd", "${}"), ("cost_per_absorbed", "${}")):
                A(f"| {key} | " + " | ".join(fmt.format(s["campaign"][key]) if s["campaign"][key] is not None else "—"
                                             for s in sessions) + " |")
            A(f"| 通用层占比 | " + " | ".join(str(s['files']['common_layer_ratio']) for s in sessions) + " |")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize evolution-arm sessions into comparison outputs.")
    ap.add_argument("--session-dir", type=pathlib.Path, action="append", required=True,
                    help="Arm session dir (repeat for V0 and V3 to get the comparison table)")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="Write markdown report to path (default stdout)")
    args = ap.parse_args()
    sessions = [summarize_session(d) for d in args.session_dir]
    report = render(sessions)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"report: {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())