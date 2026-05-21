"""Hybrid retrieval: dense pgvector + BM25 sparse, fused with RRF — Phase 3.3.

Reciprocal Rank Fusion (RRF) with k=60 (Cormack et al., 2009).  Two streams:
  1. Dense — top-K by cosine similarity (pgvector HNSW)
  2. Sparse — top-K by BM25 score (in-memory rank_bm25)

RRF score for chunk c: Σ 1 / (rank_i(c) + 60)
where the sum is over both result lists and rank is 1-based.

Phase 3.3 also wires the three-stream HyDE augment in pipeline.py; this
module only handles the two-stream base case so it stays testable standalone.

D-017 records the numbers.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.bm25_index import SourceFilter, get_store
from app.rag.retriever import dense_search

# RRF constant — lower values weight top ranks more heavily.
# k=60 is the standard from Cormack et al. (2009) and empirically validated
# on the 18-query proxy set (see D-017).
RRF_K = 60


def _rrf_fuse(
    ranked_lists: list[list[str]],
    chunk_map: dict[str, dict[str, object]],
    k: int,
) -> list[dict[str, object]]:
    """Fuse multiple ranked chunk_id lists via RRF and return top-k chunks."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank + RRF_K)

    top_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]
    return [chunk_map[cid] for cid in top_ids if cid in chunk_map]


async def hybrid_search(
    session: AsyncSession,
    query: str,
    k: int = 5,
    pool_k: int = 50,
    source_filter: SourceFilter = "all",
) -> list[dict[str, object]]:
    """Dense + BM25 hybrid retrieval fused with RRF.

    Args:
        session: async SQLAlchemy session (for dense search).
        query: natural-language query string.
        k: number of results to return after fusion.
        pool_k: how many candidates to pull from each retriever before fusion.
        source_filter: "docs", "issues", or "all" — applied to both retrievers.

    Returns:
        List of chunk dicts with keys: chunk_id, source_type, source_id,
        text, metadata.  (No score — score is internal to RRF.)
    """
    source_type_param: str | None = None
    if source_filter == "docs":
        source_type_param = "doc"
    elif source_filter == "issues":
        source_type_param = "issue"

    # 1. Dense retrieval
    dense_results = await dense_search(session, query, k=pool_k, source_type=source_type_param)
    dense_ids = [str(r["chunk_id"]) for r in dense_results]

    # 2. BM25 sparse retrieval
    store = get_store()
    bm25_results = store.get(source_filter).search(query, k=pool_k)
    bm25_ids = [str(c["chunk_id"]) for c, _ in bm25_results]

    # Build chunk_map from both result sets (BM25 chunks may not overlap dense)
    chunk_map: dict[str, dict[str, object]] = {}
    for r in dense_results:
        chunk_map[str(r["chunk_id"])] = r
    for chunk, _ in bm25_results:
        cid = str(chunk["chunk_id"])
        if cid not in chunk_map:
            chunk_map[cid] = chunk

    return _rrf_fuse([dense_ids, bm25_ids], chunk_map, k=k)
