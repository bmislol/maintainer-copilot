"""FastAPI lifespan — startup and shutdown hooks.

Refuses to boot if:
  - Vault is unreachable, OR
  - Langfuse is misconfigured / unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI

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
    logger.info("api startup complete")

    yield

    logger.info("api shutdown — flushing langfuse")
    shutdown_langfuse()
