"""Widget config API — Phase 4.6.

Routes:
  POST   /widgets/           — create widget (admin only)
  GET    /widgets/{id}/config — public; returns display-safe fields only
  GET    /widgets/{id}        — get widget (owner or admin)
  PATCH  /widgets/{id}        — update widget (owner or admin)

After create or update, allowed_origins in app.state is refreshed so
CORS and frame-ancestors headers pick up the change without a restart (D-026).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import current_active_superuser, current_active_user
from app.repositories.widgets import (
    create_widget,
    get_widget,
    list_widgets_for_owner,
    load_allowed_origins,
    update_widget,
)

router = APIRouter(prefix="/widgets", tags=["widgets"])


# ── Request / response schemas ───────────────────────────────────────────────


class WidgetCreate(BaseModel):
    name: str = Field(..., max_length=128)
    theme: str = Field("dark", pattern="^(dark|light)$")
    greeting: str = Field("Hello! How can I help?", max_length=512)
    enabled_tools: list[str] = Field(default_factory=lambda: ["retrieve_docs"])
    allowed_origins: list[str] = Field(default_factory=list)


class WidgetPatch(BaseModel):
    name: str | None = Field(None, max_length=128)
    theme: str | None = Field(None, pattern="^(dark|light)$")
    greeting: str | None = Field(None, max_length=512)
    enabled_tools: list[str] | None = None
    allowed_origins: list[str] | None = None


class WidgetOut(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID | None
    theme: str
    greeting: str
    enabled_tools: list[Any]
    allowed_origins: list[str]


class WidgetConfigOut(BaseModel):
    """Public-facing config — no allowed_origins (server-side only)."""

    id: uuid.UUID
    theme: str
    greeting: str
    enabled_tools: list[Any]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _refresh_state(request: Request, session: AsyncSession) -> None:
    """Update app.state.allowed_origins from DB after a write operation."""
    request.app.state.allowed_origins = await load_allowed_origins(session)


def _assert_owner_or_admin(widget_owner_id: uuid.UUID | None, user: User) -> None:
    if not user.is_superuser and widget_owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your widget")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/mine", response_model=list[WidgetOut])
async def list_my_widgets(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[WidgetOut]:
    """Return all widgets owned by the calling user."""
    widgets = await list_widgets_for_owner(session, user.id)
    return [
        WidgetOut(
            id=w.id,
            name=w.name,
            owner_id=w.owner_id,
            theme=w.theme,
            greeting=w.greeting,
            enabled_tools=w.enabled_tools,
            allowed_origins=w.allowed_origins,
        )
        for w in widgets
    ]


@router.post("/", response_model=WidgetOut, status_code=status.HTTP_201_CREATED)
async def create_widget_endpoint(
    body: WidgetCreate,
    request: Request,
    user: User = Depends(current_active_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> WidgetOut:
    widget = await create_widget(
        session,
        name=body.name,
        owner_id=user.id,
        theme=body.theme,
        greeting=body.greeting,
        enabled_tools=body.enabled_tools,
        allowed_origins=body.allowed_origins,
    )
    await _refresh_state(request, session)
    return WidgetOut(
        id=widget.id,
        name=widget.name,
        owner_id=widget.owner_id,
        theme=widget.theme,
        greeting=widget.greeting,
        enabled_tools=widget.enabled_tools,
        allowed_origins=widget.allowed_origins,
    )


@router.get("/{widget_id}/config", response_model=WidgetConfigOut)
async def get_widget_config(
    widget_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> WidgetConfigOut:
    """Public endpoint — no auth. Returns only display-safe fields."""
    widget = await get_widget(session, widget_id)
    if not widget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    return WidgetConfigOut(
        id=widget.id,
        theme=widget.theme,
        greeting=widget.greeting,
        enabled_tools=widget.enabled_tools,
    )


@router.get("/{widget_id}", response_model=WidgetOut)
async def get_widget_endpoint(
    widget_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> WidgetOut:
    widget = await get_widget(session, widget_id)
    if not widget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    _assert_owner_or_admin(widget.owner_id, user)
    return WidgetOut(
        id=widget.id,
        name=widget.name,
        owner_id=widget.owner_id,
        theme=widget.theme,
        greeting=widget.greeting,
        enabled_tools=widget.enabled_tools,
        allowed_origins=widget.allowed_origins,
    )


@router.patch("/{widget_id}", response_model=WidgetOut)
async def patch_widget_endpoint(
    widget_id: uuid.UUID,
    body: WidgetPatch,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> WidgetOut:
    widget = await get_widget(session, widget_id)
    if not widget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    _assert_owner_or_admin(widget.owner_id, user)
    patch_data = {k: v for k, v in body.model_dump().items() if v is not None}
    widget = await update_widget(session, widget, patch=patch_data)
    await _refresh_state(request, session)
    return WidgetOut(
        id=widget.id,
        name=widget.name,
        owner_id=widget.owner_id,
        theme=widget.theme,
        greeting=widget.greeting,
        enabled_tools=widget.enabled_tools,
        allowed_origins=widget.allowed_origins,
    )
