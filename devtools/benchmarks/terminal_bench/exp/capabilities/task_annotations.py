"""Per-task annotations injected into the Terminal-Bench task instruction.

WHAT THIS IS

For tasks where earlier runs of this benchmark were observed to die, the adapter can
append a short note describing what killed them (e.g. make-doom-for-mips: "mimo ran
the full 15 minutes and never once executed `node vm.js`"). It is the only
prompt-side capability this adapter has.

VALIDITY -- read before using these in a reported measurement

The bodies encode *what previous runs of this exact task died on*. That is knowledge
distilled from the benchmark's own failure modes, so a run with annotations on is NOT
a clean measurement of the model against the dataset. Fine for internal ablation and
debugging; it must be disclosed wherever results are reported, and it must not be
silently mixed into a baseline arm.

LAYOUT

The bodies live as one file per task under `annotations/<task>.txt`, not as string
literals here. They run to ~4 KB each, so inlining them made this a 39 KB module
whose every edit was a whole-file diff and where navigating between the loader and
one task's text meant scrolling past thirteen others. With the files split out:

  * `ls annotations/` answers "which tasks are annotated" without reading code;
  * adding an annotation is adding a file, not another 200-line paste;
  * the loader below is short enough to read in one screen.

The filename IS the task key, so a renamed task and its annotation cannot drift
apart silently -- `annotated_tasks()` simply reflects the directory.

Everything the adapter imports is unchanged: TASK_ANNOTATIONS,
render_task_annotations(), annotations_enabled().
"""
from __future__ import annotations

import os
from pathlib import Path

# The one flag that turns this arm on. Owned here (not in the adapter) so the
# adapter and any future caller cannot disagree about whether it is enabled.
ENV_FLAG = "OUROBOROS_TB_TASK_ANNOTATIONS"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

ANNOTATIONS_DIR = Path(__file__).resolve().parent / "annotations"
_SUFFIX = ".txt"


# --------------------------------------------------------------------------- loading


def _load_annotations(directory: Path = ANNOTATIONS_DIR) -> dict[str, str]:
    """Read one annotation per `<task>.txt`, keyed by filename stem.

    A missing directory loads as empty rather than raising: annotations are an
    optional arm, and a packaging mistake should disable the feature, not break
    every trial that imports this module. Only newlines are stripped, so an editor
    that appends a trailing newline is harmless while any leading indentation in a
    body survives verbatim.
    """
    if not directory.is_dir():
        return {}
    loaded: dict[str, str] = {}
    for path in sorted(directory.glob(f"*{_SUFFIX}")):
        try:
            body = path.read_text(encoding="utf-8").strip("\n")
        except OSError:
            continue  # unreadable file disables that one task, not the feature
        if body:
            loaded[path.stem] = body
    return loaded


#: task name -> annotation body. Populated from `annotations/` at import.
TASK_ANNOTATIONS: dict[str, str] = _load_annotations()


def reload_annotations() -> dict[str, str]:
    """Re-read `annotations/` into TASK_ANNOTATIONS and return it.

    For tests and long-lived processes that add or edit an annotation file after
    import; ordinary runs load once.
    """
    TASK_ANNOTATIONS.clear()
    TASK_ANNOTATIONS.update(_load_annotations())
    return TASK_ANNOTATIONS


# ------------------------------------------------------------------------- selection


def annotations_enabled() -> bool:
    """True when OUROBOROS_TB_TASK_ANNOTATIONS is truthy. Default OFF.

    Single reader of the flag, so the adapter and any future caller cannot disagree
    about whether this arm is on. Default-off matters: see VALIDITY above.
    """
    return str(os.environ.get(ENV_FLAG) or "").strip().lower() in _TRUTHY


def resolve_task_name(raw: str) -> str:
    """Normalise the shapes a task name actually arrives in to a bare name.

    The adapter sees a trial dir name, and other callers may pass an instance id, so
    accepting only the bare form would silently drop annotations for some call sites:

        'write-compressor'                 -> 'write-compressor'
        'terminal-bench/write-compressor'  -> 'write-compressor'
        'write-compressor__t6wfVjj'        -> 'write-compressor'   (trial dir)
    """
    name = str(raw or "").strip()
    if not name:
        return ""
    name = name.rsplit("/", 1)[-1]  # drop an org/dataset prefix
    if "__" in name:                # drop a trial-hash suffix
        name = name.rsplit("__", 1)[0]
    return name.strip()


# ------------------------------------------------------------------------- rendering


def render_task_annotations(task_name: str, *, require_flag: bool = True) -> str:
    """Render the annotation block, or "" when disabled or nothing is known.

    `require_flag=True` is what the adapter uses, making the env flag the single
    gate. Pass False from tooling that inspects the table directly.
    """
    if require_flag and not annotations_enabled():
        return ""
    body = TASK_ANNOTATIONS.get(resolve_task_name(task_name))
    if not body:
        return ""
    header = "--- task-specific annotations (from task failure analysis) ---"
    return f"{header}\n<task-annotations>\n{body}\n</task-annotations>"


# ------------------------------------------------------------------------- listings


def annotated_tasks() -> list[str]:
    """Tasks that carry an annotation, sorted."""
    return sorted(TASK_ANNOTATIONS)


def annotated_task_count() -> int:
    return len(TASK_ANNOTATIONS)
