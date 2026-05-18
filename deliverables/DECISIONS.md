# DECISIONS.md

Status: Baseline decisions document
Purpose: Record architecture and implementation decisions as the project evolves.

Each decision follows this format:

```text
## D-XXX: Decision title

Status: Proposed | Accepted | Rejected | Superseded
Date: YYYY-MM-DD

### Context
What problem are we solving?

### Decision
What did we decide?

### Why
Why this option?

### Alternatives Considered
- Option A
- Option B

### Trade-offs
What do we gain and what do we accept?
```

---

## D-001: Backend Layer Boundary

Status: Accepted
Date: 2026-05-18

### Context

The brief grades architecture, not just the working chatbot. It explicitly states: "The architecture is graded. Layers respected." The Friday review will ask for a new endpoint or tool to be added live, so the layer boundary has to be real and enforced.

### Decision

Use the following backend layers under `backend/app/`:

- `app/api/` — HTTP routers only.
- `app/services/` — business logic, transaction boundaries, cache and memory invalidation, tool orchestration.
- `app/repositories/` — SQL only via async SQLAlchemy.
- `app/domain/` — Pydantic domain models, enums, internal contracts.
- `app/infra/` — adapters for Vault, Redis, MinIO, the LLM provider, Langfuse, and the redaction layer.
- `app/db/` — SQLAlchemy ORM models, sessions, Alembic migrations.

Plus task-specific subfolders that follow the same rules: `app/rag/`, `app/chatbot/`, `app/memory/`, `app/eval/`, `app/prompts/`, `app/core/`.

### Why

The same standard as the Week 6 project. Routers stay thin and HTTP-only. Services own business rules. Repositories own SQL. Infra adapters wrap everything external. The boundary is testable and defensible in the live review.

### Trade-offs

More files early. Worth it for the grade and for staying sane during the chatbot phase when tool calls, RAG, and memory all need to compose cleanly.

---

## D-002: Dataset Source — `tiangolo/fastapi`

Status: Accepted
Date: 2026-05-18

### Context

The brief requires picking one open-source repo and using its closed issues as the classification dataset. The choice has to support: enough closed-issue volume for train/val/test splits, labels that map cleanly to bug / feature / docs / question, English-dominant text, and a public docs corpus for the RAG side.

### Decision

Use the `tiangolo/fastapi` GitHub repository as the dataset source. Closed issues are fetched via the GitHub REST API; the project's published documentation (the `docs/` directory of the repo, or the rendered docs site) is the RAG corpus.

### Why

- Thousands of closed issues with active maintainer labeling.
- Native labels map naturally: `bug` → bug, `feature` → feature, `docs` → docs, `question` → question.
- English-dominant.
- The docs site is large, well-structured Markdown — good RAG corpus.
- The persona ("FastAPI maintainer triaging issues") is the demo. The story writes itself.

### Alternatives Considered

- `pydantic/pydantic` — clean labels but lower volume.
- `huggingface/transformers` — huge volume but the docs corpus is sprawling and would burn a day on preprocessing.

### Trade-offs

The FastAPI label set is not perfectly clean. The exact label→class mapping is documented separately in this file (see D-XXX, filled by Phase 1.6).

---

## D-003: LLM Provider — Anthropic Claude

Status: Accepted
Date: 2026-05-18

### Context

The project uses an LLM for the classification baseline, the chatbot generator, RAG answer generation, and possibly LLM-as-judge for RAG evaluation. A provider has to be picked and committed.

### Decision

Use Anthropic Claude as the sole LLM provider for every LLM-call site in the project.

### Why

Existing API credits are with Anthropic. One provider keeps the secrets surface in Vault small, simplifies the LLM-call adapter in `app/infra/`, and removes a class of comparison work that does not serve the project's grading criteria.

### Alternatives Considered

- OpenAI only.
- Both providers for cross-provider comparison in DECISIONS.md.

### Trade-offs

The classification-baseline DECISIONS entry compares classical ML, fine-tuned transformer, and Claude — all three on the same test split — so the comparison story is intact even with a single LLM provider.

---

## D-004: Tracing Backend — Langfuse (Self-Hosted)

Status: Accepted
Date: 2026-05-18

### Context

The brief requires picking a tracing backend and defending the choice. Every LLM call, tool call, and RAG retrieval must appear as a span, and a conversation must be a trace tree rooted at the user message. The Friday demo walks through a real trace tree including one error path.

### Recommendation
Use Langfuse, self-hosted in the project's compose stack.

### Why

- Open source and free; runs in compose alongside Vault and MinIO. Matches the spirit of the project (secrets in Vault, blob in MinIO, traces in your stack).
- Real trace-tree UI suited to tool-calling LLM conversations.
- First-class Python SDK with explicit spans for LLM calls, tool calls, and arbitrary nested operations.
- No external dependency for the Friday demo.

### Alternatives Considered

- LangSmith — cloud-only, paid past the free tier, ties demo reliability to a third-party service.
- Arize Phoenix — similar self-hostable model; Langfuse picked for richer LLM-conversation-shaped trace UI.
- OpenTelemetry + Jaeger — more generic, more setup, less LLM-aware out of the box.

### Trade-offs

Adds one more service to compose and one more startup dependency. Refuse-to-boot logic covers the misconfigured case.

---

## D-005: Package Manager — `uv`

Status: Accepted
Date: 2026-05-18

### Context

Python dependency and virtualenv management strategy for the backend, modelserver, chatbot app, and eval harness.

### Decision

Use `uv` for everything Python in the project. Single `pyproject.toml` per Python service; `uv sync` in Docker builds; `uv run` for local commands.

### Why

Same tooling as the Week 6 project. Fast resolver, deterministic locks, good Docker layer caching.

### Trade-offs

None worth listing.

---

## D-006: Frontend Folder Naming

Status: Accepted
Date: 2026-05-18

### Context

The project ships two frontends: the internal Streamlit admin tool, and the embeddable React widget. Folder naming should make it obvious which is which.

### Decision

- `frontend-admin/` — Streamlit admin app.
- `frontend-widget/` — React embeddable widget.

### Why

Both names describe purpose. "Admin" is unambiguous for the internal maintainer-facing tool. "Widget" matches the embeddable surface and matches the brief's own vocabulary.

### Alternatives Considered

- `frontend-dev/` + `frontend/` — rejected because "dev" reads "development environment," which is the opposite of what the Streamlit app is (the internal production-facing maintainer tool).

### Trade-offs

None.

---

## Pending Decisions

Filled in as phases land. Reserved slots:

- **D-007 — Issue label → class mapping for FastAPI dataset.** Filled by Phase 1.6.
- **D-008 — Train/val/test split strategy and sizes.** Filled by Phase 1.6.
- **D-009 — Fine-tuned classifier backbone, hyperparameters, and freeze policy.** Filled by Phase 2.1.
- **D-010 — Classical ML baseline pipeline.** Filled by Phase 2.2.
- **D-011 — LLM classification baseline (prompt, structured output strategy, latency/cost budget).** Filled by Phase 2.3.
- **D-012 — Three-way classifier comparison and deployment choice.** Filled by Phase 2.3.
- **D-013 — Classification eval thresholds in `eval_thresholds.yaml`.** Filled by Phase 2.4.
- **D-014 — NER and summarization tool choices.** Filled by Phase 2.5.
- **D-015 — Embedding model and retrieval-quality number vs at least one alternative.** Filled by Phase 3.1.
- **D-016 — Chunking strategy.** Filled by Phase 3.2.
- **D-017 — Hybrid retrieval weighting.** Filled by Phase 3.3.
- **D-018 — Reranker choice.** Filled by Phase 3.3.
- **D-019 — Query transformation technique.** Filled by Phase 3.3.
- **D-020 — Metadata filter design.** Filled by Phase 3.3.
- **D-021 — RAG eval thresholds and judge model.** Filled by Phase 3.4.
- **D-022 — Redaction pattern list.** Filled by Phase 3.5 (cross-references SECURITY.md).
- **D-023 — Short-term memory TTL and justification.** Filled by Phase 4.3.
- **D-024 — Long-term memory type (episodic / semantic / procedural) and defense.** Filled by Phase 4.3.
- **D-025 — Widget bundle target size and any trade-offs accepted to hit it.** Filled by Phase 4.5.
