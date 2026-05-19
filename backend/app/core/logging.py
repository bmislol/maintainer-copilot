"""Structured JSON logging with request/trace correlation.

Every log line emitted from anywhere in the app carries:
  - timestamp (ISO-8601)
  - level
  - service ("api" / "modelserver" / etc.)
  - event (snake_case event name, derived from logger name + message)
  - request_id (UUID v4, from the current request context)
  - trace_id (Langfuse trace ID, from the current request context)

Request/trace IDs flow through Python's contextvars, so they're available
to any log call inside a request without manual plumbing.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Context variables — set per request, read by the formatter.
# Default values (empty strings) are used outside request scope (e.g. at startup).
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class JSONFormatter(logging.Formatter):
    """Emits each log record as a single line of JSON."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self.service_name,
            "event": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HealthzFilter(logging.Filter):
    """Drops uvicorn access logs for /healthz.

    Healthcheck noise overwhelms real logs at 1 hit / 5 seconds per service.
    We still log application-level events from /healthz — only the raw
    access log line is suppressed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "/healthz" not in record.getMessage()


def configure_logging(service_name: str, level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger.

    Call once at startup, before any log call.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn has its own loggers — make sure they go through our handler too.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(noisy)
        log.handlers.clear()
        log.propagate = True

    # Filter healthcheck noise from the access log.
    logging.getLogger("uvicorn.access").addFilter(HealthzFilter())
