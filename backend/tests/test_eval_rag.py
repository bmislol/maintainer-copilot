"""Eval gate: RAG pipeline on the 24-triple golden set — Phase 3.4 (D-021).

Runs RAGPipeline(use_hyde=True, top_k=10) on each question in
eval_rag.jsonl and asserts:
  - hit@5  >= thresholds['rag']['hit_at_5']
  - MRR@10 >= thresholds['rag']['reciprocal_rank']

Marked @pytest.mark.eval — does NOT run in the default pytest invocation.
Requires DATABASE_URL (live pgvector DB with indexed data) and
ANTHROPIC_API_KEY. Both skipped gracefully if absent.

Refuse-to-run guard: skips if eval_rag.jsonl has fewer than 24 triples.

Design note (D-021): this gate is manual-dispatch only in CI because it
requires a live pgvector DB — spinning up postgres + migrations + indexing
~9700 chunks would add 5–10 min of fragile build time. The classification
gate (no DB dependency) remains PR-triggered.

Costs: ~24 Haiku API calls for HyDE passages, ~$0.05 per run.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
import yaml

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "eval_rag.jsonl"
THRESHOLDS_FILE = Path(__file__).resolve().parent.parent / "eval_thresholds.yaml"

MIN_TRIPLES = 24
PIPELINE_TOP_K = 10  # fetch 10 so MRR@10 is computed against the full ranked list


@pytest.mark.eval
def test_rag_golden_set_meets_thresholds() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    if not EVAL_FILE.exists():
        pytest.skip(f"eval file missing: {EVAL_FILE}")

    triples = [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]
    if len(triples) < MIN_TRIPLES:
        pytest.skip(f"eval_rag.jsonl has {len(triples)} triples — need at least {MIN_TRIPLES}")

    thresholds = yaml.safe_load(THRESHOLDS_FILE.read_text())["rag"]
    required_hit5 = float(thresholds["hit_at_5"])
    required_mrr = float(thresholds["reciprocal_rank"])

    async def _run_all() -> list[dict[str, object]]:
        from anthropic import AsyncAnthropic
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from app.rag.bm25_index import build_indexes
        from app.rag.pipeline import RAGPipeline

        db_url: str = os.environ["DATABASE_URL"]
        api_key: str = os.environ["ANTHROPIC_API_KEY"]

        build_indexes(db_url)

        async_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(async_url, echo=False)
        client = AsyncAnthropic(api_key=api_key)

        rows: list[dict[str, object]] = []
        async with AsyncSession(engine) as session:
            for triple in triples:
                pipeline = RAGPipeline(
                    session=session,
                    anthropic_client=client,
                    top_k=PIPELINE_TOP_K,
                    source_filter="all",
                    use_hyde=True,
                    use_rerank=False,
                )
                chunks = await pipeline.run(str(triple["question"]))
                # Match on source_type:source_id — strip chunk_index suffix.
                gt_key = str(triple["ground_truth_chunk_id"]).rsplit(":", 1)[0]
                returned = [f"{c.source_type}:{c.source_id}" for c in chunks]
                rows.append(
                    {
                        "question_id": triple["question_id"],
                        "gt_key": gt_key,
                        "returned": returned,
                    }
                )

        await engine.dispose()
        return rows

    query_results = asyncio.run(_run_all())

    h5_sum = 0.0
    mrr_sum = 0.0
    for r in query_results:
        gt = str(r["gt_key"])
        returned = list(r["returned"])  # type: ignore[arg-type]
        top5 = returned[:5]
        top10 = returned[:10]

        h5_sum += 1.0 if gt in top5 else 0.0

        for rank, key in enumerate(top10, start=1):
            if key == gt:
                mrr_sum += 1.0 / rank
                break

    n = len(query_results)
    hit_at_5 = h5_sum / n
    mrr_at_10 = mrr_sum / n

    print(f"\nRAG golden set — {n} triples, hyde mode")
    print(f"  hit@5  : {hit_at_5:.4f}  (required >= {required_hit5})")
    print(f"  MRR@10 : {mrr_at_10:.4f}  (required >= {required_mrr})")
    print()
    for r in query_results:
        gt = str(r["gt_key"])
        returned = list(r["returned"])  # type: ignore[arg-type]
        mark = "✓" if gt in returned[:5] else "✗"
        print(f"  [{mark}] {r['question_id']}  {gt}")

    assert hit_at_5 >= required_hit5, f"hit@5 {hit_at_5:.4f} below threshold {required_hit5}"
    assert mrr_at_10 >= required_mrr, f"MRR@10 {mrr_at_10:.4f} below threshold {required_mrr}"
