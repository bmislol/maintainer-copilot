"""Tests for /static/widget.js — Phase 4.5.

Skipped when widget.js has not been built yet.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_WIDGET_JS = os.path.join(os.path.dirname(__file__), "..", "app", "static", "widget.js")


@pytest.mark.skipif(
    not os.path.exists(_WIDGET_JS),
    reason="widget.js not built — run `npm run build` in frontend-widget/",
)
@pytest.mark.asyncio
async def test_widget_js_served_with_correct_content_type() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/static/widget.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
