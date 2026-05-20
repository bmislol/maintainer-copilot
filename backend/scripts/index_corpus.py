"""Index the RAG corpus into the rag_chunks table.

Reads data/rag_corpus/docs/ and data/rag_corpus/issues/, chunks each file
using structural chunking (app/rag/chunker.py), embeds with MiniLM-L6-v2,
and upserts into the rag_chunks table.

Re-running is idempotent: existing chunks are updated via ON CONFLICT.

Run from backend/:
    DATABASE_URL=postgresql://... uv run python scripts/index_corpus.py

Or with docker-compose postgres:
    DATABASE_URL=postgresql://copilot:copilot@localhost:5432/copilot \\
        uv run python scripts/index_corpus.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import psycopg2  # type: ignore[import-untyped]
from pgvector.psycopg2 import register_vector  # type: ignore[import-untyped]
from psycopg2.extras import execute_values  # type: ignore[import-untyped]

# Allow running from backend/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.chunker import Chunk, chunk_doc, chunk_issue
from app.rag.embedder import MODEL_NAME, embed_texts

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAG_DIR = BACKEND_DIR / "data" / "rag_corpus"
DOCS_DIR = RAG_DIR / "docs"
ISSUES_DIR = RAG_DIR / "issues"

BATCH_EMBED = 128  # embed this many texts at a time


def _db_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL env var not set.\n"
            "Example: DATABASE_URL=postgresql://copilot:copilot@localhost:5432/copilot "
            "uv run python scripts/index_corpus.py"
        )
    return url


def _load_chunks() -> list[Chunk]:
    """Load and chunk all corpus files."""
    chunks: list[Chunk] = []

    doc_files = sorted(DOCS_DIR.glob("*.json"))
    print(f"  chunking {len(doc_files)} docs …")
    for p in doc_files:
        doc = json.loads(p.read_text())
        chunks.extend(chunk_doc(doc))

    issue_files = sorted(ISSUES_DIR.glob("*.json"))
    print(f"  chunking {len(issue_files)} issues …")
    for p in issue_files:
        issue = json.loads(p.read_text())
        chunks.extend(chunk_issue(issue))

    return chunks


def _embed_chunks(chunks: list[Chunk]) -> np.ndarray:  # type: ignore[type-arg]
    """Embed all chunk texts, returning shape (N, 384)."""
    texts = [c.text for c in chunks]
    n = len(texts)
    print(f"  embedding {n} chunks with {MODEL_NAME} …")
    t0 = time.time()
    embeddings = embed_texts(texts, batch_size=BATCH_EMBED)
    print(f"  done in {time.time() - t0:.1f}s")
    return embeddings


def _upsert(conn: psycopg2.connection, chunks: list[Chunk], embeddings: np.ndarray) -> int:
    """Upsert chunks into rag_chunks. Returns number of rows affected."""
    rows = []
    for chunk, emb in zip(chunks, embeddings, strict=True):
        rows.append(
            (
                str(uuid.uuid4()),
                chunk.chunk_id,
                chunk.source_type,
                chunk.source_id,
                chunk.chunk_index,
                chunk.text,
                emb.tolist(),
                chunk.n_tokens,
                json.dumps(chunk.metadata),
            )
        )

    sql = """
        INSERT INTO rag_chunks
            (id, chunk_id, source_type, source_id, chunk_index,
             text, embedding, n_tokens, metadata)
        VALUES %s
        ON CONFLICT (chunk_id) DO UPDATE SET
            text       = EXCLUDED.text,
            embedding  = EXCLUDED.embedding,
            n_tokens   = EXCLUDED.n_tokens,
            metadata   = EXCLUDED.metadata
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, template=None, page_size=200)
    conn.commit()
    return len(rows)


def main() -> None:
    url = _db_url()

    print("Phase 3.2 — index_corpus.py")
    print(f"  corpus  : {RAG_DIR}")

    t_start = time.time()

    print("\n[1/3] Loading + chunking corpus …")
    chunks = _load_chunks()
    doc_chunks = sum(1 for c in chunks if c.source_type == "doc")
    issue_chunks = sum(1 for c in chunks if c.source_type == "issue")
    print(f"  total chunks: {len(chunks)}  (docs={doc_chunks}, issues={issue_chunks})")

    print("\n[2/3] Embedding …")
    embeddings = _embed_chunks(chunks)
    print(f"  embedding shape: {embeddings.shape}")

    print("\n[3/3] Upserting into DB …")
    conn = psycopg2.connect(url)
    register_vector(conn)
    n_upserted = _upsert(conn, chunks, embeddings)
    conn.close()
    print(f"  upserted {n_upserted} rows")

    elapsed = time.time() - t_start
    print(f"\n✓ indexing complete in {elapsed:.1f}s")
    print(f"  doc_chunks={doc_chunks}  issue_chunks={issue_chunks}  total={len(chunks)}")


if __name__ == "__main__":
    main()
