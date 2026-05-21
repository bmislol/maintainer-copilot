"""memory_long: add memory_type column

Phase 4.3 — short/long-term memory.

memory_type stores the episodic/semantic/procedural classification.
Default 'episodic' because write_memory is explicit-only (user-stated
facts); semantic knowledge lives in the RAG corpus (D-024).

Revision ID: 7e637234595f
Revises: fc629b51e563
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7e637234595f"
down_revision: str | Sequence[str] | None = "fc629b51e563"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add memory_type VARCHAR(32) NOT NULL DEFAULT 'episodic'."""
    op.add_column(
        "memory_long",
        sa.Column(
            "memory_type",
            sa.String(length=32),
            nullable=False,
            server_default="episodic",
        ),
    )


def downgrade() -> None:
    """Remove memory_type column."""
    op.drop_column("memory_long", "memory_type")
