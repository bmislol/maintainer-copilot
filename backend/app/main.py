"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.api.middleware import RequestContextMiddleware
from app.core.lifespan import lifespan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(
    title="Maintainer's Copilot API",
    version="0.1.0",
    description="Authenticated chatbot backend for OSS maintainers.",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)

logger = logging.getLogger(__name__)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    logger.info("healthz called")
    return {"status": "ok"}
