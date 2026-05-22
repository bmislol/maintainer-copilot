"""widgets: add owner_id, theme, greeting, enabled_tools

Revision ID: b3e9f1a2c4d5
Revises: 7e637234595f
Create Date: 2026-05-22

Phase 4.6 — widget config fields required for the admin UI and the
public /widgets/{id}/config endpoint.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3e9f1a2c4d5"
down_revision = "7e637234595f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "widgets",
        sa.Column(
            "owner_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,  # nullable so existing rows don't fail; backfilled below
        ),
    )
    op.add_column(
        "widgets",
        sa.Column("theme", sa.String(length=16), server_default="dark", nullable=False),
    )
    op.add_column(
        "widgets",
        sa.Column(
            "greeting",
            sa.Text(),
            server_default="Hello! How can I help?",
            nullable=False,
        ),
    )
    op.add_column(
        "widgets",
        sa.Column(
            "enabled_tools",
            sa.JSON(),
            server_default='["retrieve_docs"]',
            nullable=False,
        ),
    )
    # Create index on owner_id for the common "list my widgets" query.
    op.create_index("ix_widgets_owner_id", "widgets", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_widgets_owner_id", table_name="widgets")
    op.drop_column("widgets", "enabled_tools")
    op.drop_column("widgets", "greeting")
    op.drop_column("widgets", "theme")
    op.drop_column("widgets", "owner_id")
