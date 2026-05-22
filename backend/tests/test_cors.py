"""Tests for DynamicCORSMiddleware — Phase 4.6.

Verifies that CORS headers are added for allowed origins and withheld for
blocked origins, and that OPTIONS preflight is handled correctly.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _set_allowed_origins() -> Any:
    app.state.allowed_origins = {"http://allowed.example.com"}
    yield
    if hasattr(app.state, "allowed_origins"):
        del app.state.allowed_origins


# ── Non-preflight requests ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_cors_allowed_origin_gets_header() -> None:
    """Allowed origin receives Access-Control-Allow-Origin header."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz", headers={"Origin": "http://allowed.example.com"})
    assert resp.headers.get("access-control-allow-origin") == "http://allowed.example.com"
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.anyio
async def test_cors_blocked_origin_no_header() -> None:
    """Unknown origin does NOT receive CORS headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.anyio
async def test_cors_no_origin_no_header() -> None:
    """Request without Origin header is unaffected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert "access-control-allow-origin" not in resp.headers


# ── OPTIONS preflight ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_cors_preflight_allowed_origin() -> None:
    """OPTIONS from allowed origin returns 204 with full CORS headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/chat/send",
            headers={
                "Origin": "http://allowed.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
    assert resp.status_code == 204
    assert resp.headers.get("access-control-allow-origin") == "http://allowed.example.com"
    assert "POST" in resp.headers.get("access-control-allow-methods", "")
    assert resp.headers.get("access-control-max-age") == "600"


@pytest.mark.anyio
async def test_cors_preflight_blocked_origin() -> None:
    """OPTIONS from blocked origin returns 204 with NO CORS headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/chat/send",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 204
    assert "access-control-allow-origin" not in resp.headers
