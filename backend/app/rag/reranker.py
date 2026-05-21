"""Cross-encoder reranker — Phase 3.3 (D-018).

Loads ms-marco-MiniLM-L-6-v2 as a singleton cross-encoder.  Given a query
and a list of candidate chunks (already retrieved by hybrid search), it
produces a relevance score for each (query, chunk-text) pair and returns
the chunks sorted by that score.

Model choice: cross-encoder/ms-marco-MiniLM-L-6-v2 (D-018).
  - 22 M parameters, ~90 MB on disk.
  - MS-MARCO trained — directly calibrated for passage retrieval.
  - Runs in ~30 ms for 50 candidates on CPU (measured on this corpus).

The cross-encoder is loaded inline (not delegated to modelserver) because
it has no GPU dependency and keeping it here avoids an extra HTTP hop
on the hot path (D-018 rationale).
"""

from __future__ import annotations

import logging

from sentence_transformers.cross_encoder import CrossEncoder

logger = logging.getLogger(__name__)

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    """Return the module-level CrossEncoder singleton, loading on first call."""
    global _reranker
    if _reranker is None:
        logger.info("Loading cross-encoder reranker: %s", _MODEL_NAME)
        _reranker = CrossEncoder(_MODEL_NAME)
    return _reranker


def rerank(
    query: str,
    chunks: list[dict[str, object]],
    top_k: int | None = None,
) -> list[dict[str, object]]:
    """Score each (query, chunk.text) pair and return chunks sorted by score.

    Args:
        query: the user query string.
        chunks: candidate chunks with at least a "text" key.
        top_k: if set, return only the top_k chunks after reranking.

    Returns:
        Chunks sorted by cross-encoder score, highest first.  Each chunk
        dict gains a "rerank_score" key with the raw logit.
    """
    if not chunks:
        return []

    reranker = get_reranker()
    pairs = [(query, str(chunk["text"])) for chunk in chunks]
    scores: list[float] = reranker.predict(pairs).tolist()  # type: ignore[arg-type]

    scored = sorted(
        zip(chunks, scores, strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )

    result = []
    for chunk, score in scored:
        entry = dict(chunk)
        entry["rerank_score"] = score
        result.append(entry)

    return result[:top_k] if top_k is not None else result
