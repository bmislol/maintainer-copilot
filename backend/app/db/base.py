"""SQLAlchemy declarative base + model registry.

All ORM models inherit from `Base`. Import every model at the bottom so
Base.metadata is fully populated when Alembic introspects it.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# Import every ORM model below so Alembic's autogenerate sees them.
# Each phase adds its models here.
from app.db.models import (  # noqa: E402, F401
    audit_log,
    conversations,
    memory_long,
    messages,
    users,
    widgets,
)
