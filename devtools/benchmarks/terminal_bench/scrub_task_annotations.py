#!/usr/bin/env python3
"""Strip injected task-annotation blocks out of a run's output artifacts.

WHY THIS EXISTS

When OUROBOROS_TB_TASK_ANNOTATIONS=1, the adapter appends a `<task-annotations>`
block to the task instruction, and that block is then persisted everywhere the
instruction is: the trial's instruction.txt, the trajectory's first message, the
runner's task-result JSON (six fields carry the whole instruction), the event
and journal jsonl files, and the in-container headless-task logs. Runs made
under that flag are not a clean measurement, so before an artifact is quoted,
published or fed to a downstream corpus, the annotated text has to come out --
everywhere, not just in instruction.txt.

WHAT IT TOUCHES

Point it at a job directory (a timestamped batch dir holding many trial dirs),
a single trial dir, or any parent of either. It walks the tree, finds every text
file that still carries the block, and removes the block together with its
`--- task-specific annotations ... ---` header line. Nothing else is rewritten:
the raw bytes outside the removed region are left alone, JSON/JSONL files are
re-parsed afterwards to prove they are still valid, and a dry run (the default)
prints exactly what --apply would change.

Usage:
    python scrub_task_annotations.py <path> [<path> ...]            # dry run
    python scrub_task_annotations.py <path> [...] --apply           # rewrite
    python scrub_task_annotations.py <path> [...] --apply --backup  # keep .pre-scrub

Exit status is 1 when any marker survives (a variant this tool does not know
about), so a caller can gate on it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HEADER = r"---\s*task-specific annotations \(from task failure analysis\)\s*---"
OPEN_TAG = "<task-annotations>"
CLOSE_TAG = "</task-annotations>"

# A JSON-string newline shows up in the raw bytes as the two characters backslash-n,
# while a plain-text file has a real newline. Both shapes occur in the same run, so
# every pattern below accepts either.
_NL = r"(?:\\n|\r?\n)"
_TAGGED_BLOCK = re.compile(
    _NL + r"*[ \t]*" + HEADER + _NL + r"*[ \t]*" + re.escape(OPEN_TAG) + r".*?" + re.escape(CLOSE_TAG),
    re.S,
)
_HEADER_ONLY = re.compile(_NL + r"*[ \t]*" + HEADER)
_ORPHAN_OPEN = re.compile(re.escape(OPEN_TAG) + r".*?" + re.escape(CLOSE_TAG), re.S)
_ORPHAN_TAGS = re.compile(re.escape(OPEN_TAG) + r"|" + re.escape(CLOSE_TAG))

# The runtime shortens long strings it journals, so a copy of the instruction can end
# with the annotation's opening tag and no closing tag -- "... [+459 chars; full text in
# this task's task_results / digest]". Pairing-only patterns miss those, and a tag-only
# cleanup then leaves the annotation BODY embedded in the text. Everything from the
# header/opening tag to the elision notice (or to the end of the string, when the notice
# is absent) is annotation content: the adapter appends the block last, so the tail is
# always annotation.
_TRUNCATION_NOTICE = re.compile(r"… \[\+?\d+ chars;[^\]\n]*\]")
_TRUNCATED_BLOCK = re.compile(
    r"(?:" + _NL + r"*[ \t]*" + HEADER + _NL + r"*[ \t]*)?" + re.escape(OPEN_TAG),
)

MARKER_PROBES = (OPEN_TAG, CLOSE_TAG, "task-specific annotations")


def _corpus_probes() -> tuple[str, ...]:
    """Opening words of every annotation body this repo ships, as content probes.

    Tags and the header line are cheap to detect but easy to lose: the runtime's own
    text elision can cut the closing tag off, and a tag-only cleanup then leaves the
    annotation BODY in place. Probing for the body itself catches that class.
    """
    ann_dir = pathlib.Path(__file__).resolve().parent / "exp" / "capabilities" / "annotations"
    probes: list[str] = []
    if ann_dir.is_dir():
        for path in sorted(ann_dir.glob("*.txt")):
            first = (path.read_text(encoding="utf-8", errors="replace").strip().splitlines() or [""])[0]
            first = first.strip()
            if len(first) >= 24:
                probes.append(first[:48])
    return tuple(probes)


_CONTENT_PROBES = _corpus_probes()
RESIDUAL_PROBES = MARKER_PROBES + _CONTENT_PROBES


def _cut_truncated(text: str) -> tuple[str, int]:
    """Drop the annotation tail when the closing tag was elided away."""
    match = _TRUNCATED_BLOCK.search(text)
    if match is None:
        return text, 0
    end = len(text)
    notice = _TRUNCATION_NOTICE.search(text, match.end())
    if notice is not None:
        end = notice.start()
    return text[: match.start()] + text[end:], 1


def clean_blob(text: str) -> tuple[str, int]:
    """Remove annotation blocks from one decoded-or-raw string. Returns (new, hits)."""
    hits = 0
    for pattern in (_TAGGED_BLOCK, _ORPHAN_OPEN):
        text, n = pattern.subn("", text)
        hits += n
    # Only now: an opening tag that survived the paired patterns has no closing tag,
    # so the annotation runs to the elision notice or to the end of the string.
    if OPEN_TAG in text:
        text, n = _cut_truncated(text)
        hits += n
    for pattern in (_HEADER_ONLY, _ORPHAN_TAGS):
        text, n = pattern.subn("", text)
        hits += n
    return text, hits


# ------------------------------------------------------------------------ file IO


def _read_text(path: pathlib.Path) -> str | None:
    """Decode a file as UTF-8, or return None when it is not text."""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _dump_matching_style(path: pathlib.Path, obj) -> str:
    """Re-encode JSON the way the file was written, so the diff stays the block."""
    indent = 2 if path.read_text(encoding="utf-8", errors="replace").startswith("{\n") else None
    return json.dumps(obj, ensure_ascii=False, indent=indent)


def _clean_json(path: pathlib.Path, text: str, hits: int) -> tuple[str, int, str]:
    obj = json.loads(text)
    cleaned, n = _clean_json_value(obj)
    if n:
        text = _dump_matching_style(path, cleaned) + ("\n" if text.endswith("\n") else "")
    return text, hits + n, "json"


def _clean_json_value(obj) -> tuple[object, int]:
    if isinstance(obj, dict):
        out, n = {}, 0
        for k, v in obj.items():
            new_v, m = _clean_json_value(v)
            out[k] = new_v
            n += m
        return out, n
    if isinstance(obj, list):
        out, n = [], 0
        for v in obj:
            new_v, m = _clean_json_value(v)
            out.append(new_v)
            n += m
        return out, n
    if isinstance(obj, str):
        return clean_blob(obj)
    return obj, 0


def _clean_file(path: pathlib.Path) -> tuple[str, int, str]:
    """Return (new_text, hits, kind) for one file; kind is '' when nothing matched."""
    text = _read_text(path)
    if text is None or not any(probe in text for probe in RESIDUAL_PROBES):
        return "", 0, ""
    cleaned, hits = clean_blob(text)
    if path.suffix in (".json", ".jsonl") and any(probe in cleaned for probe in RESIDUAL_PROBES):
        # A variant the raw pass could not remove (e.g. a truncated block whose end
        # anchor is missing). Re-encode structurally so the cut happens inside the
        # string value and the file cannot end up invalid JSON.
        try:
            if path.suffix == ".json":
                return _clean_json(path, text, hits)
            out_lines, total = [], hits
            for line in text.splitlines(keepends=True):
                body = line.rstrip("\n")
                if not body.strip() or not any(probe in body for probe in RESIDUAL_PROBES):
                    out_lines.append(line)
                    continue
                obj = json.loads(body)
                obj, n = _clean_json_value(obj)
                total += n
                out_lines.append(json.dumps(obj, ensure_ascii=False) + ("\n" if line.endswith("\n") else ""))
            return "".join(out_lines), total, "jsonl"
        except json.JSONDecodeError:
            pass  # fall through: keep the raw-pass result rather than corrupting the file
    return cleaned, hits, "text"


def _validate(path: pathlib.Path, text: str) -> str:
    """Prove the rewritten bytes still parse. Returns '' when fine, else a reason."""
    if path.suffix == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            return f"invalid JSON after scrub: {exc}"
    elif path.suffix == ".jsonl":
        for idx, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                return f"invalid JSONL at line {idx}: {exc}"
    return ""


# ------------------------------------------------------------------------- driver


def _trial_root(path: pathlib.Path) -> pathlib.Path | None:
    """Nearest ancestor that looks like a trial dir (<task>__<hash> with agent/)."""
    for candidate in (path, *path.parents):
        if (candidate / "agent" / "instruction.txt").is_file():
            return candidate
    return None


def scrub(paths: list[pathlib.Path], *, apply: bool, backup: bool) -> int:
    targets: list[tuple[pathlib.Path, pathlib.Path, str, int, str]] = []
    for root in paths:
        if not root.exists():
            print(f"!! missing path: {root}", file=sys.stderr)
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            # Never touch our own backups: re-running after --backup would otherwise
            # scrub the pristine copy the user asked to keep.
            if path.name.endswith(".pre-scrub"):
                continue
            new_text, hits, kind = _clean_file(path)
            if hits:
                trial = _trial_root(path)
                targets.append((path, trial or path.parent, kind, hits, new_text))

    if not targets:
        print("no annotation traces found")
        return 0

    by_trial: dict[pathlib.Path, list] = {}
    for path, trial, kind, hits, new_text in targets:
        by_trial.setdefault(trial, []).append((path, kind, hits, new_text))

    failures = 0
    for trial, entries in sorted(by_trial.items()):
        print(f"\n{trial}")
        for path, kind, hits, new_text in entries:
            raw = _read_text(path) or ""
            # Validation follows the file format, not the cleaning path: a .json whose
            # block came out with the raw pass still has to prove it parses.
            reason = _validate(path, new_text) if path.suffix in (".json", ".jsonl") else ""
            delta = len(raw) - len(new_text)
            rel = path.relative_to(trial) if path.is_relative_to(trial) else path
            status = "SKIP (would corrupt)" if reason else ("write" if apply else "would write")
            if reason:
                failures += 1
            print(f"  [{kind:5}] -{delta:>7} B  {rel}  ({status}{'; ' + reason if reason else ''})")
            if apply and not reason:
                if backup:
                    path.with_name(path.name + ".pre-scrub").write_text(raw, encoding="utf-8")
                path.write_text(new_text, encoding="utf-8")

    # Two independent checks. The first inspects the text we are about to write, so a
    # pattern gap (e.g. an annotation body whose tags were elided away) is reported even
    # in a dry run. The second re-reads the files after --apply and proves it is gone.
    incomplete = [path for path, _, _, _, new_text in targets
                  if any(probe in new_text for probe in RESIDUAL_PROBES)]
    residual = []
    if apply:
        for path, _, _, _, _ in targets:
            text = _read_text(path) or ""
            if any(probe in text for probe in RESIDUAL_PROBES):
                residual.append(path)
    print(f"\n{len(targets)} file(s) across {len(by_trial)} trial(s); "
          f"{'rewritten' if apply else 'dry run (pass --apply to rewrite)'}")
    if incomplete:
        print(f"!! {len(incomplete)} file(s) would keep annotation text after cleaning "
              f"(pattern gap -- extend clean_blob):")
        for path in incomplete[:10]:
            print(f"   {path}")
        return 1
    if residual:
        print(f"!! {len(residual)} file(s) still carry a marker:")
        for path in residual:
            print(f"   {path}")
        return 1
    if failures:
        print(f"!! {failures} file(s) skipped to avoid corruption")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=pathlib.Path,
                        help="job dir, trial dir, or any parent holding them")
    parser.add_argument("--apply", action="store_true", help="rewrite files (default: dry run)")
    parser.add_argument("--backup", action="store_true", help="keep a <file>.pre-scrub copy before rewriting")
    args = parser.parse_args()
    return scrub([p.expanduser() for p in args.paths], apply=args.apply, backup=args.backup)


if __name__ == "__main__":
    sys.exit(main())
