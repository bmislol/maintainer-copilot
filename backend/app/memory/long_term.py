"""Long-term (pgvector) memory — Phase 4.3.

Writes episodic memories for a user with a pgvector embedding so they can
be recalled semantically in future conversations.  Every write also appends
an audit_log row (D-023, SECURITY §6).

Memory type default: 'episodic' — because write_memory is explicit-only
(user-stated facts).  See D-024 for the full rationale.

Layer: app/memory/
Dependencies flow IN via parameters so this module is testable without
live infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog
from app.db.models.memory_long import MemoryLong
from app.domain.memory import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


async def write_entry(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    content: str,
    memory_type: MemoryType = "episodic",
    request_id: str = "",
    trace_id: str = "",
) -> MemoryEntry:
    """Embed content, insert into memory_long, and append an audit_log row."""
    from app.rag.embedder import embed_query

    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(None, embed_query, content)

    entry = MemoryLong(
        id=uuid.uuid4(),
        user_id=user_id,
        content=content,
        memory_type=memory_type,
        embedding=embedding.tolist(),
    )
    session.add(entry)

    audit = AuditLog(
        id=uuid.uuid4(),
        actor=user_id,
        action="memory_write",
        target=str(entry.id),
        request_id=uuid.UUID(request_id) if request_id else uuid.uuid4(),
        trace_id=trace_id or None,
    )
    session.add(audit)

    await session.commit()
    await session.refresh(entry)

    logger.info("wrote memory entry %s for user %s", entry.id, user_id)
    return MemoryEntry.model_validate(entry)


async def search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    k: int = 5,
) -> list[MemoryEntry]:
    """Embed query, return top-k entries by cosine similarity (pgvector KNN)."""
    from app.rag.embedder import embed_query

    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(None, embed_query, query)
    vec_literal = "[" + ",".join(str(x) for x in embedding.tolist()) + "]"

    result = await session.execute(
        text(
            "SELECT id, user_id, content, memory_type, created_at "
            "FROM memory_long "
            "WHERE user_id = :user_id "
            "ORDER BY embedding <=> CAST(:vec AS vector) "
            "LIMIT :k"
        ),
        {"user_id": str(user_id), "vec": vec_literal, "k": k},
    )
    rows = result.mappings().all()
    return [
        MemoryEntry(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            memory_type=row["memory_type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def list_entries(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> list[MemoryEntry]:
    """Return all memory entries for a user, newest first."""
    result = await session.execute(
        select(MemoryLong)
        .where(MemoryLong.user_id == user_id)
        .order_by(MemoryLong.created_at.desc())
    )
    rows = result.scalars().all()
    return [MemoryEntry.model_validate(r) for r in rows]
