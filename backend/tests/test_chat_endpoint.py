"""Tests for the /chat/send SSE endpoint — Phase 4.2.

Uses httpx AsyncClient with the FastAPI test app. Overrides auth and the
chat service to avoid live infrastructure.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi_users.authentication import JWTStrategy
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import get_current_user_or_widget, get_jwt_strategy
from app.main import app

_TEST_SECRET = "test-jwt-secret-for-chat-unit-tests-only"


@pytest.fixture(autouse=True)
def _setup_app_state() -> Any:
    """Provide minimal app.state and override infra deps for all tests in this module."""
    app.state.anthropic_client = AsyncMock()
    app.state.http_client = AsyncMock()
    app.state.redis_client = MagicMock()
    app.dependency_overrides[get_async_session] = _mock_session

    def _test_jwt_strategy() -> JWTStrategy[User, int]:  # type: ignore[type-arg]
        return JWTStrategy(secret=_TEST_SECRET, lifetime_seconds=3600, algorithm="HS256")

    app.dependency_overrides[get_jwt_strategy] = _test_jwt_strategy
    yield
    app.dependency_overrides.clear()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "user@example.com"
    user.is_active = True
    user.is_superuser = False
    return user


async def _fake_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
    yield "Hello"
    yield " maintainer"


async def _mock_session() -> AsyncGenerator[Any, None]:
    yield AsyncMock()


@pytest.fixture()
def auth_override() -> None:
    app.dependency_overrides[get_current_user_or_widget] = lambda: _mock_user()


@pytest.mark.asyncio
async def test_send_message_streams_sse(auth_override: None) -> None:  # noqa: ARG001
    with patch(
        "app.api.chat.stream_chat_response",
        side_effect=_fake_stream,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/chat/send",
                json={"conversation_id": None, "message": "triage this issue"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "Hello" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_send_message_requires_auth() -> None:
    # No Bearer token and no widget_id → get_current_user_or_widget raises 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/chat/send",
            json={"conversation_id": None, "message": "hi"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_send_message_with_conversation_id(auth_override: None) -> None:  # noqa: ARG001
    captured_kwargs: dict[str, Any] = {}

    async def _capture(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
        captured_kwargs.update(kwargs)
        yield "ok"

    with patch("app.api.chat.stream_chat_response", side_effect=_capture):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/chat/send",
                json={
                    "conversation_id": "12345678-1234-1234-1234-123456789012",
                    "message": "hello",
                },
            )

    assert captured_kwargs.get("conversation_id") == "12345678-1234-1234-1234-123456789012"
    assert captured_kwargs.get("user_message") == "hello"
    assert captured_kwargs.get("user_id") is not None
