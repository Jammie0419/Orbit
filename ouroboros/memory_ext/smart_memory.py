"""Smart memory (PAPER_INTEGRATION_ANALYSIS 不足 2): importance-aware
scratchpad block management on top of the plain FIFO Memory.

Upgrades:
- importance score per block (hybrid: rules first, LLM only when the rule
  verdict is ambiguous, LLM failure falls back to the rule score)
- auto tag extraction (LLM-backed; silent fallback to empty on any failure)
- importance-based eviction instead of blind FIFO
- tag / importance search

Downstream compatibility: the block schema only ADDS ``importance`` and
``tags`` keys; ``ts`` / ``source`` / ``content`` (the keys consolidator,
regenerate_scratchpad_md and journal entries read) are unchanged, so the
plain Memory pipeline keeps working when SmartMemory is off.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

from ouroboros.memory import Memory
from ouroboros.utils import atomic_write_json, utc_now_iso

log = logging.getLogger(__name__)

# Rule verdicts inside this band are ambiguous -> ask the LLM to confirm.
_RULE_AMBIGUOUS_MIN = 0.4
_RULE_AMBIGUOUS_MAX = 0.6

_HIGH_VALUE_KEYWORDS = (
    "bug",
    "error",
    "critical",
    "important",
    "discovered",
    "lesson",
    "architecture",
    "decision",
    "fix",
    "security",
)

_DEFAULT_MAX_BLOCKS = 10


class HybridImportanceModel:
    """Rules first; the LLM only arbitrates rule-ambiguous verdicts."""

    def __init__(self, llm_client: Any = None, model: str = ""):
        self.llm_client = llm_client
        self.model = model or ""

    def assess(self, content: str, source: str) -> float:
        rule_score = self._rule_based_assess(content, source)
        if self.llm_client is not None and _RULE_AMBIGUOUS_MIN <= rule_score <= _RULE_AMBIGUOUS_MAX:
            llm_score = self._llm_based_assess(content, source)
            if llm_score is not None:
                return llm_score
        return rule_score

    def _rule_based_assess(self, content: str, source: str) -> float:
        score = 0.5
        source_key = str(source or "").lower()
        if source_key == "error":
            score += 0.2
        elif source_key == "reflection" or source_key == "experience_review":
            score += 0.1

        text_lower = str(content or "").lower()
        high_value_hit = any(kw in text_lower for kw in _HIGH_VALUE_KEYWORDS)
        if high_value_hit:
            score += 0.2

        # Short + no high-value signal = routine noise. A short but high-value
        # block (e.g. "discovered a critical bug") must NOT be penalized.
        if not high_value_hit and len(text_lower) < 50:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _llm_based_assess(self, content: str, source: str) -> Optional[float]:
        """LLM confirmation of a rule-ambiguous block; any failure -> None."""
        if self.llm_client is None:
            return None
        prompt = (
            "Rate the long-term importance of the following memory block for a "
            "self-evolving AI agent. Answer with a single number between 0.0 "
            "(routine/trivial) and 1.0 (critical lesson / architectural insight). "
            "JSON only: {\"importance\": 0.0}\n\n"
            f"Content:\n{content}\n\n"
            f"Source: {source}"
        )
        try:
            msg, _ = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model or "default",
                reasoning_effort="low",
                max_tokens=64,
            )
            raw = (msg.get("content") or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            score = float(parsed.get("importance", -1.0))
            if 0.0 <= score <= 1.0:
                return score
        except Exception:
            log.debug("LLM importance assessment failed; using rule score", exc_info=True)
        return None

    def extract_tags(self, content: str) -> List[str]:
        """LLM tag extraction; any failure -> [] (content is still kept)."""
        if self.llm_client is None:
            return []
        prompt = (
            "Extract 3-5 concise keyword tags (lowercase, English) that capture "
            "the topic of the following memory block. JSON only: "
            '{"tags": ["tag1", "tag2"]}\n\n'
            f"Content:\n{content}"
        )
        try:
            msg, _ = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model or "default",
                reasoning_effort="low",
                max_tokens=128,
            )
            raw = (msg.get("content") or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            tags = parsed.get("tags", [])
            if isinstance(tags, list):
                cleaned = []
                for t in tags:
                    tag = str(t).strip().lower().replace(" ", "-")[:40]
                    if tag and tag not in cleaned:
                        cleaned.append(tag)
                return cleaned[:8]
        except Exception:
            log.debug("LLM tag extraction failed; block keeps no tags", exc_info=True)
        return []


class SmartMemory(Memory):
    """Importance-aware scratchpad memory; drops in for ``Memory``.

    With ``llm_client=None`` it degrades to rule-only scoring (no LLM cost).
    """

    def __init__(
        self,
        drive_root: pathlib.Path,
        repo_dir: Optional[pathlib.Path] = None,
        llm_client: Any = None,
        model: str = "",
        max_blocks: int = _DEFAULT_MAX_BLOCKS,
    ):
        super().__init__(drive_root=drive_root, repo_dir=repo_dir)
        self.llm_client = llm_client
        self.max_blocks = max(1, int(max_blocks))
        self.importance_model = HybridImportanceModel(llm_client=llm_client, model=model)

    def append_scratchpad_block(
        self,
        content: str,
        source: str = "task",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        bp = self.scratchpad_blocks_path()
        bp.parent.mkdir(parents=True, exist_ok=True)

        if self._has_retired_flat_scratchpad_without_blocks():
            msg = (
                "LEGACY_SCRATCHPAD_REQUIRES_MANUAL_UPGRADE: "
                "memory/scratchpad.md exists without scratchpad_blocks.json. "
                "Move preserved notes manually before appending new scratchpad blocks."
            )
            from ouroboros.utils import append_jsonl

            append_jsonl(self.journal_path(), {
                "ts": utc_now_iso(),
                "type": "legacy_scratchpad_requires_manual_upgrade",
                "path": str(self.scratchpad_path()),
            })
            raise RuntimeError(msg)

        importance = self.importance_model.assess(content, source)
        tags = self.importance_model.extract_tags(content)

        new_block: Dict[str, Any] = {
            "ts": utc_now_iso(),
            "source": source,
            "content": content,
            "importance": importance,
            "tags": tags,
        }
        if metadata:
            new_block["metadata"] = dict(metadata)

        from ouroboros.platform_layer import (
            file_lock_exclusive as _lock_ex,
        )
        from ouroboros.platform_layer import (
            file_unlock as _unlock,
        )

        fd = None
        try:
            fd = os.open(str(bp) + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
            _lock_ex(fd)

            try:
                text = bp.read_text(encoding="utf-8").strip() if bp.exists() else ""
            except OSError:
                text = ""
            blocks = json.loads(text) if text else []
            if not isinstance(blocks, list):
                blocks = []

            blocks.append(new_block)
            if len(blocks) > self.max_blocks:
                evicted = self._pick_eviction(blocks)
                self._journal_evictions(evicted)
                blocks = [b for b in blocks if b not in evicted]

            atomic_write_json(bp, blocks)
        except Exception:
            log.error("Failed to append smart scratchpad block", exc_info=True)
            from ouroboros.utils import append_jsonl

            try:
                append_jsonl(self.journal_path(), {
                    "ts": utc_now_iso(),
                    "type": "block_append_failed",
                    "source": source,
                    "block": dict(new_block),
                })
            except Exception:
                log.debug("Failed to journal block_append_failed", exc_info=True)
            raise
        finally:
            if fd is not None:
                try:
                    _unlock(fd)
                    os.close(fd)
                except OSError:
                    pass

        self.regenerate_scratchpad_md()

        from ouroboros.utils import append_jsonl

        try:
            total_chars = sum(len(b.get("content", "")) for b in self.load_scratchpad_blocks())
            append_jsonl(self.journal_path(), {
                "ts": utc_now_iso(),
                "type": "block_appended",
                "content_len": total_chars,
                "source": source,
                "metadata": dict(metadata or {}),
                "block": dict(new_block),
            })
        except Exception:
            log.debug("Failed to write scratchpad size to journal", exc_info=True)

        return new_block

    def _pick_eviction(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Evict the lowest-importance block(s); tie-break by age (oldest first)."""
        excess = len(blocks) - self.max_blocks
        if excess <= 0:
            return []
        # Block identity = (ts, source) exactly as consolidator keys it.

        def _rank(b: Dict[str, Any]) -> tuple:
            return (
                float(b.get("importance", 0.5)),
                str(b.get("ts", "")),
                str(b.get("source", "")),
            )

        ranked = sorted(blocks, key=_rank)
        return ranked[:excess]

    def _journal_evictions(self, evicted: List[Dict[str, Any]]) -> None:
        from ouroboros.utils import append_jsonl

        for eb in evicted:
            try:
                append_jsonl(self.journal_path(), {
                    "ts": utc_now_iso(),
                    "type": "block_evicted",
                    "evicted_block_ts": eb.get("ts", ""),
                    "evicted_block_source": eb.get("source", ""),
                    "evicted_block_content": eb.get("content", ""),
                    "evicted_block_importance": eb.get("importance", None),
                })
            except Exception:
                log.debug("Failed to journal block_evicted", exc_info=True)

    def search_by_tags(self, tags: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        blocks = self.load_scratchpad_blocks()
        wanted = {str(t).strip().lower() for t in tags if str(t).strip()}
        if not wanted:
            return []
        matching = [
            b for b in blocks
            if wanted & {str(t).lower() for t in b.get("tags", [])}
        ]
        matching.sort(key=lambda b: float(b.get("importance", 0.5)), reverse=True)
        return matching[:max(0, int(limit))]

    def search_by_importance(self, min_importance: float = 0.7, limit: int = 10) -> List[Dict[str, Any]]:
        blocks = self.load_scratchpad_blocks()
        high = [
            b for b in blocks
            if float(b.get("importance", 0.0)) >= float(min_importance)
        ]
        high.sort(key=lambda b: float(b.get("importance", 0.0)), reverse=True)
        return high[:max(0, int(limit))]

    def regenerate_scratchpad_md(self) -> None:
        blocks = self.load_scratchpad_blocks()
        if not blocks:
            bp = self.scratchpad_blocks_path()
            if bp.exists() and bp.stat().st_size > 2:
                from ouroboros.utils import write_text

                write_text(
                    self.scratchpad_path(),
                    "# Scratchpad\n\n⚠️ scratchpad_blocks.json exists but could not be "
                    "parsed — working memory storage is corrupt, NOT empty. "
                    "Inspect/restore the file before appending new blocks.\n",
                )
                return
            from ouroboros.utils import write_text

            write_text(self.scratchpad_path(), self._default_scratchpad())
            return

        n = len(blocks)
        parts = [f"## Scratchpad (working memory — {n}/{self.max_blocks} blocks)\n"]
        for block in reversed(blocks):
            ts = str(block.get("ts", ""))[:16]
            source = block.get("source", "?")
            content = block.get("content", "")
            imp = block.get("importance", None)
            tags = block.get("tags") or []
            header = f"### [{ts} — {source}]"
            if imp is not None:
                header += f" (importance {float(imp):.2f})"
            if tags:
                header += " tags: " + ", ".join(str(t) for t in tags)
            parts.append(f"{header}\n{content}\n\n---\n")

        from ouroboros.utils import write_text

        write_text(self.scratchpad_path(), "\n".join(parts))
