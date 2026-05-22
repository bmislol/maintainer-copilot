"""FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.cors import DynamicCORSMiddleware
from app.api.memory import router as memory_router
from app.api.middleware import RequestContextMiddleware
from app.api.widgets import router as widgets_router
from app.core.lifespan import lifespan
from app.domain.exceptions import CopilotError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

app = FastAPI(
    title="Maintainer's Copilot API",
    version="0.1.0",
    description="Authenticated chatbot backend for OSS maintainers.",
    lifespan=lifespan,
)

# CORS first — must precede other middleware so preflight responses are returned
# before RequestContextMiddleware touches the request.
app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(RequestContextMiddleware)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(widgets_router)

logger = logging.getLogger(__name__)

_WIDGET_JS = Path(__file__).parent / "static" / "widget.js"


@app.get("/widget.js", include_in_schema=False)
async def serve_widget_js(request: Request) -> Response:
    """Serve widget.js with Content-Security-Policy: frame-ancestors header.

    Served at /widget.js (not /static/widget.js) because Starlette mounts
    take routing priority over explicit routes for paths under the mount
    prefix, regardless of registration order (D-027).
    """
    if not _WIDGET_JS.exists():
        return Response(status_code=404, content="widget.js not built")
    content = _WIDGET_JS.read_bytes()
    allowed: set[str] = getattr(request.app.state, "allowed_origins", set())
    frame_ancestors = "'self'"
    if allowed:
        frame_ancestors += " " + " ".join(sorted(allowed))
    return Response(
        content=content,
        media_type="application/javascript",
        headers={"Content-Security-Policy": f"frame-ancestors {frame_ancestors}"},
    )


_LOADER_JS = """\
(function () {
  var script = document.currentScript;
  var widgetId = script.getAttribute('data-widget-id') || '';
  var apiBase = script.getAttribute('data-api-base') || 'http://localhost:8000';
  var s = document.createElement('script');
  s.src = apiBase + '/widget.js';
  s.setAttribute('data-widget-id', widgetId);
  s.setAttribute('data-api-base', apiBase);
  document.head.appendChild(s);
}());
"""


@app.get("/loader.js", include_in_schema=False)
async def serve_loader_js() -> Response:
    """Tiny loader — reads data-widget-id, injects the widget bundle."""
    return Response(
        content=_LOADER_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.exception_handler(CopilotError)
async def copilot_error_handler(request: Request, exc: CopilotError) -> JSONResponse:
    """Convert domain exceptions to structured JSON error responses."""
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
