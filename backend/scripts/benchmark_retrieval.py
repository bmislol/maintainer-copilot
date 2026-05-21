"""Retrieval benchmark — Phase 3.2 baseline + Phase 3.3 hybrid comparison.

Measures hit@1, hit@5, MRR@10, and recall@10 for:
  - dense  : pgvector cosine similarity only (Phase 3.2 anchor — D-016)
  - hybrid : dense + BM25 RRF fusion (Phase 3.3 — D-017)

The 18 queries are copied verbatim from scripts/benchmark_embeddings.py
(Phase 3.1) to ensure apples-to-apples comparison.

Run from backend/:
    DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot \\
        uv run python scripts/benchmark_retrieval.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.bm25_index import tokenize
from app.rag.embedder import embed_query
from app.rag.hybrid_retriever import RRF_K

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
            "Example: DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot "
            "uv run python scripts/benchmark_retrieval.py"
        )
    return url


def dense_search(
    cur: Any,
    q_emb: np.ndarray[Any, Any],
    k: int,
) -> list[str]:
    """Return top-k chunk_ids by cosine similarity."""
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in q_emb) + "]"
    cur.execute(
        """
        SELECT source_type || ':' || source_id AS key
        FROM   rag_chunks
        ORDER  BY embedding <=> %s::vector
        LIMIT  %s
        """,
        (vec_str, k),
    )
    return [row[0] for row in cur.fetchall()]


def _load_bm25_indexes(
    cur: Any,
) -> dict[str, tuple[BM25Okapi, list[str]]]:
    """Load all chunks and build three BM25 indexes; return (bm25, keys) per filter."""
    cur.execute("SELECT source_type, source_id, text FROM rag_chunks ORDER BY chunk_id")
    rows = cur.fetchall()

    def _make(subset: list[tuple[str, str, str]]) -> tuple[BM25Okapi, list[str]]:
        keys = [f"{r[0]}:{r[1]}" for r in subset]
        corpus = [tokenize(r[2]) for r in subset]
        return BM25Okapi(corpus), keys

    all_rows = rows
    doc_rows = [r for r in rows if r[0] == "doc"]
    issue_rows = [r for r in rows if r[0] == "issue"]

    return {
        "all": _make(all_rows),
        "docs": _make(doc_rows),
        "issues": _make(issue_rows),
    }


def bm25_search(
    bm25: BM25Okapi,
    keys: list[str],
    query: str,
    k: int,
) -> list[str]:
    """Return top-k source keys by BM25 score."""
    tokens = tokenize(query)
    scores: list[float] = bm25.get_scores(tokens).tolist()
    ranked = sorted(range(len(keys)), key=lambda i: scores[i], reverse=True)
    return [keys[i] for i in ranked[:k]]


def rrf_fuse(ranked_lists: list[list[str]], k: int) -> list[str]:
    """Fuse ranked lists with RRF (k=60) and return top-k keys."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (rank + RRF_K)
    return sorted(scores, key=lambda x: scores[x], reverse=True)[:k]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _hit(top_keys: list[str], relevant: list[str]) -> bool:
    return bool(set(top_keys) & set(relevant))


def _mrr(top_keys: list[str], relevant: list[str]) -> float:
    rel_set = set(relevant)
    for rank, key in enumerate(top_keys, start=1):
        if key in rel_set:
            return 1.0 / rank
    return 0.0


def _recall(top_keys: list[str], relevant: list[str]) -> float:
    if not relevant:
        return 0.0
    return len(set(top_keys) & set(relevant)) / len(relevant)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(
    cur: Any,
    bm25_indexes: dict[str, tuple[BM25Okapi, list[str]]],
    mode: str,
) -> dict[str, Any]:
    """Run all 18 queries for a given mode ('dense' or 'hybrid').

    Returns a dict with aggregated metrics and per-query breakdown.
    """
    pool_k = 50

    h1 = h5 = mrr10_sum = rec10_sum = 0.0
    per_query = []

    t0 = time.time()
    for query, relevant in QUERIES:
        q_emb = embed_query(query)
        dense_ids = dense_search(cur, q_emb, k=pool_k)

        if mode == "dense":
            top10 = dense_ids[:10]
            top5 = dense_ids[:5]
            top1 = dense_ids[:1]
        else:
            bm25_bm, bm25_keys = bm25_indexes["all"]
            bm25_ids = bm25_search(bm25_bm, bm25_keys, query, k=pool_k)
            fused = rrf_fuse([dense_ids, bm25_ids], k=10)
            top10 = fused
            top5 = fused[:5]
            top1 = fused[:1]

        hit1 = _hit(top1, relevant)
        hit5 = _hit(top5, relevant)
        mrr = _mrr(top10, relevant)
        rec = _recall(top10, relevant)

        h1 += hit1
        h5 += hit5
        mrr10_sum += mrr
        rec10_sum += rec

        per_query.append(
            {
                "query": query[:60],
                "relevant": relevant,
                "hit@1": hit1,
                "hit@5": hit5,
                "mrr@10": round(mrr, 4),
                "recall@10": round(rec, 4),
            }
        )

    elapsed = time.time() - t0
    n = len(QUERIES)
    return {
        "mode": mode,
        "n_queries": n,
        "hit_at_1": round(h1 / n, 4),
        "hit_at_5": round(h5 / n, 4),
        "mrr_at_10": round(mrr10_sum / n, 4),
        "recall_at_10": round(rec10_sum / n, 4),
        "elapsed_s": round(elapsed, 1),
        "per_query": per_query,
    }


def _print_results(res: dict[str, Any]) -> None:
    n: int = res["n_queries"]
    print(f"  Mode      : {res['mode']}")
    h1_count = round(float(res["hit_at_1"]) * n)
    print(f"  hit@1     : {res['hit_at_1']:.2%}  ({h1_count}/{n})")
    print(f"  hit@5     : {res['hit_at_5']:.2%}")
    print(f"  MRR@10    : {res['mrr_at_10']:.4f}")
    print(f"  recall@10 : {res['recall_at_10']:.2%}")
    print(f"  time      : {res['elapsed_s']}s")
    print()
    print("  Per-query breakdown:")
    for pq in res["per_query"]:
        m1 = "✓" if pq["hit@1"] else " "
        m5 = "✓" if pq["hit@5"] else " "
        print(f"    [@1{m1}][@5{m5}] {pq['query'][:55]}")


def main() -> None:
    url = _db_url()
    conn = psycopg2.connect(url)
    register_vector(conn)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM rag_chunks")
    row = cur.fetchone()
    total_chunks: int = row[0] if row else 0
    if total_chunks == 0:
        conn.close()
        raise SystemExit("rag_chunks is empty — run scripts/index_corpus.py first")

    print(f"rag_chunks rows : {total_chunks}")
    print(f"Queries         : {len(QUERIES)}")
    print()

    print("Loading BM25 indexes …")
    bm25_indexes = _load_bm25_indexes(cur)
    print(f"  docs={len(bm25_indexes['docs'][1])}  issues={len(bm25_indexes['issues'][1])}  all={len(bm25_indexes['all'][1])}")
    print()

    dense_res = run_benchmark(cur, bm25_indexes, mode="dense")
    hybrid_res = run_benchmark(cur, bm25_indexes, mode="hybrid")

    conn.close()

    sep = "=" * 60
    print(sep)
    print("DENSE BASELINE (Phase 3.2 anchor — D-016)")
    print(sep)
    _print_results(dense_res)

    print(sep)
    print("HYBRID RRF (Phase 3.3 — D-017)")
    print(sep)
    _print_results(hybrid_res)

    print(sep)
    print("DELTA (hybrid − dense)")
    print(sep)
    for metric in ("hit_at_1", "hit_at_5", "mrr_at_10", "recall_at_10"):
        delta = float(hybrid_res[metric]) - float(dense_res[metric])
        sign = "+" if delta >= 0 else ""
        print(f"  {metric:<14}: {sign}{delta:+.4f}")

    out = Path("benchmark_retrieval_results.json")
    out.write_text(
        json.dumps(
            {
                "phase": "3.3-hybrid",
                "corpus_chunks": total_chunks,
                "dense": dense_res,
                "hybrid": hybrid_res,
            },
            indent=2,
        )
    )
    print(f"\nResults written to {out.resolve()}")


if __name__ == "__main__":
    main()
