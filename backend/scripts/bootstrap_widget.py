"""Bootstrap the demo widget with a fixed deterministic UUID.

Idempotent — skips creation if the widget already exists.
Must be run after bootstrap_admin.py (requires the admin user to exist).

Usage
-----
    DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot" \\
    uv run python -m scripts.bootstrap_widget
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base  # noqa: F401
from app.db.models.users import User
from app.db.models.widgets import Widget

DEMO_WIDGET_ID = uuid.UUID("00000000-0000-0000-0001-000000000001")
ADMIN_EMAIL = "admin@maintainer-copilot.dev"


async def _bootstrap(session: AsyncSession) -> None:
    # Check if demo widget already exists
    existing = await session.get(Widget, DEMO_WIDGET_ID)
    if existing is not None:
        print(f"Demo widget {DEMO_WIDGET_ID} already exists. Skipping.")
        return

    # Find the admin user
    result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))  # type: ignore[arg-type]
    admin = result.scalar_one_or_none()
    if admin is None:
        print(f"ERROR: admin user {ADMIN_EMAIL!r} not found. Run bootstrap_admin.py first.")
        sys.exit(1)

    widget = Widget(
        id=DEMO_WIDGET_ID,
        name="Demo Widget",
        owner_id=admin.id,
        theme="dark",
        greeting="Hello! I'm the Maintainer's Copilot. How can I help you triage issues?",
        enabled_tools=["retrieve_docs", "classify_issue", "summarize_thread"],
        allowed_origins=["http://localhost:8080"],
    )
    session.add(widget)
    await session.commit()
    print(f"Demo widget created: {DEMO_WIDGET_ID}")
    print(f"  name:            {widget.name}")
    print(f"  owner:           {ADMIN_EMAIL}")
    print(f"  allowed_origins: {widget.allowed_origins}")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL env var is required.")
        sys.exit(1)

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await _bootstrap(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
