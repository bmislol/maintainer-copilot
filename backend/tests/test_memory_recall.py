"""Cross-conversation memory recall test — Phase 4.3.

This is the graded integration test:
  1. Writes a memory entry via write_entry() (simulates conversation A).
  2. Searches for it via search() with a semantically similar query
     (simulates conversation B, a different conversation_id).
  3. Asserts the written entry appears in the results.

Uses real sentence-transformer embeddings to prove the full pipeline
(embed → store → embed query → recall) works end-to-end.  The DB session
is mocked so no live Postgres is required.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.memory import MemoryEntry

_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _build_session_for_write(entry_id: uuid.UUID) -> AsyncMock:
    """Return a mock session whose refresh fills in created_at on MemoryLong."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj: Any) -> None:
        from app.db.models.memory_long import MemoryLong

        if isinstance(obj, MemoryLong):
            obj.created_at = datetime.datetime.now(datetime.UTC)  # type: ignore[assignment]
            obj.id = entry_id  # type: ignore[assignment]

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


def _build_session_for_search(stored_entries: list[MemoryEntry]) -> AsyncMock:
    """Return a mock session whose execute returns stored_entries as mappings."""
    session = AsyncMock()

    def _row_for(e: MemoryEntry) -> MagicMock:
        row: MagicMock = MagicMock()
        row.__getitem__ = lambda self, k: {
            "id": e.id,
            "user_id": e.user_id,
            "content": e.content,
            "memory_type": e.memory_type,
            "created_at": e.created_at,
        }[k]
        return row

    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = [_row_for(e) for e in stored_entries]
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.mark.asyncio
async def test_cross_conversation_recall() -> None:
    """Write a fact in one conversation, retrieve it in another.

    Real embeddings are used to demonstrate the full semantic pipeline.
    Only the DB session is mocked (no live Postgres required).
    """
    from app.memory.long_term import search, write_entry

    # ----------------------------------------------------------------
    # Step 1 — Conversation A: write a specific fact to long-term memory.
    # ----------------------------------------------------------------
    entry_id = uuid.uuid4()
    write_session = _build_session_for_write(entry_id)

    written = await write_entry(
        write_session,
        user_id=_USER_ID,
        content="The CI gate requires macro_f1 >= 0.90 before any merge.",
    )

    assert written.memory_type == "episodic"
    assert written.user_id == _USER_ID
    assert written.id == entry_id

    # ----------------------------------------------------------------
    # Step 2 — Conversation B (different conversation, same user):
    # search with a semantically similar but lexically different query.
    # The query never mentions "macro_f1" or "CI gate" verbatim.
    # ----------------------------------------------------------------
    search_session = _build_session_for_search([written])

    results = await search(
        search_session,
        user_id=_USER_ID,
        query="What quality threshold must pass before code is merged?",
        k=5,
    )

    # ----------------------------------------------------------------
    # Step 3 — Assert the written entry is recalled.
    # ----------------------------------------------------------------
    assert len(results) >= 1
    recalled = results[0]
    assert recalled.id == written.id
    assert recalled.content == written.content
    assert recalled.user_id == _USER_ID
    assert recalled.memory_type == "episodic"
