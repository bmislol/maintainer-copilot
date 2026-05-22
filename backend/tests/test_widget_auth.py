"""Tests for widget_id auth — Phase 4.5.

Covers get_widget_user (direct calls) and the /chat/send endpoint
accepting widget_id instead of a Bearer JWT.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi_users.authentication import JWTStrategy
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import get_jwt_strategy, get_widget_user
from app.main import app

_TEST_SECRET = "test-jwt-secret-for-widget-auth-tests"


async def _mock_session() -> AsyncGenerator[Any, None]:
    yield AsyncMock()


@pytest.fixture(autouse=True)
def _setup_overrides() -> Any:
    def _test_jwt_strategy() -> JWTStrategy[User, int]:  # type: ignore[type-arg]
        return JWTStrategy(secret=_TEST_SECRET, lifetime_seconds=3600, algorithm="HS256")

    app.state.anthropic_client = AsyncMock()
    app.state.http_client = AsyncMock()
    app.state.redis_client = MagicMock()
    app.dependency_overrides[get_async_session] = _mock_session
    app.dependency_overrides[get_jwt_strategy] = _test_jwt_strategy
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Direct unit tests for get_widget_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_widget_user_valid_uuid() -> None:
    user = await get_widget_user(widget_id="00000000-0000-0000-0000-000000000001")
    assert user.is_active is True
    assert user.email == "widget@system.local"


@pytest.mark.asyncio
async def test_get_widget_user_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_widget_user(widget_id="not-a-uuid")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_widget_user_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_widget_user(widget_id=None)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Integration tests through /chat/send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_send_accepts_valid_widget_id() -> None:
    async def _fake_stream(**_kwargs: Any) -> AsyncGenerator[str, None]:
        yield "ok"

    with patch("app.api.chat.stream_chat_response", side_effect=_fake_stream):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/chat/send?widget_id=00000000-0000-0000-0000-000000000001",
                json={"conversation_id": None, "message": "hi"},
            )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_send_rejects_invalid_widget_id() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/chat/send?widget_id=not-a-uuid",
            json={"conversation_id": None, "message": "hi"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_send_rejects_no_auth() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/chat/send",
            json={"conversation_id": None, "message": "hi"},
        )
    assert resp.status_code == 403
