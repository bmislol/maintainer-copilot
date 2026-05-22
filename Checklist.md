## Phase 1.1 closeout checklist
### Tick these and you're done with 1.1:

- [x]  .gitkeep files in all empty folders (the find one-liner above).
- [x]  Filled .gitignore.
- [x]  .github/pull_request_template.md created.
- [x]  CONTRIBUTING.md at root.
- [x]  Root README.md (the stub above).
- [x]  Branch protection on main configured in GitHub UI.
- [x]  All committed on feat/01-foundations.
- [x]  PR opened against main using the new template.
- [x]  PR merged (squash). Phase 1.1 ticked.

## Phase 1.2 closeout checklist
### Tick these and you're done with 1.2:

- [x]  Replaced .gitkeep with __init__.py in backend/app/ and subfolders
- [x]  backend/main.py deleted, backend/app/main.py created with the FastAPI stub
- [x]  backend/pyproject.toml updated with deps and tool configs
- [x]  uv sync ran cleanly, uv.lock committed
- [x]  backend/tests/__init__.py and backend/tests/test_healthz.py created
- [x]  Local verify: ruff check, ruff format --check, mypy app, pytest all green
- [x]  .github/workflows/ci.yml created
- [x]  Commit, push to feat/02-python-tooling
- [x]  Open PR against main using the template
- [x]  CI runs and turns green on the PR
- [x]  Squash merge
- [x]  Go to GitHub Settings → Rules → Rulesets → main and now enable "Require status checks to pass" — pick Backend (lint / format / type-check / test) from the list (it will only show up after the first CI run completes)
- [x]  Tick Phase 1.2 in CLAUDE.md

## Phase 1.3 closeout checklist
### Tick these and you're done with 1.3:

- [x] mypy override block deleted from backend/pyproject.toml
- [x] backend/Dockerfile created
- [x] backend/app/modelserver.py created
- [x] frontend-admin/pyproject.toml, app.py, Dockerfile created, uv lock ran
- [x] frontend-widget/Dockerfile, nginx.conf, public/index.html, public/widget.js created
- [x] demo/host/Dockerfile, nginx.conf, public/index.html created
- [x] .env.example updated
- [x] docker-compose.yml created
- [x] cp .env.example .env && docker compose up --build — every service reaches healthy
- [x] Every /healthz returns 200 (manual curl for each)
- [x] docker compose down -v && docker compose up --build — clean fresh-clone boot works second time
- [x] deliverables/RUNBOOK.md §1 and deliverables/ARCH.md §2 sanity-checked against reality
- [x] Local CI green: uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
- [x] Commit, push to feat/03-compose-skeleton, open PR, CI green, squash merge

## Phase 1.4 closeout checklist
### Tick these and you're done with 1.4:

- [x] backend/pyproject.toml deps added, uv.lock updated and committed
- [x] backend/app/core/config.py created
- [x] backend/app/core/lifespan.py created
- [x] backend/app/infra/vault.py created
- [x] backend/app/main.py updated with lifespan
- [x] backend/scripts/vault-init.sh created and chmod +x
- [x] backend/app/db/base.py created
- [x] backend/app/db/models/{users,conversations,messages,widgets,audit_log,memory_long}.py created
- [x] backend/alembic/ initialized via alembic init -t async
- [x] backend/alembic/env.py replaced with the Vault-aware version
- [x] backend/alembic.ini sqlalchemy.url blanked
- [x] First migration generated and CREATE EXTENSION vector added manually
- [x] .env.example updated with VAULT_KV_PATH_PREFIX and ANTHROPIC_API_KEY
- [x] docker-compose.yml — vault-init service added; api/modelserver depends_on updated; migrate rewired to alembic
- [x] backend/tests/test_vault.py and test_refuse_to_boot.py created
- [x] Local CI: ruff/format/mypy/pytest all green
- [x] docker compose down -v && docker compose up --build — vault-init seeds, migrate runs alembic, every service healthy
- [x] Refuse-to-boot proven by stopping vault and watching api refuse
- [x] psql \dt shows all six tables; pg_extension shows vector
- [x] types-hvac added to dev dependencies (you just did this).
- [x] mypy override for pgvector. added to pyproject.toml* (you just did this).
- [x] Deliverables updated: ARCH §9, SECURITY §3, RUNBOOK §2, optionally DECISIONS
- [x] Commit, push to feat/04-vault-alembic, open PR with template, CI green, squash merge
- [x] Tick Phase 1.4 in CLAUDE.md / Checklist.md

## Phase 1.5 closeout checklist
### Tick these and you're done with 1.5:

- [x] Langfuse keys grabbed from UI and added to .env
- [x] .env.example updated with LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY placeholders
- [x] vault-init.sh updated to forward env-var keys
- [x] docker-compose.yml — vault-init service forwards the two new env vars
- [x] langfuse>=2.50.0,<3.0.0 added to backend/pyproject.toml, uv.lock updated
- [x] app/core/logging.py created
- [x] app/infra/tracing.py created
- [x] app/api/middleware.py created
- [x] app/core/lifespan.py updated to init tracing + configure logging
- [x] app/main.py updated — middleware mounted, logger added to healthz
- [x] app/modelserver.py updated — configure_logging called
- [x] backend/tests/test_logging.py and test_refuse_to_boot_langfuse.py created
- [x] mypy override for langfuse.* added if needed
- [x] docker compose up -d --force-recreate vault-init re-seeds with real keys
- [x] docker compose up -d --build api brings api up healthy
- [x] /healthz returns 200 with X-Request-ID header
- [x] api logs are structured JSON with populated request_id + trace_id
- [x] Langfuse UI shows the /healthz trace under Traces
- [x] Refuse-to-boot proven: docker compose stop langfuse && docker compose restart api → REFUSING TO BOOT: Could not reach Langfuse
- [x] Local CI: ruff / format / mypy / pytest all green
- [x] Deliverables: ARCH §9 + §12, RUNBOOK §2, DECISIONS D-031 + D-032
- [x] Commit, push to feat/05-langfuse-logging, PR template, CI green, squash merge

## Phase 1.6 closeout checklist
### Tick these and you're done with 1.6:

- [x] `backend/pyproject.toml` deps added (`httpx`), dev deps added (`tqdm`); `uv.lock` updated and committed
- [x] `backend/data/issues/raw/` and `backend/data/issues/splits/` directories created
- [x] `.gitignore` confirms `backend/data/` is excluded (verified via `git check-ignore`)
- [x] GitHub fine-grained personal access token generated, `GITHUB_TOKEN` added to `.env` (public read-only scope)
- [x] `.env.example` updated with `GITHUB_TOKEN` placeholder
- [x] `backend/scripts/fetch_issues.py` created (REST API, paginated, resumable cache, 422 deep-pagination tolerance)
- [x] `backend/scripts/fetch_issues_graphql.py` created (cursor-based, beyond REST 10k limit)
- [x] Empirical inspection of label distributions across `tiangolo/fastapi`, `langchain-ai/langchain`, `huggingface/transformers`, `scikit-learn/scikit-learn` to pick the final dataset
- [x] Final repo locked in: `scikit-learn/scikit-learn`
- [x] REST fetch ran successfully (99 pages cached) — `data/issues/raw/scikit-learn__scikit-learn/page_*.json`
- [x] GraphQL fetch ran successfully (~100+ batches cached) — `data/issues/raw/scikit-learn__scikit-learn/gql_batch_*.json`
- [x] `backend/scripts/build_dataset.py` created with label mapping, ambiguity exclusion, CI bot filter, and time-based stratified split
- [x] `build_dataset.py` ran cleanly on full cache; produced `train.jsonl`, `val.jsonl`, `test.jsonl`, and `metadata.json`
- [x] Final dataset numbers: 3,844 classified — train 2690 / val 576 / test 578
- [x] Training data SHA-256 hash committed in `metadata.json` (referenced from Phase 2.1's model card)
- [x] Question class spot-check: sample examples are real triage-tagged issues, not CI bot templates
- [x] `backend/tests/test_dataset_splits.py` created (4 tests: splits exist, required fields, test newer than train, all four classes per split)
- [x] All 4 dataset tests pass
- [x] CI bot filter (`⚠️ CI failed ...`) removes 656 templated issues
- [x] Local CI: `ruff check`, `ruff format --check`, `mypy app`, `pytest` all green
- [x] `CLAUDE.md` references updated (FastAPI repo → scikit-learn repo, in §2 locked decisions table)
- [x] `deliverables/ARCH.md` §11 RAG corpus row updated to scikit-learn
- [x] `deliverables/DECISIONS.md` D-002 replaced (scikit-learn dataset rationale + revision note)
- [x] `deliverables/DECISIONS.md` D-007 added (label mapping, question proxy, CI bot filter, quantified outcomes)
- [x] `deliverables/DECISIONS.md` D-008 added (split strategy, temporal drift observation, SHA-256)
- [x] `deliverables/DECISIONS.md` "Pending Decisions" section no longer lists D-007 / D-008
- [x] Commit, push to `feat/06-dataset-fetch`, PR opened using the template
- [x] CI green on the PR
- [x] Squash merge to `main`
- [x] Tick Phase 1.6 in CLAUDE.md and Checklist.md

## Phase 2.1 closeout checklist
### Tick these and you're done with 2.1:

Sitting A (Training):
- [x] Branch `feat/07-classifier-finetune` created from main
- [x] ML deps added to pyproject.toml (torch, transformers, datasets, evaluate, wandb, etc.)
- [x] uv lock / uv sync / CUDA detected on RTX 3060
- [x] W&B account created, `wandb login` configured
- [x] `backend/notebooks/01_train_classifier.ipynb` created with 8 cells
- [x] Training run completes; early stopping triggered after epoch 2 (expected)
- [x] Test accuracy 0.8478, macro-F1 0.7462, all four classes present in per-class F1
- [x] Artifacts saved to `data/classifier_artifacts/` (classifier.pt, tokenizer/, model_card.json)
- [x] model_card.json includes wandb_run pointer with run URL
- [x] `tests/test_classifier_inference.py` (3 tests) green

Sitting B (Wiring):
- [x] `minio>=7.2.0` added to dependencies
- [x] `app/infra/object_storage.py` created
- [x] `scripts/push_classifier_to_minio.py` created and runs successfully
- [x] Artifacts pushed to MinIO bucket `classifier-artifacts/v1/`
- [x] `app/modelserver.py` rewritten with lifespan, artifact download, SHA-256 check, threshold check, /classify endpoint
- [x] modelserver Dockerfile rebuilds cleanly
- [x] `docker compose up -d --build modelserver` brings it up healthy
- [x] modelserver logs show artifact download, SHA verified, model loaded
- [x] `POST /classify` from another container returns correct shape
- [x] Refuse-to-boot proven: stop minio → restart modelserver → REFUSING TO BOOT
- [x] `tests/test_classifier_inference.py` adds threshold tests (5 tests total) green
- [x] mypy override for `minio.*` added if needed
- [x] Local CI all green: ruff / format / mypy / pytest
- [x] Deliverables: ARCH §10 populated, DECISIONS D-009 added, RUNBOOK §2 appended, EVALS §1 populated
- [x] Commit/squash, push to feat/07-classifier-finetune, PR opened, CI green, squash merge
- [x] Tick Phase 2.1 in CLAUDE.md / Checklist.md

## Phase 2.2 closeout checklist
### Tick these and you're done with 2.2:

Fix carry-over:
- [x] mypy fix for modelserver type annotations (squashed into this branch)

Classical baseline:
- [x] Branch `feat/08-classical-baseline` created from main
- [x] Notebook `backend/notebooks/02_classical_baseline.ipynb` created
- [x] Same JSONL splits loaded (train.jsonl, val.jsonl, test.jsonl)
- [x] TF-IDF vectorizer fit on train only
- [x] Both LogisticRegression and LinearSVC trained
- [x] Winner picked on val, tested ONCE on test
- [x] Test-set evaluation: accuracy, macro-F1, per-class F1, confusion matrix
- [x] Side-by-side comparison printed with DistilBERT numbers
- [x] W&B run logged (job_type="baseline")
- [x] Artifacts saved to `data/classical_baseline_artifacts/`
- [x] `backend/tests/test_classical_baseline.py` (2 tests) green or skipped
- [x] `deliverables/DECISIONS.md` D-010 added (classical baseline rationale)
- [x] `deliverables/EVALS.md` §1 updated with classical row
- [x] Local CI: ruff / format / mypy / pytest all green
- [x] Commit, push, PR template, CI green, squash merge
- [x] Tick Phase 2.2 in CLAUDE.md / Checklist.md

## Phase 2.3 closeout checklist
### Tick these and you're done with 2.3:

- [x] Branch `feat/09-llm-baseline` created from main
- [x] `anthropic` and `tenacity` added to dependencies; uv lock/sync clean
- [x] ANTHROPIC_API_KEY confirmed in .env
- [x] Notebook `backend/notebooks/03_llm_baseline.ipynb` created
- [x] Structured-output tool schema defined (label enum + reasoning)
- [x] Concurrency 5, exponential-backoff retries, JSONL caching
- [x] Haiku smoke test on 10 examples — 7/10, $0.02
- [x] Haiku full run on 578 examples — macro-F1 0.7664, $1.06
- [x] Sonnet full run on 578 examples — macro-F1 0.7329, $3.12
- [x] Four-way comparison report written to data/llm_baseline_artifacts/
- [x] `tests/test_llm_baseline.py` (3 tests) green
- [x] DECISIONS D-011 added (LLM baseline rationale, prompt, costs)
- [x] DECISIONS D-012 added (three-way comparison and deployment choice)
- [x] EVALS §1 updated with four-row final comparison table
- [x] Local CI: ruff / format / mypy / pytest all green
- [x] Commit (squashed), push to feat/09-llm-baseline, PR opened
- [x] CI green on GitHub
- [x] Squash merge
- [x] Tick Phase 2.3 in CLAUDE.md / Checklist.md

## Phase 2.4 closeout checklist
### Tick these and you're done with 2.4:

Golden set:
- [x] Branch `feat/10-eval-classification-gate` created from main
- [x] Interactive curator script `backend/scripts/curate_golden_set.py` created
- [x] Curated from `test.jsonl` (not fresh GitHub issues) — defended in D-013 as the "regression floor" strategy since Haiku is frozen and DistilBERT didn't train on test
- [x] 25 examples committed: 7 bug, 7 feature, 6 docs, 5 question
- [x] `backend/data/eval/eval_classification.jsonl` committed to git

CI gate:
- [x] `backend/eval_thresholds.yaml` (inside backend/, not project root) with `classification.macro_f1: 0.90` and `classification.per_class_min_f1: 0.50`
- [x] `backend/tests/test_eval_classification.py` runs Haiku on golden set, asserts both thresholds
- [x] Custom `@pytest.mark.eval` marker registered in pyproject.toml
- [x] `.github/workflows/eval-classification.yml` runs on path-relevant PRs + manual dispatch (paths filter prevents wasted runs)
- [x] GitHub repo secret `ANTHROPIC_API_KEY` added
- [x] First measured Haiku floor: macro-F1 1.0000, all classes 1.0000
- [x] Threshold defended in D-013 (0.90 floor = 10pt cushion absorbing LLM non-determinism while remaining sensitive to real regressions)
- [x] Local eval gate run: `uv run pytest -m eval -v -s` passes

Refuse-to-boot integration:
- [x] `app/core/lifespan.py` refactored: `_check_eval_thresholds(yaml_path)` + `_resolve_thresholds_path()` for testability
- [x] Lifespan call wired in between Vault and Langfuse checks
- [x] 5 unit tests in `tests/test_eval_thresholds_refuse_to_boot.py` cover: positive values pass / missing file / zero / negative / non-numeric
- [x] Dockerfile copies `eval_thresholds.yaml` into the image
- [x] `types-PyYAML` added to dev deps for mypy

Deliverables:
- [x] DECISIONS D-013 added (golden set methodology, threshold defense, 1.0 floor measurement)
- [x] EVALS.md §1 updated with classification CI gate row
- [x] RUNBOOK.md §2 updated with eval-threshold refuse-to-boot proof
- [x] RUNBOOK.md §4 updated with local gate-run instructions
- [x] ARCH.md §9 updated (eval threshold check now (implemented in Phase 2.4))
- [x] CLAUDE.md / Checklist.md — tick Phase 2.4

PR:
- [x] Commit (squashed), push, PR template filled
- [x] CI green (lint/test) AND eval gate green (1.0 macro-F1 on Haiku)
- [x] Squash merged to main
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 2.4 in CLAUDE.md / Checklist.md

## Phase 2.5 closeout checklist
### Tick these and you're done with 2.5:

NER + Summarize implementation:
- [x] Branch `feat/11-ner-summarizer` created from main
- [x] app/modelserver.py updated:
  - [x] NER pipeline loaded at startup (task="token-classification")
  - [x] Anthropic SDK client created at startup
  - [x] POST /ner endpoint with input limits
  - [x] POST /summarize endpoint with input limits
  - [x] Refuse-to-boot on NER load failure
- [x] tests/test_ner_endpoint.py (3 tests, stubbed pipeline)
- [x] tests/test_summarize_endpoint.py (3 tests, stubbed Anthropic client)
- [x] Local CI: ruff / format / mypy / pytest all green
- [x] modelserver rebuild succeeds, container healthy
- [x] Smoke test from inside docker: /ner returned 4 entities, /summarize compressed 451→253 chars

Deliverables:
- [x] DECISIONS D-014 added (no MinIO for NER, Claude for summarizer, task name choice)
- [x] ARCH §10.2 added (NER + summarize artifacts)
- [x] EVALS §2 added (specs + Phase 2.5 smoke results)
- [x] RUNBOOK §2 updated with NER refuse-to-boot condition

PR:
- [x] Commit (squashed), push
- [x] PR opened with template
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] git pull on main
- [x] Tick Phase 2.5 in CLAUDE.md / Checklist.md

## Phase 3.1 closeout checklist
### Tick these and you're done with 3.1:

Corpus build:
- [x] `.gitignore` updated — `backend/data/rag_corpus/docs/`, `backend/data/rag_corpus/issues/`, `backend/data/scikit-learn-clone/` excluded; `manifest.json` kept
- [x] `sentence-transformers>=3.0.0` added to `backend/pyproject.toml`; `uv lock && uv sync` clean
- [x] `backend/scripts/build_rag_corpus.py` created — clones scikit-learn@1.6.0, extracts 176 `.rst` docs, reads comment-enriched issues, writes manifest
- [x] `backend/scripts/fetch_issue_comments.py` created — GraphQL per-issue fetch, `--limit` flag, sorted most-recent-closed first, skips zero-comment results; resumable
- [x] Root cause of `0 candidates` diagnosed: Phase 1.6 cache has no `comments` field so pre-filter silently dropped all issues; fixed by removing the comment-count pre-filter and fetching unconditionally
- [x] Fetch ran: 500 candidates selected, 465 written (35 skipped — zero comments on GitHub), wall time 4m28s
- [x] Corpus built: 176 docs + 465 issues = 641 items; manifest written to `backend/data/rag_corpus/manifest.json`
- [x] Contamination guard confirmed: 3,844 train+val+test IDs excluded from RAG candidates before fetch

Embedding benchmark:
- [x] `backend/scripts/benchmark_embeddings.py` created — 18 hand-written queries with known-relevant doc/issue pairs, hit@1 and hit@5 measured over both models
- [x] `BAAI/bge-base-en-v1.5`: hit@1 55.56% (10/18), hit@5 88.89% (16/18), encode 7.5s, dim 768
- [x] `sentence-transformers/all-MiniLM-L6-v2`: hit@1 55.56% (10/18), hit@5 88.89% (16/18), encode 1.0s, dim 384
- [x] Models tied on retrieval quality; MiniLM selected for 7.5× faster encode and 2× smaller pgvector index
- [x] `backend/benchmark_results.json` written with full per-query breakdown

Deliverables:
- [x] `deliverables/DECISIONS.md` D-015 added (corpus composition, comment enrichment strategy, embedding benchmark table and winner rationale)
- [x] `deliverables/DECISIONS.md` pending-decisions D-015 entry marked ✅
- [x] `deliverables/ARCH.md` §11 embedding model row filled in (MiniLM, benchmark numbers, deferred decisions linked to phases)

CI:
- [x] Local CI: `ruff check`, `ruff format --check`, `mypy app`, `pytest` all green (30 passed, 2 skipped)

PR:
- [x] Commit, push to `feat/12-rag-corpus`, PR opened with Phase 3.1 closeout checklist
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 3.1 in CLAUDE.md / Checklist.md

## Phase 3.2 closeout checklist
### Tick these and you're done with 3.2:

Chunker:
- [x] `app/rag/chunker.py` — RST heading splitter, issue body+comment chunker, sliding-window fallback at 220 tokens / 50-token overlap (stride 170); comment cap 300 tokens (first-paragraph assumption, D-016)
- [x] `app/rag/embedder.py` — MiniLM-L6-v2 singleton (384-dim, selected D-015)
- [x] `app/rag/retriever.py` — async pgvector dense search baseline; preserved for Phase 3.4 A/B comparison

Migration:
- [x] `alembic/versions/a1b2c3d4e5f6` — `rag_chunks` table with `vector(384)`, HNSW (m=16, ef_construction=64), GIN on metadata, btree on (source_type, source_id)
- [x] Migration also fixes `memory_long.embedding` dim 1536 → 384 (D-015 locked all-MiniLM-L6-v2)
- [x] Migration ran cleanly; schema verified via `\d rag_chunks` (all indexes present)

Indexing:
- [x] `scripts/index_corpus.py` — chunks + embeds + upserts idempotently; 641 items → 9,701 chunks (docs=4,846, issues=4,855) in 58.8s
- [x] `scripts/benchmark_retrieval.py` — 18 proxy queries against live DB (hit@1, hit@5)

Baseline numbers (18-query proxy set):
- [x] hit@1: 55.56% (Phase 3.1 flat) → **83.33% (15/18)** (+27.8 pp)
- [x] hit@5: 88.89% (Phase 3.1 flat) → **94.44% (17/18)** (+5.6 pp)
- [x] `backend/benchmark_retrieval_results.json` written with full per-query breakdown

Tests:
- [x] `tests/test_chunker.py` — 16 round-trip tests on real corpus files (common_pitfalls.json + issue 104880490.json); all pass
  - No empty chunks, no doc chunks exceed MAX_TOKENS, n_tokens matches count_tokens(), section_title populated, chunk_id format correct, unique ids, coverage

Deliverables:
- [x] `deliverables/DECISIONS.md` D-016 added (chunking strategy, schema, HNSW rationale, baseline numbers table, alternatives rejected)
- [x] `deliverables/ARCH.md` §11 chunking and vector store rows filled with real numbers

CI:
- [x] Local CI: `ruff check`, `ruff format --check`, `mypy app`, `pytest` all green (43 passed, 1 skipped)

PR:
- [x] Commit, push to `feat/13-smart-chunking`, PR opened with Phase 3.2 closeout checklist
- [x] CI green
- [x] Squash merged (#12)
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 3.2 in CLAUDE.md / Checklist.md

---

## Phase 3.3 closeout checklist
### Branch: `feat/14-hybrid-retrieval-rerank`

**Commit 1 — Catchup: degenerate chunk filter**
- [x] Deleted 47 degenerate chunks (n_tokens < 5) via `DELETE FROM rag_chunks WHERE n_tokens < 5`
- [x] Documented in D-017 as precondition for BM25 indexing

**Commit 2 — BM25 + hybrid RRF**
- [x] `app/rag/bm25_index.py` — three in-memory BM25 indexes (docs / issues / all), loaded at startup
- [x] `app/rag/hybrid_retriever.py` — RRF fusion (k=60) over dense + BM25 results
- [x] `scripts/benchmark_retrieval.py` updated: add MRR@10 and recall@10 metrics
- [x] D-017 written with baseline vs. hybrid numbers

**Commit 3 — Cross-encoder reranker**
- [x] `app/rag/reranker.py` — inline `CrossEncoderReranker` using ms-marco-MiniLM-L-6-v2
- [x] D-018 written with rerank hit@1/hit@5 numbers vs. hybrid baseline

**Commit 4 — HyDE query transform + RAG pipeline**
- [x] `app/rag/query_transform.py` — HyDE transform (accepts `AsyncAnthropic` client as param)
- [x] `app/rag/pipeline.py` — `RAGPipeline` with `ChunkResult` typed dataclass, three-stream HyDE augment
- [x] D-019 written with HyDE numbers vs. rerank-only baseline

**Commit 5 — Metadata filter**
- [x] Metadata filter Literal["docs","issues","all"] formalized in pipeline
- [x] D-020 written

**Commit 6 — Final benchmark + ARCH §11**
- [x] Full benchmark table: dense → hybrid → +rerank → +HyDE across hit@1/hit@5/MRR@10/recall@10
- [x] `deliverables/ARCH.md` §11 sparse/rerank/transform rows filled
- [x] fix: added HyDE benchmark mode to benchmark_retrieval.py after initial push (Gemini review caught the gap); D-019 rewritten with real measurements

PR:
- [x] Commit, push to `feat/14-hybrid-retrieval-rerank`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 3.3 in CLAUDE.md / Checklist.md

---

## Phase 3.4 closeout checklist
### Branch: `feat/15-rag-golden-set`

**Golden set curation**
- [x] `scripts/curate_rag_golden_set.py` written — Phase 1 caches retrieval results (`RAGPipeline(use_hyde=False, top_k=5)`) to `data/eval/.curation_cache.json`; Phase 2 is interactive y/1-5/s/q loop
- [x] 56 candidate questions (c001–c056) across doc and issue categories
- [x] Interactive curation session produced 24 verified triples
- [x] 3 entries re-curated after diagnostic review: section-header chunk (q003), FAQ-redirect chunk (q004), issue-opener chunk (q005) — all replaced with substantive answers via DB inspection
- [x] 1 question dropped (c002 — custom transformer): no adequate chunk in top-5; replaced with c056 targeting `doc:developers__develop:23`
- [x] Source split: 17 doc / 7 issue
- [x] All 24 `ground_truth_chunk_id` values verified present in live `rag_chunks` table
- [x] `data/eval/eval_rag.jsonl` committed (24 rows, 24 unique chunk_ids)

**Benchmark on final golden set**
- [x] `scripts/benchmark_retrieval.py` extended with `--eval-file` and `--mode` args
- [x] Benchmark run: `--mode hyde --eval-file data/eval/eval_rag.jsonl`
- [x] hit@5: **95.83%** (23/24) — single miss: q014 (set_output API)
- [x] MRR@10: **0.8532**
- [x] recall@10: **100.00%**

**Thresholds**
- [x] `backend/eval_thresholds.yaml` updated: `rag.hit_at_5: 0.8583`, `rag.reciprocal_rank: 0.7532`
- [x] Methodology: measured − 10 pp (same as D-013 classification thresholds)

**Judge agreement**
- [x] `scripts/judge_agreement.py` written — calls Haiku once per triple on first 5, saves `data/eval/judge_agreement.json`
- [x] Agreement: 1/5 (20%) — documented in D-021 as calibration gap (human standard: "best available chunk for retrieval recall"; Haiku standard: "passage fully and specifically answers the question")
- [x] Decision: 20% is the honest measurement; judge prompt not adjusted to inflate the number (would be p-hacking the eval)

**CI gate**
- [x] `backend/tests/test_eval_rag.py` — `@pytest.mark.eval`, skips without `DATABASE_URL` or `ANTHROPIC_API_KEY`, refuse-to-run if fewer than 24 triples, asserts hit@5 and MRR@10 against thresholds
- [x] `.github/workflows/eval-rag.yml` — `workflow_dispatch` only (live pgvector DB dependency; spinning it up in CI adds 5–10 min fragile build time)
- [x] CI green: 46 passed, 3 skipped (vault + 2 eval tests self-skip without env vars)

**Deliverables**
- [x] D-021 written — curation methodology, benchmark results, threshold defense, judge agreement analysis, CI design rationale

**PR**
- [x] Commit, push to `feat/15-rag-golden-set`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 3.4 in CLAUDE.md / Checklist.md

---

## Phase 3.5 closeout checklist
### Branch: `feat/16-redaction-exceptions`

**Redaction module**
- [x] `app/infra/redaction.py` created — `redact(text: str) -> str`, 8 compiled patterns applied most-specific-first:
  - `sk-ant-[A-Za-z0-9\-]+` — Anthropic API keys (before generic `sk-` rule)
  - `sk-[A-Za-z0-9\-]{20,}` — generic `sk-` bearer tokens (hyphens included; mandatory `sk-test-FAKE-not-real` grading criterion passes because of `\-`)
  - `gh[ps]_[A-Za-z0-9]{36}` — GitHub classic PATs and server tokens
  - `github_pat_[A-Za-z0-9_]{82}` — GitHub fine-grained PATs
  - `hvs\.[A-Za-z0-9]+` — HashiCorp Vault service tokens
  - `postgresql://[^\s]+` — Postgres DSNs (entire URI including embedded password)
  - three-segment base64url heuristic (10-char floor) — JWT tokens
  - email address pattern — PII (GDPR data minimisation)

**Logging integration**
- [x] `app/core/logging.py` — `RedactionFilter` class added; attached to the `StreamHandler` via `handler.addFilter()` (not `root.addFilter()`)
- [x] Key finding: `root.addFilter()` is bypassed for child-logger records during propagation — Python's `callHandlers()` calls handlers directly without invoking the parent logger's `handle()` (and therefore its filters). Handler-level filters run for every record regardless of source.
- [x] `configure_logging()` rewritten to preserve non-`JSONFormatter` handlers (e.g. pytest's `LogCaptureHandler`) instead of blanket `root.handlers.clear()` — prevents caplog from going dark mid-test. Our handler is inserted at index 0 so `RedactionFilter` mutates the shared `LogRecord` before caplog reads it.

**Langfuse integration**
- [x] `app/infra/tracing.py` — `redact_metadata(meta: dict) -> dict` added; wraps all string values before every `langfuse.trace()` / `langfuse.span()` metadata argument

**Middleware update**
- [x] `app/api/middleware.py` — imports `redact_metadata`; calls it on trace metadata; adds `request.state.request_id = request_id` so the exception handler can read the correlation ID

**Domain exception hierarchy**
- [x] `app/domain/exceptions.py` created — `CopilotError` base (http_status=500, code="internal_error") + 5 subclasses:
  - `NotFoundError` — 404 / not_found
  - `PermissionDeniedError` — 403 / permission_denied
  - `ToolFailureError` — 502 / tool_failure
  - `RateLimitError` — 429 / rate_limited
  - `ValidationError` — 422 / validation_error
- [x] Domain exceptions are distinct from infra exceptions (`VaultUnreachableError`, `LangfuseUnreachableError`) — infra exceptions abort startup; domain exceptions are caught at the request boundary

**API exception handler**
- [x] `app/main.py` — `@app.exception_handler(CopilotError)` added; converts every `CopilotError` subclass to structured JSON `{"error": {"code": ..., "message": ..., "request_id": ...}}`; users never see a stack trace; `request_id` correlates the error response to the Langfuse trace and the structured log entry

**Tests**
- [x] `tests/test_redaction.py` created — 8 tests:
  - `test_anthropic_key_is_redacted` — mandatory grading criterion (`sk-test-FAKE-not-real` never appears unredacted)
  - `test_postgres_dsn_is_redacted` — full DSN including password replaced
  - `test_clean_text_passes_through` — no false positives on clean prose
  - `test_log_filter_redacts_in_log_output` — `caplog.text` contains `[REDACTED]` (proves filter active in live pipeline)
  - `test_github_token_is_redacted` — `ghp_` + 36-char body caught
  - `test_vault_token_is_redacted` — `hvs.` prefix token caught
  - `test_email_is_redacted` — `user@example.com` caught
  - `test_multiple_secrets_in_one_string` — three secret types in one string → ≥ 3 `[REDACTED]` tokens
- [x] Final pytest count: **54 passed, 3 skipped**

**Deliverables**
- [x] `deliverables/DECISIONS.md` D-022 added — full pattern table with per-pattern rationale, handler-attachment explanation, alternatives rejected (AWS/signed-URL patterns deferred), trade-offs
- [x] `deliverables/SECURITY.md` §7 rewritten — integration points, pattern table, test matrix

**PR**
- [x] Commit, push to `feat/16-redaction-exceptions`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 3.5 in CLAUDE.md / Checklist.md
- [x] **Section 3 complete** — all 5 phases (3.1 through 3.5) merged to main
---

## Phase 4.1 closeout checklist
### Branch: `feat/17-auth`

**Dependencies**
- [x] `fastapi-users[sqlalchemy]>=13.0.0,<14.0.0` + `bcrypt>=4.0.0` added to `pyproject.toml`
- [x] `types-passlib>=1.7.7` added to dev deps
- [x] `uv sync` clean; `uv.lock` updated

**Database**
- [x] `app/db/models/users.py` rewritten — inherits from `SQLAlchemyBaseUserTableUUID` + `Base`; `__tablename__ = "users"` overrides the mixin's default "user"; `created_at` retained as an extra column; `id` re-declared as `UUID(as_uuid=True)` for Alembic dialect compatibility
- [x] `app/db/session.py` created — `get_async_session(request: Request)` dependency reads `request.app.state.db_session_factory` per request
- [x] Alembic migration `fc629b51e563` generated and manually trimmed:
  - Adds `hashed_password`, `is_active`, `is_superuser`, `is_verified` to `users`
  - Swaps unique constraint `users_email_key` → unique index `ix_users_email`
  - Explicitly does NOT drop `created_at` (kept in model) or the HNSW index on `rag_chunks` (autogenerate false-positive — index exists in DB and is preserved)
- [x] `alembic upgrade head` ran cleanly

**Lifespan update**
- [x] `app/core/lifespan.py` — creates `create_async_engine(secrets.database.url)` and `async_sessionmaker(...)` after Vault resolves; stores both in `app.state.db_engine` / `app.state.db_session_factory`; disposes engine on shutdown

**Auth infra**
- [x] `app/infra/auth.py` created:
  - `get_user_db` — yields `SQLAlchemyUserDatabase` backed by the per-request session
  - `UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID])` — minimal, no custom hooks
  - `get_user_manager` — yields `UserManager`
  - `get_jwt_strategy(request: Request) -> JWTStrategy` — **reads from `request.app.state.secrets.jwt` at request time**; never reads from env, never reads at import time
  - `auth_backend = AuthenticationBackend(name="jwt", transport=BearerTransport, get_strategy=get_jwt_strategy)`
  - `fastapi_users`, `current_active_user`, `current_active_superuser` exported

**API routers**
- [x] `app/domain/schemas.py` created — `UserRead(BaseUser[UUID])`, `UserUpdate(BaseUserUpdate)`
- [x] `app/api/auth.py` created — mounts login/logout (`/auth/jwt/...`) and `/users/me`; the `get_register_router()` is intentionally NOT mounted
- [x] `app/main.py` — `app.include_router(auth_router)` added

**Bootstrap script**
- [x] `app/entrypoints/bootstrap_admin.py` created — reads `DATABASE_URL`, `BOOTSTRAP_EMAIL`, `BOOTSTRAP_PASSWORD` from env; connects host-side via asyncpg; aborts if user already exists; creates `is_superuser=True` user with bcrypt-hashed password

**Tests**
- [x] `tests/test_auth.py` — 5 tests via `app.dependency_overrides`:
  - `get_user_manager` overridden with mock `SQLAlchemyUserDatabase` (two users: regular + admin)
  - `get_jwt_strategy` overridden with fixed test secret (avoids `app.state.secrets` requirement in tests)
  - Fixture clears overrides after each test to prevent bleed-through
  - `test_login_correct_credentials_returns_token` ✅
  - `test_login_wrong_password_returns_400` ✅ (fastapi-users returns 400, not 401)
  - `test_users_me_with_valid_token` ✅
  - `test_users_me_without_token_returns_401` ✅
  - `test_non_admin_blocked_from_admin_route` ✅
- [x] Final pytest count: **59 passed, 3 skipped**

**Key decisions**
- [x] Role model: `is_superuser: bool` (not a `role` column) — D-033
- [x] JWT secret: read from `request.app.state.secrets.jwt` via FastAPI dependency, never env/import-time
- [x] DB engine: created in lifespan from Vault-resolved URL, stored in `app.state`

**Deliverables**
- [x] `deliverables/ARCH.md` §6 updated (full auth description, JWT threading, role model, DB engine pattern)
- [x] `deliverables/ARCH.md` §7 updated (endpoint table with auth routes live, placeholders for later phases)
- [x] `deliverables/SECURITY.md` §4 updated (JWT from Vault, no public register)
- [x] `deliverables/SECURITY.md` §5 updated (is_superuser enforcement, 403 before handler runs)
- [x] `deliverables/RUNBOOK.md` §3 updated (bootstrap_admin.py run command, verify login, verify /users/me)
- [x] `deliverables/DECISIONS.md` D-033 added (is_superuser vs role column)

**PR**
- [x] Commit, push to `feat/17-auth`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.1 in CLAUDE.md / Checklist.md

---

## Phase 4.2 closeout checklist
### Branch: `feat/18-chatbot-core`

**Dependencies**
- [x] `sse-starlette>=2.0.0` added to `pyproject.toml`
- [x] `uv sync` clean; `uv.lock` updated

**Config / lifespan**
- [x] `app/core/config.py` — `modelserver_url: str = "http://modelserver:8001"` added to `BootstrapSettings`
- [x] `app/core/lifespan.py` — `httpx.AsyncClient(base_url=modelserver_url, timeout=30s)` created at startup, stored as `app.state.http_client`; `AsyncAnthropic(api_key=secrets.anthropic.api_key)` stored as `app.state.anthropic_client`; both closed on shutdown

**Chatbot core**
- [x] `app/prompts/system.md` created — concise system prompt for issue triage assistant
- [x] `app/chatbot/__init__.py` created — empty package marker
- [x] `app/services/__init__.py` created — empty package marker
- [x] `app/chatbot/tools.py` created:
  - 5 `TOOL_SCHEMAS` dicts passed verbatim to Anthropic API: `classify_issue`, `extract_entities`, `summarize_thread`, `retrieve_docs`, `write_memory`
  - 5 async executor functions; all catch exceptions and return `{"error": "tool_name unavailable: reason"}`
  - `execute_write_memory` is a stub (`{"status": "ok"}`) until Phase 4.3
  - `_EXECUTORS: dict[str, _ExecutorFn]` typed dispatcher
  - `execute_tool()` public dispatcher
- [x] `app/chatbot/loop.py` created:
  - `MAX_ROUNDS = 5`, `MODEL = "claude-haiku-4-5"`
  - `run_stream()` async generator: standard Anthropic tool-use pattern
  - Final round forces `tools=[]` so Claude must produce `end_turn` (D-034)
  - Yields full text block on `end_turn`; falls back to `"[max tool rounds reached]"` if budget exhausted
- [x] `app/services/chat_service.py` created:
  - `_load_system_prompt()` cached with `@lru_cache(maxsize=1)`
  - `stream_chat_response()` opens a Langfuse span (`chatbot_turn`) if tracing active; delegates to `run_stream()`; yields text delta strings

**API endpoint**
- [x] `app/api/chat.py` created — `POST /chat/send`; request body `{"conversation_id": uuid|null, "message": str}`; `current_active_user` auth dep; `EventSourceResponse` streaming; final event `data: [DONE]`
- [x] `app/main.py` — `app.include_router(chat_router)` added

**Tests**
- [x] `tests/test_chatbot_tools.py` — 9 tests; mock `httpx.AsyncClient`; verifies executor output shapes and error returns; patches `RAGPipeline` for `retrieve_docs`
- [x] `tests/test_chatbot_loop.py` — 4 tests; mock Anthropic client via `MagicMock` async context manager:
  - `test_loop_end_turn_yields_text` ✅
  - `test_loop_tool_use_then_end_turn` ✅
  - `test_loop_exhausts_rounds_and_yields_fallback` ✅
  - `test_last_round_sends_no_tools` ✅ (asserts `tools=[]` on MAX_ROUNDS-th call)
- [x] `tests/test_chat_endpoint.py` — 3 tests; autouse fixture sets `app.state.anthropic_client/http_client` and overrides `get_async_session` + `get_jwt_strategy`:
  - `test_send_message_streams_sse` ✅ (checks `text/event-stream`, `[DONE]` in body)
  - `test_send_message_requires_auth` ✅ (no token → 401)
  - `test_send_message_with_conversation_id` ✅ (UUID forwarded to service)
- [x] Final pytest count: **75 passed, 3 skipped**

**Key decisions**
- [x] Tool-calling loop: single loop, MAX_ROUNDS=5, claude-haiku-4-5, empty tools on final round — D-034
- [x] Shared `httpx.AsyncClient` per process: created in lifespan, not per-request (D-034 / lifespan pattern)
- [x] SSE body shape: `conversation_id` in request body (not path param); final `[DONE]` event

**Deliverables**
- [x] `deliverables/ARCH.md` §5 rewritten (full chatbot turn data flow, tool routing, SSE streaming)
- [x] `deliverables/ARCH.md` §7 updated (`/chat/send` marked live)
- [x] `deliverables/DECISIONS.md` D-034 added (tool-calling loop design, MAX_ROUNDS defense)

**PR**
- [x] Commit, push to `feat/18-chatbot-core`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.2 in CLAUDE.md / Checklist.md

---

## Phase 4.3 closeout checklist
### Branch: `feat/19-memory`

**Dependencies**
- [x] No new pip deps — `redis`, `numpy`, `sqlalchemy[asyncio]` already in `pyproject.toml`

**DB model**
- [x] `app/db/models/memory_long.py` — `memory_type: Mapped[str]` column added (VARCHAR 32, server_default `'episodic'`)
- [x] Alembic migration `7e637234595f_memory_long_add_memory_type.py` — manually written (autogenerate had HNSW false-positive); adds `memory_type VARCHAR(32) NOT NULL DEFAULT 'episodic'`

**Domain model**
- [x] `app/domain/memory.py` — `MemoryType = Literal["episodic","semantic","procedural"]`, `MemoryEntry` Pydantic model with `model_config = {"from_attributes": True}`

**Memory modules**
- [x] `app/memory/__init__.py` created — empty package marker
- [x] `app/memory/short_term.py` — `append_message`, `get_history`, `clear`; `_TTL_SECONDS=86400`, `_MAX_MESSAGES=50`; key pattern `conv:{cid}:messages`; RPUSH+LTRIM+EXPIRE in one pipeline
- [x] `app/memory/long_term.py` — `write_entry` (embed+insert MemoryLong+AuditLog+commit), `search` (pgvector `<=>` cosine KNN), `list_entries` (ORM select ordered desc); lazy `embed_query` import inside functions

**Redis in lifespan**
- [x] `app/core/lifespan.py` — `aioredis.from_url(secrets.redis.url, decode_responses=True)` stored as `app.state.redis_client`; `await app.state.redis_client.aclose()` on shutdown

**Loop + service wiring**
- [x] `app/chatbot/loop.py` — new params: `conversation_id`, `redis_client`, `user_id`, `request_id`, `trace_id`; loads Redis history at start; appends assistant response on `end_turn`; passes `user_id/request_id/trace_id` to `execute_tool`
- [x] `app/services/chat_service.py` — new params: `user_id`, `redis_client`, `request_id`, `trace_id`; generates UUID for `conversation_id` when none provided
- [x] `app/api/chat.py` — reads `redis_client` from `app.state`; reads `request_id/trace_id` from `request.state`; passes `user_id=user.id` to service
- [x] `app/chatbot/tools.py` — `execute_write_memory` stub replaced with real `write_entry` call; `execute_tool` accepts `user_id/request_id/trace_id` kwargs

**Tests**
- [x] `tests/test_short_term_memory.py` — 6 tests; pipeline mock uses `MagicMock` for rpush/ltrim/expire (sync), `AsyncMock` only for execute
- [x] `tests/test_long_term_memory.py` — 4 tests; patches `app.rag.embedder.embed_query` (not caller namespace)
- [x] `tests/test_memory_recall.py` — 1 graded cross-conversation recall test; real embeddings; only DB session mocked
- [x] `tests/test_chatbot_loop.py` — updated; added `_mock_redis()`, `_run_stream_kwargs()` helper, `_CONV_ID/_USER_ID`; added `test_loop_loads_history_from_redis`
- [x] `tests/test_chatbot_tools.py` — `test_write_memory_stub_returns_ok` replaced with `test_write_memory_calls_long_term_and_returns_entry_id`
- [x] `tests/test_chat_endpoint.py` — `app.state.redis_client = MagicMock()` added to autouse fixture; `user_id is not None` assertion added
- [x] Final pytest count: **87 passed, 3 skipped**

**CI gates**
- [x] `ruff check` — all passed
- [x] `mypy app/ --ignore-missing-imports` — Success: no issues found in 54 source files

**Key decisions**
- [x] D-023 — Redis TTL 24 h, sliding window 50 messages — defended in DECISIONS.md
- [x] D-024 — Default memory type `episodic` (write_memory is explicit-only; stated facts are episodic); pgvector rationale — defended in DECISIONS.md

**Deliverables**
- [x] `deliverables/DECISIONS.md` D-023 added (TTL 24h, window 50, rationale)
- [x] `deliverables/DECISIONS.md` D-024 added (episodic default, pgvector over external vector store)
- [x] `deliverables/ARCH.md` §8 updated with full short-term + long-term memory design
- [x] `CLAUDE.md` status updated to Phase 4.3 on `feat/19-memory`

**PR**
- [x] Commit, push to `feat/19-memory`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.3 in CLAUDE.md / Checklist.md

---

## Phase 4.4 closeout checklist
### Branch: `feat/20-streamlit`

**Backend — new endpoint**
- [x] `backend/app/api/memory.py` — `GET /memory/entries`; auth-gated via `current_active_user`; returns `list[MemoryEntryOut]` (id, content, memory_type, created_at — no user_id in response)
- [x] `backend/app/main.py` — `memory_router` wired in
- [x] `backend/app/chatbot/loop.py` — `max_tokens` increased 1024 → 2048 (fix for `[unexpected stop reason: max_tokens]` truncation)

**Backend tests**
- [x] `backend/tests/test_memory_endpoint.py` — 2 tests: authenticated returns list, unauthenticated returns 401; `get_jwt_strategy` overridden in autouse fixture (same pattern as chat endpoint tests)
- [x] Final pytest count: **89 passed, 3 skipped**

**Frontend-admin**
- [x] `frontend-admin/app.py` — login form (email + password → `POST /auth/jwt/login`); JWT stored in `st.session_state`; sidebar shows `Logged in as: {email}` + Logout button on all pages; already-logged-in users see a "go to Chat" prompt
- [x] `frontend-admin/utils/api_client.py` — `login()`, `send_message_stream()`, `get_memory_entries()`; SSE parsed manually with `requests` + `stream=True` + `iter_lines()`; no sseclient-py dependency
- [x] `frontend-admin/utils/auth_guard.py` — `require_auth()` shared by all pages: stops page if no token, renders sidebar email + Logout button
- [x] `frontend-admin/pages/chat.py` — `st.chat_input` + `st.write_stream()` consuming `send_message_stream()`; conversation_id generated client-side on first turn; `st.caption(f"Conversation: {conversation_id}")` displayed after each response; New Conversation button resets state
- [x] `frontend-admin/pages/memory.py` — read-only list of long-term memory entries from `GET /memory/entries`; rendered as expandable cards; Refresh button
- [x] `frontend-admin/pages/widget_config.py` — placeholder; "Widget configuration coming in Phase 4.6"
- [x] `frontend-admin/requirements.txt` — `streamlit>=1.40.0`, `requests>=2.32.0`
- [x] `frontend-admin/pyproject.toml` — deps updated; `[tool.pytest.ini_options]` added with `pythonpath = ["."]`

**Frontend-admin tests**
- [x] `frontend-admin/tests/test_api_client.py` — 4 tests: `login()` returns token on 200, raises on 400; `get_memory_entries()` returns list on 200, raises on 401; all using `unittest.mock.patch` over `requests`

**Deliverables**
- [x] `deliverables/ARCH.md` §13.1 updated — full Streamlit app description: pages, SSE approach, new endpoint, running instructions

**PR**
- [x] Commit, push to `feat/20-streamlit`, PR opened
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.4 in CLAUDE.md / Checklist.md

---

## Phase 4.5 closeout checklist
### Branch: `feat/21-react-widget`

**Widget build**
- [x] `frontend-widget/vite.config.js` — iife library mode, `entry: src/main.jsx`, `fileName: () => 'widget.js'`, `outDir: ../backend/app/static`, `inlineDynamicImports: true`; Preact alias (`react` → `preact/compat`); jsdom test environment
- [x] `frontend-widget/package.json` — `preact ^10.29.2` only runtime dep; `@testing-library/preact ^3.2.4` for tests
- [x] Bundle size: **25.14 KB raw / 10.16 KB gzipped** (Vite production build, measured)
- [x] Previous React + ReactDOM baseline: ~144 KB gzipped; Preact delivers 93% reduction

**Widget source**
- [x] `frontend-widget/src/main.jsx` — IIFE entry; reads `data-widget-id` from `document.currentScript` or `window.__WIDGET_DEV_CONFIG__` fallback (ES module dev mode); mounts into Shadow DOM
- [x] `frontend-widget/src/Widget.jsx` — bubble toggle, config fetch with `DEFAULT_CONFIG` fallback; `styles.css` injected as `<style>` inside shadow root via `?inline` import
- [x] `frontend-widget/src/ChatPanel.jsx` — panel header ("Maintainer's Copilot"), message list, input row with send button
- [x] `frontend-widget/src/Message.jsx` — renders user/assistant messages; typing indicator for streaming state
- [x] `frontend-widget/src/useSSEChat.js` — `fetch` + `response.body.getReader()` + `TextDecoder({stream:true})` for SSE over POST; `[DONE]` sentinel handling; error caught → "Unable to connect. Please try again."
- [x] `frontend-widget/src/api.js` — `fetchConfig()`, `createChatStream()`, `DEFAULT_CONFIG` (theme: dark, greeting: "Hello! How can I help?", enabled_tools: ["retrieve_docs"])
- [x] `frontend-widget/index.html` — dev harness; sets `window.__WIDGET_DEV_CONFIG__` before loading `src/main.jsx` as ES module

**Backend changes**
- [x] `backend/app/infra/auth.py` — `get_widget_user`: validates UUID format, returns system user `00000000-0000-0000-0000-000000000001`; `get_current_user_or_widget`: tries Bearer JWT first via `strategy.read_token`, falls back to `get_widget_user`
- [x] `backend/app/api/chat.py` — `/chat/send` dependency changed from `current_active_user` to `get_current_user_or_widget`
- [x] `backend/app/main.py` — `StaticFiles` mounted at `/static` from `app/static`; `widget.js` confirmed at `GET /static/widget.js` → 200

**Backend tests**
- [x] `backend/tests/test_widget_auth.py` — 6 tests: `get_widget_user` (valid UUID, invalid UUID, missing); `/chat/send` integration (valid widget_id → 200, invalid UUID → 403, no auth → 403)
- [x] `backend/tests/test_static_files.py` — 1 test (skipped if widget.js absent)
- [x] `backend/tests/test_chat_endpoint.py` — auth_override fixture updated to override `get_current_user_or_widget`; `test_send_message_requires_auth` updated: no-auth now returns 403 (not 401) because `get_widget_user` raises 403
- [x] Final pytest count: **96 passed, 3 skipped**

**Frontend tests**
- [x] `frontend-widget/src/__tests__/Widget.test.jsx` — 2 tests: renders bubble, opens panel on click
- [x] `frontend-widget/src/__tests__/useSSEChat.test.js` — 3 tests: initial state, successful stream, error → "Unable to connect. Please try again."
- [x] `frontend-widget/src/__tests__/api.test.js` — 3 tests: `fetchConfig` success, fallback on failure, `createChatStream` constructs correct URL
- [x] Final vitest count: **8 passed**

**Manual verification (Playwright headless Chromium)**
- [x] `http://localhost:5174` loads with heading "Widget Dev Harness"
- [x] 🤖 bubble appears in Shadow DOM at `.widget-bubble`
- [x] Click bubble → `.chat-panel` opens with header "Maintainer's Copilot" and close button
- [x] Greeting "Hello! How can I help?" present as `.message.assistant`
- [x] Type "hello" + Enter → `.message.user` with "hello" appears
- [x] Panel closes on ✕ click; bubble reappears cleanly
- [x] CORS block on config + chat fetch → widget falls back gracefully (default config, "Unable to connect." error message)

**Deliverables**
- [x] `deliverables/DECISIONS.md` D-025 — iife rationale, Preact vs React numbers (144 KB → 10.16 KB), Shadow DOM isolation, fetch+ReadableStream for SSE POST, widget_id auth stub, CSP frame-ancestors deferred to Phase 4.6 with rationale
- [x] `deliverables/ARCH.md` §13.2 — full React widget design: bundle format, Preact, Shadow DOM, SSE approach, auth, config fallback, CSP deferral, dev harness instructions, file layout

**PR**
- [x] Commit on `feat/21-react-widget` ✅ (done)
- [x] Push to remote, open PR
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.5 in CLAUDE.md / Checklist.md

---

## Phase 4.6 closeout checklist
### Branch: `feat/22-widget-config`

**Database migration**
- [x] `alembic/versions/b3e9f1a2c4d5_widgets_add_owner_theme_greeting_tools.py` — adds `owner_id UUID FK→users CASCADE`, `theme VARCHAR(16) DEFAULT 'dark'`, `greeting TEXT DEFAULT 'Hello! How can I help?'`, `enabled_tools JSON DEFAULT '["retrieve_docs"]'`; creates `ix_widgets_owner_id`; `owner_id` nullable so existing rows survive
- [x] `app/db/models/widgets.py` rewritten — `owner_id`, `allowed_origins ARRAY(String)`, `theme`, `greeting`, `enabled_tools JSON`, `created_at`
- [x] Migration ran cleanly; `\d widgets` confirmed in live DB

**Widget API**
- [x] `app/repositories/widgets.py` — `create_widget`, `get_widget`, `update_widget`, `list_widgets_for_owner`, `load_allowed_origins` (returns `set[str]`, union across all rows)
- [x] `app/api/widgets.py` — routes: `GET /widgets/mine`, `POST /widgets/` (superuser only), `GET /widgets/{id}/config` (public — no auth; `allowed_origins` never in response), `GET /widgets/{id}`, `PATCH /widgets/{id}`; `_refresh_state()` called after POST and PATCH to update `app.state.allowed_origins` live without restart
- [x] `app/main.py` — `widgets_router` included

**Dynamic CORS middleware (D-026)**
- [x] `app/api/cors.py` — pure ASGI `DynamicCORSMiddleware`; reads `app.state.allowed_origins` from `scope["app"]` at every request; non-preflight: injects `Access-Control-Allow-Origin` + `Access-Control-Allow-Credentials` if origin allowed; OPTIONS preflight: 204 + full headers if allowed, 204 + no headers if blocked (passive block — no 403); SSE-safe (only touches `http.response.start`, not body frames)
- [x] `app/main.py` — `app.add_middleware(DynamicCORSMiddleware)` first, before `RequestContextMiddleware`
- [x] Allowed origins seeded into `app.state.allowed_origins` in `core/lifespan.py` at startup

**frame-ancestors CSP on widget.js (D-027)**
- [x] `GET /widget.js` dedicated FastAPI route (NOT `/static/widget.js` — Starlette mount takes routing priority over explicit routes under the mount prefix regardless of registration order); sets `Content-Security-Policy: frame-ancestors 'self' <sorted allowed_origins>`
- [x] `StaticFiles` mount removed (no other files needed serving)
- [x] `_LOADER_JS` inline in `main.py`: `GET /loader.js`; injects `widget.js` from `apiBase + '/widget.js'`

**get_widget_user upgrade (Phase 4.6 DB-backed)**
- [x] `app/infra/auth.py` — `get_widget_user` now takes `session: AsyncSession = Depends(get_async_session)`; does real DB lookup via `get_widget()`; fetches owner `User`; checks `owner.is_active`; returns 403 if widget not found, owner absent, or owner inactive
- [x] `get_current_user_or_widget` passes session to `get_widget_user`

**Streamlit widget config page**
- [x] `frontend-admin/pages/widget_config.py` — full form: name, theme selectbox, greeting text, enabled_tools multiselect, allowed_origins textarea; loads existing widgets via `get_my_widgets()`; shows embed snippet after create/update
- [x] `frontend-admin/utils/api_client.py` — `create_widget()`, `update_widget()`, `get_my_widgets()` added

**Demo host + bootstrap**
- [x] `demo/host/public/index.html` — updated to fixed UUID `00000000-0000-0000-0001-000000000001`; comment updated to point at bootstrap_widget.py
- [x] `backend/scripts/__init__.py` — created (enables `python -m scripts.bootstrap_widget`)
- [x] `backend/scripts/bootstrap_widget.py` — idempotent; creates demo widget with `DEMO_WIDGET_ID = "00000000-0000-0000-0001-000000000001"`; owner = `admin@maintainer-copilot.dev`; `allowed_origins: ["http://localhost:8080"]`; skips if already exists

**Tests**
- [x] `backend/tests/test_widget_auth.py` — rewritten for Phase 4.6 real DB lookup: 4 unit tests (`get_widget_user` valid, not found, invalid UUID, missing) + 3 integration tests through `/chat/send`; patches `get_widget`, passes mock session explicitly
- [x] `backend/tests/test_widgets_api.py` — 8 tests: CRUD endpoints, create requires admin, config public (no `allowed_origins` in response), frame-ancestors header on `/widget.js`, no-origins → `'self'` only, loader.js served
- [x] `backend/tests/test_cors.py` — 5 tests: allowed origin gets header, blocked origin no header, no origin no header, preflight allowed (204 + full headers), preflight blocked (204 + no headers)
- [x] Final pytest count: **110 passed, 3 skipped**

**Playwright verification**
- [x] `http://localhost:8080` loads demo host, widget bubble appears (Shadow DOM `.widget-bubble`)
- [x] Click bubble → panel opens, greeting "Hello! I'm the Maintainer's Copilot…" appears
- [x] Type "hello" → LLM streams real response (confirmed via Shadow DOM query)
- [x] Zero console errors; zero CORS errors in network tab
- [x] `curl -v http://localhost:8000/widget.js` → `content-security-policy: frame-ancestors 'self' http://localhost:8080`

**Key decisions**
- [x] D-026 — Pure ASGI CORS middleware, DB-driven, SSE-safe; `scope["app"]` access pattern; passive OPTIONS block
- [x] D-027 — `frame-ancestors` on dedicated `/widget.js` route (not StaticFiles); Starlette mount priority bug documented

**Deliverables**
- [x] `deliverables/DECISIONS.md` D-026 + D-027 added
- [x] `deliverables/SECURITY.md` §8 rewritten — §8.1 CORS allowlist, §8.2 frame-ancestors, §8.3 widget auth
- [x] `deliverables/ARCH.md` §13.3 updated
- [x] `deliverables/RUNBOOK.md` §6 updated with bootstrap_widget step and 4-step pre-demo sequence

**PR**
- [x] Commit on `feat/22-widget-config`
- [x] Push to remote, open PR (#20)
- [x] CI green
- [x] Squash merged
- [x] Local branch deleted
- [x] `git pull` on main
- [x] Tick Phase 4.6 in CLAUDE.md / Checklist.md

---

## Phase 4.7 closeout checklist
### Branch: `feat/23-demo-validation`

**Block/allow demo infrastructure**
- [x] `demo/blocked/blocked.html` — serves from `http://localhost:8090`; explains CSP enforcement; widget embed intentionally included so browser can block it
- [x] `docker-compose.yml` — `blocked-host` service added: `image: nginx:1.27-alpine`, port `8090:80`, volume `./demo/blocked:/usr/share/nginx/html:ro`; `http://localhost:8090` intentionally NOT in `allowed_origins`
- [x] Confirmed: `http://localhost:8090/blocked.html` serves correctly; browser blocks widget embed with `frame-ancestors` CSP violation

**Memory recall demo script**
- [x] `backend/scripts/demo_memory_recall.py` — hybrid write-via-API / recall-via-search:
  - Step 1: POST to `/chat/send?widget_id=...` with "Please remember..." → Claude calls `write_memory` → entry persisted in pgvector
  - Step 2: `search()` from `app.memory.long_term` with semantically different query → asserts written entry recalled
  - Looks up admin user_id from DB for `search()` scoping
  - Prints structured PASS/FAIL output; includes NOTE about `search_memory` tool deferral to Phase 5
- [x] Demo run output (2026-05-23): Claude replied "Got it, Alex! I've saved that…" ✅ write_memory called; pgvector recalled 2 matching entries ✅ PASS

**Eval gates — both green on current codebase**
- [x] Classification gate (`uv run pytest -m eval tests/test_eval_classification.py -v -s`):
  - macro-F1: **1.0000** ✓ (threshold 0.90)
  - All 4 classes: **1.0000** ✓ (threshold 0.50 per class)
  - Runtime: 15.31s, 1 passed
- [x] RAG gate (`DATABASE_URL=postgresql://... uv run pytest -m eval tests/test_eval_rag.py -v -s`):
  - hit@5: **0.9583** (23/24) ✓ (threshold 0.8583)
  - MRR@10: **0.8139** ✓ (threshold 0.7532)
  - Runtime: 85.95s, 1 passed
  - Note: RAG gate requires `postgresql://` (not `postgresql+asyncpg://`) — psycopg2 used by BM25 index builder
- [x] Both measured numbers recorded verbatim in RUNBOOK.md §6.2 step 9

**RUNBOOK.md §6 — Friday demo script**
- [x] §6.1 Prerequisites: 4-step setup sequence (compose up → bootstrap_admin → bootstrap_widget → rebuild host)
- [x] §6.2 10-step demo flow (1 min each):
  1. Architecture overview — docker-compose.yml, 11 services, secrets/artifacts/traces
  2. Refuse-to-boot proof — lifespan.py startup checks
  3. Classification demo — Swagger `/classify`, three-model comparison (D-012)
  4. Streamlit chat + tool-calling — issue text, tool spans, Langfuse trace tree
  5. Memory write + recall — `write_memory` in session A, Memory Inspector, `demo_memory_recall.py` PASS output
  6. Widget Config — form, embed snippet, no-restart live update
  7. Allowed origin demo — localhost:8080, bubble + SSE streaming, DevTools `frame-ancestors` header
  8. Blocked origin demo — localhost:8090/blocked.html, no bubble, console CSP violation
  9. Eval gates — `eval_thresholds.yaml`, measured numbers table (macro-F1 1.0, hit@5 0.9583)
  10. Redaction proof — `test_redaction.py` 8 passed, `sk-test-FAKE-not-real` never unredacted
- [x] §6.3 Fallback talking points — widget doesn't load (curl widget.js), chat doesn't stream (Swagger), blocked host silent (curl OPTIONS with evil.com origin)
- [x] §6.4 URL reference table — includes blocked-host at 8090

**Deliverables**
- [x] `deliverables/RUNBOOK.md` §6 rewritten as full numbered Friday demo script
- [x] `CLAUDE.md` status updated — "Sections 1–4 complete, Section 5 starting"

**PR**
- [ ] Commit on `feat/23-demo-validation`
- [ ] Push to remote, open PR
- [ ] CI green
- [ ] Squash merged
- [ ] Local branch deleted
- [ ] `git pull` on main
- [ ] Tick Phase 4.7 in CLAUDE.md / Checklist.md
- [ ] **Section 4 complete** — all 7 phases (4.1 through 4.7) merged to main
