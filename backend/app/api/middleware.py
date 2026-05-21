"""HTTP middleware — request ID generation, trace creation, and context binding."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import request_id_var, trace_id_var
from app.infra.tracing import get_client, redact_metadata


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generates a request_id and trace_id for every request and binds them to context."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Use the client-provided ID if it's a valid UUID, else generate one.
        client_id = request.headers.get("X-Request-ID", "")
        try:
            request_id = str(uuid.UUID(client_id)) if client_id else str(uuid.uuid4())
        except ValueError:
            request_id = str(uuid.uuid4())

        # Start a Langfuse trace rooted at this request — when tracing
        # has been initialized. In unit tests the lifespan doesn't run,
        # so we degrade gracefully to an empty trace_id.
        langfuse = get_client()
        if langfuse is not None:
            trace = langfuse.trace(
                name=f"{request.method} {request.url.path}",
                metadata=redact_metadata({"request_id": request_id}),
            )
            trace_id: str = trace.id
        else:
            trace_id = ""

        # Expose on request.state so exception handlers can read it.
        request.state.request_id = request_id

        # Bind to context so every log line in this request picks them up.
        request_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)

        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(request_token)
            trace_id_var.reset(trace_token)

        # Echo the request_id back so clients can correlate.
        response.headers["X-Request-ID"] = request_id
        return response
