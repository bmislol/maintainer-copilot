# CLAUDE.md

Working guide for the AI assistant collaborating on this project. Read top-to-bottom before any session.

---

## 1. Project: Maintainer's Copilot

An authenticated chatbot that an open-source maintainer talks to when triaging incoming issues. Built solo over five days as Week 7 of the AIE Program.

The chatbot:

- **Classifies** issues into bug / feature / docs / question using three models compared on the same test set (classical ML, fine-tuned transformer, Claude LLM baseline).
- **Extracts entities** (NER) — function names, file paths, error codes, version strings.
- **Summarizes** long issue threads.
- **Answers questions** via advanced RAG over the project's docs and a held-out slice of resolved issues with maintainer answers.
- **Remembers** — short-term within a conversation (Redis), long-term across conversations (pgvector, with audit-logged writes).

It runs in two places that share one FastAPI backend:

- **Streamlit admin app** (`frontend-admin/`) for the maintainer: login, full chat, memory inspector, widget configuration.
- **React widget** (`frontend-widget/`) that any host site embeds via a single `<script>` tag. The widget is the production-shaped surface; Streamlit is the internal tool.

Quality is enforced by **two golden eval sets** (classification + RAG) that fail CI when you regress. Architecture is graded the same as Week 6: secrets in Vault, blob in MinIO, layered code, traces in Langfuse, logs redacted before they leave a service boundary.

For the full flow diagram, layer rules, endpoint inventory, and refuse-to-boot logic, see `deliverables/ARCH.md`.

---

## 2. Locked-In Decisions

| Decision | Choice | Detail |
|---|---|---|
| Dataset source | `scikit-learn/scikit-learn` GitHub repo (closed issues + docs) | `deliverables/DECISIONS.md` D-002 |
| LLM provider | Anthropic Claude (only) | `deliverables/DECISIONS.md` D-003 |
| Tracing backend | Langfuse, self-hosted in compose | `deliverables/DECISIONS.md` D-004 |
| Package manager | `uv` | `deliverables/DECISIONS.md` D-005 |
| Frontend folders | `frontend-admin/` (Streamlit), `frontend-widget/` (React) | `deliverables/DECISIONS.md` D-006 |
| Layered backend | `api / services / repositories / domain / infra / db` plus task subfolders | `deliverables/ARCH.md` §4, `deliverables/DECISIONS.md` D-001 |

---

## 3. Project Rules (From the Brief, Memorized)

These are graded.

1. **No vibe coding.** Every line shipped is understood. Friday review asks about it.
2. **The architecture is the grade.** A working chatbot in a tangled codebase scores below a slightly-worse one in a clean codebase. Layers respected, secrets in Vault, blob in MinIO, traces visible, logs redacted, exceptions handled.
3. **The evals are the grade.** A great chatbot without working eval CI gates scores below a worse one whose CI fails on regression. Committed thresholds mean something.
4. **Every decision is backed by a number.** Embedding model, chunking strategy, deployment choice, retrieval weighting — every choice in DECISIONS.md is backed by a number on the golden set.
5. **Logs are redacted, traces are real.** A redaction test proves the first. A trace tree demo proves the second.

---

## 4. Repository Layout

```text
.
├── backend/
│   └── app/
│       ├── api/             # HTTP routers only
│       ├── services/        # Business logic, tool orchestration, cache/memory invalidation
│       ├── repositories/    # SQL via async SQLAlchemy
│       ├── domain/          # Pydantic domain models
│       ├── infra/           # Vault, Redis, MinIO, LLM, Langfuse, redaction adapters
│       ├── db/              # SQLAlchemy ORM models, sessions, Alembic migrations
│       ├── rag/             # Chunking, hybrid retrieval, rerank, query transform
│       ├── chatbot/         # Tool-calling loop, tool registry, prompt loading
│       ├── memory/          # Short-term (Redis) and long-term (pgvector) memory
│       ├── eval/            # Golden sets, eval harnesses
│       ├── prompts/         # Versioned prompt files
│       └── core/            # Config, logging, lifespan, shared errors
├── frontend-admin/          # Streamlit
├── frontend-widget/         # React + Vite, single bundled JS file
├── demo/host/               # One HTML page + nginx — Friday embed-demo target
├── deliverables/            # ARCH, DECISIONS, RUNBOOK, EVALS, SECURITY, LICENSES
├── .github/workflows/       # lint, type-check, tests, eval gates, smoke
├── docker-compose.yml
├── .env.example
├── eval_thresholds.yaml     # Committed thresholds — CI fails on regression
└── CLAUDE.md
```

The full layer-by-layer rule table is in `deliverables/ARCH.md` §4.

---

## 5. Phase Breakdown

Five sections (one per day). 26 phases total. Each phase = one branch, one PR, CI green, merge, tick off.

Branch naming: `feat/<NN>-<short-slug>`, e.g. `feat/01-foundations`, `feat/06-dataset-fetch`, `feat/14-rag-eval-golden`.
Commit style: conventional commits.
PR template: lives at `.github/pull_request_template.md` (added in Phase 1.1).

---

### Section 1 — Foundations (Monday) · 6 phases

#### Phase 1.1 · Repo skeleton + Git setup

- Create folder layout per §4.
- `.gitignore`, conventional-commit guide, PR template.
- Branch protection on `main` (CI required, linear history, squash merge).
- First commit on `feat/01-foundations`.

**Deliverables updated:** none yet — structure only.

- [x] Phase 1.1 - done

#### Phase 1.2 · Python tooling + first CI 

- `uv` initialised. `pyproject.toml` for `backend/` (api), `backend/` (modelserver shares deps), and `frontend-admin/`.
- Dev deps: `ruff`, `mypy`, `pytest`, `pytest-asyncio`.
- Configs: `ruff.toml` (or `[tool.ruff]` in pyproject), `mypy.ini`, `pytest.ini`.
- `.github/workflows/ci.yml`: lint + format-check + type-check + unit-test jobs.
- First green CI run on the open PR for Phase 1.1.

**Deliverables updated:** none.

- [x] Phase 1.2 - done

#### Phase 1.3 · docker-compose skeleton (every service stubbed)

- `docker-compose.yml` declares: `api`, `modelserver`, `chatbot`, `widget`, `host`, `migrate`, `db`, `redis`, `minio`, `vault`, `langfuse`, plus init containers (`vault-init`, `minio-init`).
- Every service has a working Dockerfile and a `/healthz` endpoint returning 200 (FastAPI services) or a static page (host).
- `cp .env.example .env && docker compose up --build` boots clean from a fresh clone.

**Deliverables updated:** `deliverables/RUNBOOK.md` §1 (access points + startup order), `deliverables/ARCH.md` §2 (services table — confirm ports).

- [x] Phase 1.3 - done

#### Phase 1.4 · Vault + Alembic baseline

- `app/infra/vault.py` with `load_secrets()` called from API lifespan startup.
- `vault-init` seeds dev secrets into KV v2 per `deliverables/SECURITY.md` §3.
- API refuses to boot if Vault is unreachable (test it locally: stop vault, restart api, observe refusal).
- Alembic baseline migration creates empty tables: `users`, `conversations`, `messages`, `widgets`, `audit_log`, `memory_long`. Exact fields per phase that owns them.
- `migrate` service runs `alembic upgrade head` and exits before `api` boots.

**Deliverables updated:** `deliverables/SECURITY.md` §3, §9 (refuse-to-boot), `deliverables/ARCH.md` §9.

- [x] Phase 1.4 - done

#### Phase 1.5 · Langfuse + structured logging

- `app/infra/tracing.py` wraps the Langfuse SDK.
- `langfuse` service in compose with first-boot signup, project + keys created, keys written into Vault by `vault-init`.
- Every request gets a `request_id` (UUID v4) and a Langfuse `trace_id`. A test span is emitted on `/healthz`.
- Structured JSON logger (`app/core/logging.py`) emits both IDs on every line.

**Deliverables updated:** `deliverables/ARCH.md` §12 (logging + tracing).

- [x] Phase 1.5 - done

#### Phase 1.6 · Dataset fetch + splits

- `scripts/fetch_issues.py` pulls closed issues from `scikit-learn/scikit-learn` via the GitHub API. Caches raw JSON to `backend/data/issues/raw/` (gitignored).
- `scripts/build_dataset.py` normalises issues → JSONL, applies the label → class mapping (defended in DECISIONS D-007).
- Stratified time-based split: test set is strictly more recent than train. Sizes recorded in DECISIONS D-008.
- Training data hash (SHA-256 of the sorted training JSONL) committed for the model card.
- (Optional but ideal) kick off Colab fine-tuning at end of day so it cooks overnight.

**Deliverables updated:** `deliverables/DECISIONS.md` D-007, D-008.

- [x] Phase 1.6 - done

---

### Section 2 — Deep Learning Track (Tuesday) · 5 phases

#### Phase 2.1 · Fine-tuned encoder + model card

- Train a small encoder (DistilBERT, MiniLM, or similar) on the splits from 1.6.
- Track training with a real run logger (W&B, MLflow, or TensorBoard logs to MinIO).
- Produce `model_card.json` per the schema in `deliverables/ARCH.md` §10.
- Push `classifier.pt` + `model_card.json` to MinIO; manifest with SHA-256 committed.
- `modelserver` loads the artifact at boot, refuses to start on SHA mismatch or `test_macro_f1` below threshold.

**Deliverables updated:** `deliverables/DECISIONS.md` D-009, `deliverables/ARCH.md` §10, `deliverables/EVALS.md` §1 (model entry).

- [x] Phase 2.1 - done

#### Phase 2.2 · Classical ML baseline

- TF-IDF + LogisticRegression (or LinearSVC) trained on the same splits.
- Same metrics surface; results stored in `backend/app/eval/classification/baselines/classical.json`.

**Deliverables updated:** `deliverables/DECISIONS.md` D-010, `deliverables/EVALS.md` §1.

#### Phase 2.3 · LLM baseline + three-way comparison

- Claude classification baseline using structured output (e.g. tool use returning the label). Prompt versioned under `app/prompts/`.
- Same metrics on the same test split.
- Three-way comparison written to DECISIONS D-012: accuracy, macro-F1, per-class F1, latency, cost.
- Deployment choice defended in one line.

**Deliverables updated:** `deliverables/DECISIONS.md` D-011, D-012, `deliverables/EVALS.md` §1.

#### Phase 2.4 · Classification golden set + CI gate

- 25-example golden set hand-curated, **not** drawn from train/val/test.
- `app/eval/classification/run_eval.py` runs all three classifiers against the golden set, writes `eval_report.json` to MinIO.
- `eval_thresholds.yaml` committed with real numbers (no zero/disabled entries — API refuses to boot if any is zero).
- `.github/workflows/eval-classification.yml` runs on every push and PR.

**Deliverables updated:** `deliverables/DECISIONS.md` D-013, `deliverables/EVALS.md` §1.4–§1.5.

#### Phase 2.5 · NER + summarizer

- NER tool: spaCy or a HF token classifier, fronted by a `modelserver` endpoint.
- Summarizer tool: pre-trained small model or a Claude-driven call, fronted by a `modelserver` endpoint.
- Both endpoints have healthchecks and are wired into compose.

**Deliverables updated:** `deliverables/DECISIONS.md` D-014, `deliverables/ARCH.md` §2.

---

### Section 3 — Advanced RAG (Wednesday) · 5 phases

#### Phase 3.1 · Corpus + embedding choice

- Build the RAG corpus: FastAPI docs (cloned) + held-out resolved-issues slice. Strict: held-out issues are not in classifier training.
- Preprocessing pipeline defended in DECISIONS D-016 prep (Markdown handling, code-block strategy, frontmatter strip).
- Pick an embedding model; compare against at least one alternative on the eventual golden set (or a quick proxy set if 3.4 is not landed yet). Record the retrieval-quality number.

**Deliverables updated:** `deliverables/DECISIONS.md` D-015.

#### Phase 3.2 · Smart chunking + pgvector

- Chunking strategy that is **not** naive fixed-size: pick semantic / structural / late-chunking and defend.
- pgvector tables and indexes live in Alembic.
- Naive dense baseline retrieval working — this is the number every subsequent phase has to beat.

**Deliverables updated:** `deliverables/DECISIONS.md` D-016, `deliverables/ARCH.md` §11.

#### Phase 3.3 · Hybrid + rerank + query transform + metadata filter

- BM25 sparse retrieval + dense retrieval, weighted (tuned on the golden set or proxy).
- Cross-encoder reranker over the top-k.
- Query transformation: HyDE or multi-query — pick one.
- Metadata filtering: at least one filter (e.g. `is_resolved`, `version`).

**Deliverables updated:** `deliverables/DECISIONS.md` D-017, D-018, D-019, D-020, `deliverables/ARCH.md` §11.

#### Phase 3.4 · RAG golden set + CI gate + judge agreement

- 25 triples (question / ideal answer / ground-truth chunks).
- Eval harness measures hit@5, MRR@10, faithfulness, answer relevancy.
- Hand-label 5 of 25; report human↔judge agreement in DECISIONS D-021.
- `eval_thresholds.yaml` updated with real RAG numbers.
- `.github/workflows/eval-rag.yml` runs on every push and PR.

**Deliverables updated:** `deliverables/DECISIONS.md` D-021, `deliverables/EVALS.md` §2.

#### Phase 3.5 · Redaction + exception handling

- `app/infra/redaction.py` with the defended pattern list.
- Called by the logger, the Langfuse adapter, the memory writer, before any string crosses the service boundary.
- Redaction test asserts that `sk-test-FAKE-not-real` never appears unredacted in logs, traces, short-term memory, or long-term memory.
- Domain exception hierarchy (`NotFoundError`, `PermissionDenied`, `ToolFailure`, etc.) distinct from infra exceptions.
- Single exception handler at the API boundary maps domain exceptions to structured HTTP errors with a `code` and `request_id`. Users never see a stack trace.

**Deliverables updated:** `deliverables/DECISIONS.md` D-022, `deliverables/SECURITY.md` §7.

---

### Section 4 — Chatbot + Memory + Embed (Thursday — heaviest day) · 7 phases

#### Phase 4.1 · Auth

- `fastapi-users` + JWT, signing key from Vault.
- Two roles: `user`, `admin`.
- Admin-invite-only registration (no public `/register`).
- Bootstrap scripts: `app.entrypoints.bootstrap_admin` and `bootstrap_admin_role`.
- End-to-end login test passing.

**Deliverables updated:** `deliverables/ARCH.md` §6, §7, `deliverables/SECURITY.md` §4, §5, `deliverables/RUNBOOK.md` §3.

#### Phase 4.2 · Chatbot core (single tool-calling LLM)

- One Claude tool-calling loop. Not a workflow. Not multi-agent.
- Tools registered: `classify_issue`, `extract_entities`, `summarize_thread`, `retrieve_docs`, `write_memory`.
- Prompts as versioned files in `app/prompts/`.
- Tool failures caught in services and recovered (return a user-visible "tool X is unavailable" assistant message; no 500).
- `/chat/send` endpoint streams the assistant reply.

**Deliverables updated:** `deliverables/ARCH.md` §5, §7.

#### Phase 4.3 · Memory (short + long)

- Short-term: Redis. TTL chosen and defended.
- Long-term: pgvector. Memory type (episodic / semantic / procedural) chosen and defended.
- `write_memory` is explicit only — never auto-write.
- Every long-term write produces an `audit_log` row with `actor`, `action`, `target`, `timestamp`, `request_id`, `trace_id`.
- Cross-conversation recall test: write a fact in conversation A, retrieve it in conversation B.

**Deliverables updated:** `deliverables/DECISIONS.md` D-023, D-024, `deliverables/ARCH.md` §8, `deliverables/SECURITY.md` §6.

#### Phase 4.4 · Streamlit admin app

- Login page (JWT).
- Full chat with streamed responses.
- Memory inspector (read-only list of own long-term entries).
- Admin-only widget configuration page that generates embed snippets.
- Fully demoable here before touching React.

**Deliverables updated:** `deliverables/ARCH.md` §13.1.

#### Phase 4.5 · React widget

- Vite build → single bundled JS file.
- Chat panel, input box, streamed messages, collapsible bubble.
- Theme + greeting + enabled-tools list pulled from `/widgets/{wid}/config` at runtime.
- One `postMessage` channel (at minimum for iframe resize).
- Bundle size measured (gzipped) and recorded for the submission block + DECISIONS D-025.

**Deliverables updated:** `deliverables/DECISIONS.md` D-025, `deliverables/ARCH.md` §13.2.

#### Phase 4.6 · Widget config + loader + demo host

- `widgets` table fields: `id`, `theme`, `greeting`, `enabled_tools`, `allowed_origins` (list).
- Admin Streamlit page creates/edits widget configs and shows the embed snippet.
- Loader at `/widget.js` reads `data-widget-id` and injects the iframe.
- CORS allowlist enforced from `allowed_origins`, not from env.
- `Content-Security-Policy: frame-ancestors` header set from `allowed_origins` on widget-bundle route.
- `demo/host/` is one HTML file plus nginx config; loads the widget.

**Deliverables updated:** `deliverables/ARCH.md` §13.3, `deliverables/SECURITY.md` §8.

#### Phase 4.7 · Block/allow demo + both eval suites green in CI

- Run the widget in `demo/host/` on the allowed origin → bubble appears, chat works.
- Run a second host page on a disallowed origin → browser blocks the embed; console shows `frame-ancestors` violation.
- Cross-conversation memory recall demo end-to-end.
- Both eval gates green on `main`.

**Deliverables updated:** `deliverables/RUNBOOK.md` §6 (demo flow).

---

### Section 5 — Polish + Present (Friday) · 3 phases

#### Phase 5.1 · Final deliverables pass

- Walk every deliverable file. Fill in any remaining placeholders.
- EVALS final-submission numbers table.
- LICENSES final dependency list.
- SECURITY redaction-pattern defenses written.
- DECISIONS — confirm every D-XXX is either Accepted or explicitly Superseded.

**Deliverables updated:** all of `deliverables/`.

#### Phase 5.2 · Final integration smoke + tag

- Fresh clone test from a clean machine (or `git clone` to a tempdir).
- `cp .env.example .env && docker compose up --build` — clean boot.
- Bootstrap admin, run the full demo flow.
- CI green on `main`.
- `git tag v0.1.0-week7` and push.

**Deliverables updated:** none new — verification only.

#### Phase 5.3 · Demo script + practice

- 10-minute walkthrough (see `deliverables/RUNBOOK.md` §6).
- Two practice runs end-to-end with a timer.

**Deliverables updated:** `deliverables/RUNBOOK.md` §6 (refined).

---

## 6. Deliverables Index

Where each file lives and what it covers:

| File | Covers | Maintained by phases |
|---|---|---|
| `deliverables/ARCH.md` | System overview, flow diagram, services, layer rules, data flow, endpoint inventory, memory plan, refuse-to-boot, classifier artifact contract, RAG architecture, tracing/logging, frontends, embed flow. | 1.3, 1.4, 1.5, 2.1, 2.5, 3.x, 4.x |
| `deliverables/DECISIONS.md` | Every D-XXX decision with context / decision / why / alternatives / trade-offs. | All phases |
| `deliverables/RUNBOOK.md` | Local startup, refuse-to-boot troubleshooting, admin bootstrap, running evals, reset, Friday demo flow, common issues. | 1.3, 1.4, 4.1, 4.7, 5.3 |
| `deliverables/EVALS.md` | Classification eval, RAG eval, redaction test, CI gates, final-submission numbers table. | 2.4, 3.4, 3.5, 5.1 |
| `deliverables/SECURITY.md` | Goals, Vault layout, auth, RBAC, audit log, redaction patterns + test, CORS + CSP, refuse-to-boot, defense notes. | 1.4, 3.5, 4.1, 4.3, 4.6, 5.1 |
| `deliverables/LICENSES.md` | Project license, dataset license, model licenses, Python deps, JS deps, infra images. | 5.1 (final pass), 2.1, 2.5, 3.1, 3.3, 4.5 (as deps land) |

---

## 7. Working Style (For the Agent)

- **No vibe coding.** Every code change explained, every chosen library justified. If unsure why a line exists, stop and ask.
- **One phase per branch.** Don't bleed across phases; if scope creep is needed, open a new branch.
- **Commit small, commit often.** Conventional commits.
- **Update deliverables in the same PR as the code.** Decisions are written when made, not at the end of the week.
- **CI must be green before merging.** Don't bypass.
- **Ask before making architectural changes.** Layer rules are graded — moving logic across layers is a decision, not a refactor.

---

## 8. Daily Quickstart

Each morning:

1. Pull `main`, confirm CI green.
2. Open today's section in CLAUDE.md §5.
3. Pick the next unticked phase, create the branch (`feat/<NN>-<slug>`).
4. Read the relevant deliverable section(s) to refresh context.
5. Work the phase. Commit. Push. Open PR.
6. Wait for CI green. Merge. Tick off the phase.
