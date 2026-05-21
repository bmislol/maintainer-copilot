"""Retrieval benchmark — Phase 3.2 baseline + Phase 3.3 full comparison.

Measures hit@1, hit@5, MRR@10, and recall@10 for:
  - dense    : pgvector cosine similarity only (Phase 3.2 anchor — D-016)
  - hybrid   : dense + BM25 RRF fusion (Phase 3.3 — D-017)
  - reranked : hybrid + cross-encoder rerank (Phase 3.3 — D-018)
  - hyde     : dense(query) + dense(hyde_passage) + BM25(query) → RRF (D-019)

The 18 queries are copied verbatim from scripts/benchmark_embeddings.py
(Phase 3.1) to ensure apples-to-apples comparison.

Run from backend/:
    DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot \\
    ANTHROPIC_API_KEY=sk-ant-... \\
        uv run python scripts/benchmark_retrieval.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import psycopg2
from anthropic import Anthropic
from anthropic.types import TextBlock
from pgvector.psycopg2 import register_vector
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.bm25_index import tokenize
from app.rag.embedder import embed_query
from app.rag.hybrid_retriever import RRF_K
from app.rag.reranker import rerank as rerank_chunks

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


def _load_eval_file(path: Path) -> list[tuple[str, list[str]]]:
    """Load a JSONL golden-set file into (query, [source_key]) pairs.

    ground_truth_chunk_id format: "source_type:source_id:chunk_index".
    We strip the chunk index to get the source_key for hit/MRR matching.
    """
    queries: list[tuple[str, list[str]]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row: dict[str, str] = json.loads(line)
        question = row["question"]
        chunk_id = row["ground_truth_chunk_id"]
        # "doc:common_pitfalls:8" → "doc:common_pitfalls"
        source_key = chunk_id.rsplit(":", 1)[0]
        queries.append((question, [source_key]))
    return queries


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
) -> list[tuple[str, str]]:
    """Return top-k (source_key, text) pairs by cosine similarity.

    source_key has format 'source_type:source_id'.
    Multiple rows for the same source_key may be returned (one per chunk).
    """
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in q_emb) + "]"
    cur.execute(
        """
        SELECT source_type || ':' || source_id AS key, text
        FROM   rag_chunks
        ORDER  BY embedding <=> %s::vector
        LIMIT  %s
        """,
        (vec_str, k),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


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
# HyDE helper (sync wrapper for benchmark use)
# ---------------------------------------------------------------------------

_HYDE_SYSTEM = (
    "You are an expert on scikit-learn.  "
    "Write a short passage (3–6 sentences) that would appear in documentation "
    "or a GitHub issue and directly answers the user's question.  "
    "Do not add headings or bullet points — plain prose only."
)


def hyde_passage_sync(query: str, client: Anthropic) -> str:
    """Generate a hypothetical passage for the query (synchronous)."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_HYDE_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    texts = [b.text for b in response.content if isinstance(b, TextBlock)]
    return texts[0] if texts else ""


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _fetch_chunks_by_key(cur: Any, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch one representative chunk per source_type:source_id key.

    Uses chunk_index=0 (body/first-section) as the representative chunk.
    This gives the reranker exactly one candidate per source — same cardinality
    as the fused list — so it ranks sources rather than chunks.
    """
    if not keys:
        return {}
    cur.execute(
        """
        SELECT DISTINCT ON (source_type, source_id)
               source_type, source_id, text
        FROM   rag_chunks
        WHERE  source_type || ':' || source_id = ANY(%s)
        ORDER  BY source_type, source_id, chunk_index ASC
        """,
        (keys,),
    )
    return {
        f"{row[0]}:{row[1]}": {"source_type": row[0], "source_id": row[1], "text": row[2]}
        for row in cur.fetchall()
    }


def run_benchmark(
    cur: Any,
    bm25_indexes: dict[str, tuple[BM25Okapi, list[str]]],
    mode: str,
    anthropic_client: Anthropic | None = None,
    queries: list[tuple[str, list[str]]] | None = None,
) -> dict[str, Any]:
    """Run queries for a given mode.

    mode: "dense" | "hybrid" | "reranked" | "hyde"
    anthropic_client: required for mode="hyde".
    queries: override the default 18-query proxy set (e.g. golden eval file).
    Returns a dict with aggregated metrics and per-query breakdown.
    """
    if mode == "hyde" and anthropic_client is None:
        raise ValueError("anthropic_client is required for mode='hyde'")
    _queries = queries if queries is not None else QUERIES
    pool_k = 50

    h1 = h5 = mrr10_sum = rec10_sum = 0.0
    per_query = []

    t0 = time.time()
    for query, relevant in _queries:
        q_emb = embed_query(query)
        dense_rows = dense_search(cur, q_emb, k=pool_k)

        # Full list with duplicates — used for RRF (duplicates boost the source score).
        dense_ids = [key for key, _ in dense_rows]

        # Best-text map: first (highest-ranked) chunk text per source for reranking.
        dense_key_text: dict[str, str] = {}
        for key, text in dense_rows:
            if key not in dense_key_text:
                dense_key_text[key] = text

        bm25_bm, bm25_keys = bm25_indexes["all"]
        bm25_ids = bm25_search(bm25_bm, bm25_keys, query, k=pool_k)

        if mode == "dense":
            top10 = dense_ids[:10]
        elif mode == "hybrid":
            fused = rrf_fuse([dense_ids, bm25_ids], k=pool_k)
            top10 = fused[:10]
        elif mode == "reranked":
            fused = rrf_fuse([dense_ids, bm25_ids], k=pool_k)
            # For sources not in dense results, fetch chunk_index=0 text.
            extra_keys = [k for k in fused if k not in dense_key_text]
            if extra_keys:
                extra_map = _fetch_chunks_by_key(cur, extra_keys)
                for k, v in extra_map.items():
                    dense_key_text[k] = str(v["text"])
            candidates: list[dict[str, object]] = [
                {
                    "source_type": k.split(":", 1)[0],
                    "source_id": k.split(":", 1)[1],
                    "text": dense_key_text[k],
                }
                for k in fused
                if k in dense_key_text
            ]
            reranked = rerank_chunks(query, candidates, top_k=10)
            top10 = [f"{c['source_type']}:{c['source_id']}" for c in reranked]
        elif mode == "hyde":
            # Three-stream: dense(query) + dense(hyde) + BM25(query) → RRF
            assert anthropic_client is not None  # guaranteed by pre-check
            hyde_text = hyde_passage_sync(query, anthropic_client)
            hyde_emb = embed_query(hyde_text)
            hyde_rows = dense_search(cur, hyde_emb, k=pool_k)
            hyde_ids = [key for key, _ in hyde_rows]
            # Update best-text map with HyDE results (don't overwrite existing)
            for key, text in hyde_rows:
                if key not in dense_key_text:
                    dense_key_text[key] = text
            fused = rrf_fuse([dense_ids, hyde_ids, bm25_ids], k=pool_k)
            top10 = fused[:10]
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

        top5 = top10[:5]
        top1 = top10[:1]

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
    n = len(_queries)
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


def _anthropic_client() -> Anthropic:
    import os

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit(
            "ANTHROPIC_API_KEY env var not set — required for HyDE mode.\n"
            "Example: ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/benchmark_retrieval.py"
        )
    return Anthropic(api_key=key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval benchmark")
    parser.add_argument(
        "--mode",
        choices=["dense", "hybrid", "reranked", "hyde"],
        default=None,
        help="Run a single mode only (default: run all four)",
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        default=None,
        dest="eval_file",
        help="Custom JSONL eval file (default: 18-query proxy set)",
    )
    args = parser.parse_args()

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

    queries: list[tuple[str, list[str]]] | None = None
    eval_label = "proxy-18"
    if args.eval_file is not None:
        queries = _load_eval_file(args.eval_file)
        eval_label = str(args.eval_file)

    n_queries = len(queries) if queries is not None else len(QUERIES)
    print(f"rag_chunks rows : {total_chunks}")
    print(f"Queries         : {n_queries}  ({eval_label})")
    print()

    print("Loading BM25 indexes …")
    bm25_indexes = _load_bm25_indexes(cur)
    print(
        f"  docs={len(bm25_indexes['docs'][1])}  issues={len(bm25_indexes['issues'][1])}  all={len(bm25_indexes['all'][1])}"
    )
    print()

    modes_to_run: list[str] = [args.mode] if args.mode else ["dense", "hybrid", "reranked", "hyde"]
    anthropic_client: Anthropic | None = None
    if "hyde" in modes_to_run:
        anthropic_client = _anthropic_client()

    all_results: dict[str, Any] = {}
    for mode in modes_to_run:
        if mode == "reranked":
            print("Warming up cross-encoder reranker …")
        elif mode == "hyde":
            print("Running HyDE augment benchmark (calls Anthropic API) …")
        res = run_benchmark(
            cur,
            bm25_indexes,
            mode=mode,
            anthropic_client=anthropic_client,
            queries=queries,
        )
        all_results[mode] = res

    conn.close()

    sep = "=" * 60
    mode_labels = {
        "dense": "DENSE BASELINE (Phase 3.2 anchor — D-016)",
        "hybrid": "HYBRID RRF (Phase 3.3 — D-017)",
        "reranked": "HYBRID + RERANK (Phase 3.3 — D-018)",
        "hyde": "HYBRID + HyDE 3-STREAM (Phase 3.3 — D-019)",
    }
    for mode in modes_to_run:
        print(sep)
        print(mode_labels[mode])
        print(sep)
        _print_results(all_results[mode])

    if len(modes_to_run) > 1:
        dense_res = all_results["dense"]
        print(sep)
        print("DELTA vs dense baseline")
        print(sep)
        other_modes = [m for m in modes_to_run if m != "dense"]
        header = f"  {'metric':<14}" + "".join(f"  {m:>10}" for m in other_modes)
        print(header)
        for metric in ("hit_at_1", "hit_at_5", "mrr_at_10", "recall_at_10"):
            row_str = f"  {metric:<14}"
            for m in other_modes:
                delta = float(all_results[m][metric]) - float(dense_res[metric])
                row_str += f"  {delta:>+10.4f}"
            print(row_str)

    out = Path("benchmark_retrieval_results.json")
    out.write_text(
        json.dumps(
            {
                "eval_label": eval_label,
                "corpus_chunks": total_chunks,
                **all_results,
            },
            indent=2,
        )
    )
    print(f"\nResults written to {out.resolve()}")


if __name__ == "__main__":
    main()
