"""Naive dense retrieval via pgvector cosine similarity — Phase 3.2 baseline.

Phase 3.3 adds BM25 sparse retrieval, cross-encoder reranking, and query
transformation (HyDE or multi-query) on top of this function.

The returned hit@5 on the 18-query proxy set is the anchor number that
Phase 3.3 must beat (recorded in D-016).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embedder import embed_query

# Hard cap: never pull more than this many rows for reranking budget.
MAX_POOL_K = 100


async def dense_search(
    session: AsyncSession,
    query: str,
    k: int = 5,
    source_type: str | None = None,
) -> list[dict[str, object]]:
    """Return top-k chunks by cosine similarity.

    Args:
        session: async SQLAlchemy session.
        query: natural-language query string.
        k: number of results to return (capped at MAX_POOL_K).
        source_type: optional filter — "doc" or "issue".

    Returns:
        List of dicts with keys: chunk_id, source_type, source_id,
        text, metadata, score (1 − cosine_distance).
    """
    q_emb = embed_query(query)
    # pgvector expects a string literal like '[0.1, 0.2, ...]' for parameter binding.
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in q_emb) + "]"

    where_clause = "WHERE source_type = :source_type" if source_type else ""
    sql = text(
        f"""
        SELECT chunk_id,
               source_type,
               source_id,
               text,
               metadata,
               1.0 - (embedding <=> CAST(:embedding AS vector)) AS score
        FROM   rag_chunks
        {where_clause}
        ORDER  BY embedding <=> CAST(:embedding AS vector)
        LIMIT  :k
        """
    )

    params: dict[str, object] = {
        "embedding": vec_str,
        "k": min(k, MAX_POOL_K),
    }
    if source_type:
        params["source_type"] = source_type

    result = await session.execute(sql, params)
    return [dict(row._mapping) for row in result.fetchall()]
