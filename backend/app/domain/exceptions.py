"""Domain exception hierarchy — Phase 3.5 (D-022).

These are *domain* exceptions — raised inside services and tool calls when
a known error condition occurs during request processing.  They are distinct
from *infra* exceptions (VaultUnreachableError, LangfuseUnreachableError,
ModelServerStateError) which abort startup.

The API boundary exception handler in app/main.py converts every CopilotError
subclass to a structured JSON response.  Users never see a stack trace.
"""

from __future__ import annotations


class CopilotError(Exception):
    """Base for all domain errors.

    Subclasses set ``http_status`` and ``code`` as class attributes.
    The exception message becomes the user-facing ``message`` field.
    """

    http_status: int = 500
    code: str = "internal_error"


class NotFoundError(CopilotError):
    """Requested resource does not exist."""

    http_status = 404
    code = "not_found"


class PermissionDeniedError(CopilotError):
    """Caller is authenticated but not authorised for this resource."""

    http_status = 403
    code = "permission_denied"


class ToolFailureError(CopilotError):
    """A chatbot tool call failed (upstream dependency error, timeout, etc.)."""

    http_status = 502
    code = "tool_failure"


class RateLimitError(CopilotError):
    """Caller has exceeded their request rate limit."""

    http_status = 429
    code = "rate_limited"


class ValidationError(CopilotError):
    """Input failed domain-level validation (distinct from Pydantic schema errors)."""

    http_status = 422
    code = "validation_error"
