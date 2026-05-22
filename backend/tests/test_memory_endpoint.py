"""Tests for GET /memory/entries endpoint — Phase 4.4."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi_users.authentication import JWTStrategy
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import current_active_user, get_jwt_strategy
from app.main import app

_TEST_SECRET = "test-jwt-secret-for-memory-unit-tests-only"

_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


async def _mock_session() -> AsyncGenerator[Any, None]:
    yield AsyncMock()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = _USER_ID
    user.email = "user@example.com"
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def _setup_overrides() -> Any:
    def _test_jwt_strategy() -> JWTStrategy[User, int]:  # type: ignore[type-arg]
        return JWTStrategy(secret=_TEST_SECRET, lifetime_seconds=3600, algorithm="HS256")

    app.dependency_overrides[get_async_session] = _mock_session
    app.dependency_overrides[get_jwt_strategy] = _test_jwt_strategy
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_override() -> None:
    app.dependency_overrides[current_active_user] = lambda: _mock_user()


@pytest.mark.asyncio
async def test_get_memory_entries_returns_list(auth_override: None) -> None:  # noqa: ARG001
    from app.domain.memory import MemoryEntry

    fake_entry = MemoryEntry(
        id=uuid.uuid4(),
        user_id=_USER_ID,
        content="check CI before merging",
        memory_type="episodic",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
    )

    with patch("app.api.memory.list_entries", new=AsyncMock(return_value=[fake_entry])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/memory/entries")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "check CI before merging"
    assert data[0]["memory_type"] == "episodic"
    assert "user_id" not in data[0]


@pytest.mark.asyncio
async def test_get_memory_entries_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/memory/entries")
    assert resp.status_code == 401
