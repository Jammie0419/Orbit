"""Tests for SmartMemory (PAPER_INTEGRATION_ANALYSIS 不足 2): importance-aware
scratchpad blocks, rule+LLM hybrid scoring, importance-based eviction, and
tag/importance search."""
import json

import pytest

from ouroboros.memory_ext.smart_memory import (
    _DEFAULT_MAX_BLOCKS,
    HybridImportanceModel,
    SmartMemory,
)


class FakeLLM:
    """Deterministic fake LLM: importance+tags answered from content markers."""

    def __init__(self, importance: float = 0.9, tags=None):
        self.importance = importance
        self.tags = tags or ["async", "worker-pool"]
        self.calls = []

    def chat(self, messages, model, **kw):
        self.calls.append(messages[0]["content"])
        content = messages[0]["content"]
        if "Extract 3-5" in content:
            payload = {"tags": self.tags}
        else:
            payload = {"importance": self.importance}
        return ({"content": json.dumps(payload)}, {})


@pytest.fixture
def memory(tmp_path):
    drive = tmp_path / "data"
    drive.mkdir()
    (drive / "memory").mkdir()
    (drive / "logs").mkdir()
    return SmartMemory(drive_root=drive, llm_client=None)


@pytest.fixture
def smart_memory(tmp_path):
    drive = tmp_path / "data"
    drive.mkdir()
    (drive / "memory").mkdir()
    (drive / "logs").mkdir()
    return SmartMemory(drive_root=drive, llm_client=FakeLLM())


class TestImportanceModel:
    def test_high_value_keyword_raises_score(self):
        model = HybridImportanceModel()
        assert model.assess("discovered a critical bug", "task") >= 0.7

    def test_error_source_raises_score(self):
        model = HybridImportanceModel()
        assert model.assess("something failed", "error") >= 0.6

    def test_short_routine_content_scores_low(self):
        model = HybridImportanceModel()
        assert model.assess("ok", "task") < 0.5

    def test_ambiguous_verdict_uses_llm(self):
        model = HybridImportanceModel(llm_client=FakeLLM(importance=0.85))
        # rule: "routine stuff" -> 0.5 (ambiguous band) -> LLM arbitrates
        assert model.assess("routine stuff", "task") == 0.85

    def test_llm_failure_falls_back_to_rule_score(self):
        class BrokenLLM:
            def chat(self, *args, **kwargs):
                raise RuntimeError("boom")

        model = HybridImportanceModel(llm_client=BrokenLLM())
        score = model.assess("routine stuff", "task")
        assert 0.4 <= score <= 0.6  # rule score, not LLM

    def test_no_llm_never_calls(self):
        model = HybridImportanceModel()
        score = model.assess("routine stuff", "task")
        assert 0.4 <= score <= 0.6


class TestSmartMemoryBlocks:
    def test_block_has_importance_and_tags_fields(self, smart_memory):
        block = smart_memory.append_scratchpad_block("discovered an async bug", source="task")
        assert "importance" in block
        assert "tags" in block
        assert block["tags"] == ["async", "worker-pool"]

    def test_plain_fifo_absent_when_smart_enabled(self, smart_memory):
        smart_memory.append_scratchpad_block("discovered an async bug", source="task")
        blocks = smart_memory.load_scratchpad_blocks()
        assert len(blocks) == 1
        assert blocks[0]["importance"] is not None

    def test_importance_eviction_keeps_high_value(self, tmp_path):
        drive = tmp_path / "data"
        drive.mkdir()
        (drive / "memory").mkdir()
        (drive / "logs").mkdir()
        # Only the FIRST block goes through the LLM (importance 0.9); the rest
        # are rule-scored routine (0.4).
        mem = SmartMemory(drive_root=drive, llm_client=FakeLLM(importance=0.9), max_blocks=3)
        for i in range(5):
            mem.append_scratchpad_block(f"routine update {i}", source="task")
        blocks = mem.load_scratchpad_blocks()
        assert len(blocks) == 3
        imps = sorted(float(b.get("importance", 0)) for b in blocks)
        assert imps[-1] == 0.9  # high-importance block survives

    def test_fifo_behavior_preserved_when_no_smart_fields(self, memory):
        for i in range(_DEFAULT_MAX_BLOCKS + 2):
            memory.append_scratchpad_block(f"block {i}")
        blocks = memory.load_scratchpad_blocks()
        assert len(blocks) == _DEFAULT_MAX_BLOCKS

    def test_eviction_journaled(self, smart_memory):
        for i in range(_DEFAULT_MAX_BLOCKS + 2):
            smart_memory.append_scratchpad_block(f"routine {i}", source="task")
        journal = smart_memory.journal_path()
        lines = journal.read_text(encoding="utf-8").strip().split("\n")
        evictions = [line for line in lines if '"block_evicted"' in line]
        assert len(evictions) == 2
        assert '"evicted_block_importance"' in evictions[0]


class TestSearch:
    def test_search_by_tags(self, smart_memory):
        smart_memory.append_scratchpad_block("discovered an async worker bug", source="task")
        hit = smart_memory.search_by_tags(["async"])
        assert len(hit) == 1
        assert hit[0]["content"] == "discovered an async worker bug"

    def test_search_by_tags_no_match(self, smart_memory):
        smart_memory.append_scratchpad_block("routine note", source="task")
        assert smart_memory.search_by_tags(["unrelated"]) == []

    def test_search_by_importance(self, smart_memory):
        smart_memory.append_scratchpad_block("discovered a critical bug", source="task")
        hit = smart_memory.search_by_importance(min_importance=0.7)
        assert len(hit) == 1
        assert hit[0]["importance"] >= 0.7

    def test_search_respects_limit(self, memory):
        memory.append_scratchpad_block("discovered critical architecture decision A", source="task")
        memory.append_scratchpad_block("discovered critical architecture decision B", source="task")
        hit = memory.search_by_importance(min_importance=0.7, limit=1)
        assert len(hit) == 1


class TestDownstreamCompat:
    def test_regenerate_md_with_importance(self, smart_memory):
        smart_memory.append_scratchpad_block("discovered an async bug", source="task")
        md = smart_memory.load_scratchpad()
        assert "importance" in md
        assert "async" in md

    def test_consolidator_keys_still_readable(self, smart_memory):
        """Consolidator reads ts/source/content; those keys must survive."""
        block = smart_memory.append_scratchpad_block("discovered an async bug", source="task")
        assert block["ts"] and block["source"] == "task" and block["content"]
