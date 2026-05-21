"""auth: add fastapi-users columns to users

Revision ID: fc629b51e563
Revises: a1b2c3d4e5f6
Create Date: 2026-05-21 19:16:04.259121

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc629b51e563"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fastapi-users required columns to the users table.

    hashed_password, is_active, is_superuser, is_verified are all
    required by the fastapi-users SQLAlchemy adapter (SQLAlchemyUserDatabase).

    The unique constraint on email is replaced by a unique index
    (ix_users_email) — semantically equivalent; fastapi-users expects
    the indexed form so lookups use the index name.

    The HNSW index on rag_chunks.embedding is intentionally NOT touched
    here: it was created via a raw CREATE INDEX CONCURRENTLY in the
    previous migration and Alembic autogenerate incorrectly flagged it
    as removed. The index exists in the DB and must be preserved.
    """
    op.add_column("users", sa.Column("hashed_password", sa.String(length=1024), nullable=False))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False))
    op.add_column("users", sa.Column("is_superuser", sa.Boolean(), nullable=False))
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), nullable=False))
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    """Remove fastapi-users columns and restore original users schema."""
    op.drop_index("ix_users_email", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_active")
    op.drop_column("users", "hashed_password")
