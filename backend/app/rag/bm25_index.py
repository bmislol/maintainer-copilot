"""In-memory BM25 indexes for sparse retrieval — Phase 3.3.

Three separate indexes are maintained so callers can filter by source_type
without re-ranking a merged list:
  - "docs"   — doc chunks only
  - "issues" — issue chunks only
  - "all"    — combined (docs + issues)

The indexes are built at application startup (or on first use) by loading
all rows from rag_chunks.  On a 9 700-chunk corpus this takes ~0.5 s and
occupies ~50 MB RAM — acceptable for a single-tenant tool (D-017).

Tokenisation: whitespace split + lower-case.  BM25Okapi is parameter-free
for k1/b defaults (k1=1.5, b=0.75) which are the standard values.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

import psycopg2
from pgvector.psycopg2 import register_vector
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

SourceFilter = Literal["docs", "issues", "all"]

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-\.]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class BM25Index:
    """Wrapper around BM25Okapi that also stores the original chunk rows."""

    bm25: BM25Okapi
    chunks: list[dict[str, object]]

    def search(self, query: str, k: int) -> list[tuple[dict[str, object], float]]:
        """Return top-k (chunk, score) pairs sorted descending by BM25 score."""
        tokens = tokenize(query)
        scores: list[float] = self.bm25.get_scores(tokens).tolist()
        ranked = sorted(
            zip(self.chunks, scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return ranked[:k]


@dataclass
class BM25Store:
    """Holds three BM25Index instances keyed by source filter."""

    indexes: dict[SourceFilter, BM25Index] = field(default_factory=dict)

    def get(self, source_filter: SourceFilter) -> BM25Index:
        return self.indexes[source_filter]

    def ready(self) -> bool:
        return bool(self.indexes)


# Module-level singleton populated by build_indexes() at startup.
_store: BM25Store = BM25Store()


def build_indexes(db_url: str) -> None:
    """Load all chunks from rag_chunks and build the three BM25 indexes.

    Called once at API startup (see app/core/lifespan.py).  Uses the sync
    psycopg2 driver so the startup hook can run outside an async context.
    """
    conn = psycopg2.connect(db_url)
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id, source_type, source_id, text, metadata FROM rag_chunks ORDER BY chunk_id"
    )
    rows = cur.fetchall()
    conn.close()

    all_chunks: list[dict[str, object]] = [
        {
            "chunk_id": r[0],
            "source_type": r[1],
            "source_id": r[2],
            "text": r[3],
            "metadata": r[4],
        }
        for r in rows
    ]

    doc_chunks = [c for c in all_chunks if c["source_type"] == "doc"]
    issue_chunks = [c for c in all_chunks if c["source_type"] == "issue"]

    def _make_index(chunks: list[dict[str, object]]) -> BM25Index:
        corpus = [tokenize(str(c["text"])) for c in chunks]
        return BM25Index(bm25=BM25Okapi(corpus), chunks=chunks)

    _store.indexes["docs"] = _make_index(doc_chunks)
    _store.indexes["issues"] = _make_index(issue_chunks)
    _store.indexes["all"] = _make_index(all_chunks)

    logger.info(
        "BM25 indexes built: docs=%d issues=%d all=%d",
        len(doc_chunks),
        len(issue_chunks),
        len(all_chunks),
    )


def get_store() -> BM25Store:
    """Return the module-level BM25Store (must have been built first)."""
    if not _store.ready():
        raise RuntimeError("BM25 indexes not yet built — call build_indexes() at startup")
    return _store
