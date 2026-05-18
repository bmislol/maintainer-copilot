"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Maintainer's Copilot API",
    version="0.1.0",
    description="Authenticated chatbot backend for OSS maintainers.",
)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
