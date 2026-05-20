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

---

## 2. Agent Directives & Current Status

**Execution Rule**: Always act as a technical planner first. For complex tasks, propose a step-by-step implementation plan and wait for my approval before executing code changes. Once approved, write the code.

**Status**: Section 1 (foundations) and Section 2 (DL track) are complete and merged. We're now on Section 3 (advanced RAG). Branch is `feat/12-rag-corpus`, on Phase 3.1.

Before suggesting any work, read these files in order:
1. `Checklist.md` — Read this to understand the granular step-by-step progress and exactly which checklist items have been completed so far. **You are responsible for maintaining this file. Update it whenever we start or finish a new phase.**
2. `deliverables/DECISIONS.md` — every architectural decision (D-001 through D-014) with rationale and numbers
3. `deliverables/ARCH.md` — system overview and layer rules
4. `deliverables/RUNBOOK.md` §1, §2, §4 — startup, refuse-to-boot, eval running
5. `backend/eval_thresholds.yaml` — committed CI gates

---

## 3. Locked-In Decisions

| Decision | Choice | Detail |
|---|---|---|
| Dataset source | `scikit-learn/scikit-learn` GitHub repo (closed issues + docs) | `deliverables/DECISIONS.md` D-002 |
| LLM provider | Anthropic Claude (only) | `deliverables/DECISIONS.md` D-003 |
| Tracing backend | Langfuse, self-hosted in compose | `deliverables/DECISIONS.md` D-004 |
| Package manager | `uv` | `deliverables/DECISIONS.md` D-005 |
| Frontend folders | `frontend-admin/` (Streamlit), `frontend-widget/` (React) | `deliverables/DECISIONS.md` D-006 |
| Layered backend | `api / services / repositories / domain / infra / db` plus task subfolders | `deliverables/ARCH.md` §4, `deliverables/DECISIONS.md` D-001 |
| Issue label mapping | bug/feature/docs/question via aliases | `deliverables/DECISIONS.md` D-007 |
| Classifier deployment | Claude Haiku 4.5 (chatbot), DistilBERT (modelserver proof) | `deliverables/DECISIONS.md` D-012 |
| LLM model strings | `claude-haiku-4-5`, `claude-sonnet-4-6` | `deliverables/DECISIONS.md` D-011, D-012 |
| NER model | `dslim/bert-base-NER` from HF Hub | `deliverables/DECISIONS.md` D-014 |
| Summarizer | Claude Haiku 4.5 via Anthropic SDK | `deliverables/DECISIONS.md` D-014 |
| Eval threshold floor | classification.macro_f1 ≥ 0.90, per-class ≥ 0.50 | `deliverables/DECISIONS.md` D-013 |

---

## 4. Project Rules (From the Brief, Memorized)

These are graded. Do not violate.

1. **No vibe coding.** Every line shipped is understood, every library justified. Friday review asks about it.
2. **The architecture is the grade.** Layers respected (api/services/repositories/domain/infra/db split), secrets in Vault, blob in MinIO, traces visible, logs redacted, exceptions handled.
3. **The evals are the grade.** CI must be green before merge. A great chatbot without working eval CI gates scores below a worse one whose CI fails on regression. 
4. **Every decision is backed by a number.** Embedding model, chunking strategy, deployment choice, retrieval weighting — every choice in DECISIONS.md is backed by a number on a golden set.
5. **Logs are redacted, traces are real.** A redaction test proves the first. A trace tree demo proves the second.

---

## 5. Engineering Conventions

- `uv` for package management; `uv lock && uv sync` after dep changes.
- ruff + ruff format + mypy + pytest all green locally before pushing.
- mypy: pin every `# type: ignore` to specific codes like `[no-untyped-call]`, never blanket.
- Squash merge always; commit messages use conventional commits with one-line summary + body.
- Decisions go in deliverables/DECISIONS.md as the work happens, not at end of phase.
- Refuse-to-boot pattern: api/modelserver crash early if dependencies misconfigured (Vault, MinIO SHA, eval thresholds).
- Anthropic API key in Vault under `secrets.anthropic.api_key`.
- Models in use: `claude-haiku-4-5` (chatbot tools), `claude-sonnet-4-6` (comparison only); DistilBERT in modelserver for the engineering proof.

**Don't do**:
- Don't introduce OpenAI or other LLM providers (D-003 locks us to Anthropic).
- Don't add per-line `# type: ignore` without a specific error code.
- Don't push without local CI green.
- Don't write `# TODO: figure this out later` — finish the phase or have an explicit DECISIONS entry on the deferral.

---

## 6. Repository Layout

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

## 7. Phase Breakdown

Five sections (one per day). 26 phases total. Each phase = one branch, one PR, CI green, merge, tick off.

Branch naming: `feat/<NN>-<short-slug>`, e.g. `feat/01-foundations`, `feat/06-dataset-fetch`, `feat/14-rag-eval-golden`.
Commit style: conventional commits.
PR template: lives at `.github/pull_request_template.md` (added in Phase 1.1).

---

### Section 1 — Foundations (Monday) · 6 phases (COMPLETED)
(Phases 1.1 through 1.6 are complete. See Checklist.md for granular details).
---

### Section 2 — Deep Learning Track (Tuesday) · 5 phases (COMPLETED)
(Phases 2.1 through 2.5 are complete. See Checklist.md for granular details).

---

### Section 3 — Advanced RAG (Wednesday) · 5 phases (CURRENT)

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
(Details omitted for brevity until Section 3 is complete).
---

### Section 5 — Polish + Present (Friday) · 3 phases
(Details omitted for brevity until Section 4 is complete).
---

## 8. Working Style (For the Agent)

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
