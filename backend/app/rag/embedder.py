"""MiniLM-L6-v2 singleton embedder — 384-dim, selected in D-015.

Tied hit@5 (88.89%) with BAAI/bge-base-en-v1.5 on the Phase 3.1 proxy
benchmark while encoding 7.5× faster and producing 2× smaller vectors.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(
    texts: list[str], batch_size: int = 64
) -> np.ndarray[tuple[int, int], np.dtype[np.float32]]:
    """Return L2-normalized embeddings, shape (N, 384)."""
    model = get_model()
    result: np.ndarray[tuple[int, int], np.dtype[np.float32]] = model.encode(  # type: ignore[assignment]
        texts,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=False,
    )
    return result


def embed_query(query: str) -> np.ndarray[tuple[int], np.dtype[np.float32]]:
    """Return L2-normalized embedding for a single query, shape (384,)."""
    result: np.ndarray[tuple[int], np.dtype[np.float32]] = embed_texts([query])[0]
    return result
