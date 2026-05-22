"""Dynamic CORS middleware — pure ASGI, reads allowed_origins from app.state.

Uses pure ASGI (not BaseHTTPMiddleware) so streaming SSE responses are
not buffered.  The allowed set is loaded from the widgets table at startup
and refreshed after each POST/PATCH /widgets/ operation (D-026).

Security note: unrecognised origins receive a 204 with NO CORS headers on
OPTIONS.  The browser sees no Access-Control-Allow-Origin and blocks the
subsequent request.  We do not return 403 — that would short-circuit the
browser's CORS enforcement and leak information about which origins exist.
"""

from __future__ import annotations

from typing import Any

_CORS_HEADERS = (
    b"access-control-allow-methods",
    b"access-control-allow-headers",
    b"access-control-max-age",
    b"access-control-allow-credentials",
)

_ALLOW_METHODS = b"GET, POST, PATCH, DELETE, OPTIONS"
_ALLOW_HEADERS = b"Authorization, Content-Type, X-Request-ID"
_MAX_AGE = b"600"


class DynamicCORSMiddleware:
    """ASGI middleware that enforces the per-widget allowed_origins allowlist."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract origin from request headers (bytes).
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        origin: str = headers.get(b"origin", b"").decode()

        # Read the live allowed set from the FastAPI app state.
        fastapi_app = scope.get("app")
        allowed: set[str] = getattr(getattr(fastapi_app, "state", None), "allowed_origins", set())
        origin_allowed = bool(origin) and origin in allowed

        if scope.get("method") == "OPTIONS":
            await self._handle_preflight(send, origin, origin_allowed)
            return

        # Non-preflight: wrap send to inject CORS headers into the start event.
        async def send_with_cors(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and origin_allowed:
                extra = [
                    (b"access-control-allow-origin", origin.encode()),
                    (b"access-control-allow-credentials", b"true"),
                ]
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        await self.app(scope, receive, send_with_cors)

    @staticmethod
    async def _handle_preflight(send: Any, origin: str, origin_allowed: bool) -> None:
        if origin_allowed:
            resp_headers = [
                (b"access-control-allow-origin", origin.encode()),
                (b"access-control-allow-credentials", b"true"),
                (b"access-control-allow-methods", _ALLOW_METHODS),
                (b"access-control-allow-headers", _ALLOW_HEADERS),
                (b"access-control-max-age", _MAX_AGE),
                (b"content-length", b"0"),
            ]
        else:
            resp_headers = [(b"content-length", b"0")]

        await send({"type": "http.response.start", "status": 204, "headers": resp_headers})
        await send({"type": "http.response.body", "body": b""})
