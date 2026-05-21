"""Async SQLAlchemy session dependency.

The async engine and session factory are created during lifespan startup
(after Vault resolves the DB URL) and stored in app.state. This module
provides the FastAPI dependency that yields a session per request.

Layer: app/db/
Used by: app/infra/auth.py get_user_db, and any repository that needs a session.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_async_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session bound to the current request."""
    async with request.app.state.db_session_factory() as session:
        yield session
