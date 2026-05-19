"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.core.lifespan import lifespan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(
    title="Maintainer's Copilot API",
    version="0.1.0",
    description="Authenticated chatbot backend for OSS maintainers.",
    lifespan=lifespan,
)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
