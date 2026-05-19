"""FastAPI lifespan — startup and shutdown hooks.

Refuses to boot if:
  - Vault is unreachable, OR
  - Langfuse is misconfigured / unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import configure_logging
from app.infra.tracing import (
    LangfuseUnreachableError,
    init_langfuse,
    shutdown_langfuse,
)
from app.infra.vault import Secrets, VaultUnreachableError, load_secrets

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: configure logging, load secrets, init tracing. Refuse to boot on failure."""
    configure_logging(service_name="api")
    logger.info("api startup — resolving secrets")

    try:
        secrets: Secrets = load_secrets()
    except VaultUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    try:
        init_langfuse(secrets.langfuse)
    except LangfuseUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    app.state.secrets = secrets
    logger.info("api startup complete")

    yield

    logger.info("api shutdown — flushing langfuse")
    shutdown_langfuse()
