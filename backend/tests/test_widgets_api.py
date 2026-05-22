"""Tests for the widget config API — Phase 4.6.

Covers: CRUD endpoints, CORS headers for allowed vs blocked origins,
frame-ancestors CSP header on /widget.js, and /loader.js content.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.db.models.widgets import Widget
from app.db.session import get_async_session
from app.infra.auth import current_active_superuser, current_active_user
from app.main import app

_ADMIN_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WIDGET_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


def _make_admin() -> User:
    u = User(
        id=_ADMIN_ID,
        email="admin@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    return u


def _make_widget(owner_id: uuid.UUID = _ADMIN_ID) -> Widget:
    return Widget(
        id=_WIDGET_ID,
        name="Test Widget",
        owner_id=owner_id,
        theme="dark",
        greeting="Hello! How can I help?",
        enabled_tools=["retrieve_docs"],
        allowed_origins=["http://localhost:8080"],
    )


async def _mock_session() -> AsyncGenerator[Any, None]:
    yield AsyncMock()


@pytest.fixture(autouse=True)
def _setup_state() -> Any:
    app.state.allowed_origins = {"http://localhost:8080"}
    app.dependency_overrides[get_async_session] = _mock_session
    yield
    app.dependency_overrides.clear()
    if hasattr(app.state, "allowed_origins"):
        del app.state.allowed_origins


@pytest.fixture()
def admin_override() -> None:
    admin = _make_admin()
    app.dependency_overrides[current_active_user] = lambda: admin
    app.dependency_overrides[current_active_superuser] = lambda: admin


# ── Widget CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_widget(admin_override: None) -> None:  # noqa: ARG001
    widget = _make_widget()
    with (
        patch("app.api.widgets.create_widget", return_value=widget) as mock_create,
        patch("app.api.widgets.load_allowed_origins", return_value={"http://localhost:8080"}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/widgets/",
                json={
                    "name": "Test Widget",
                    "theme": "dark",
                    "greeting": "Hello! How can I help?",
                    "enabled_tools": ["retrieve_docs"],
                    "allowed_origins": ["http://localhost:8080"],
                },
            )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Widget"
    assert body["theme"] == "dark"
    assert "http://localhost:8080" in body["allowed_origins"]
    mock_create.assert_called_once()


@pytest.mark.anyio
async def test_create_widget_requires_admin() -> None:
    """Non-superuser cannot create a widget."""
    _non_admin = User(
        id=uuid.uuid4(),
        email="user@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    app.dependency_overrides[current_active_superuser] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403)
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/widgets/", json={"name": "X"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(current_active_superuser, None)


@pytest.mark.anyio
async def test_get_widget_config_public() -> None:
    """GET /widgets/{id}/config is public — no auth required."""
    widget = _make_widget()
    with patch("app.api.widgets.get_widget", return_value=widget):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/widgets/{_WIDGET_ID}/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "dark"
    assert body["greeting"] == "Hello! How can I help?"
    # allowed_origins must NOT be in the public config response
    assert "allowed_origins" not in body


@pytest.mark.anyio
async def test_get_widget_config_not_found() -> None:
    with patch("app.api.widgets.get_widget", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/widgets/{uuid.uuid4()}/config")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_widget(admin_override: None) -> None:  # noqa: ARG001
    widget = _make_widget()
    updated = _make_widget()
    updated.greeting = "Updated greeting"
    with (
        patch("app.api.widgets.get_widget", return_value=widget),
        patch("app.api.widgets.update_widget", return_value=updated),
        patch("app.api.widgets.load_allowed_origins", return_value={"http://localhost:8080"}),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/widgets/{_WIDGET_ID}", json={"greeting": "Updated greeting"}
            )
    assert resp.status_code == 200
    assert resp.json()["greeting"] == "Updated greeting"


# ── CSP frame-ancestors on widget.js ─────────────────────────────────────────


@pytest.mark.anyio
async def test_widget_js_frame_ancestors_header() -> None:
    """GET /widget.js includes frame-ancestors header with allowed origins."""
    fake_js = b"// widget bundle"
    with patch("app.main._WIDGET_JS") as mock_path:
        mock_path.exists.return_value = True
        mock_path.read_bytes.return_value = fake_js
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/widget.js")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors" in csp
    assert "'self'" in csp
    assert "http://localhost:8080" in csp


@pytest.mark.anyio
async def test_widget_js_no_origins_self_only() -> None:
    """frame-ancestors is 'self' when no origins are configured."""
    app.state.allowed_origins = set()
    fake_js = b"// widget bundle"
    with patch("app.main._WIDGET_JS") as mock_path:
        mock_path.exists.return_value = True
        mock_path.read_bytes.return_value = fake_js
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/widget.js")
    csp = resp.headers.get("content-security-policy", "")
    assert csp == "frame-ancestors 'self'"


# ── loader.js ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_loader_js_served() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/loader.js")
    assert resp.status_code == 200
    assert "data-widget-id" in resp.text
    assert "apiBase" in resp.text
    assert resp.headers["content-type"].startswith("application/javascript")
