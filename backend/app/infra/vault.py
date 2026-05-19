"""Vault adapter — resolves runtime secrets at startup.

Layer: app/infra/
Used by: app/core/lifespan.py at startup, NEVER by services or routers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

import hvac
from hvac.exceptions import VaultError

from app.core.config import bootstrap_settings

logger = logging.getLogger(__name__)


class VaultUnreachableError(RuntimeError):
    """Vault could not be reached, or a required secret is missing."""


@dataclass(frozen=True)
class DatabaseSecrets:
    url: str


@dataclass(frozen=True)
class JWTSecrets:
    signing_key: str
    algorithm: str
    access_token_lifetime_seconds: int


@dataclass(frozen=True)
class MinioSecrets:
    endpoint: str
    access_key: str
    secret_key: str


@dataclass(frozen=True)
class RedisSecrets:
    url: str


@dataclass(frozen=True)
class AnthropicSecrets:
    api_key: str


@dataclass(frozen=True)
class LangfuseSecrets:
    public_key: str
    secret_key: str
    host: str


@dataclass(frozen=True)
class Secrets:
    """All runtime secrets, resolved once at startup."""

    database: DatabaseSecrets
    jwt: JWTSecrets
    minio: MinioSecrets
    redis: RedisSecrets
    anthropic: AnthropicSecrets
    langfuse: LangfuseSecrets


def _build_client() -> hvac.Client:
    client = hvac.Client(
        url=bootstrap_settings.vault_addr,
        token=bootstrap_settings.vault_token,
    )
    if not client.is_authenticated():
        raise VaultUnreachableError(
            f"Vault authentication failed at {bootstrap_settings.vault_addr}"
        )
    return client


def _read_kv(client: hvac.Client, key: str) -> dict[str, str]:
    """Read a single KV v2 path and return its data dict."""
    path = f"{bootstrap_settings.vault_kv_path_prefix}/{key}"
    try:
        resp = client.secrets.kv.v2.read_secret_version(
            mount_point=bootstrap_settings.vault_kv_mount,
            path=path,
            raise_on_deleted_version=True,
        )
    except VaultError as exc:
        raise VaultUnreachableError(
            f"Failed to read secret at {bootstrap_settings.vault_kv_mount}/{path}: {exc}"
        ) from exc
    data: dict[str, str] = cast(dict[str, str], resp["data"]["data"])
    return data


def load_secrets() -> Secrets:
    """Resolve every runtime secret from Vault. Called once at startup.

    Raises VaultUnreachableError if Vault is down or any secret is missing.
    """
    logger.info("loading secrets from vault at %s", bootstrap_settings.vault_addr)

    try:
        client = _build_client()
    except VaultUnreachableError:
        raise
    except Exception as exc:  # network errors, DNS failures, etc.
        raise VaultUnreachableError(
            f"Could not connect to Vault at {bootstrap_settings.vault_addr}: {exc}"
        ) from exc

    db = _read_kv(client, "db")
    jwt = _read_kv(client, "jwt")
    minio = _read_kv(client, "minio")
    redis = _read_kv(client, "redis")
    anthropic = _read_kv(client, "anthropic")
    langfuse = _read_kv(client, "langfuse")

    secrets = Secrets(
        database=DatabaseSecrets(url=db["url"]),
        jwt=JWTSecrets(
            signing_key=jwt["signing_key"],
            algorithm=jwt["algorithm"],
            access_token_lifetime_seconds=int(jwt["access_token_lifetime_seconds"]),
        ),
        minio=MinioSecrets(
            endpoint=minio["endpoint"],
            access_key=minio["access_key"],
            secret_key=minio["secret_key"],
        ),
        redis=RedisSecrets(url=redis["url"]),
        anthropic=AnthropicSecrets(api_key=anthropic["api_key"]),
        langfuse=LangfuseSecrets(
            public_key=langfuse["public_key"],
            secret_key=langfuse["secret_key"],
            host=langfuse["host"],
        ),
    )
    logger.info("loaded secrets for paths: db, jwt, minio, redis, anthropic, langfuse")
    return secrets
