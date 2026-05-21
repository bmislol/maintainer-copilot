"""Langfuse adapter — initializes the SDK and exposes span helpers.

Layer: app/infra/
Used by: app/core/lifespan.py at startup, services to wrap operations in spans.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langfuse import Langfuse

if TYPE_CHECKING:
    from app.infra.vault import LangfuseSecrets

logger = logging.getLogger(__name__)


class LangfuseUnreachableError(RuntimeError):
    """Langfuse could not be reached or the SDK could not be initialized."""


_client: Langfuse | None = None


def init_langfuse(secrets: LangfuseSecrets) -> Langfuse:
    """Initialize the Langfuse SDK at startup.

    Verifies connectivity by calling `auth_check()`. If that fails, raises
    LangfuseUnreachableError so the lifespan can refuse to boot.
    """
    global _client

    logger.info("initializing langfuse client at %s", secrets.host)

    client = Langfuse(
        public_key=secrets.public_key,
        secret_key=secrets.secret_key,
        host=secrets.host,
    )

    # auth_check returns True on success, False on bad credentials.
    # It returns a bool; on network failure it raises.
    try:
        ok = client.auth_check()
    except Exception as exc:
        raise LangfuseUnreachableError(
            f"Could not reach Langfuse at {secrets.host}: {exc}"
        ) from exc

    if not ok:
        raise LangfuseUnreachableError(f"Langfuse rejected credentials for {secrets.host}")

    _client = client
    logger.info("langfuse client ready")
    return client


def get_client() -> Langfuse | None:
    """Get the initialized Langfuse client.

    Returns None if `init_langfuse()` hasn't been called yet. In unit tests
    that import the app without running its lifespan, tracing is simply skipped.
    """
    return _client


def shutdown_langfuse() -> None:
    """Flush pending events at shutdown."""
    if _client is not None:
        _client.flush()


def redact_metadata(meta: dict[str, object]) -> dict[str, object]:
    """Redact string values in a Langfuse metadata dict before the trace call.

    Non-string values are passed through unchanged.  Callers should use this
    for every metadata dict passed to ``langfuse.trace()`` or span helpers so
    that credentials in request metadata never reach the Langfuse backend.
    """
    from app.infra.redaction import redact

    return {k: redact(str(v)) if isinstance(v, str) else v for k, v in meta.items()}
