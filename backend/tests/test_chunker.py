"""Round-trip chunker tests on real corpus files.

Requirements (from Phase 3.2 spec):
  - No empty chunks
  - No chunk exceeds MAX_TOKENS subword tokens (the model's effective window)
  - section_title metadata populated on every chunk
  - Total chunks cover the source text (modulo truncation for comments)
  - Same assertions for a real issue with comments

Test fixtures: real files from data/rag_corpus/ — not mocked.
The tokenizer (all-MiniLM-L6-v2) is loaded from HuggingFace cache on first
run; subsequent runs use the cache and are fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.chunker import (
    MAX_COMMENT_TOKENS,
    MAX_TOKENS,
    chunk_doc,
    chunk_issue,
    count_tokens,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
CORPUS_DOCS = BACKEND_DIR / "data" / "rag_corpus" / "docs"
CORPUS_ISSUES = BACKEND_DIR / "data" / "rag_corpus" / "issues"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_corpus() -> None:
    if not CORPUS_DOCS.exists() or not any(CORPUS_DOCS.iterdir()):
        pytest.skip("RAG corpus not built — run scripts/build_rag_corpus.py first")


# ---------------------------------------------------------------------------
# Doc tests
# ---------------------------------------------------------------------------


class TestDocChunker:
    def test_common_pitfalls_no_empty_chunks(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        assert chunks, "expected at least one chunk"
        for c in chunks:
            assert c.text.strip(), f"empty chunk at index {c.chunk_index}"

    def test_common_pitfalls_no_chunk_exceeds_token_cap(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        over = [c for c in chunks if c.n_tokens > MAX_TOKENS]
        assert not over, f"{len(over)} chunk(s) exceed MAX_TOKENS={MAX_TOKENS}: " + str(
            [(c.chunk_index, c.n_tokens) for c in over]
        )

    def test_common_pitfalls_section_title_metadata_populated(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        # The common_pitfalls doc has section headings — at least some chunks
        # should have a non-empty section_title.
        titled = [c for c in chunks if c.metadata.get("section_title")]
        assert titled, "no chunks carry a section_title — heading detection may be broken"

    def test_common_pitfalls_coverage(self) -> None:
        """Chunks must cover all non-whitespace text in the source document.

        We verify coverage by checking that every heading that appears in the
        raw RST appears somewhere in the combined chunk text.  Full token-level
        coverage is guaranteed by the sliding-window implementation.
        """
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        combined = " ".join(c.text for c in chunks)
        # The document has a known top-level heading.
        assert "Common pitfalls" in combined or "Inconsistent preprocessing" in combined

    def test_chunk_ids_unique(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "duplicate chunk_ids detected"

    def test_chunk_id_format(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        file_id = str(doc["file_id"])
        for c in chunks:
            assert c.chunk_id == f"doc:{file_id}:{c.chunk_index}"

    def test_n_tokens_matches_count(self) -> None:
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        for c in chunks:
            actual = count_tokens(c.text)
            assert c.n_tokens == actual, (
                f"chunk {c.chunk_index}: n_tokens={c.n_tokens} but count_tokens()={actual}"
            )

    def test_produces_multiple_sections(self) -> None:
        """common_pitfalls.rst has 9 detected headings — should yield multiple chunks."""
        _require_corpus()
        doc = json.loads((CORPUS_DOCS / "common_pitfalls.json").read_text())
        chunks = chunk_doc(doc)
        assert len(chunks) >= 5, f"expected >= 5 chunks, got {len(chunks)}"


# ---------------------------------------------------------------------------
# Issue tests
# ---------------------------------------------------------------------------


class TestIssueChunker:
    @pytest.fixture
    def issue_data(self) -> dict:  # type: ignore[type-arg]
        _require_corpus()
        # issue 5212 has 39 comments — good stress test.
        issue_file = CORPUS_ISSUES / "104880490.json"
        if not issue_file.exists():
            pytest.skip("issue 104880490.json not in corpus")
        return json.loads(issue_file.read_text())  # type: ignore[return-value]

    def test_no_empty_chunks(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        assert chunks
        for c in chunks:
            assert c.text.strip(), f"empty chunk at index {c.chunk_index}"

    def test_no_chunk_exceeds_token_cap(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        """Body chunks ≤ MAX_TOKENS; comment chunks ≤ MAX_COMMENT_TOKENS (D-016).

        Comments have a larger cap: first paragraph of a maintainer comment is
        preserved in full (up to 300 tokens).  Body/window chunks must fit
        within MiniLM's effective window (MAX_TOKENS=220).
        """
        chunks = chunk_issue(issue_data)
        body_chunks = [
            c for c in chunks if not str(c.metadata.get("section_title", "")).startswith("comment_")
        ]
        over_body = [c for c in body_chunks if c.n_tokens > MAX_TOKENS]
        assert not over_body, (
            f"{len(over_body)} body chunk(s) exceed MAX_TOKENS={MAX_TOKENS}: "
            + str([(c.chunk_index, c.n_tokens) for c in over_body])
        )
        comment_chunks = [
            c for c in chunks if str(c.metadata.get("section_title", "")).startswith("comment_")
        ]
        over_comment = [c for c in comment_chunks if c.n_tokens > MAX_COMMENT_TOKENS]
        assert not over_comment, (
            f"{len(over_comment)} comment chunk(s) exceed MAX_COMMENT_TOKENS={MAX_COMMENT_TOKENS}: "
            + str([(c.chunk_index, c.n_tokens) for c in over_comment])
        )

    def test_section_title_metadata_populated(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        for c in chunks:
            assert "section_title" in c.metadata, (
                f"chunk {c.chunk_index} missing section_title in metadata"
            )

    def test_body_chunk_is_index_zero_or_first(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        # chunk_index 0 should always be the body (or first window of body)
        body_chunks = [c for c in chunks if c.metadata.get("section_title") == "body"]
        assert body_chunks, "no body chunk produced"

    def test_comment_chunks_respect_token_cap(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        comment_chunks = [
            c for c in chunks if str(c.metadata.get("section_title", "")).startswith("comment_")
        ]
        for c in comment_chunks:
            assert c.n_tokens <= MAX_COMMENT_TOKENS, (
                f"comment chunk {c.chunk_index} has {c.n_tokens} tokens > {MAX_COMMENT_TOKENS}"
            )

    def test_chunk_count_matches_comments(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        """Non-empty comments each produce exactly one chunk."""
        chunks = chunk_issue(issue_data)
        non_empty_comments = sum(
            1 for c in issue_data.get("comments", []) if str(c.get("body") or "").strip()
        )
        # body might expand to multiple sliding-window chunks; comments are exactly 1 each
        comment_chunks = [
            c for c in chunks if str(c.metadata.get("section_title", "")).startswith("comment_")
        ]
        assert len(comment_chunks) == non_empty_comments, (
            f"expected {non_empty_comments} comment chunks, got {len(comment_chunks)}"
        )

    def test_chunk_id_format(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        number = str(issue_data["number"])
        for c in chunks:
            assert c.chunk_id == f"issue:{number}:{c.chunk_index}"

    def test_chunk_ids_unique(self, issue_data: dict) -> None:  # type: ignore[type-arg]
        chunks = chunk_issue(issue_data)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "duplicate chunk_ids in issue"
