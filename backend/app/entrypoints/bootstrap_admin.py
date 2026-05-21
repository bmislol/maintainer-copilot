"""Bootstrap the first admin user.

Run once, host-side, before any user can log in. Reads the target DB
directly via DATABASE_URL — does not go through Vault or the API.

Usage
-----
    DATABASE_URL="postgresql+asyncpg://copilot:pass@localhost:5432/copilot" \\
    BOOTSTRAP_EMAIL="admin@example.com" \\
    BOOTSTRAP_PASSWORD="change-me" \\
    uv run python -m app.entrypoints.bootstrap_admin

All three env vars are required. The script exits non-zero if:
  - DATABASE_URL is missing
  - BOOTSTRAP_EMAIL or BOOTSTRAP_PASSWORD is missing
  - A user with that email already exists
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import all models so Base.metadata is complete before we do anything.
from app.db.base import Base  # noqa: F401
from app.db.models.users import User


async def _create_admin(session: AsyncSession, email: str, password: str) -> None:
    result = await session.execute(select(User).where(User.email == email))  # type: ignore[arg-type]
    if result.scalar_one_or_none() is not None:
        print(f"ERROR: user {email!r} already exists. Aborting.")
        sys.exit(1)

    helper = PasswordHelper()
    hashed = helper.hash(password)
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
        is_superuser=True,
    )
    session.add(user)
    await session.commit()
    print(f"Admin user created: {email}")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    email = os.environ.get("BOOTSTRAP_EMAIL")
    password = os.environ.get("BOOTSTRAP_PASSWORD")

    missing = [
        name
        for name, val in [
            ("DATABASE_URL", database_url),
            ("BOOTSTRAP_EMAIL", email),
            ("BOOTSTRAP_PASSWORD", password),
        ]
        if not val
    ]
    if missing:
        print(f"ERROR: missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    # Normalise the driver scheme: standard DATABASE_URL uses postgresql://
    # but asyncpg requires postgresql+asyncpg://. Auto-convert so the script
    # works with the value copied directly from .env without editing.
    assert database_url is not None  # checked above
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await _create_admin(session, email, password)  # type: ignore[arg-type]
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
