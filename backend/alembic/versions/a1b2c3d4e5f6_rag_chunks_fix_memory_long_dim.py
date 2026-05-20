"""rag_chunks table + fix memory_long embedding dim 1536 → 384

D-015 locked all-MiniLM-L6-v2 (384-dim). The baseline migration used 1536
as a placeholder. This migration corrects the column and adds the rag_chunks
table with HNSW index for Phase 3.2 dense retrieval.

Revision ID: a1b2c3d4e5f6
Revises: 283526252229
Create Date: 2026-05-20 00:00:00.000000

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "283526252229"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Fix memory_long.embedding: placeholder dim 1536 → 384 (D-015).
    # Safe in dev — no production data at this stage.
    op.drop_column("memory_long", "embedding")
    op.add_column(
        "memory_long",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(384),
            nullable=False,
        ),
    )

    # Create rag_chunks table.
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.Column("n_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", name="uq_rag_chunks_chunk_id"),
    )

    # Composite btree index for source lookups (source_type + source_id → all chunks of a doc/issue).
    op.create_index("ix_rag_chunks_source", "rag_chunks", ["source_type", "source_id"])

    # GIN index on metadata JSONB for Phase 3.3 metadata filtering.
    op.execute("CREATE INDEX ix_rag_chunks_metadata ON rag_chunks USING gin (metadata)")

    # HNSW index for approximate nearest-neighbor cosine search.
    # m=16 and ef_construction=64 are pgvector defaults — sufficient for the
    # ~15 k-chunk corpus expected after Phase 3.2 indexing. Tunable in Phase
    # 3.4 if recall@5 falls short on the golden set.
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding_hnsw ON rag_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("rag_chunks")

    # Restore memory_long.embedding to placeholder dim 1536.
    op.drop_column("memory_long", "embedding")
    op.add_column(
        "memory_long",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1536),
            nullable=False,
        ),
    )
