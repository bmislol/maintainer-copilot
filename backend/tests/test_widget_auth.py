"""Tests for widget_id auth — Phase 4.5 / 4.6.

Phase 4.5: UUID format validation.
Phase 4.6: real DB lookup — widget must exist and have an active owner.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi_users.authentication import JWTStrategy
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.db.models.widgets import Widget
from app.db.session import get_async_session
from app.infra.auth import get_jwt_strategy, get_widget_user
from app.main import app

_TEST_SECRET = "test-jwt-secret-for-widget-auth-tests"
_WIDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_OWNER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _make_owner() -> User:
    return User(
        id=_OWNER_ID,
        email="owner@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


def _make_widget() -> Widget:
    w = Widget(
        id=_WIDGET_ID,
        name="Test Widget",
        owner_id=_OWNER_ID,
        theme="dark",
        greeting="Hello!",
        enabled_tools=["retrieve_docs"],
        allowed_origins=[],
    )
    return w


async def _mock_session() -> AsyncGenerator[Any, None]:
    yield AsyncMock()


@pytest.fixture(autouse=True)
def _setup_overrides() -> Any:
    def _test_jwt_strategy() -> JWTStrategy[User, int]:  # type: ignore[type-arg]
        return JWTStrategy(secret=_TEST_SECRET, lifetime_seconds=3600, algorithm="HS256")

    app.state.anthropic_client = AsyncMock()
    app.state.http_client = AsyncMock()
    app.state.redis_client = MagicMock()
    app.state.allowed_origins = set()
    app.dependency_overrides[get_async_session] = _mock_session
    app.dependency_overrides[get_jwt_strategy] = _test_jwt_strategy
    yield
    app.dependency_overrides.clear()
    if hasattr(app.state, "allowed_origins"):
        del app.state.allowed_origins


# ---------------------------------------------------------------------------
# Direct unit tests for get_widget_user (Phase 4.6 DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_widget_user_valid_uuid_and_owner() -> None:
    """Valid widget_id with an existing widget and active owner returns the owner."""
    mock_session = AsyncMock()
    widget = _make_widget()
    _owner = _make_owner()

    async def _fake_get(model: type, pk: Any) -> Any:
        if model is Widget:
            return widget
        if model is User:
            return _owner
        return None

    mock_session.get.side_effect = _fake_get

    with patch("app.repositories.widgets.get_widget", return_value=widget):
        user = await get_widget_user(widget_id=str(_WIDGET_ID), session=mock_session)
    assert user.id == _OWNER_ID
    assert user.is_active is True


@pytest.mark.asyncio
async def test_get_widget_user_widget_not_found() -> None:
    """widget_id with no matching row raises 403."""
    mock_session = AsyncMock()
    with (
        patch("app.repositories.widgets.get_widget", return_value=None),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_widget_user(widget_id=str(_WIDGET_ID), session=mock_session)
    assert exc_info.value.status_code == 403
    assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_widget_user_invalid_uuid() -> None:
    """Malformed UUID is rejected before any DB call."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_widget_user(widget_id="not-a-uuid", session=mock_session)
    assert exc_info.value.status_code == 403
    mock_session.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_widget_user_missing() -> None:
    """No widget_id raises 403."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_widget_user(widget_id=None, session=mock_session)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Integration tests through /chat/send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_send_accepts_valid_widget_id() -> None:
    """Valid widget_id (DB returns widget+owner) — endpoint returns 200."""
    widget = _make_widget()
    _owner = _make_owner()

    async def _fake_stream(**_kwargs: Any) -> AsyncGenerator[str, None]:
        yield "ok"

    with (
        patch("app.repositories.widgets.get_widget", return_value=widget),
        patch("app.api.chat.stream_chat_response", side_effect=_fake_stream),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # We also need session.get(User, owner_id) to return owner
            # — the mock session from the override returns AsyncMock by default,
            # which is truthy; the is_active check will pass.
            resp = await client.post(
                f"/chat/send?widget_id={_WIDGET_ID}",
                json={"conversation_id": None, "message": "hi"},
            )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_send_rejects_invalid_widget_id() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/chat/send?widget_id=not-a-uuid",
            json={"conversation_id": None, "message": "hi"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_send_rejects_no_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/chat/send",
            json={"conversation_id": None, "message": "hi"},
        )
    assert resp.status_code == 403
