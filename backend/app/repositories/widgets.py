"""Widget repository — CRUD for the widgets table + allowed_origins loader."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.widgets import Widget


async def create_widget(
    session: AsyncSession,
    *,
    name: str,
    owner_id: uuid.UUID,
    theme: str = "dark",
    greeting: str = "Hello! How can I help?",
    enabled_tools: list[str] | None = None,
    allowed_origins: list[str] | None = None,
) -> Widget:
    widget = Widget(
        id=uuid.uuid4(),
        name=name,
        owner_id=owner_id,
        theme=theme,
        greeting=greeting,
        enabled_tools=enabled_tools if enabled_tools is not None else ["retrieve_docs"],
        allowed_origins=allowed_origins if allowed_origins is not None else [],
    )
    session.add(widget)
    await session.commit()
    await session.refresh(widget)
    return widget


async def get_widget(session: AsyncSession, widget_id: uuid.UUID) -> Widget | None:
    return await session.get(Widget, widget_id)


async def update_widget(
    session: AsyncSession,
    widget: Widget,
    *,
    patch: dict[str, Any],
) -> Widget:
    allowed_fields = {"name", "theme", "greeting", "enabled_tools", "allowed_origins"}
    for key, value in patch.items():
        if key in allowed_fields:
            setattr(widget, key, value)
    await session.commit()
    await session.refresh(widget)
    return widget


async def list_widgets_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[Widget]:
    result = await session.execute(
        select(Widget).where(Widget.owner_id == owner_id).order_by(Widget.created_at)
    )
    return list(result.scalars().all())


async def load_allowed_origins(session: AsyncSession) -> set[str]:
    """Return the union of all allowed_origins across every widget row.

    Called at startup (lifespan) and after each POST/PATCH so the in-memory
    set stays fresh without a restart (D-026).
    """
    result = await session.execute(select(Widget.allowed_origins))
    origins: set[str] = set()
    for row_origins in result.scalars().all():
        if row_origins:
            origins.update(row_origins)
    return origins
