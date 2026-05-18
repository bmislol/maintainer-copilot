"""Smoke tests for the FastAPI app entry point."""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_healthz_returns_ok() -> None:
    """Healthz endpoint returns 200 with status ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
