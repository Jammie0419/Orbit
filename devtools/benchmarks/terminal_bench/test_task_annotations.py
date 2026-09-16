#!/usr/bin/env python3
"""Contract tests for the per-task annotation capability.

These pin three things that fail silently in production:

  1. the enable flag defaults OFF and the adapter's gate agrees with the module;
  2. every shape a task name arrives in resolves to a bare name (the adapter passes
     a trial dir name, so accepting only the bare form drops annotations unseen);
  3. every annotation file survives the container source copy -- one task name trips
     the secret-shaped filename heuristic, which would drop that file from the
     upload while the flag still read as enabled.
"""
from __future__ import annotations

import pathlib

from devtools.benchmarks.terminal_bench.exp.capabilities import task_annotations as ta


def test_flag_defaults_off_and_reads_truthy(monkeypatch):
    monkeypatch.delenv(ta.ENV_FLAG, raising=False)
    assert ta.annotations_enabled() is False
    assert ta.render_task_annotations("write-compressor") == ""

    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(ta.ENV_FLAG, value)
        assert ta.annotations_enabled() is False, value

    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(ta.ENV_FLAG, value)
        assert ta.annotations_enabled() is True, value


def test_render_requires_flag_but_can_be_bypassed(monkeypatch):
    monkeypatch.delenv(ta.ENV_FLAG, raising=False)
    assert ta.render_task_annotations("write-compressor") == ""
    assert ta.render_task_annotations("write-compressor", require_flag=False) != ""


def test_render_is_empty_for_unannotated_task(monkeypatch):
    monkeypatch.setenv(ta.ENV_FLAG, "1")
    # Derived, not hardcoded: this assertion named "regex-log" until that task gained an
    # annotation, at which point the test inverted and failed. Any name absent from the
    # table proves the same thing and cannot go stale the same way.
    absent = next(n for n in (f"unannotated-{i}" for i in range(100)) if n not in ta.TASK_ANNOTATIONS)
    assert ta.render_task_annotations(absent) == ""
    assert ta.render_task_annotations(absent, require_flag=False) == ""


def test_task_name_resolves_from_every_shape_it_arrives_in():
    cases = {
        "write-compressor": "write-compressor",
        "terminal-bench/write-compressor": "write-compressor",
        "write-compressor__t6wfVjj": "write-compressor",
        "  write-compressor  ": "write-compressor",
        "": "",
        "terminal-bench/write-compressor__t6wfVjj": "write-compressor",
    }
    for raw, expected in cases.items():
        assert ta.resolve_task_name(raw) == expected, raw


def test_render_block_is_wrapped_in_matching_tags(monkeypatch):
    monkeypatch.setenv(ta.ENV_FLAG, "1")
    rendered = ta.render_task_annotations("write-compressor")
    assert rendered.startswith("--- task-specific annotations")
    assert "<task-annotations>" in rendered
    assert rendered.rstrip().endswith("</task-annotations>")


def test_annotations_directory_is_populated_and_keys_are_filenames():
    assert ta.annotated_task_count() > 0
    on_disk = sorted(p.stem for p in ta.ANNOTATIONS_DIR.glob("*.txt"))
    assert on_disk == ta.annotated_tasks()
    # A filename IS the key, so a renamed task and its annotation cannot drift apart
    # silently; guard the one name known to trip the secret-shaped heuristic.
    assert "count-dataset-tokens" in ta.annotated_tasks()


def test_every_annotation_survives_the_container_source_copy():
    """The copy drops secret-shaped filenames, and `count-dataset-tokens.txt` matches
    ('token' + a text extension). If the annotations directory were not exempt, that
    file would vanish from the container and its annotation would silently never
    apply."""
    import tempfile

    from devtools.benchmarks.terminal_bench.harbor_installed_agent import _copy_clean_source

    source_root = pathlib.Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "src"
        _copy_clean_source(source_root, target)
        copied = target / ta.ANNOTATIONS_DIR.relative_to(source_root)
        assert copied.is_dir(), copied
        assert sorted(p.stem for p in copied.glob("*.txt")) == ta.annotated_tasks()

        # And the copied tree still renders, i.e. the loader finds its own data dir.
        assert (copied / "count-dataset-tokens.txt").read_text(encoding="utf-8").strip()
