"""Tests for long-term (pgvector) memory — Phase 4.3.

Uses mock SQLAlchemy session and patches embed_query to avoid model loading.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.domain.memory import MemoryEntry

_FAKE_EMBEDDING = np.zeros(384, dtype=np.float32)
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_write_entry_inserts_memory_and_audit() -> None:
    session = _mock_session()

    with patch("app.rag.embedder.embed_query", return_value=_FAKE_EMBEDDING):
        # refresh sets the attributes the ORM would normally fill from DB
        async def _refresh(obj: object) -> None:
            import datetime

            from app.db.models.memory_long import MemoryLong

            if isinstance(obj, MemoryLong):
                obj.created_at = datetime.datetime.now(datetime.UTC)  # type: ignore[assignment]

        session.refresh = AsyncMock(side_effect=_refresh)

        from app.memory.long_term import write_entry

        entry = await write_entry(
            session,
            user_id=_USER_ID,
            content="remember to check the CI before merging",
        )

    assert session.add.call_count == 2  # MemoryLong + AuditLog
    assert session.commit.await_count == 1
    assert isinstance(entry, MemoryEntry)
    assert entry.content == "remember to check the CI before merging"
    assert entry.memory_type == "episodic"
    assert entry.user_id == _USER_ID


@pytest.mark.asyncio
async def test_write_entry_uses_provided_memory_type() -> None:
    session = _mock_session()

    with patch("app.rag.embedder.embed_query", return_value=_FAKE_EMBEDDING):

        async def _refresh(obj: object) -> None:
            import datetime

            from app.db.models.memory_long import MemoryLong

            if isinstance(obj, MemoryLong):
                obj.created_at = datetime.datetime.now(datetime.UTC)  # type: ignore[assignment]

        session.refresh = AsyncMock(side_effect=_refresh)

        from app.memory.long_term import write_entry

        entry = await write_entry(
            session,
            user_id=_USER_ID,
            content="some procedural knowledge",
            memory_type="procedural",
        )

    assert entry.memory_type == "procedural"


@pytest.mark.asyncio
async def test_search_returns_memory_entries() -> None:
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, k: {
        "id": uuid.uuid4(),
        "user_id": _USER_ID,
        "content": "remember to check the CI",
        "memory_type": "episodic",
        "created_at": MagicMock(),
    }[k]

    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = [fake_row]

    session = _mock_session()
    session.execute = AsyncMock(return_value=result_mock)

    with patch("app.rag.embedder.embed_query", return_value=_FAKE_EMBEDDING):
        from app.memory.long_term import search

        entries = await search(session, user_id=_USER_ID, query="CI check")

    assert len(entries) == 1
    assert entries[0].content == "remember to check the CI"


@pytest.mark.asyncio
async def test_list_entries_returns_ordered_results() -> None:
    import datetime

    m1 = MagicMock()
    m1.id = uuid.uuid4()
    m1.user_id = _USER_ID
    m1.content = "older memory"
    m1.memory_type = "episodic"
    m1.created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    m2 = MagicMock()
    m2.id = uuid.uuid4()
    m2.user_id = _USER_ID
    m2.content = "newer memory"
    m2.memory_type = "episodic"
    m2.created_at = datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [m2, m1]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    session = _mock_session()
    session.execute = AsyncMock(return_value=result_mock)

    from app.memory.long_term import list_entries

    entries = await list_entries(session, user_id=_USER_ID)
    assert len(entries) == 2
    assert entries[0].content == "newer memory"
    assert entries[1].content == "older memory"
