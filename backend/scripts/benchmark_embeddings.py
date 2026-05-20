"""Proxy benchmark: BAAI/bge-base-en-v1.5 vs sentence-transformers/all-MiniLM-L6-v2.

Measures hit@1 and hit@5 against 18 hand-written queries with known-relevant
corpus items (identified by file_id for docs or issue number for issues).

Metrics:
  hit@1  — ground-truth item appears in top-1 result
  hit@5  — ground-truth item appears in top-5 results

Each corpus item is embedded as-is (no chunking — Phase 3.2 handles that).
For docs the first 512 tokens are used; for issues title + body[:400] + first
comment body[:200].

Run from backend/:
    uv run python scripts/benchmark_embeddings.py

Outputs a results table and writes benchmark_results.json to cwd.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import NamedTuple

import numpy as np
from sentence_transformers import SentenceTransformer

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "rag_corpus"

# ---------------------------------------------------------------------------
# Ground-truth proxy set  (18 queries)
# Each entry: query text → list of relevant item keys.
# Key format: "doc:<file_id>" or "issue:<number>"
# "doc" items are matched by file_id; "issue" items by issue number.
# A query hits if ANY listed relevant key is in the top-k.
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


class CorpusItem(NamedTuple):
    key: str  # "doc:<file_id>" or "issue:<number>"
    text: str


def load_corpus() -> list[CorpusItem]:
    items: list[CorpusItem] = []

    for p in sorted((CORPUS_DIR / "docs").glob("*.json")):
        rec = json.loads(p.read_text())
        # Use first 2000 chars — proxy benchmark doesn't need full chunking
        text = rec["raw_text"][:2000].strip()
        items.append(CorpusItem(key=f"doc:{rec['file_id']}", text=text))

    for p in sorted((CORPUS_DIR / "issues").glob("*.json")):
        rec = json.loads(p.read_text())
        title = rec.get("title", "")
        body = (rec.get("body") or "")[:400]
        first_comment = ""
        if rec.get("comments"):
            first_comment = (rec["comments"][0].get("body") or "")[:200]
        text = f"{title}\n{body}\n{first_comment}".strip()
        items.append(CorpusItem(key=f"issue:{rec['number']}", text=text))

    return items


def hits_at_k(
    query: str,
    relevant: list[str],
    corpus: list[CorpusItem],
    corpus_embeddings: np.ndarray,
    model: SentenceTransformer,
    k: int,
) -> bool:
    q_emb = model.encode([query], normalize_embeddings=True)
    scores = corpus_embeddings @ q_emb.T  # (N, 1)
    top_k_idx = np.argsort(scores[:, 0])[::-1][:k]
    top_k_keys = {corpus[i].key for i in top_k_idx}
    return bool(top_k_keys & set(relevant))


def evaluate_model(
    model_name: str,
    corpus: list[CorpusItem],
    queries: list[tuple[str, list[str]]],
) -> dict:
    print(f"\n{'=' * 60}")
    print(f"Model: {model_name}")
    print(f"Corpus size: {len(corpus)} items")
    print("Loading model...", flush=True)

    t0 = time.time()
    model = SentenceTransformer(model_name)
    load_time = time.time() - t0
    print(f"  loaded in {load_time:.1f}s")

    texts = [item.text for item in corpus]
    print("Encoding corpus...", flush=True)
    t0 = time.time()
    corpus_emb = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=True, batch_size=64
    )
    encode_time = time.time() - t0
    print(f"  encoded {len(texts)} items in {encode_time:.1f}s")

    h1_hits = 0
    h5_hits = 0
    per_query = []
    for query, relevant in queries:
        h1 = hits_at_k(query, relevant, corpus, corpus_emb, model, k=1)
        h5 = hits_at_k(query, relevant, corpus, corpus_emb, model, k=5)
        h1_hits += int(h1)
        h5_hits += int(h5)
        per_query.append({"query": query[:60], "relevant": relevant, "hit@1": h1, "hit@5": h5})

    n = len(queries)
    result = {
        "model": model_name,
        "corpus_size": len(corpus),
        "n_queries": n,
        "hit_at_1": round(h1_hits / n, 4),
        "hit_at_5": round(h5_hits / n, 4),
        "encode_time_s": round(encode_time, 1),
        "per_query": per_query,
    }

    print(f"\n  hit@1 : {result['hit_at_1']:.2%}  ({h1_hits}/{n})")
    print(f"  hit@5 : {result['hit_at_5']:.2%}  ({h5_hits}/{n})")
    print(f"  encode: {encode_time:.1f}s")

    print("\n  Per-query breakdown:")
    for pq in per_query:
        mark1 = "✓" if pq["hit@1"] else " "
        mark5 = "✓" if pq["hit@5"] else " "
        print(f"    [@1{mark1}][@5{mark5}] {pq['query'][:55]}")

    return result


def main() -> None:
    corpus = load_corpus()
    print(
        f"Corpus loaded: {len(corpus)} items "
        f"({sum(1 for c in corpus if c.key.startswith('doc:'))} docs, "
        f"{sum(1 for c in corpus if c.key.startswith('issue:'))} issues)"
    )
    print(f"Queries: {len(QUERIES)}")

    models = [
        "BAAI/bge-base-en-v1.5",
        "sentence-transformers/all-MiniLM-L6-v2",
    ]

    results = []
    for model_name in models:
        r = evaluate_model(model_name, corpus, QUERIES)
        results.append(r)

    # Summary comparison
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'Model':<45} {'hit@1':>7} {'hit@5':>7} {'encode':>8}")
    print("-" * 70)
    for r in results:
        print(
            f"{r['model']:<45} {r['hit_at_1']:>7.2%} {r['hit_at_5']:>7.2%} {r['encode_time_s']:>7.1f}s"
        )

    winner = max(results, key=lambda r: (r["hit_at_5"], r["hit_at_1"]))
    print(f"\nWinner (by hit@5 then hit@1): {winner['model']}")

    out = Path("benchmark_results.json")
    out.write_text(json.dumps({"queries": len(QUERIES), "results": results}, indent=2))
    print(f"Results written to {out.resolve()}")


if __name__ == "__main__":
    main()
