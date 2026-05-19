"""FastAPI lifespan — startup and shutdown hooks.

Refuses to boot if Vault is unreachable or any required secret is missing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infra.vault import Secrets, VaultUnreachableError, load_secrets

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: load secrets from Vault. Refuse to boot on failure."""
    logger.info("api startup — resolving secrets")
    try:
        secrets: Secrets = load_secrets()
    except VaultUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    # Stash secrets on app.state so request handlers can reach them later
    # without re-reading Vault.
    app.state.secrets = secrets
    logger.info("api startup complete")

    yield

    logger.info("api shutdown")
