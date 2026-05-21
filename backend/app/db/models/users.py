"""Users ORM model — fastapi-users compatible (Phase 4.1)."""

import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User account.

    Inherits from SQLAlchemyBaseUserTableUUID which provides:
      id (UUID PK), email (unique), hashed_password, is_active,
      is_verified, is_superuser.

    __tablename__ is overridden to "users" because the fastapi-users mixin
    defaults to "user" (singular) but our baseline migration and all
    existing FKs use the plural form.

    is_superuser is used as the admin flag. Two roles — user / admin —
    map cleanly to a boolean; no role column is needed (D-033).

    created_at is retained from the Phase 1.4 stub for audit purposes
    (the mixin does not include it).
    """

    __tablename__ = "users"

    # Explicit re-declaration needed because the mixin defines `id` as GUID
    # (a custom type) while we want the standard UUID dialect type for
    # Alembic-level compatibility.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
