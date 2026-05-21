"""Interactive curation tool for the RAG golden set — Phase 3.4.

Builds 25 (question, ground_truth_chunk_id, ground_truth_text) triples from
35 candidate questions.  The retrieval results are cached so the interactive
loop is purely local (no DB / API calls after Phase 1).

Phase 1 — cache retrieval:
  Creates a RAGPipeline(use_hyde=False, top_k=5) per question and stores
  the 5 candidates to data/eval/.curation_cache.json.  Skips questions
  already in cache.

Phase 2 — interactive curation:
  For each un-curated candidate (not already in eval_rag.jsonl, not
  skipped), shows the question and its 5 retrieved chunks.  Prompts:
    y        — accept top-1 chunk as ground truth
    1–5      — accept the Nth chunk instead
    s        — skip (bad question / all wrong)
    q        — quit (progress saved)

Output:
  data/eval/eval_rag.jsonl — one JSON object per line:
    {question_id, question, ground_truth_chunk_id, ground_truth_text,
     source_type, notes}
  question_id is q001–q025 (renumbered by accepted count).
  The original candidate ID (e.g. c017) is stored in `notes`.

Run from backend/:
    DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot \\
    ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY ../.env | cut -d= -f2-) \\
        uv run python scripts/curate_rag_golden_set.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# 35 candidate questions
# c001–c018: verbatim from benchmark_retrieval.py QUERIES list
# c019–c035: additional coverage questions
# ---------------------------------------------------------------------------
CANDIDATES: list[tuple[str, str]] = [
    # --- Documentation queries (c001–c009) ---
    ("c001", "How do I prevent data leakage when applying preprocessing inside cross-validation?"),
    (
        "c002",
        "What are the steps to implement a custom transformer compatible with sklearn Pipeline?",
    ),
    ("c003", "How does StandardScaler handle features with zero variance?"),
    ("c004", "How do I tune hyperparameters with GridSearchCV and cross-validation?"),
    ("c005", "What metrics are available for evaluating multi-label classifiers?"),
    (
        "c006",
        "How does SelectKBest feature selection work and which score functions are available?",
    ),
    ("c007", "How can I speed up sklearn predictions for large datasets?"),
    ("c008", "What is the difference between PCA and TruncatedSVD for dimensionality reduction?"),
    ("c009", "How do I contribute a new estimator to scikit-learn?"),
    # --- Issue queries (c010–c018) ---
    ("c010", "LabelEncoder raises AttributeError about set_output after fitting"),
    ("c011", "RandomForest split criterion documentation is confusing or incorrect"),
    ("c012", "LogisticRegression hangs or freezes when input has very large feature values"),
    ("c013", "VotingClassifier should support prefit estimators without refitting"),
    ("c014", "OneVsOneClassifier decision_function returns unexpected shape"),
    ("c015", "check_estimator fails after calling set_output on a transformer"),
    ("c016", "Request to add progress bar support to long-running sklearn estimators"),
    ("c017", "How to change which class is treated as positive in binary classification metrics?"),
    ("c018", "RFC or discussion on freezing fitted estimators to prevent accidental mutation"),
    # --- Additional documentation questions (c019–c025) ---
    ("c019", "How do I use Pipeline with ColumnTransformer to handle mixed-type features?"),
    (
        "c020",
        "What is the difference between fit_transform and calling fit then transform separately?",
    ),
    ("c021", "How does cross_val_score differ from cross_validate?"),
    ("c022", "What is the set_output API and how do I make my transformer return a DataFrame?"),
    ("c023", "How does StratifiedKFold handle imbalanced class distributions?"),
    ("c024", "What does the warm_start parameter do in ensemble estimators?"),
    ("c025", "What scoring functions can be passed to make_scorer?"),
    # --- Additional issue questions (c026–c035) ---
    ("c026", "Pipeline fit raises NotFittedError after set_params changes a step"),
    (
        "c027",
        "ColumnTransformer raises KeyError when column names change between fit and transform",
    ),
    ("c028", "GridSearchCV with refit=False still calls fit on the full dataset"),
    ("c029", "Sparse matrix input to StandardScaler raises TypeError about dense data"),
    ("c030", "Memory leak when calling fit repeatedly on a large dataset in a loop"),
    ("c031", "Add support for __sklearn_tags__ to improve compatibility checks"),
    ("c032", "Request: expose n_features_in_ on all transformers after fit"),
    ("c033", "What are the requirements for a scikit-learn estimator to pass check_estimator?"),
    ("c034", "How do I run only a subset of scikit-learn's test suite for a specific module?"),
    ("c035", "What is the process for deprecating a parameter in scikit-learn?"),
    # --- Additional doc questions — specific classes/functions (c036–c039) ---
    ("c036", "How does DBSCAN determine the eps parameter?"),
    ("c037", "What does the max_iter parameter control in LogisticRegression?"),
    ("c038", "How do I use FeatureUnion to combine multiple transformers?"),
    ("c039", "What is the purpose of the BaseEstimator and ClassifierMixin classes?"),
    # --- Additional doc questions — practical usage (c040–c042) ---
    ("c040", "How do I save and load a trained sklearn model?"),
    ("c041", "How does class_weight='balanced' work in classifiers?"),
    ("c042", "What is the difference between transform and fit_transform on test data?"),
    # --- Additional issue questions (c043–c045) ---
    ("c043", "MinMaxScaler produces NaN values when feature has zero range"),
    ("c044", "pickle.dumps fails on a Pipeline containing a lambda function"),
    ("c045", "HistGradientBoostingClassifier categorical_features parameter raises ValueError"),
    # --- Wildcards (c046–c047) ---
    ("c046", "How do I interpret the feature_importances_ attribute in tree-based models?"),
    (
        "c047",
        "Pipeline predict raises ValueError about input shape after adding a dimensionality reduction step",
    ),
    # --- Additional doc questions — specific API details (c048–c055) ---
    ("c048", "How does the n_jobs parameter affect parallel execution in sklearn estimators?"),
    ("c049", "What does the verbose parameter control in fitting methods?"),
    ("c050", "How do I use partial_fit for incremental/online learning?"),
    ("c051", "What is the clone function in sklearn.base and when should I use it?"),
    ("c052", "How does Pipeline handle the steps parameter and what names are valid?"),
    ("c053", "What does check_is_fitted do and when does it raise NotFittedError?"),
    ("c054", "How do I inspect feature importances from a RandomForestClassifier?"),
    ("c055", "What is the difference between predict_proba and decision_function?"),
    # --- Re-curation replacement for dropped c002 (c056) ---
    (
        "c056",
        "What base classes does a custom sklearn transformer need to inherit from, and what methods must it implement?",
    ),
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent.parent
_DATA_DIR = _BACKEND / "data" / "eval"
_CACHE_FILE = _DATA_DIR / ".curation_cache.json"
_EVAL_FILE = _DATA_DIR / "eval_rag.jsonl"
_SKIPPED_FILE = _DATA_DIR / ".rag_skipped.json"

TARGET = 25


# ---------------------------------------------------------------------------
# Phase 1 — async cache build
# ---------------------------------------------------------------------------


async def _build_cache() -> None:
    """Retrieve top-5 chunks per question (use_hyde=False) and cache to disk."""
    from anthropic import AsyncAnthropic
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.rag.bm25_index import build_indexes
    from app.rag.pipeline import RAGPipeline

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit(
            "DATABASE_URL not set.\n"
            "Example: DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot \\\n"
            "ANTHROPIC_API_KEY=... uv run python scripts/curate_rag_golden_set.py"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set.")

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    cache: dict[str, list[dict[str, Any]]] = {}
    if _CACHE_FILE.exists():
        cache = json.loads(_CACHE_FILE.read_text())

    missing = [cid for cid, _ in CANDIDATES if cid not in cache]
    if not missing:
        print(f"Cache complete — {len(cache)} questions cached.")
        return

    print(f"Building cache for {len(missing)} questions (use_hyde=False, top_k=5)…")

    # SQLAlchemy async engine (no tables needed — read-only)
    async_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)

    # BM25 indexes require a sync psycopg2 connection
    build_indexes(db_url)

    client = AsyncAnthropic(api_key=api_key)

    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        for cid, question in CANDIDATES:
            if cid in cache:
                continue
            pipeline = RAGPipeline(
                session=session,
                anthropic_client=client,
                top_k=5,
                source_filter="all",
                use_hyde=False,
                use_rerank=False,
            )
            try:
                results = await pipeline.run(question)
                cache[cid] = [
                    {
                        "chunk_id": r.chunk_id,
                        "source_type": r.source_type,
                        "source_id": r.source_id,
                        "text": r.text,
                        "metadata": r.metadata,
                    }
                    for r in results
                ]
                print(f"  {cid}: {len(results)} chunks retrieved")
            except Exception as exc:  # noqa: BLE001
                print(f"  {cid}: FAILED — {exc}")
                cache[cid] = []

            _CACHE_FILE.write_text(json.dumps(cache, indent=2))

    await engine.dispose()
    print(f"Cache written to {_CACHE_FILE}")


# ---------------------------------------------------------------------------
# Phase 2 — interactive curation loop
# ---------------------------------------------------------------------------


def _load_accepted() -> list[dict[str, Any]]:
    if not _EVAL_FILE.exists():
        return []
    return [json.loads(line) for line in _EVAL_FILE.read_text().splitlines() if line.strip()]


def _append_accepted(row: dict[str, Any]) -> None:
    with _EVAL_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _load_skipped() -> set[str]:
    if _SKIPPED_FILE.exists():
        return set(json.loads(_SKIPPED_FILE.read_text()))
    return set()


def _save_skipped(skipped: set[str]) -> None:
    _SKIPPED_FILE.write_text(json.dumps(sorted(skipped)))


def _fmt_chunk(rank: int, chunk: dict[str, Any]) -> str:
    source = f"{chunk['source_type']}:{chunk['source_id']}"
    text_preview = (chunk.get("text") or "").strip()[:300]
    text_preview = textwrap.indent(text_preview, "    ")
    return f"  [{rank}] {source}\n{text_preview}"


def _curate() -> None:
    cache: dict[str, list[dict[str, Any]]] = {}
    if _CACHE_FILE.exists():
        cache = json.loads(_CACHE_FILE.read_text())
    if not cache:
        raise SystemExit(f"Cache file not found or empty: {_CACHE_FILE}\nRun Phase 1 first.")

    accepted = _load_accepted()
    accepted_cids = {
        # Extract original candidate ID from notes field (e.g. "c024, top-1 accepted" → "c024")
        row["notes"].split(",")[0].strip()
        for row in accepted
        if row.get("notes")
    }
    skipped = _load_skipped()

    total_accepted = len(accepted)
    print("\n--- RAG Golden Set Curation ---")
    print(f"Progress: {total_accepted}/{TARGET} accepted, {len(skipped)} skipped\n")

    if total_accepted >= TARGET:
        print(f"Target reached: {TARGET} triples accepted. Done.")
        return

    for cid, question in CANDIDATES:
        if cid in accepted_cids or cid in skipped:
            continue

        chunks = cache.get(cid, [])
        if not chunks:
            print(f"\n[{cid}] No cached results — skipping automatically.")
            skipped.add(cid)
            _save_skipped(skipped)
            continue

        # Show question + options
        print(f"\n{'─' * 70}")
        print(f"[{cid}] {question}")
        print()
        for i, chunk in enumerate(chunks, start=1):
            print(_fmt_chunk(i, chunk))
            print()

        # Prompt
        while True:
            raw = input("Accept? [y=top-1 / 1-5=pick / s=skip / q=quit] > ").strip().lower()
            if raw == "q":
                print("Quit. Progress saved.")
                return
            if raw == "s":
                skipped.add(cid)
                _save_skipped(skipped)
                print("  Skipped.")
                break
            if raw == "y":
                pick_idx = 0
                note_suffix = "top-1 accepted"
                break
            if raw in ("1", "2", "3", "4", "5"):
                idx = int(raw) - 1
                if idx < len(chunks):
                    pick_idx = idx
                    note_suffix = f"alternative {raw} selected"
                    break
                print(f"  Only {len(chunks)} options available.")
                continue
            print("  Invalid input. Enter y, 1–5, s, or q.")
            continue

        if raw == "s":
            continue

        chosen = chunks[pick_idx]
        total_accepted += 1
        question_id = f"q{total_accepted:03d}"
        row: dict[str, Any] = {
            "question_id": question_id,
            "question": question,
            "ground_truth_chunk_id": chosen["chunk_id"],
            "ground_truth_text": chosen["text"],
            "source_type": chosen["source_type"],
            "notes": f"{cid}, {note_suffix}",
        }
        _append_accepted(row)
        print(f"  Accepted as {question_id}. ({total_accepted}/{TARGET})")

        if total_accepted >= TARGET:
            print(f"\nTarget reached: {TARGET} triples accepted.")
            break

    total_accepted = len(_load_accepted())
    print(f"\nDone. {total_accepted}/{TARGET} triples in {_EVAL_FILE}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    # Phase 1: build / top-up cache
    asyncio.run(_build_cache())

    # Phase 2: interactive curation
    _curate()


if __name__ == "__main__":
    main()
