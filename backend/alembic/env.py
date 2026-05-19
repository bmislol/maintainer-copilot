"""Alembic environment.

Pulls the database URL from Vault at migration time, the same way the api does
at startup. This keeps the secret out of alembic.ini and out of source.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.db.base import Base  # noqa: F401 — imported for metadata side effects

# Alembic config object — provides access to alembic.ini values.
config = context.config

# Database URL resolution:
#   - If DATABASE_URL env var is set, use it directly. This is the path used
#     for host-side `alembic revision --autogenerate`, where the developer
#     points at localhost:5432 (the docker-exposed Postgres port) and Vault
#     is not reachable from outside the docker network.
#   - Otherwise, resolve from Vault. This is the path used by the `migrate`
#     container at compose startup, which is inside the docker network and
#     can reach Vault.
_db_url_override = os.environ.get("DATABASE_URL")
if _db_url_override:
    config.set_main_option("sqlalchemy.url", _db_url_override)
else:
    from app.infra.vault import load_secrets

    secrets = load_secrets()
    config.set_main_option("sqlalchemy.url", secrets.database.url)

# Set up Python logging per the [loggers]/[handlers]/[formatters] sections.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the metadata object autogenerate compares against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout instead of a DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the DB and runs against it."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
