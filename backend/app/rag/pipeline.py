"""RAG pipeline — Phase 3.3 (D-019, D-020).

The RAGPipeline wires together all retrieval components:
  - Dense pgvector search (app/rag/retriever.py)
  - BM25 sparse search (app/rag/bm25_index.py)
  - RRF hybrid fusion (app/rag/hybrid_retriever.py)
  - HyDE query transformation (app/rag/query_transform.py)
  - Cross-encoder reranker (app/rag/reranker.py)

Three-stream HyDE augment pattern (D-019):
  Stream A: dense(original_query)
  Stream B: dense(hyde_passage)     — closer embedding to relevant passages
  Stream C: BM25(original_query)    — exact keyword matching

All three streams are fused with RRF (k=60) into a single ranked list.
Reranking is off by default due to D-018 domain-mismatch finding.

Metadata filter (D-020): callers can restrict to "docs", "issues", or "all".

ChunkResult is the typed output contract for Phase 4 chatbot tool calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.bm25_index import SourceFilter, get_store
from app.rag.embedder import embed_query
from app.rag.hybrid_retriever import _rrf_fuse  # noqa: PLC2701
from app.rag.query_transform import hyde_transform
from app.rag.reranker import rerank as rerank_chunks
from app.rag.retriever import MAX_POOL_K, dense_search

logger = logging.getLogger(__name__)

SourceFilterLiteral = Literal["docs", "issues", "all"]


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


@dataclass
class ChunkResult:
    """A single retrieved chunk returned by the RAG pipeline.

    This is the typed contract between the retrieval layer and the Phase 4
    chatbot tool layer.  Adding or removing fields here is a breaking change
    for tool callers.
    """

    chunk_id: str
    source_type: str
    source_id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    rerank_score: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> ChunkResult:
        return cls(
            chunk_id=str(d.get("chunk_id", "")),
            source_type=str(d.get("source_type", "")),
            source_id=str(d.get("source_id", "")),
            text=str(d.get("text", "")),
            metadata=dict(d.get("metadata", {})),  # type: ignore[call-overload]
            rerank_score=float(d["rerank_score"]) if d.get("rerank_score") is not None else None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class RAGPipeline:
    """Full retrieval pipeline.

    Args:
        session: async SQLAlchemy session (for dense pgvector search).
        anthropic_client: caller-provided AsyncAnthropic (Vault-keyed).
        top_k: number of results to return.
        pool_k: candidates pulled from each retriever before fusion.
        source_filter: "docs", "issues", or "all".
        use_hyde: whether to add a HyDE stream.
        use_rerank: whether to apply cross-encoder reranking (default False —
            D-018 shows ms-marco hurts on this corpus).
        hyde_model: model used for HyDE passage generation.
    """

    def __init__(
        self,
        session: AsyncSession,
        anthropic_client: AsyncAnthropic,
        top_k: int = 5,
        pool_k: int = 50,
        source_filter: SourceFilterLiteral = "all",
        use_hyde: bool = True,
        use_rerank: bool = False,
        hyde_model: str = "claude-haiku-4-5",
    ) -> None:
        self._session = session
        self._client = anthropic_client
        self._top_k = top_k
        self._pool_k = min(pool_k, MAX_POOL_K)
        self._source_filter: SourceFilter = source_filter
        self._use_hyde = use_hyde
        self._use_rerank = use_rerank
        self._hyde_model = hyde_model

    async def run(self, query: str) -> list[ChunkResult]:
        """Run the full pipeline and return top_k ChunkResult objects."""
        # --- Determine source_type param for pgvector filter ---
        source_type_param: str | None = None
        if self._source_filter == "docs":
            source_type_param = "doc"
        elif self._source_filter == "issues":
            source_type_param = "issue"

        # --- Stream A: dense(original) ---
        dense_a = await dense_search(
            self._session, query, k=self._pool_k, source_type=source_type_param
        )
        ids_a = [str(r["chunk_id"]) for r in dense_a]
        chunk_map: dict[str, dict[str, object]] = {str(r["chunk_id"]): r for r in dense_a}

        streams: list[list[str]] = [ids_a]

        # --- Stream B: dense(HyDE) ---
        if self._use_hyde:
            try:
                hyde_passage = await hyde_transform(query, self._client, self._hyde_model)
                q_emb_hyde = embed_query(hyde_passage)

                # Build raw SQL via retriever pattern
                from sqlalchemy import text as sql_text

                vec_str = "[" + ",".join(f"{float(x):.8f}" for x in q_emb_hyde) + "]"
                where = "WHERE source_type = :source_type" if source_type_param else ""
                sql = sql_text(
                    f"""
                    SELECT chunk_id, source_type, source_id, text, metadata,
                           1.0 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM   rag_chunks {where}
                    ORDER  BY embedding <=> CAST(:embedding AS vector)
                    LIMIT  :k
                    """
                )
                params: dict[str, object] = {"embedding": vec_str, "k": self._pool_k}
                if source_type_param:
                    params["source_type"] = source_type_param
                result = await self._session.execute(sql, params)
                dense_b = [dict(row._mapping) for row in result.fetchall()]

                ids_b = [str(r["chunk_id"]) for r in dense_b]
                for r in dense_b:
                    cid = str(r["chunk_id"])
                    if cid not in chunk_map:
                        chunk_map[cid] = r
                streams.append(ids_b)
                logger.debug("HyDE stream: %d candidates", len(ids_b))
            except Exception:
                logger.warning("HyDE transform failed, skipping stream B", exc_info=True)

        # --- Stream C: BM25(original) ---
        store = get_store()
        bm25_idx = store.get(self._source_filter)
        bm25_pairs = bm25_idx.search(query, k=self._pool_k)
        ids_c_raw: list[str] = []
        for bm25_chunk, _ in bm25_pairs:
            cid = str(bm25_chunk["chunk_id"])
            ids_c_raw.append(cid)
            if cid not in chunk_map:
                chunk_map[cid] = bm25_chunk
        streams.append(ids_c_raw)

        # --- RRF fusion ---
        fused_ids = _rrf_fuse(streams, chunk_map, k=self._pool_k)
        candidates = [chunk_map[str(c["chunk_id"])] for c in fused_ids if "chunk_id" in c]

        # --- Optional reranking ---
        if self._use_rerank and candidates:
            candidates = rerank_chunks(query, candidates, top_k=self._top_k)
        else:
            candidates = candidates[: self._top_k]

        return [ChunkResult.from_dict(c) for c in candidates]


def build_pipeline(
    session: AsyncSession,
    anthropic_client: AsyncAnthropic,
    top_k: int = 5,
    source_filter: SourceFilterLiteral = "all",
    use_hyde: bool = True,
    use_rerank: bool = False,
) -> RAGPipeline:
    """Factory used by service layer to construct a pipeline."""
    return RAGPipeline(
        session=session,
        anthropic_client=anthropic_client,
        top_k=top_k,
        source_filter=source_filter,
        use_hyde=use_hyde,
        use_rerank=use_rerank,
    )
