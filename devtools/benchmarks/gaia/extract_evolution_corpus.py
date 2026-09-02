#!/usr/bin/env python3
"""Extract the GAIA evolution corpus from existing benchmark runs (offline).

Input : a directory of GAIA run outputs produced by ``run_gaia.py`` (ouroboros
        headless runs wrapped by inspect_ai): one subdirectory per run, each
        containing ``inspect_logs/*.json`` (authoritative scoring),
        ``ouroboros_data/`` (traces) and ``samples/<uuid>/result.json``
        (task-side records). ``--pack-source`` prepares a trimmed copy of this
        input (extraction-only files, no API keys) for another host.
Output: the evolution corpus consumed by the offline-replay pipeline
        (EVOLUTION_EXPERIMENT_SPEC.md §1)::

            bench_runs/evolution_corpus/
            ├── gaia_corpus_<date>.jsonl   # 40 records, spec §1.2 format
            ├── traces/<id>.json           # normalized traces (spec §10.6 form b)
            └── corpus_stats.md            # dedup/capability/validation report

Pipeline of the script:
  1. parse every inspect log sample (uuid/level/question/score/…);
  2. dedupe by sample uuid keeping the best score (C > I > None, ties by
     latest ``started_at``) — repeat runs of the same GAIA task collapse to a
     single record;
  3. resolve each task's tool trace (per-task ``tools.jsonl``, then the global
     per-run ``tools.jsonl`` filtered by task id, then a last-resort
     reconstruction from the inspect ``messages``);
  4. tag tasks with capability labels from GAIA annotator metadata plus the
     tool names actually used in the trace;
  5. select the corpus by constrained greedy sampling: hard level×outcome
     allocation (12/20/8 across levels; 14 failed / 26 passed), capability
     coverage quotas per tag, recovery-rich traces preferred, deterministic
     seed;
  6. write corpus + traces + stats, then validate every record locally
     (spec §10.6 ``load_trace_from_path`` semantics) at zero LLM cost.

The script is read-only w.r.t. the runs root: it never reads ``settings.json``
(plaintext API keys) and never touches ``observability/`` blobs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import sys
from collections import Counter, defaultdict

if __package__ in {None, ""}:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

REPO = pathlib.Path(__file__).resolve().parents[3]

# TOOL_TIMEOUT 结果文本前缀：旧版日志的 timeout tools.jsonl 行不带
# is_error/status 字段（v6.90 起生产已补），提取侧按此文本兜底识别，
# 保证旧 run 的超时调用不被误判为成功。
_TOOL_TIMEOUT_MARKER = "⚠️ TOOL_TIMEOUT"

# ---------------------------------------------------------------------------
# dedup / scoring helpers
# ---------------------------------------------------------------------------

_SCORE_RANK = {"C": 2, "I": 1, None: 0}

_QUESTION_MARKERS = (
    "Here is the question:\n\n",
    "Here is the question:\n",
    "Here is the question:",
)


def normalize_scorer(raw) -> str | None:
    """inspect gaia_scorer: dict {"value": "C"|"I"} (or legacy list)."""
    if isinstance(raw, dict):
        val = raw.get("value")
    elif isinstance(raw, list):
        val = raw[0] if raw else None
    else:
        val = raw
    if isinstance(val, list):
        val = val[0] if val else None
    if val is None:
        return None
    s = str(val).strip().upper()
    return s if s in ("C", "I") else None


def extract_question(input_text: str) -> str:
    if not input_text:
        return ""
    for marker in _QUESTION_MARKERS:
        idx = input_text.find(marker)
        if idx >= 0:
            return input_text[idx + len(marker):].strip()
    return input_text.strip()


def norm_text(s: str) -> str:
    return " ".join(str(s or "").split())


def _status_is_ok(status) -> bool:
    return str(status or "").strip().lower() in ("", "ok", "success", "done", "completed", "none")


# ---------------------------------------------------------------------------
# inspect log parsing
# ---------------------------------------------------------------------------


def parse_inspect_log(log_path: pathlib.Path) -> list[dict]:
    try:
        data = json.loads(log_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ! skip unreadable inspect log {log_path.name}: {exc}")
        return []
    out = []
    for s in data.get("samples") or []:
        meta = s.get("metadata") or {}
        runtime = meta.get("ouroboros_runtime_outcome") or {}
        annotator = meta.get("Annotator Metadata") or meta.get("annotator_metadata") or {}
        completion = (s.get("output") or {}).get("completion") or ""
        target = s.get("target")
        if isinstance(target, list):
            target = " ".join(str(x) for x in target)
        out.append({
            "uuid": str(s.get("id") or ""),
            "run": "",
            "log_path": log_path,
            "level": int(meta.get("level") or 0) if str(meta.get("level") or "").isdigit() else 0,
            "input": s.get("input") or "",
            "question": extract_question(s.get("input") or ""),
            "target": str(target or ""),
            "completion": str(completion),
            "score": normalize_scorer((s.get("scores") or {}).get("gaia_scorer")),
            "started_at": s.get("started_at") or "",
            "reason_code": str(runtime.get("reason_code") or ""),
            "runtime_status": str(runtime.get("status") or ""),
            "annotator": annotator if isinstance(annotator, dict) else {},
            "messages": s.get("messages") or [],
            "sample": s,
        })
    return out


def scan_runs(runs_root: pathlib.Path) -> list[dict]:
    records = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        logs = sorted((run_dir / "inspect_logs").glob("*.json")) if (run_dir / "inspect_logs").is_dir() else []
        for lp in logs:
            for rec in parse_inspect_log(lp):
                rec["run"] = run_dir.name
                rec["run_dir"] = run_dir
                records.append(rec)
    return records


def dedup(records: list[dict]) -> list[dict]:
    """Best score per uuid (C > I > None); ties by latest started_at."""
    by_uuid: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_uuid[r["uuid"]].append(r)
    best = []
    for uuid, recs in by_uuid.items():
        recs.sort(key=lambda r: (_SCORE_RANK[r["score"]], r["started_at"]))
        best.append(recs[-1])
    best.sort(key=lambda r: (r["level"], r["uuid"]))
    return best


# ---------------------------------------------------------------------------
# trace resolution
# ---------------------------------------------------------------------------


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    except (json.JSONDecodeError, OSError):
        return []


_HEX_INDEX_CACHE: dict[str, list] = {}


def _hex_index(run_dir: pathlib.Path) -> list:
    """Per-run index of (hex_id, normalized full description)."""
    key = str(run_dir)
    if key in _HEX_INDEX_CACHE:
        return _HEX_INDEX_CACHE[key]
    entries: list[tuple[str, str]] = []
    roots = []
    task_results_dir = run_dir / "ouroboros_data" / "task_results"
    if task_results_dir.is_dir():
        roots.append(task_results_dir)
    headless_dir = run_dir / "ouroboros_data" / "state" / "headless_tasks"
    if headless_dir.is_dir():
        for hdir in sorted(headless_dir.iterdir()):
            p = hdir / "data" / "task_results" / f"{hdir.name}.json"
            if p.is_file():
                roots.append(p)
    seen = set()
    for p in roots:
        if not p.is_file():
            continue
        if p.name in seen:
            continue
        seen.add(p.name)
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        desc = norm_text(d.get("description") or "")
        if desc:
            entries.append((p.stem, desc))
    _HEX_INDEX_CACHE[key] = entries
    return entries


def _desc_matches(desc_norm: str, q: str) -> bool:
    q_norm = norm_text(q)
    if not q_norm:
        return False
    if q_norm == extract_question(desc_norm):
        return True
    if len(q_norm) >= 30 and q_norm in desc_norm:
        return True
    return False


def find_task_hex(uuid: str, run_dir: pathlib.Path, question: str) -> str | None:
    """uuid -> 16-hex ouroboros task id via result.json, else description index."""
    sid_dir = run_dir / "samples" / uuid
    result_json = sid_dir / "result.json"
    if result_json.is_file():
        try:
            data = json.loads(result_json.read_text(encoding="utf-8-sig"))
            hexid = str(data.get("root_task_id") or "").strip()
            if hexid:
                return hexid
        except (json.JSONDecodeError, OSError):
            pass
    for hex_id, desc_norm in _hex_index(run_dir):
        if _desc_matches(desc_norm, question):
            return hex_id
    return None


def trace_from_messages(rec: dict) -> list[dict]:
    """Last-resort: rebuild tool calls from inspect conversation messages."""
    calls = []
    pending = None
    for m in rec.get("messages") or []:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype in ("tool_use", "tool_call"):
                pending = {
                    "tool": str(item.get("name") or item.get("tool") or ""),
                    "args": item.get("input") or item.get("arguments") or {},
                }
            elif itype == "tool_result" and pending:
                is_err = bool(item.get("is_error"))
                calls.append({
                    "tool": pending["tool"],
                    "args": pending["args"],
                    "result": str(item.get("content") or ""),
                    "is_error": is_err,
                    "status": "error" if is_err else "ok",
                })
                pending = None
    return calls


def result_json_data(run_dir: pathlib.Path, uuid: str) -> dict | None:
    p = run_dir / "samples" / uuid / "result.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# production-grade trace reconstruction
#
# 目标：语料 trace 与生产 llm_trace 逐字段对齐（generate_reflection 的直接
# 输入）。生产 llm_trace 的 tool_calls 每条 =
#   {tool, tool_call_id, args(args_for_log), result(_truncate_tool_result 视图),
#    is_error, trace_ref, **result_meta}
# （loop_tool_execution.py process_tool_results），reasoning_notes = 每轮无
# 工具调用的纯文本回复（loop.py _handle_text_response）。
#
# run 目录里可用于重建的原始数据：
#   - per-task logs/tools.jsonl：调用序列（顺序/tool/args_for_log/is_error/status/
#     tool_call_id/result_ref），result_preview 仅 2000 字符截断；
#   - observability/calls/<task>/<call_id>.json：per-call manifest；
#   - observability/blobs/<sha256>.json.gz：内容定址全量 payload（gzip JSON），
#     tool_call 类含完整 result + result_meta，llm_*_response 类含 message
#     （含每轮文本）。blob/manifest 里的 path 是生成机器的绝对路径，跨机
#     拷贝后失效 —— 索引以 sha256/call_id 为 key，与路径无关。
#   - headless_tasks/<hex>/data/task_results/<hex>.json：生产持久化的
#     trace_summary 原文、trace_refs、cost_fields、review_evidence。
# ---------------------------------------------------------------------------


def trace_safe_id(corpus_id: str) -> str:
    """JSONL id 保持 `2023_levelN:M`（与 run_gaia sample-id 对齐）；trace /
    backup 目录名用安全形式 —— 冒号在 Linux 上非法、在 Windows NTFS 上会
    产生附加数据流（ADS）文件，跨机器不可移植。"""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(corpus_id)).strip("_") or "unknown"


class _ObservabilityIndex:
    """Per-run content-addressed index of observability blobs + call manifests.

    ``_build`` 每个 run 只跑一次（缓存），覆盖 run 根与 headless 子任务
    各自的 observability 目录。"""
    def __init__(self, run_dir: pathlib.Path):
        self.run_dir = run_dir
        self.blobs: dict[str, pathlib.Path] = {}
        self.manifests: dict[str, pathlib.Path] = {}
        self._built = False

    def _build(self) -> None:
        if self._built:
            return
        self._built = True
        # run 根 drive 的 observability
        for base in (self.run_dir / "ouroboros_data", self.run_dir / "ouroboros_data" / "state"):
            obs_dir = base / "observability"
            self._index_obs_dir(obs_dir)
        # headless 子任务各自独立的 data root(drive) observability
        ht_root = self.run_dir / "ouroboros_data" / "state" / "headless_tasks"
        if ht_root.is_dir():
            for hd in ht_root.iterdir():
                self._index_obs_dir(hd / "data" / "observability")

    def _index_obs_dir(self, obs_dir: pathlib.Path) -> None:
        blobs_dir = obs_dir / "blobs"
        if blobs_dir.is_dir():
            for p in blobs_dir.glob("*.json.gz"):
                self.blobs.setdefault(p.stem.split(".")[0], p)
        calls_root = obs_dir / "calls"
        if calls_root.is_dir():
            for p in calls_root.glob("*/*.json"):
                self.manifests.setdefault(p.stem, p)

    def blob_path(self, sha256: str) -> pathlib.Path | None:
        self._build()
        return self.blobs.get(sha256)

    def manifest_path(self, call_id: str) -> pathlib.Path | None:
        self._build()
        return self.manifests.get(call_id)


_OBS_INDEX_CACHE: dict[str, _ObservabilityIndex] = {}


def _obs_index(run_dir: pathlib.Path) -> _ObservabilityIndex:
    key = str(run_dir)
    idx = _OBS_INDEX_CACHE.get(key)
    if idx is None:
        idx = _ObservabilityIndex(run_dir)
        _OBS_INDEX_CACHE[key] = idx
    return idx


def _load_manifest_blob(index: _ObservabilityIndex, ref: dict) -> dict | None:
    """manifest_ref {path, call_id, sha256} → 读 manifest → 读 full blob payload。

    返回 (manifest_dict, blob_payload) 或 None；解析失败返回 {}。
    """
    if not isinstance(ref, dict):
        return None
    call_id = str(ref.get("call_id") or "")
    mp = index.manifest_path(call_id)
    if mp is None and ref.get("path"):
        cand = pathlib.Path(str(ref["path"]))
        mp = cand if cand.is_file() else None
    if mp is None:
        return None
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    fp = manifest.get("full_payload_ref") or {}
    sha = str(fp.get("sha256") or "")
    bp = index.blob_path(sha) if sha else None
    if bp is None and fp.get("path"):
        cand = pathlib.Path(str(fp["path"]))
        bp = cand if cand.is_file() else None
    if bp is None:
        return None
    try:
        with gzip.open(bp, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _result_view(result_full: str, tool_name: str, tool_args: dict) -> str:
    """生产 agent 视角的工具结果截断（loop_tool_execution._truncate_tool_result）。

    优先导入生产实现保证逐字节一致；导入失败（缺少 ouroboros 运行时依赖）时
    回退为同语义的 15000 字符头截断。"""
    try:
        from ouroboros.loop_tool_execution import _truncate_tool_result
        return _truncate_tool_result(result_full, tool_name, tool_args)
    except Exception:
        limit = 15000
        if len(result_full) <= limit:
            return result_full
        return result_full[:limit] + f"\n... (truncated from {len(result_full)} chars, limit={limit})"


def _result_meta_rebuilt(result_full: str, tool_name: str, is_err: bool) -> dict:
    """按生产 _extract_result_metadata 语义重建 result_meta（status/exit_code/
    signal/artifact_registered 等）。失败时退化为 {status: ...}。"""
    try:
        from ouroboros.loop_tool_execution import _extract_result_metadata
        meta = _extract_result_metadata(tool_name, result_full, is_err)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {"status": "error" if is_err else "ok"}


def _reconstruct_call(line: dict, payload: dict | None) -> dict:
    """tools.jsonl 行 + observability 全量 payload → 生产级 tool_call entry。"""
    tool = str(line.get("tool") or "")
    blob_result = str((payload or {}).get("result") or "") if payload else ""
    result_full = blob_result or str(line.get("result_preview") or "")
    args = line.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    is_err = bool(line.get("is_error"))
    status = str(line.get("status") or "")
    if result_full.startswith(_TOOL_TIMEOUT_MARKER):
        # 旧日志 timeout 行缺 is_error/status —— 文本兜底（生产 v6.90 起已补字段）
        is_err, status = True, "timeout"
    elif line.get("is_error") is None and not status:
        # 更古老的缺失字段行：用 blob 的语义标记佐证
        bl = payload or {}
        if isinstance(bl.get("tool_ok"), bool):
            is_err = not bl["tool_ok"]
        status = str((bl.get("result_meta") or {}).get("status") or ("error" if is_err else "ok"))
    entry = {
        "tool": tool,
        "tool_call_id": str(line.get("tool_call_id") or (payload or {}).get("tool_call_id") or ""),
        "args": args,
        "result": _result_view(result_full, tool, payload.get("args") if payload else args),
        "is_error": is_err,
        "trace_ref": line.get("result_ref") or {},
    }
    if payload and isinstance(payload.get("result_meta"), dict):
        meta = dict(payload["result_meta"])
        meta.setdefault("status", status or ("error" if is_err else "ok"))
        entry.update(meta)
    else:
        entry.update(_result_meta_rebuilt(result_full, tool, is_err))
    return entry


def _reconstruct_reasoning_notes(run_dir: pathlib.Path, hex_id: str,
                                 index: _ObservabilityIndex, llm_call_refs: list) -> list[str]:
    """每轮无工具调用的纯文本回复 → reasoning_notes（对齐 loop._handle_text_response）。

    顺序权威源：per-task events.jsonl 的 llm_round 行（时间序、带 response_ref）；
    兜底：task record 的 trace_refs.llm_call_refs。"""
    if not hex_id:
        return []
    notes: list[str] = []
    seen_msgs: set[str] = set()
    hd_logs = run_dir / "ouroboros_data" / "state" / "headless_tasks" / hex_id / "data" / "logs"
    refs: list[dict] = []
    for row in _read_jsonl(hd_logs / "events.jsonl"):
        if row.get("type") == "llm_round" and isinstance(row.get("response_ref"), dict):
            refs.append(row["response_ref"])
    if not refs:
        for item in llm_call_refs or []:
            if isinstance(item, dict) and isinstance(item.get("response_ref"), dict):
                refs.append(item["response_ref"])
    for ref in refs:
        if len(notes) >= 30:
            break
        payload = _load_manifest_blob(index, ref)
        if not payload:
            continue
        msg = payload.get("message") or {}
        if msg.get("tool_calls"):
            continue  # 工具轮：content 不进 notes（_handle_text_response 语义）
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if content in seen_msgs:
            continue
        seen_msgs.add(content)
        notes.append(content[:4000])
    return notes


_TASK_RECORD_CACHE: dict[str, dict] = {}


def _task_result_record(run_dir: pathlib.Path, hex_id: str) -> dict:
    """headless 任务的 task_results/<hex>.json 全量记录（trace_summary 原文/
    trace_refs/cost/review_evidence），带 per-run 缓存。"""
    if not hex_id:
        return {}
    key = f"{run_dir}|{hex_id}"
    rec = _TASK_RECORD_CACHE.get(key)
    if rec is not None:
        return rec
    candidates = [
        run_dir / "ouroboros_data" / "state" / "headless_tasks" / hex_id / "data" / "task_results" / f"{hex_id}.json",
        run_dir / "ouroboros_data" / "task_results" / f"{hex_id}.json",
    ]
    rec = {}
    for p in candidates:
        if p.is_file():
            try:
                rec = json.loads(p.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                rec = {}
            if rec:
                break
    _TASK_RECORD_CACHE[key] = rec
    return rec


def resolve_trace(rec: dict) -> dict:
    """Return production-grade trace data for one record.

    返回 ``{tool_calls, reasoning_notes, trace_summary, source, hex_id,
    reconstruction, usage, review_evidence}``；observability 全量 payload
    可得时 tool_calls 为生产级 entry（完整 result 的生产视图 + result_meta），
    否则降级为 tools.jsonl 的 2000 字符视图并如实标注 reconstruction。
    """
    run_dir = rec["run_dir"]
    hex_id = find_task_hex(rec["uuid"], run_dir, rec["question"])
    calls: list[dict] = []
    source = "none"
    index = _obs_index(run_dir)
    task_record = _task_result_record(run_dir, hex_id) if hex_id else {}

    if hex_id:
        per_task = run_dir / "ouroboros_data" / "state" / "headless_tasks" / hex_id / "data" / "logs" / "tools.jsonl"
        if per_task.is_file():
            source = "headless_tools"
            calls = per_task_lines(per_task)
        else:
            glob_log = run_dir / "ouroboros_data" / "logs" / "tools.jsonl"
            calls = [c for c in per_task_lines(glob_log) if c.get("task_id") == hex_id]
            source = "global_tools" if calls else "none"

    calls_full = 0
    recovered_calls: list[dict] = []
    for line in calls:
        payload = None
        ref = line.get("result_ref")
        if isinstance(ref, dict):
            payload = _load_manifest_blob(index, ref)
        if payload is not None:
            calls_full += 1
        else:
            payload = None
        recovered_calls.append(_reconstruct_call(line, payload))
    if not recovered_calls:
        recovered_calls = trace_from_messages(rec)
        source = "inspect_messages" if recovered_calls else source

    trace_summary = ""
    summary_source = "synthetic"
    stored_summary = str(task_record.get("trace_summary") or "")
    if stored_summary:
        trace_summary = stored_summary
        summary_source = "task_result"
    else:
        rj = result_json_data(run_dir, rec["uuid"])
        if rj:
            rj_summary = str(rj.get("trace_summary") or "")
            if rj_summary:
                trace_summary = rj_summary
                summary_source = "result_json"
            rec.setdefault("extra_rounds", rj.get("total_rounds"))

    llm_call_refs = (task_record.get("trace_refs") or {}).get("llm_call_refs") or []
    reasoning_notes = _reconstruct_reasoning_notes(run_dir, hex_id, index, llm_call_refs)
    notes_source = "llm_response_blobs" if reasoning_notes else "none"

    if source in ("headless_tools", "global_tools"):
        src = "observability_blobs" if calls_full else "tools_jsonl"
        if calls_full and calls_full < len(recovered_calls):
            src = "observability_blobs_partial"
    else:
        src = "inspect_messages"
    reconstruction = {
        "tool_calls_source": src,
        "notes_source": notes_source,
        "summary_source": summary_source,
        "full_results_count": calls_full,
        "full_results_total": len(recovered_calls),
        "blobs_backed_up": False,
    }

    cost_fields = {
        key: task_record.get(key)
        for key in ("total_rounds", "cost_usd", "prompt_tokens", "completion_tokens", "cached_tokens",
                    "cost_accounting_status", "cost_final", "reserved_usd", "unresolved_upper_bound_usd")
        if task_record.get(key) is not None
    }
    review_evidence = task_record.get("review_evidence")
    if not isinstance(review_evidence, dict) or not review_evidence:
        review_evidence = {}

    if not calls and not recovered_calls:
        # record evidence of a genuinely tool-less run (zero-tool direct answer)
        if hex_id:
            ev_path = run_dir / "ouroboros_data" / "state" / "headless_tasks" / hex_id / "data" / "logs" / "events.jsonl"
            for line in _read_jsonl(ev_path):
                if line.get("type") == "task_eval":
                    rec["eval_tool_calls"] = line.get("tool_calls")
                    break

    return {
        "tool_calls": recovered_calls,
        "reasoning_notes": reasoning_notes,
        "trace_summary": trace_summary,
        "source": source,
        "hex_id": hex_id,
        "reconstruction": reconstruction,
        "usage": cost_fields,
        "review_evidence": review_evidence,
    }


def per_task_lines(path: pathlib.Path) -> list[dict]:
    return [r for r in _read_jsonl(path) if r.get("type") == "tool_call" and r.get("tool")]


def tool_call_feature(call: dict) -> dict:
    is_err = bool(call.get("is_error")) or not _status_is_ok(call.get("status"))
    return {
        "tool": str(call.get("tool") or ""),
        "args": call.get("args") or {},
        "result": str(call.get("result_preview") or call.get("result") or ""),
        "is_error": is_err,
        "status": str(call.get("status") or ("error" if is_err else "ok")),
    }


def trace_features(calls: list[dict]) -> dict:
    n_errors = sum(1 for c in calls if c["is_error"])
    recovered = 0
    for i, c in enumerate(calls):
        if c["is_error"] and any(c2["tool"] == c["tool"] and not c2["is_error"] for c2 in calls[i + 1:]):
            recovered += 1
    tools = Counter(c["tool"] for c in calls)
    return {
        "n_calls": len(calls),
        "n_errors": n_errors,
        "n_recovered": recovered,
        "tools": tools,
        "tools_top": [t for t, _ in tools.most_common(6)],
    }


# ---------------------------------------------------------------------------
# capability tagging
# ---------------------------------------------------------------------------

_ANNOTATOR_RULES = [
    ("WEB_SEARCH", re.compile(r"search engine|web search|web browser|google|bing|duckduckgo|search the web")),
    ("CODE_SHELL", re.compile(r"\bcode\b|python|\bshell\b|terminal|command line|execute|script")),
    ("FILE_DATA", re.compile(r"excel|spreadsheet|\.csv|\.pdf|\.docx?|document|file|table|database")),
    ("CALC", re.compile(r"calculator|calculate|\bmath\b|arithmetic|compute")),
    ("AV_MEDIA", re.compile(r"video|audio|youtube|transcript|podcast|movie|tv show|lyrics")),
    ("IMAGE", re.compile(r"image|photo|picture|screenshot|ocr|figure|chart|diagram")),
]

_TRACE_TOOL_RULES = [
    ("WEB_SEARCH", re.compile(r"search|browse|fetch_url|web_|duckduckgo|google|wikipedia")),
    ("CODE_SHELL", re.compile(r"run_command|execute|bash|shell|python|pip|npm|git")),
    ("FILE_DATA", re.compile(r"read_file|write_file|edit_file|list_dir|find|grep|ls|cat|head|tail|wc|file")),
    ("CALC", re.compile(r"calcul|math|sympy|numpy")),
    ("AV_MEDIA", re.compile(r"yt|video|audio|transcript|ffmpeg|youtube")),
    ("IMAGE", re.compile(r"image|ocr|vision|screenshot|pil|opencv")),
]

_MULTIHOP_TOOLS = {"web_search", "search", "browse", "fetch_url", "read_file", "grep"}


def capability_tags(rec: dict, tools: Counter) -> list[str]:
    tags: set[str] = set()
    ann = rec.get("annotator") or {}
    ann_text = " ".join(
        str(ann.get(k) or "") for k in ("Tools", "Steps", "Number of steps", "Number of Steps", "tools", "steps")
    ).lower()
    steps_n = 0
    m = re.search(r"\d+", str(ann.get("Number of steps") or ann.get("Number of Steps") or ""))
    if m:
        steps_n = int(m.group())
    if not steps_n:
        steps_n = sum(1 for ln in str(ann.get("Steps") or "").splitlines() if re.match(r"^\s*\d+[\.\)]", ln))
    if steps_n >= 4 or len(re.findall(r"\b(search|find|look up|retrieve)\b", ann_text)) >= 2:
        tags.add("MULTIHOP")
    for tag, rx in _ANNOTATOR_RULES:
        if rx.search(ann_text):
            tags.add(tag)
    for tag, rx in _TRACE_TOOL_RULES:
        if any(rx.search(t) for t in tools):
            tags.add(tag)
    if any(re.search(r"search|web|browse", t) for t in tools) and len(set(tools)) >= 3:
        tags.add("MULTIHOP")
    tools_set = set(tools)
    if tools_set & _MULTIHOP_TOOLS and len(tools_set) >= 2:
        tags.add("MULTIHOP")
    if not tags:
        tags.add("OTHER")
    return sorted(tags)


# ---------------------------------------------------------------------------
# corpus selection
# ---------------------------------------------------------------------------


def build_trace_document(calls: list[dict], reasoning_notes: list[str], trace_summary: str,
                         meta: dict) -> dict:
    """组装生产级 form (b) trace 文档。

    合约（spec §10.6 form b）：顶层 ``{"tool_calls": [...], "reasoning_notes":
    [...], "trace_summary": ...}`` 由 ``load_trace_from_path`` 原样返回给
    ``generate_reflection`` —— 与生产 llm_trace 同构。``meta`` 携带回放驱动
    需要的 usage/review_evidence/重建来源信息，不参与反射 prompt。"""
    summary = trace_summary.strip()
    if not summary:
        feats = trace_features([tool_call_feature(c) for c in calls])
        lines = [f"## Tool trace ({feats['n_calls']} calls, {feats['n_errors']} errors, {feats['n_recovered']} recovered)"]
        for i, c in enumerate(calls[:40], 1):
            try:
                args_preview = json.dumps(c["args"], ensure_ascii=False)[:120]
            except (TypeError, ValueError):
                args_preview = str(c["args"])[:120]
            lines.append(f"{i}. {c['tool']}({args_preview})")
        summary = "\n".join(lines)
    doc = {
        "tool_calls": calls,
        "reasoning_notes": list(reasoning_notes),
        "trace_summary": summary,
    }
    if meta:
        doc["meta"] = meta
    return doc


def allocate(counts: dict, n: int) -> dict:
    """Largest-remainder allocation of n slots across groups."""
    total = sum(counts.values())
    if total <= 0 or n <= 0:
        return {}
    raw = {k: c * n / total for k, c in counts.items()}
    base = {k: int(v) for k, v in raw.items()}
    rem = n - sum(base.values())
    best_keys = sorted(raw, key=lambda k: (raw[k] - base[k], counts[k]), reverse=True)
    for k in best_keys[:rem]:
        base[k] += 1
    return base


def select_corpus(tasks: list[dict], size: int, failed_count: int, quota: int, min_calls: int, seed: int) -> tuple[list[dict], list[str]]:
    """Constrained greedy selection; returns (selected tasks, warnings)."""
    warnings: list[str] = []
    failed_pool = {lvl: [t for t in tasks if not t["passed"] and t["level"] == lvl and t["n_calls"] >= min_calls]
                   for lvl in (1, 2, 3)}
    passed_pool = {lvl: [t for t in tasks if t["passed"] and t["level"] == lvl and t["n_calls"] >= min_calls]
                   for lvl in (1, 2, 3)}
    failed_alloc = allocate({lvl: len(v) for lvl, v in failed_pool.items()}, failed_count)
    passed_alloc = allocate({lvl: len(v) for lvl, v in passed_pool.items()}, size - failed_count)
    allocations = {(lvl, False): failed_alloc.get(lvl, 0) for lvl in (1, 2, 3)}
    allocations.update({(lvl, True): passed_alloc.get(lvl, 0) for lvl in (1, 2, 3)})

    for lvl in (1, 2, 3):
        if failed_alloc.get(lvl, 0) > len(failed_pool[lvl]):
            warnings.append(f"level {lvl} failed pool ({len(failed_pool[lvl])}) < allocation {failed_alloc[lvl]}")
        if passed_alloc.get(lvl, 0) > len(passed_pool[lvl]):
            warnings.append(f"level {lvl} passed pool ({len(passed_pool[lvl])}) < allocation {passed_alloc[lvl]}")

    rng = random.Random(seed)
    all_tags = sorted({t for task in tasks for t in task["tags"]})
    quotas = {t: min(quota, sum(1 for task in tasks if t in task["tags"])) for t in all_tags}
    selected: list[dict] = []
    sel_by_key: dict = {}
    sel_tags = Counter()

    def group_key(task):
        return (task["level"], task["passed"])

    def score(task) -> tuple:
        deficit = sum(max(0, quotas[t] - sel_tags[t]) for t in task["tags"])
        recovery = (1.0 if task["n_recovered"] > 0 else 0.0) + (0.0 if task["passed"] else min(task["n_errors"], 5) * 0.1)
        calls = min(task["n_calls"], 20) * 0.01
        tie = -rng.random()
        return (deficit, recovery, calls, tie)

    for key in sorted(allocations, key=lambda k: (k[1], k[0])):  # failed first (reflection signal)
        need = allocations[key]
        pool = failed_pool if not key[1] else passed_pool
        for _ in range(need):
            candidates = [t for t in pool[key[0]] if t["uuid"] not in sel_by_key]
            if not candidates:
                if not warnings or not any(f"level {key[0]} pool exhausted" in w for w in warnings):
                    warnings.append(f"level {key[0]} {'failed' if not key[1] else 'passed'} pool exhausted before "
                                    f"filling {need} slots")
                break
            best = max(candidates, key=score)
            pool[key[0]].remove(best)
            sel_by_key[best["uuid"]] = best
            selected.append(best)
            for t in best["tags"]:
                sel_tags[t] += 1

    if len(selected) < size:
        warnings.append(f"selected {len(selected)} < requested {size}; relaxing min_calls=1")
        for key in sorted(allocations):
            need = allocations[key]
            already = sum(1 for t in selected if (t["level"], t["passed"]) == key)
            pool = [t for t in tasks if (t["level"], t["passed"]) == key and t["uuid"] not in sel_by_key]
            for _ in range(need - already):
                if not pool:
                    break
                best = max(pool, key=score)
                pool.remove(best)
                sel_by_key[best["uuid"]] = best
                selected.append(best)
                for t in best["tags"]:
                    sel_tags[t] += 1
    return selected, warnings


# ---------------------------------------------------------------------------
# attachments + original-data backup
# ---------------------------------------------------------------------------

_TEXT_ATTACHMENT_EXTS = frozenset({
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log",
    ".py", ".yaml", ".yml", ".ini", ".toml", ".rst",
})

_ATTACHMENT_TEXT_CAP = 3000


def _attachment_text(run_dir: pathlib.Path, uuid: str) -> tuple[str | None, str]:
    """把 samples/<uuid>/attachments/ 的文本类附件内容并入 task 文本。

    GAIA 题目常带附件（csv/pdf/xlsx…），反思需要看到附件内容才能判断题目
    形态；二进制附件只记文件名，文本类（utf-8 可读）读内容并入（总量上限
    ``_ATTACHMENT_TEXT_CAP``）。返回 (file_name, appended_text)。"""
    d = run_dir / "samples" / uuid / "attachments"
    if not d.is_dir():
        return None, ""
    files = sorted(p for p in d.iterdir() if p.is_file())
    if not files:
        return None, ""
    first_name = files[0].name
    parts: list[str] = []
    total = 0
    for p in files:
        if p.suffix.lower() not in _TEXT_ATTACHMENT_EXTS:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = body.strip()
        if not body:
            continue
        if total + len(body) > _ATTACHMENT_TEXT_CAP:
            body = body[:_ATTACHMENT_TEXT_CAP - total].rstrip()
        parts.append(f"[attachment {p.name}]\n{body}")
        total += len(body)
        if total >= _ATTACHMENT_TEXT_CAP:
            break
    return first_name, ("\n\n" + "\n\n".join(parts)) if parts else ""


_SHARED_BLOBS = "_shared_blobs"
_BACKUP_SEEN_BLOBS: set[str] = set()


def _backup_record(t: dict, backup_dir: pathlib.Path) -> None:
    """把重建轨迹引用的原始数据按任务备份。

    布局：``backups/<safe_id>/{calls/*.json, tools.jsonl, task_result.json,
    blob_refs.json}`` + 全语料共享的内容定址 blob 池 ``backups/_shared_blobs/
    <sha256>.json.gz``（跨任务去重）。blob 池按 sha256 命名，与内容定址
    语义一致，任何机器上都能按 trace 的 ``result_ref``/manifest 恢复。"""
    run_dir = t["run_dir"]
    hex_id = t.get("hex_id")
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied_blobs = 0
    if hex_id:
        calls_dir = backup_dir / "calls"
        calls_dir.mkdir(parents=True, exist_ok=True)
        headless_base = run_dir / "ouroboros_data" / "state" / "headless_tasks" / hex_id / "data"
        src_tools = headless_base / "logs" / "tools.jsonl"
        if src_tools.is_file():
            shutil.copy2(src_tools, backup_dir / "tools.jsonl")
        task_rec = _task_result_record(run_dir, hex_id)
        if task_rec:
            (backup_dir / "task_result.json").write_text(
                json.dumps(task_rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        blob_refs: list[dict] = []
        seen_call_ids: set[str] = set()
        index = _obs_index(run_dir)
        for line in per_task_lines(src_tools) if src_tools.is_file() else []:
            ref = line.get("result_ref")
            if not isinstance(ref, dict):
                continue
            call_id = str(ref.get("call_id") or "")
            if not call_id or call_id in seen_call_ids:
                continue
            seen_call_ids.add(call_id)
            mp = index.manifest_path(call_id)
            if mp is None or not mp.is_file():
                continue
            shutil.copy2(mp, calls_dir / mp.name)
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                continue
            fp = manifest.get("full_payload_ref") or {}
            sha = str(fp.get("sha256") or "")
            if not sha:
                continue
            src_blob = index.blob_path(sha)
            if src_blob is None or not src_blob.is_file():
                continue
            shared = backup_dir.parent / _SHARED_BLOBS
            shared.mkdir(parents=True, exist_ok=True)
            dst = shared / src_blob.name
            if sha not in _BACKUP_SEEN_BLOBS:
                shutil.copy2(src_blob, dst)
                _BACKUP_SEEN_BLOBS.add(sha)
                copied_blobs += 1
            blob_refs.append({"sha256": sha, "kind": str(fp.get("kind") or "json"),
                              "size": fp.get("size"), "call_id": call_id,
                              "path_in_shared": f"backups/{_SHARED_BLOBS}/{src_blob.name}"})
        if blob_refs:
            (backup_dir / "blob_refs.json").write_text(
                json.dumps(blob_refs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if hex_id is None and not backup_dir.exists():
        backup_dir.rmdir()


# ---------------------------------------------------------------------------
# source packing (trimmed copy for another host)
# ---------------------------------------------------------------------------

_PACK_PATTERNS = (
    "inspect_logs/*.json",                                              # authoritative scoring
    "samples/*/result.json",                                            # uuid -> hex + trace_summary
    "ouroboros_data/logs/tools.jsonl",                                  # global trace fallback
    "ouroboros_data/task_results/*.json",                               # global description index
    "ouroboros_data/state/headless_tasks/*/data/logs/tools.jsonl",      # per-task traces
    "ouroboros_data/state/headless_tasks/*/data/logs/events.jsonl",     # zero-tool evidence
    "ouroboros_data/state/headless_tasks/*/data/task_results/*.json",   # per-task description index
    "run_manifest.json",                                                # provenance (small)
)


def _pack_observability(run_dir: pathlib.Path, pack_root: pathlib.Path,
                        stats: dict) -> None:
    """复制生产级轨迹重建所需的 observability：全部 call manifests + blobs。

    排除 settings.json 与无关文件；blob 为内容定址（跨任务同名自动去重）。
    体积大（每个 run 几 MB~上百 MB），由 ``--pack-observability`` 显式开启。
    """
    obs_roots = [run_dir / "ouroboros_data" / "observability"]
    ht_root = run_dir / "ouroboros_data" / "state" / "headless_tasks"
    if ht_root.is_dir():
        for hd in ht_root.iterdir():
            obs_roots.append(hd / "data" / "observability")
    for obs in obs_roots:
        calls_root = obs / "calls"
        if calls_root.is_dir():
            for p in calls_root.glob("*/*.json"):
                dst = pack_root / p.relative_to(run_dir.parent)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    continue
                shutil.copy2(p, dst)
                stats["files"] += 1
                stats["bytes"] += p.stat().st_size
        blobs_dir = obs / "blobs"
        if blobs_dir.is_dir():
            for p in blobs_dir.glob("*.json.gz"):
                dst = pack_root / p.relative_to(run_dir.parent)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    continue
                shutil.copy2(p, dst)
                stats["files"] += 1
                stats["bytes"] += p.stat().st_size


def pack_source(runs_root: pathlib.Path, pack_root: pathlib.Path,
                with_observability: bool = False) -> int:
    """Mirror only the files extraction reads into ``pack_root``.

    Deliberately excludes ``settings.json`` (plaintext API keys) and other
    runtime dirs — the pack is a portable input for a remote host to re-run
    ``extract_evolution_corpus.py`` deterministically. 生产级轨迹重建需要
    observability 全量 payload（完整工具结果 + 轮次文本），默认不打包
    （体积大）；``--pack-observability`` 时一并复制 calls manifests + blobs。
    """
    try:
        os.path.commonpath([str(runs_root.resolve()), str(pack_root.resolve())])
    except ValueError:
        pass
    else:
        if pack_root.resolve() != runs_root.resolve() and \
                str(pack_root.resolve()).startswith(str(runs_root.resolve())):
            print(f"error: --pack-source {pack_root} 不能位于 runs-root 内部", file=sys.stderr)
            return 2
    copied = 0
    total_bytes = 0
    obs_stats = {"files": 0, "bytes": 0}
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        for pattern in _PACK_PATTERNS:
            for src in sorted(run_dir.glob(pattern)):
                if not src.is_file():
                    continue
                dst = pack_root / src.relative_to(runs_root)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
                total_bytes += src.stat().st_size
        if with_observability:
            _pack_observability(run_dir, pack_root, obs_stats)
    print(f"pack: {copied} 个文件, {total_bytes / 1024 / 1024:.1f} MB → {pack_root}")
    if with_observability:
        print(f"pack: observability {obs_stats['files']} 个文件, "
              f"{obs_stats['bytes'] / 1024 / 1024:.1f} MB（生产级轨迹重建所需全量）")
    if not copied:
        print("  警告: 未匹配到任何文件（确认 --runs-root 结构）")
    return 0


# ---------------------------------------------------------------------------
# stats / validation
# ---------------------------------------------------------------------------


def build_pretty_markdown(selected: list[dict], args) -> str:
    """Human-readable view of the corpus; the JSONL remains the canonical form."""
    L = []
    A = L.append
    A("# GAIA 进化语料全览（人工可读版）\n")
    A(f"- 语料：`gaia_corpus_{args.date}.jsonl`（{len(selected)} 条；本文件只是排版视图，"
      f"进化管道消费的是 JSONL 原文，两者同源同序）")
    A(f"- 生成参数：size={args.size}, failed={args.failed_count}, min_calls={args.min_calls}, "
      f"tag quota={args.quota}, seed={args.seed}\n")
    A("## 速览")
    A("| # | id | L | 成败 | 能力标签 | 调用 | 错 | 恢复 | 题目摘要 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for i, t in enumerate(selected, 1):
        summary = " ".join(t["question"].split())[:58]
        A(f"| {i} | {t['id']} | {t['level']} | {'✓' if t['passed'] else '✗'} | "
          f"{','.join(t['tags'])} | {t['n_calls']} | {t['n_errors']} | {t['n_recovered']} | {summary} |")
    A("")
    for i, t in enumerate(selected, 1):
        A(f"### {i}. {t['id']} — Level {t['level']} — {'✅ 通过' if t['passed'] else '❌ 失败'}\n")
        A(f"- **任务**：{t['question']}")
        A(f"- **参考答案 (target)**：{t['target'] or '(无)'}")
        A(f"- **模型答案 (final_answer)**：{t['completion'] or '(无)'}")
        A(f"- **reason_code**：{t['reason_code'] or '(空)'}")
        A(f"- **uuid**：`{t['uuid']}` ｜ **started_at**：{t['started_at']}")
        A(f"- **能力标签**：{', '.join(t['tags'])} ｜ **轨迹源**：{t['trace_source']}"
          f"（{t['n_calls']} 次调用 / {t['n_errors']} 错误 / {t['n_recovered']} 恢复）")
        A(f"- **trace_ref**：`traces/{trace_safe_id(t['id'])}.json`（相对语料目录）\n")
        calls = [tool_call_feature(c) for c in t["calls_raw"]]
        A("**工具调用序列（前 15 条）**：\n")
        for c in calls[:15]:
            mark = "⚠" if c["is_error"] else "·"
            args_txt = " ".join(str(c["args"]).split())[:88] if c["args"] else ""
            res_txt = " ".join(c["result"].split())[:96]
            A(f"- `{mark} {c['tool']}({args_txt})` → {res_txt}")
        if len(calls) > 15:
            A(f"- …（共 {len(calls)} 次调用，完整序列见 trace 文件）")
        ts = (t.get("trace_summary_raw") or "").strip()
        if ts:
            tl = ts.splitlines()
            A("\n**trace_summary**：\n")
            A("```")
            A("\n".join(tl[:24]))
            if len(tl) > 24:
                A(f"…（共 {len(tl)} 行，完整见 trace 文件）")
            A("```")
        A("")
    return "\n".join(L)


def build_stats(tasks: list[dict], selected: list[dict], records: list[dict], out_dir: pathlib.Path,
                args) -> str:
    L = []
    A = L.append
    A(f"# GAIA 进化语料提取报告（corpus stats）\n")
    A(f"- 生成时间: {_dt.datetime.now().isoformat(timespec='seconds')}")
    A(f"- 数据源: `{args.runs_root}`（{len(set(r['run'] for r in records))} 个 run, 共 {len(records)} 条样本记录）")
    A(f"- 输出目录: `{out_dir}`")
    A(f"- 选择参数: size={args.size}, failed={args.failed_count}, min_calls={args.min_calls}, "
      f"tag quota={args.quota}, seed={args.seed}\n")
    A(f"## A. 去重统计（按 uuid, best=C>I>None, 平局取最新）")
    by_uuid = defaultdict(list)
    for r in records:
        by_uuid[r["uuid"]].append(r)
    dup_tasks = [u for u, recs in by_uuid.items() if len(recs) > 1]
    A(f"- 样本记录 {len(records)} 条 → 唯一任务 {len(tasks)} 个；重复运行任务 {len(dup_tasks)} 个，"
      f"清除多余记录 {len(records) - len(tasks)} 条")
    dist = Counter((t["level"], t["passed"]) for t in tasks)
    A(f"- 唯一任务按 (level, 成败): " + ", ".join(
        f"L{lvl}{'✓' if p else '✗'}={dist[(lvl, p)]}" for lvl in (1, 2, 3) for p in (False, True)))
    A(f"- 最好成绩 C: {sum(1 for t in tasks if t['passed'])}；最好成绩 I: {sum(1 for t in tasks if not t['passed'])}\n")
    A(f"## B. 轨迹解析情况")
    src = Counter(t["trace_source"] for t in tasks)
    A(f"- trace 来源分布: " + ", ".join(f"{k}={v}" for k, v in sorted(src.items())))
    recon = Counter(t["reconstruction"]["tool_calls_source"] for t in tasks)
    A(f"- 重建来源分布（生产级）: " + ", ".join(f"{k}={v}" for k, v in sorted(recon.items())))
    notes_src = Counter(t["reconstruction"]["notes_source"] for t in tasks)
    A(f"- reasoning_notes 来源: " + ", ".join(f"{k}={v}" for k, v in sorted(notes_src.items())))
    sum_src = Counter(t["reconstruction"]["summary_source"] for t in tasks)
    A(f"- trace_summary 来源: " + ", ".join(f"{k}={v}" for k, v in sorted(sum_src.items())))
    n_notes = sum(1 for t in tasks if t["reasoning_notes_raw"])
    A(f"- 有真实轮次文本(notes)的任务: {n_notes}/{len(tasks)}；"
      f"notes 总条数: {sum(len(t['reasoning_notes_raw']) for t in tasks)}")
    no_trace = [t for t in tasks if t["n_calls"] == 0]
    A(f"- 无轨迹任务: {len(no_trace)}（task_eval 显示零工具直接作答 → 无工具经验，排除出语料）")
    for t in no_trace:
        ev = t.get("eval_tool_calls")
        A(f"  - {t['id']} {t['uuid']} L{t['level']} {'✓' if t['passed'] else '✗'} "
          f"eval_tool_calls={ev} {repr(t['question'][:60])}")
    A("")
    A("## C. 失败任务明细（35 个 best-I；trace_ok=轨迹可用）")
    A("| id | uuid | level | n_calls | n_errors | trace | 抽入语料 |")
    A("|---|---|---|---|---|---|---|")
    sel_ids = {t["uuid"] for t in selected}
    for t in tasks:
        if t["passed"]:
            continue
        A(f"| {t['id']} | `{t['uuid']}` | {t['level']} | {t['n_calls']} | {t['n_errors']} | "
          f"{'✓' if t['n_calls'] else '✗'} | {'✓' if t['uuid'] in sel_ids else ''} |")
    A("")
    A("## D. 语料选择清单（40 条，顺序 = 喂料顺序）")
    A("| id | level | 成败 | tags | n_calls | n_err | n_rec | trace 源 |")
    A("|---|---|---|---|---|---|---|---|")
    for t in selected:
        marks = "✓" if t["passed"] else "✗"
        A(f"| {t['id']} | {t['level']} | {marks} | {','.join(t['tags'])} | {t['n_calls']} | "
          f"{t['n_errors']} | {t['n_recovered']} | {t['trace_source']} |")
    A("")
    A("## E. 能力覆盖矩阵（标签 × 选中数 / 可用池）")
    pool_tags = Counter(tg for t in tasks for tg in t["tags"])
    sel_tags = Counter(tg for t in selected for tg in t["tags"])
    A("| tag | 选中 | 可用池 | 配额 |")
    A("|---|---|---|---|")
    for tg in sorted(pool_tags):
        quota = min(args.quota, pool_tags[tg])
        A(f"| {tg} | {sel_tags[tg]} | {pool_tags[tg]} | {quota} |")
    A("")
    A("## F. 校验结果")
    ok = validate_corpus(out_dir, selected, args.size, args.failed_count)
    for line in ok["lines"]:
        A(line)
    A("")
    A("## G. 与评估切片不相交确认（spec §1.3）")
    corpus_ids = "".join(t["id"] for t in selected)
    h = hashlib.sha256(corpus_ids.encode("utf-8")).hexdigest()
    A(f"- 语料：GAIA 2023 validation 实例 {len(selected)} 条，id 序列 sha256=`{h[:16]}…`")
    A(f"- 评估集：Terminal-Bench 89 条（用户环境）。GAIA 与 TB 为不同基准、不同题面 → 零重叠成立 "
      f"（TB 任务列表在远端 harness，不做本地哈希）。")
    return "\n".join(L)


def validate_corpus(out_dir: pathlib.Path, selected: list[dict], size: int, failed_count: int) -> dict:
    lines = []
    errors = []
    safe_ids: set[str] = set()
    for t in selected:
        safe = trace_safe_id(t["id"])
        if safe in safe_ids:
            errors.append(f"safe id collision: {safe}")
        safe_ids.add(safe)
        p = out_dir / "traces" / f"{safe}.json"
        if not p.is_file():
            errors.append(f"missing trace file {safe}")
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"trace {safe} unparseable: {exc}")
            continue
        # spec §10.6 form (b): {"tool_calls": [...]} consumed as-is
        calls = data.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            errors.append(f"trace {safe} empty tool_calls")
            continue
        if any(not isinstance(c, dict) or not c.get("tool") for c in calls):
            errors.append(f"trace {safe} malformed tool_call")
        if not isinstance(data.get("reasoning_notes"), list):
            errors.append(f"trace {safe} missing reasoning_notes")
        if not isinstance(data.get("trace_summary"), str) or not data["trace_summary"].strip():
            errors.append(f"trace {safe} missing trace_summary")
        meta = data.get("meta") or {}
        if not isinstance(meta.get("usage"), dict):
            errors.append(f"trace {safe} missing meta.usage")
        if not isinstance(meta.get("reconstruction"), dict):
            errors.append(f"trace {safe} missing meta.reconstruction")
        # trace 文件路径与 JSONL id 的安全命名一致（load_trace_from_path 依赖）
        if trace_safe_id(str(meta.get("id") or "")) != safe:
            errors.append(f"trace {safe} meta.id mismatch")
        # 生产级重建时每条 call 应带 tool_call_id / 状态字段；降级视图可缺
        if meta.get("reconstruction", {}).get("tool_calls_source", "").startswith("observability_") and \
                any(not c.get("tool_call_id") for c in calls[:5] if isinstance(c, dict)):
            errors.append(f"trace {safe} production-grade calls missing tool_call_id")
        # 备份目录存在（非空语料输出时）
        backup_dir = out_dir / "backups" / safe
        if backup_dir.is_dir() and not any(backup_dir.iterdir()):
            errors.append(f"backup {safe} empty")
    ids = [t["id"] for t in selected]
    if len(ids) != len(set(ids)):
        errors.append("duplicate corpus ids")
    if len(selected) != size:
        errors.append(f"corpus size {len(selected)} != {size}")
    n_failed = sum(1 for t in selected if not t["passed"])
    if n_failed != failed_count:
        errors.append(f"failed records {n_failed} != {failed_count}")

    lines.append(f"- 逐条回读轨迹（spec §10.6 load_trace_from_path 语义）: {'通过' if not any('trace' in e or 'tool_calls' in e for e in errors) else '失败'}")
    ok_counts = Counter((t["level"], t["passed"]) for t in selected)
    lines.append(f"- 语料分布: " + ", ".join(
        f"L{lvl}{'✓' if p else '✗'}={ok_counts[(lvl, p)]}" for lvl in (1, 2, 3) for p in (False, True)) +
        f"（目标: failed={sum(1 for t in selected if not t['passed'])}）")
    if errors:
        lines.append(f"- ❌ 校验失败 {len(errors)} 项:")
        for e in errors[:20]:
            lines.append(f"  - {e}")
    else:
        lines.append("- ✅ 全部校验通过：40 条 id 唯一（含安全命名）、trace_ref 全部存在且可回读、"
                     "生产级字段（reasoning_notes/trace_summary/meta.usage）齐全、分布符合分配。")
    return {"lines": lines, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract the GAIA evolution corpus from existing run outputs.")
    ap.add_argument("--runs-root", default=os.environ.get("OUROBOROS_GAIA_RUNS_ROOT"),
                    help="Directory holding the GAIA run outputs (default env OUROBOROS_GAIA_RUNS_ROOT)")
    ap.add_argument("--pack-source", type=pathlib.Path, default=None,
                    help="Copy only the files extraction needs from --runs-root into this dir "
                         "(excludes settings.json), then exit")
    ap.add_argument("--pack-observability", action="store_true",
                    help="With --pack-source: also copy observability calls manifests + blobs "
                         "(production-grade trace reconstruction needs them; bulk of the pack)")
    ap.add_argument("--out", type=pathlib.Path,
                    default=REPO / "bench_runs" / "evolution_corpus",
                    help="Output directory (default <repo>/bench_runs/evolution_corpus)")
    ap.add_argument("--date", default=_dt.date.today().isoformat())
    ap.add_argument("--size", type=int, default=40, help="Corpus size (spec: 30~40)")
    ap.add_argument("--failed-count", type=int, default=14, help="Number of failed records (spec: >= 1/3)")
    ap.add_argument("--min-calls", type=int, default=3, help="Minimum tool calls for a usable trace")
    ap.add_argument("--quota", type=int, default=4, help="Minimum selected count per capability tag")
    ap.add_argument("--seed", type=int, default=20260829)
    args = ap.parse_args()
    if not args.runs_root or not pathlib.Path(args.runs_root).is_dir():
        print(f"error: --runs-root must point to the GAIA runs directory; got {args.runs_root!r}", file=sys.stderr)
        return 2

    runs_root = pathlib.Path(args.runs_root)
    if args.pack_source is not None:
        return pack_source(runs_root, args.pack_source.resolve(),
                           with_observability=args.pack_observability)
    print(f"[1/6] scanning {runs_root} ...")
    records = scan_runs(runs_root)
    print(f"      {len(records)} sample records across {len({r['run'] for r in records})} runs")
    if not records:
        print("error: no inspect_logs found under runs root", file=sys.stderr)
        return 2

    print("[2/6] deduplicating by uuid (best score, latest run) ...")
    tasks = dedup(records)
    print(f"      {len(tasks)} unique tasks ({sum(1 for t in tasks if t['score'] == 'C')} passed / "
          f"{sum(1 for t in tasks if t['score'] != 'C')} failed)")

    print("[3/6] resolving traces (production-grade reconstruction) ...")
    for t in tasks:
        tr = resolve_trace(t)
        t["trace_source"] = tr["source"]
        t["hex_id"] = tr["hex_id"]
        feats = trace_features([tool_call_feature(c) for c in tr["tool_calls"]])
        t["n_calls"] = feats["n_calls"]
        t["n_errors"] = feats["n_errors"]
        t["n_recovered"] = feats["n_recovered"]
        t["tools"] = feats["tools"]
        t["trace_summary_raw"] = tr["trace_summary"]
        t["calls_raw"] = tr["tool_calls"]
        t["reasoning_notes_raw"] = tr["reasoning_notes"]
        t["reconstruction"] = tr["reconstruction"]
        t["usage_raw"] = tr["usage"]
        t["review_evidence_raw"] = tr["review_evidence"]
        t["passed"] = t["score"] == "C"
        t["tags"] = capability_tags(t, feats["tools"])
        t.setdefault("extra_rounds", None)
    # corpus ids: per-level sequential index over unique tasks (sorted by uuid)
    lvl_idx = Counter()
    for t in tasks:
        lvl_idx[t["level"]] += 1
        t["id"] = f"2023_level{t['level']}:{lvl_idx[t['level']]}"
    recon_src = Counter(t["reconstruction"]["tool_calls_source"] for t in tasks)
    print(f"      trace sources: {dict(Counter(t['trace_source'] for t in tasks))}")
    print(f"      reconstruction: {dict(recon_src)}")
    has_notes = sum(1 for t in tasks if t["reasoning_notes_raw"])
    print(f"      reasoning_notes: {has_notes}/{len(tasks)} 条记录有真实轮次文本")

    print(f"[4/6] selecting {args.size} records "
          f"({args.failed_count} failed, min_calls={args.min_calls}, quota={args.quota}, seed={args.seed}) ...")
    selected, warnings = select_corpus(tasks, args.size, args.failed_count, args.quota, args.min_calls, args.seed)
    for w in warnings:
        print(f"      ! {w}")
    print(f"      selected {len(selected)} ({sum(1 for t in selected if not t['passed'])} failed)")

    print(f"[5/6] writing corpus to {args.out} ...")
    out_dir = pathlib.Path(args.out)
    traces_dir = out_dir / "traces"
    backups_dir = out_dir / "backups"
    traces_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = out_dir / f"gaia_corpus_{args.date}.jsonl"
    with corpus_path.open("w", encoding="utf-8", newline="\n") as fh:
        for t in selected:
            safe = trace_safe_id(t["id"])
            file_name, attach_text = _attachment_text(t["run_dir"], t["uuid"])
            task_text = t["question"] + (attach_text or "")
            rec = {
                "id": t["id"],
                "level": t["level"],
                "task": task_text,
                "file_name": file_name,
                "outcome": {
                    "passed": t["passed"],
                    "final_answer": t["completion"],
                    "reason_code": t["reason_code"],
                },
                "cost": t["usage_raw"] or None,
                "trace_ref": f"traces/{safe}.json",
                "uuid": t["uuid"],
                "target": t["target"],
                "started_at": t["started_at"],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for t in selected:
            safe = trace_safe_id(t["id"])
            meta = {
                "usage": t["usage_raw"] or {},
                "reconstruction": t["reconstruction"],
                "task_id": t["hex_id"],
                "uuid": t["uuid"],
                "level": t["level"],
                "id": t["id"],
            }
            if t["review_evidence_raw"]:
                meta["review_evidence"] = t["review_evidence_raw"]
            doc = build_trace_document(t["calls_raw"], t["reasoning_notes_raw"],
                                       t["trace_summary_raw"], meta)
            (traces_dir / f"{safe}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            t["reconstruction"]["blobs_backed_up"] = True
            _backup_record(t, backups_dir / safe)
    print(f"      {corpus_path}  ({len(selected)} lines)")
    print(f"      {traces_dir}  ({len(selected)} trace files)")
    print(f"      {backups_dir}  (原始数据备份: tools.jsonl/task_result/blobs)")

    print("[6/6] validating and writing stats ...")
    stats = build_stats(tasks, selected, records, out_dir, args)
    stats_path = out_dir / "corpus_stats.md"
    stats_path.write_text(stats, encoding="utf-8")
    print(f"      {stats_path}")
    pretty_path = out_dir / "corpus_pretty.md"
    pretty_path.write_text(build_pretty_markdown(selected, args), encoding="utf-8")
    print(f"      {pretty_path}")
    ok = validate_corpus(out_dir, selected, args.size, args.failed_count)
    for line in ok["lines"]:
        print("      " + line)
    return 0 if not ok["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())