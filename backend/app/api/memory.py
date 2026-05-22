"""Memory API — GET /memory/entries (Phase 4.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import current_active_user
from app.memory.long_term import list_entries

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryEntryOut(BaseModel):
    id: uuid.UUID
    content: str
    memory_type: str
    created_at: datetime


@router.get("/entries", response_model=list[MemoryEntryOut])
async def get_memory_entries(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[MemoryEntryOut]:
    """Return the authenticated user's long-term memory entries, newest first."""
    entries = await list_entries(session, user_id=user.id)
    return [
        MemoryEntryOut(
            id=e.id,
            content=e.content,
            memory_type=e.memory_type,
            created_at=e.created_at,
        )
        for e in entries
    ]
