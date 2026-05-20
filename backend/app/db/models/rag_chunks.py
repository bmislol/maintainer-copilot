"""RAG corpus chunks table — structural chunks with pgvector embeddings.

Populated by scripts/index_corpus.py (Phase 3.2).
Phase 3.3 adds BM25 + rerank on top of the dense search this table enables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Embedding dimension locked by D-015 (sentence-transformers/all-MiniLM-L6-v2).
_EMBED_DIM = 384


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Deterministic slug: "{source_type}:{source_id}:{chunk_index}"
    chunk_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "doc" | "issue"
    source_id: Mapped[str] = mapped_column(
        String(256), nullable=False
    )  # file_id for docs, str(number) for issues
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBED_DIM), nullable=False)
    n_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_rag_chunks_chunk_id"),
        Index("ix_rag_chunks_source", "source_type", "source_id"),
        # GIN index uses DB column name "metadata", not the Python attribute "metadata_".
        Index("ix_rag_chunks_metadata", "metadata", postgresql_using="gin"),
    )
