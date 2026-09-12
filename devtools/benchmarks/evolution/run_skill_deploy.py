#!/usr/bin/env python3
"""独立技能部署驱动：对一个既有进化会话的 self 技能单独执行部署窗口。

与 run_evolution_arm.py 解耦——不喂语料、不开进化战役，只做技能部署：
  修复 frontmatter(可选) → 重背书(可选，绑定当前内容哈希) → 前测(baseline)
  → [GEPA 由管线 nudge 另行触发] → 后测(post，检测到 evolution_version 提升) → Δ

用法：
  .venv/bin/python devtools/benchmarks/evolution/run_skill_deploy.py \
    --session-dir /home/lzm/bench_runs/arms/smoke_test_10 \
    --skills clinical-trial-enrollment-finder,openreview-neurips-query

  # 全部技能、强制重跑前测（忽略既有 deploy_state 阶段）：
  .venv/bin/python devtools/benchmarks/evolution/run_skill_deploy.py \
    --session-dir <session> --phase baseline

前置条件：--session-dir 下已有 clone/ 与 data/skills/self/（由 run_evolution_arm.py 产出）。
复用 run_evolution_arm 的部署函数（_run_deploy_window/_seed_settings 等），本脚本只做
会话装载、技能修复/重背书、server 启动与结果汇报。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from devtools.benchmarks.common.server_runner import IsolatedServer

_VALID_RUNTIMES = {"bash", "deno", "go", "node", "python", "python3", "ruby"}


def _load_arm():
    spec = importlib.util.spec_from_file_location(
        "run_evolution_arm", _REPO / "devtools" / "benchmarks" / "evolution" / "run_evolution_arm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fix_frontmatter(skill_dir: pathlib.Path, default_runtime: str = "python3") -> str:
    """补齐 SKILL.md frontmatter 的 runtime 字段（生成端常见缺口）。返回动作说明。"""
    p = skill_dir / "SKILL.md"
    if not p.is_file():
        return "无 SKILL.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^runtime:\s*(\S*)\s*$", text, re.M)
    if m:
        if m.group(1) in _VALID_RUNTIMES:
            return "runtime 已合法"
        text = re.sub(r"^runtime:\s*\S*\s*$", f"runtime: {default_runtime}", text, count=1, flags=re.M)
        p.write_text(text, encoding="utf-8")
        return f"runtime 修正为 {default_runtime}（原值 {m.group(1)!r} 非法）"
    # 完全缺失：插在 type: 行之后（script 技能都有 type 行）
    if re.search(r"^type:\s*script\s*$", text, re.M):
        text = re.sub(r"(^type:\s*script\s*$)", rf"\1\nruntime: {default_runtime}",
                      text, count=1, flags=re.M)
        p.write_text(text, encoding="utf-8")
        return f"补入 runtime: {default_runtime}"
    return "未找到 type: 行，跳过（非 script 技能？）"


def re_attest(arm, data_root: pathlib.Path, skill_dir: pathlib.Path) -> None:
    """重背书：把 review 状态的 content_hash 刷新为当前内容，绕开 edited-since-review 闸门。"""
    from ouroboros.skill_loader import (SkillReviewState, compute_content_hash,
                                        save_review_state, skill_state_dir)
    name = skill_dir.name
    h = compute_content_hash(skill_dir)
    save_review_state(data_root, name, SkillReviewState(
        status="clean",
        content_hash=h,
        reviewer_models=["experiment-operator"],
        review_profile="owner_attested",
    ))
    st_dir = skill_state_dir(data_root, name)
    st_dir.mkdir(parents=True, exist_ok=True)
    (st_dir / "owner_attestation.json").write_text(json.dumps({
        "attested_by": "experiment_operator",
        "ts": arm._dt.datetime.now().isoformat(timespec="seconds"),
        "note": "re-attest after content fix (run_skill_deploy)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def gen_domain_tasks(data_root: pathlib.Path, skill_dir: pathlib.Path, n: int = 5) -> str:
    """按技能 SKILL.md 用 LLM 生成 n 条领域部署任务（测技能真实价值的主战场，
    GEPA 前后测 Δ 的口径），存 <skill>/deploy_tasks.json。已存在则跳过。"""
    out = skill_dir / "deploy_tasks.json"
    if out.is_file():
        return "已存在，跳过"
    md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    prompt = (
        "你是技能部署测试的设计者。下面是一个 agent 自研技能的 SKILL.md 定义。\n"
        f"请为它生成 {n} 条领域部署测试任务，用于衡量该技能在真实使用场景下的成功率：\n"
        "1. 每条任务必须是该技能 when_to_use 描述的领域内的真实任务（不是通用数据处理杂活）；\n"
        "2. 任务应能通过调用该技能（必要时配合普通工具）完成，难度覆盖典型/边界场景；\n"
        "3. 任务文本以动词开头、自包含、可直接派发给 agent 执行；\n"
        '4. 输出纯 JSON 数组，形如 [{"id": "dom-01", "text": "..."}, ...]，不要其他内容。\n\n'
        f"SKILL.md:\n{md}\n"
    )
    from ouroboros.llm import LLMClient
    from ouroboros.llm_observability import chat_observed
    from ouroboros.evolution.trajectory_experience_learner import _default_main_model
    client = LLMClient()
    resp, _usage = chat_observed(
        client,
        drive_root=data_root,
        task_id=f"deploy_gen:{skill_dir.name}",
        call_type="skill_deploy_gen",
        messages=[{"role": "user", "content": prompt}],
        model=_default_main_model(),
        reasoning_effort="medium",
        max_tokens=4000,
    )
    content = str((resp or {}).get("content") or "")
    lo, hi = content.find("["), content.rfind("]")
    if lo < 0 or hi <= lo:
        return f"生成失败：模型输出非 JSON（{content[:60]}）"
    try:
        tasks = json.loads(content[lo:hi + 1])
    except json.JSONDecodeError as exc:
        return f"生成失败：JSON 解析错误（{exc}）"
    tasks = [t for t in tasks if isinstance(t, dict) and str(t.get("text") or "").strip()]
    for i, t in enumerate(tasks, 1):
        t.setdefault("id", f"dom-{i:02d}")
    out.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    return f"生成 {len(tasks)} 条领域任务"


def main() -> int:
    ap = argparse.ArgumentParser(description="Standalone skill-deploy driver (decoupled from the arm run).")
    ap.add_argument("--session-dir", type=pathlib.Path, required=True,
                    help="Existing evolution session dir (<session>/clone + <session>/data)")
    ap.add_argument("--skills", default="",
                    help="Comma-separated skill names (default: all self-authored skills)")
    ap.add_argument("--deploy-tasks", type=pathlib.Path,
                    default=_REPO / "devtools" / "benchmarks" / "evolution" / "deploy_tasks" / "deploy_tasks.json")
    ap.add_argument("--phase", choices=["auto", "baseline", "post"], default="auto",
                    help="auto=按 deploy_state 状态机；强制指定则忽略既有阶段")
    ap.add_argument("--fix-frontmatter", action="store_true", default=True)
    ap.add_argument("--no-fix-frontmatter", dest="fix_frontmatter", action="store_false")
    ap.add_argument("--gen-domain-tasks", action="store_true", default=True,
                    help="按 SKILL.md 生成领域部署任务（<skill>/deploy_tasks.json，缺文件时生成）")
    ap.add_argument("--no-gen-domain-tasks", dest="gen_domain_tasks", action="store_false")
    ap.add_argument("--domain-task-count", type=int, default=7,
                    help="每技能领域任务数；edge 3 + domain 7 = 10，正好满足 GEPA 变异门槛（>=10 executions 且 success<0.8）")
    ap.add_argument("--regression-n", type=int, default=3,
                    help="每技能跑多少条通用回归任务（0=不跑回归）")
    ap.add_argument("--re-attest", action="store_true",
                    help="重背书：刷新内容哈希绑定（修复 edited-since-review 拦截）")
    ap.add_argument("--budget", type=float, default=20.0, help="本次部署会话 TOTAL_BUDGET")
    ap.add_argument("--live-settings", type=pathlib.Path, default=None)
    args = ap.parse_args()

    arm = _load_arm()
    session_dir = args.session_dir.resolve()
    clone = session_dir / "clone"
    data_root = session_dir / "data"
    if not (clone / ".git").is_dir() or not data_root.is_dir():
        print(f"会话不完整：{session_dir} 需要 clone/ 与 data/（先跑 run_evolution_arm.py）")
        return 2

    skills_root = data_root / "skills" / "self"
    if not skills_root.is_dir():
        print(f"无自写技能目录: {skills_root}")
        return 2
    all_skills = sorted(d.name for d in skills_root.iterdir()
                        if d.is_dir() and (d / ".self_authored.json").is_file())
    if not all_skills:
        print("无 .self_authored 技能可部署")
        return 2
    only = frozenset(s.strip() for s in args.skills.split(",") if s.strip()) or None
    selected = sorted(only) if only else all_skills
    print(f"会话: {session_dir}")
    print(f"待部署技能 ({len(selected)}/{len(all_skills)}): {selected}")

    # 1. frontmatter 修复（哈希随之变化，必须在重背书之前）
    if args.fix_frontmatter:
        for name in selected:
            note = fix_frontmatter(skills_root / name)
            print(f"  [fix] {name}: {note}")

    # 2. 领域部署任务生成（LLM，同样影响技能目录哈希，须在重背书之前）
    if args.gen_domain_tasks:
        for name in selected:
            note = gen_domain_tasks(data_root, skills_root / name, n=args.domain_task_count)
            print(f"  [domain] {name}: {note}")

    # 3. 重背书（绑定当前内容哈希）
    if args.re_attest:
        for name in selected:
            re_attest(arm, data_root, skills_root / name)
            print(f"  [re-attest] {name}: review 哈希已刷新")

    # 3. 隔离 server（cadence=off：部署会话不跑进化战役）
    if args.live_settings is None:
        args.live_settings = arm.default_live_settings()
    settings_path = arm._seed_settings(data_root, "V3", "off", args.budget, args.live_settings)
    os.environ.setdefault("OUROBOROS_RUNTIME_MODE", "pro")
    os.environ.setdefault("OUROBOROS_SKILL_EVOLUTION", "true")
    server = IsolatedServer(clone, data_root, settings_path)
    print(f"启动隔离 server …")
    server.start(ready_timeout=240)
    try:
        work_root = session_dir / "deploy_ws"
        work_root.mkdir(parents=True, exist_ok=True)
        force = None if args.phase == "auto" else args.phase
        state = arm._run_deploy_window(server, data_root, args.deploy_tasks, work_root,
                                       only=only, force_phase=force,
                                       regression_n=args.regression_n)
        print(f"部署状态机: {json.dumps(state, ensure_ascii=False)}")
    finally:
        server.stop()

    # 4. 汇报
    stats_path = data_root / "state" / "skill_stats.json"
    if stats_path.is_file():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        print("\n=== 技能统计 ===")
        for name in selected:
            s = stats.get(name) or {}
            print(f"  {name}: 执行={s.get('execution_count', 0)} 成功={s.get('success_count', 0)}"
                  f" 率={s.get('success_rate')} 版本=v{s.get('evolution_version', 0)}")
    log_path = data_root / "state" / "deploy_log.jsonl"
    if log_path.is_file():
        rows = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        by_phase: dict = {}
        for r in rows:
            by_phase.setdefault(r.get("phase"), []).append(r.get("status"))
        print("\n=== 部署运行分布 ===")
        for ph, sts in by_phase.items():
            c: dict = {}
            for s_ in sts:
                c[s_] = c.get(s_, 0) + 1
            print(f"  {ph}: {len(sts)} runs {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
