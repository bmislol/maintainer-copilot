"""FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.middleware import RequestContextMiddleware
from app.core.lifespan import lifespan
from app.domain.exceptions import CopilotError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(
    title="Maintainer's Copilot API",
    version="0.1.0",
    description="Authenticated chatbot backend for OSS maintainers.",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)

logger = logging.getLogger(__name__)


@app.exception_handler(CopilotError)
async def copilot_error_handler(request: Request, exc: CopilotError) -> JSONResponse:
    """Convert domain exceptions to structured JSON error responses.

    Users never see a stack trace.  The request_id links this response to
    the Langfuse trace and the structured log entry so maintainers can
    investigate without exposing internals.
    """
    request_id = getattr(request.state, "request_id", "")
    logger.warning(
        "domain error %s: %s (request_id=%s)",
        exc.code,
        str(exc),
        request_id,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "request_id": request_id,
            }
        },
    )


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    logger.info("healthz called")
    return {"status": "ok"}
