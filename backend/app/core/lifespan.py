"""FastAPI lifespan — startup and shutdown hooks.

Refuses to boot if:
  - Vault is unreachable, OR
  - Langfuse is misconfigured / unreachable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import bootstrap_settings
from app.core.logging import configure_logging
from app.infra.tracing import (
    LangfuseUnreachableError,
    init_langfuse,
    shutdown_langfuse,
)
from app.infra.vault import Secrets, VaultUnreachableError, load_secrets

logger = logging.getLogger(__name__)


def _check_eval_thresholds(yaml_path: Path) -> None:
    """Raise RuntimeError if any threshold is missing, zero, or non-numeric.

    Tested in tests/test_eval_thresholds_refuse_to_boot.py via direct call;
    integration-tested by the lifespan's call to _resolve_thresholds_path()
    below.
    """
    if not yaml_path.exists():
        raise RuntimeError(
            f"REFUSING TO BOOT: eval_thresholds.yaml not found at {yaml_path}. "
            "Eval thresholds must be committed; see DECISIONS D-013."
        )

    data = yaml.safe_load(yaml_path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"REFUSING TO BOOT: {yaml_path} is not a YAML mapping")

    for category, thresholds in data.items():
        if not isinstance(thresholds, dict):
            continue
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)) or value <= 0:
                raise RuntimeError(
                    f"REFUSING TO BOOT: eval_thresholds.yaml has "
                    f"{category}.{key}={value} (must be > 0)"
                )


def _resolve_thresholds_path() -> Path:
    """Find eval_thresholds.yaml — inside docker (/app) or on the host (backend/)."""
    candidates = [
        Path("/app/eval_thresholds.yaml"),
        Path(__file__).resolve().parents[2] / "eval_thresholds.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Return the docker path so the error message is helpful.
    return candidates[0]


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
        _check_eval_thresholds(_resolve_thresholds_path())
    except RuntimeError as exc:
        logger.critical(str(exc))
        raise

    try:
        init_langfuse(secrets.langfuse)
    except LangfuseUnreachableError as exc:
        logger.critical("REFUSING TO BOOT: %s", exc)
        raise

    app.state.secrets = secrets

    # Async SQLAlchemy engine and session factory — created here so the DB URL
    # is read from Vault-resolved secrets, not from an env var.
    engine = create_async_engine(secrets.database.url, pool_pre_ping=True)
    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Shared HTTP client for modelserver calls — one connection pool for the
    # entire process lifetime. Timeout generous enough for model inference.
    app.state.http_client = httpx.AsyncClient(
        base_url=bootstrap_settings.modelserver_url,
        timeout=httpx.Timeout(30.0),
    )

    # Anthropic async client — API key from Vault.
    app.state.anthropic_client = AsyncAnthropic(api_key=secrets.anthropic.api_key)

    # BM25 indexes — built synchronously from rag_chunks using psycopg2.
    # Strip the +asyncpg driver prefix so psycopg2 can parse the URL.
    from app.rag.bm25_index import build_indexes

    psycopg2_url = secrets.database.url.replace("postgresql+asyncpg://", "postgresql://", 1)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, build_indexes, psycopg2_url)

    logger.info("api startup complete")

    yield

    logger.info("api shutdown — closing clients and disposing db engine")
    await app.state.http_client.aclose()
    await app.state.anthropic_client.close()
    await app.state.db_engine.dispose()
    shutdown_langfuse()
