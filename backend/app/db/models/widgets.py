"""Widget ORM model — Phase 4.6 adds owner_id, theme, greeting, enabled_tools."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    theme: Mapped[str] = mapped_column(String(16), nullable=False, server_default="dark")
    greeting: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="Hello! How can I help?"
    )
    enabled_tools: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, server_default='["retrieve_docs"]'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
