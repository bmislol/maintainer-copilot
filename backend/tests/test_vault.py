"""Smoke test: load_secrets() returns a populated Secrets object.

Expects Vault to be reachable and seeded. Skipped when Vault is unavailable
so unit-test runs in CI (which doesn't spin up Vault) still pass.
"""

from __future__ import annotations

import pytest

from app.infra.vault import VaultUnreachableError, load_secrets


def test_load_secrets_returns_populated_object() -> None:
    """When Vault is up and seeded, load_secrets returns all six secret groups."""
    try:
        secrets = load_secrets()
    except VaultUnreachableError:
        pytest.skip("Vault not reachable — integration test skipped")

    assert secrets.database.url.startswith("postgresql")
    assert secrets.jwt.signing_key
    assert secrets.jwt.algorithm == "HS256"
    assert secrets.minio.endpoint
    assert secrets.redis.url.startswith("redis://")
    assert secrets.anthropic.api_key
    assert secrets.langfuse.host
