"""Phase 3.2 baseline retrieval benchmark — same 18 queries as Phase 3.1.

Queries the live rag_chunks table via pgvector cosine similarity and
measures hit@1 and hit@5.  These numbers are the D-016 anchor that
Phase 3.3 (BM25 + rerank) must beat.

The 18 queries are copied verbatim from scripts/benchmark_embeddings.py
(Phase 3.1) to ensure apples-to-apples comparison.  The relevant keys
use the same format: "doc:{file_id}" and "issue:{number}".

Run from backend/:
    DATABASE_URL=postgresql://copilot:copilot@localhost:5432/copilot \\
        uv run python scripts/benchmark_retrieval.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2  # type: ignore[import-untyped]
from pgvector.psycopg2 import register_vector  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.embedder import embed_query

# ---------------------------------------------------------------------------
# Ground-truth proxy set — verbatim from scripts/benchmark_embeddings.py
# ---------------------------------------------------------------------------
QUERIES: list[tuple[str, list[str]]] = [
    # --- Documentation queries (9) ---
    (
        "How do I prevent data leakage when applying preprocessing inside cross-validation?",
        ["doc:common_pitfalls", "doc:modules__cross_validation", "doc:modules__compose"],
    ),
    (
        "What are the steps to implement a custom transformer compatible with sklearn Pipeline?",
        ["doc:modules__compose", "doc:developers__develop"],
    ),
    (
        "How does StandardScaler handle features with zero variance?",
        ["doc:modules__preprocessing"],
    ),
    (
        "How do I tune hyperparameters with GridSearchCV and cross-validation?",
        ["doc:modules__grid_search", "doc:modules__cross_validation"],
    ),
    (
        "What metrics are available for evaluating multi-label classifiers?",
        ["doc:modules__model_evaluation"],
    ),
    (
        "How does SelectKBest feature selection work and which score functions are available?",
        ["doc:modules__feature_selection"],
    ),
    (
        "How can I speed up sklearn predictions for large datasets?",
        ["doc:computing__computational_performance"],
    ),
    (
        "What is the difference between PCA and TruncatedSVD for dimensionality reduction?",
        ["doc:modules__decomposition"],
    ),
    (
        "How do I contribute a new estimator to scikit-learn?",
        ["doc:developers__contributing", "doc:developers__develop"],
    ),
    # --- Issue queries (9) ---
    (
        "LabelEncoder raises AttributeError about set_output after fitting",
        ["issue:26711"],
    ),
    (
        "RandomForest split criterion documentation is confusing or incorrect",
        ["issue:27159"],
    ),
    (
        "LogisticRegression hangs or freezes when input has very large feature values",
        ["issue:7486"],
    ),
    (
        "VotingClassifier should support prefit estimators without refitting",
        ["issue:7382"],
    ),
    (
        "OneVsOneClassifier decision_function returns unexpected shape",
        ["issue:8049"],
    ),
    (
        "check_estimator fails after calling set_output on a transformer",
        ["issue:26842"],
    ),
    (
        "Request to add progress bar support to long-running sklearn estimators",
        ["issue:7574"],
    ),
    (
        "How to change which class is treated as positive in binary classification metrics?",
        ["issue:26758"],
    ),
    (
        "RFC or discussion on freezing fitted estimators to prevent accidental mutation",
        ["issue:8370"],
    ),
]


def _db_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL env var not set.\n"
            "Example: DATABASE_URL=postgresql://copilot:copilot@localhost:5432/copilot "
            "uv run python scripts/benchmark_retrieval.py"
        )
    return url


def search(
    cur: psycopg2.cursor,
    q_emb: np.ndarray,  # type: ignore[type-arg]
    k: int,
) -> list[tuple[str, str]]:
    """Return top-k (source_type, source_id) pairs by cosine similarity."""
    # pgvector requires a vector literal '[x, y, ...]' for the <=> operator.
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in q_emb) + "]"
    cur.execute(
        """
        SELECT source_type, source_id
        FROM   rag_chunks
        ORDER  BY embedding <=> %s::vector
        LIMIT  %s
        """,
        (vec_str, k),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def main() -> None:
    url = _db_url()
    conn = psycopg2.connect(url)
    register_vector(conn)
    cur = conn.cursor()

    # Check corpus is indexed
    cur.execute("SELECT COUNT(*) FROM rag_chunks")
    total_chunks: int = cur.fetchone()[0]  # type: ignore[index]
    if total_chunks == 0:
        conn.close()
        raise SystemExit("rag_chunks is empty — run scripts/index_corpus.py first")

    print(f"rag_chunks rows : {total_chunks}")
    print(f"Queries         : {len(QUERIES)}")
    print()

    h1_hits = 0
    h5_hits = 0
    per_query = []

    t0 = time.time()
    for query, relevant in QUERIES:
        q_emb = embed_query(query)

        top1 = search(cur, q_emb, 1)
        top5 = search(cur, q_emb, 5)

        top1_keys = {f"{st}:{sid}" for st, sid in top1}
        top5_keys = {f"{st}:{sid}" for st, sid in top5}

        h1 = bool(top1_keys & set(relevant))
        h5 = bool(top5_keys & set(relevant))
        h1_hits += int(h1)
        h5_hits += int(h5)

        per_query.append(
            {
                "query": query[:60],
                "relevant": relevant,
                "hit@1": h1,
                "hit@5": h5,
            }
        )

    elapsed = time.time() - t0
    n = len(QUERIES)

    conn.close()

    print(f"{'=' * 60}")
    print("PHASE 3.2 BASELINE RETRIEVAL RESULTS")
    print(f"{'=' * 60}")
    print(f"  hit@1 : {h1_hits / n:.2%}  ({h1_hits}/{n})")
    print(f"  hit@5 : {h5_hits / n:.2%}  ({h5_hits}/{n})")
    print(f"  time  : {elapsed:.1f}s  ({n} queries x 2 searches each)")
    print()
    print("  Per-query breakdown:")
    for pq in per_query:
        m1 = "✓" if pq["hit@1"] else " "
        m5 = "✓" if pq["hit@5"] else " "
        print(f"    [@1{m1}][@5{m5}] {pq['query'][:55]}")

    # Write results JSON alongside the Phase 3.1 benchmark results.
    out = Path("benchmark_retrieval_results.json")
    out.write_text(
        json.dumps(
            {
                "phase": "3.2-baseline",
                "corpus_chunks": total_chunks,
                "n_queries": n,
                "hit_at_1": round(h1_hits / n, 4),
                "hit_at_5": round(h5_hits / n, 4),
                "per_query": per_query,
            },
            indent=2,
        )
    )
    print(f"\nResults written to {out.resolve()}")


if __name__ == "__main__":
    main()
