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

## D-004: Tracing Backend — Langfuse v2 (Self-Hosted)

Status: Accepted
Date: 2026-05-18

### Context

The brief requires picking a tracing backend and defending the choice. Every LLM call, tool call, and RAG retrieval must appear as a span, and a conversation must be a trace tree rooted at the user message. The Friday demo walks through a real trace tree including one error path.

### Decision

Use **Langfuse v2**, self-hosted in the project's compose stack. Pinned via `image: langfuse/langfuse:2` — not `:latest`.

### Why

- Open source and free; runs in compose alongside Vault and MinIO. Matches the spirit of the project (secrets in Vault, blob in MinIO, traces in your stack).
- Real trace-tree UI suited to tool-calling LLM conversations.
- First-class Python SDK with explicit spans for LLM calls, tool calls, and arbitrary nested operations.
- No external dependency for the Friday demo.

### Why v2 specifically, not v3

Langfuse v3 introduced ClickHouse as a required backing store on top of Postgres + Redis + MinIO. For a single-developer, single-machine project this multiplies the compose footprint (extra service, extra volume, extra healthcheck, extra failure mode) without any functional benefit — both v2 and v3 expose the same trace-tree UI and the same SDK surface for our use cases (LLM call spans, tool call spans, error paths, conversation tree). v2 only needs the Postgres we already have.

Pinning to the `:2` major guards against the same surprise happening again if the team upgrades the `:latest` tag.

### Alternatives Considered

- **Langfuse v3** — rejected per above (ClickHouse footprint not justified for this project).
- **LangSmith** — cloud-only, paid past the free tier, ties demo reliability to a third-party service.
- **Arize Phoenix** — similar self-hostable model; Langfuse picked for richer LLM-conversation-shaped trace UI.
- **OpenTelemetry + Jaeger** — more generic, more setup, less LLM-aware out of the box.

### Trade-offs

- Adds one more service to compose and one more startup dependency. The api-level refuse-to-boot logic (Phase 1.5) covers the misconfigured case.
- The Docker container-level healthcheck for langfuse is **disabled** — the v2 image's networking made every reasonable healthcheck probe (`wget`, `curl`, `node http.get`) fail despite the app being fully responsive in the browser and via curl from the host. Since no other service `depends_on: langfuse` (langfuse is a write-only sink, not a dependency), the missing healthcheck has no operational impact on the boot graph. Service health is instead verified by the Langfuse SDK at api startup (Phase 1.5) — if the SDK can't connect, api refuses to boot. This means the *real* health check happens at the consumer (api), not at the producer (langfuse container), which is arguably more correct anyway.
- Running on `:2` means we accept whatever maintenance posture Langfuse gives to the v2 line. For a 5-day project this is irrelevant; for a long-lived deployment it would be a decision to revisit.

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

## D-026: Vault Adapter Pattern

Status: Accepted
Date: 2026-05-19

### Context

Phase 1.4 wires Vault into the application. The brief grades the layer boundary — services and routers must not touch external systems directly. Secrets are external.

### Decision

A single `load_secrets()` function in `app/infra/vault.py` resolves every runtime secret at startup. It returns a typed frozen dataclass `Secrets` with sub-objects for each path (`DatabaseSecrets`, `JWTSecrets`, etc.). The result is stored on `app.state.secrets` and read from there by services. No code outside `app/infra/vault.py` imports `hvac`.

### Why

- Matches the layer boundary: only `app/infra/` adapters touch external systems.
- Centralizes the secret schema in one typed location, so adding a new secret requires updating exactly one file.
- The dataclass is `frozen=True`, so accidental mutation at runtime is impossible.

### Alternatives Considered

- Let services read from Vault directly. Rejected because it puts `hvac` calls in business logic and breaks the layer rule.
- Read each secret lazily on first access. Rejected because failures would surface at request time rather than at startup — the refuse-to-boot guarantee depends on resolving everything up front.

### Trade-offs

One extra indirection compared to direct Vault calls. The boundary is what makes the codebase testable and the layer rule defensible.

---

## D-027: Vault-init Container Pattern

Status: Accepted
Date: 2026-05-19

### Context

Vault dev mode boots empty. Something must seed the KV paths before app services try to read them. Two natural options: seed inside the app at startup, or seed via a dedicated init container.

### Decision

A separate `vault-init` container runs once at compose startup, waits for `vault` to be healthy, writes all six KV paths with `vault kv put`, and exits 0. App services depend on it via `condition: service_completed_successfully`.

### Why

- Seeding is infra setup, not runtime concern. The app should not write secrets it consumes.
- Clean separation: if seeding fails, vault-init's exit code makes that obvious in `docker compose ps -a`, and dependent services don't start.
- Matches the same pattern used for `migrate` (Alembic).

### Alternatives Considered

- Seed inside `lifespan.py` at api startup. Rejected because it conflates the role of the app (reads secrets) and infra (writes them).
- Seed manually via a one-time script the developer runs. Rejected because it breaks the brief's requirement that `docker compose up` from a fresh clone Just Works.

### Trade-offs

Vault dev mode stores state in memory, so a `vault` restart wipes all KV paths. After such a restart, vault-init must be re-run via `docker compose up -d --force-recreate vault-init`. This is dev-mode-only — production Vault uses persistent storage and never needs re-seeding. Documented in RUNBOOK §2.

---

## D-028: Langfuse Uses a Separate Postgres Database

Status: Accepted
Date: 2026-05-19

### Context

Langfuse v2 stores its data in Postgres. Initial compose config pointed Langfuse at the same `copilot` database the application uses. This caused two problems in Phase 1.4:

1. Alembic `--autogenerate` compared the application's six ORM models against the live database state, saw Langfuse's ~30 tables (`traces`, `observations`, `scores`, etc.) as "extra," and generated a destructive migration that would have dropped them all.
2. Both Langfuse and the application want a `users` table. Schema collision.

### Decision

One Postgres instance, two databases:

- `copilot` — application data (users, conversations, messages, widgets, audit_log, memory_long).
- `langfuse` — Langfuse's own schema.

A first-boot init script at `backend/scripts/postgres-init.sh` runs from `/docker-entrypoint-initdb.d/` and creates the `langfuse` database via a `\gexec` idempotent pattern. Langfuse's `DATABASE_URL` points at `…/langfuse`; the application's points at `…/copilot`.

### Why

- Schema isolation without paying for a second Postgres container.
- Alembic only ever sees the application schema, so autogenerate is safe.
- No name collisions.
- The init script runs only on first volume bootstrap, so it's safe to leave in place forever.

### Alternatives Considered

- Two Postgres containers (one per app). Rejected — twice the memory and one more service to manage.
- Separate schemas in the same database, using `search_path`. Rejected — Alembic's autogenerate would still see Langfuse's tables unless we filtered manually, which is more fragile than database-level isolation.

### Trade-offs

A tiny init script that runs only on fresh volumes. Documented in ARCH.md and RUNBOOK.md.

---

## D-029: Postgres Image — `pgvector/pgvector:pg16`

Status: Accepted
Date: 2026-05-19

### Context

Long-term memory in Phase 4.3 uses the pgvector extension (`Vector(1536)` column on `memory_long`). The default `postgres:16-alpine` image does not include the extension files in `/usr/local/share/postgresql/extension/`, so `CREATE EXTENSION vector` fails with "extension control file not found."

### Decision

Use the official pgvector image: `pgvector/pgvector:pg16`. Same Postgres 16, ships pgvector C extension pre-compiled and installed.

### Why

- pgvector requires C extension files; pip-installing the Python bindings is not sufficient.
- The image is published by the pgvector maintainers and tracks Postgres 16 stable.
- Single drop-in replacement — no other docker-compose changes needed.

### Alternatives Considered

- Build a custom Dockerfile extending `postgres:16-alpine` and installing pgvector. Rejected — reinvents what `pgvector/pgvector:pg16` already provides.
- Use the `ankane/pgvector` image. Older, less maintained.

### Trade-offs

Image is slightly larger than the alpine base. Functionally identical for our needs.

---

## D-030: Alembic `env.py` Accepts `DATABASE_URL` Override

Status: Accepted
Date: 2026-05-19

### Context

Migrations are generated by running `alembic revision --autogenerate` on the developer's host machine, outside the docker network. The host cannot resolve `vault:8200` (the docker-internal hostname), so the standard Vault path fails when running alembic from the host.

### Decision

`alembic/env.py` checks for a `DATABASE_URL` environment variable first. If set, it uses that value directly. If not set, it falls back to `load_secrets()` from Vault.

```python
_db_url_override = os.environ.get("DATABASE_URL")
if _db_url_override:
    config.set_main_option("sqlalchemy.url", _db_url_override)
else:
    from app.infra.vault import load_secrets
    secrets = load_secrets()
    config.set_main_option("sqlalchemy.url", secrets.database.url)
```

Developer usage:

```bash
DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot" \
  uv run alembic revision --autogenerate -m "..."
```

The `migrate` container inside docker has no `DATABASE_URL` set, so it goes through Vault.

### Why

- Keeps the runtime-resolves-from-Vault rule intact: at runtime inside docker, the override is absent.
- Provides a single, explicit, well-commented escape hatch for the only legitimate use case (developer autogenerate).
- The DB password isn't a real secret — it's a dev seed value committed in docker-compose — so exposing it to the host shell via the env-var path doesn't violate the secret-handling contract.

### Alternatives Considered

- Run autogenerate inside docker via `docker compose exec`. Rejected — the autogenerated migration file lands inside the container, not on the host filesystem where the developer can edit and commit it.
- Hardcode the DB URL in `alembic.ini`. Rejected — would commit a credential pattern to source, even if the credential itself is a dev seed.

### Trade-offs

Small dual code path in `alembic/env.py`. The override is one `if/else`, well-commented for the Friday review.

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
