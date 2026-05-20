# ARCH.md

Project: Maintainer's Copilot
Last updated: 2026-05-18

## 1. System Overview

The Maintainer's Copilot is an authenticated chatbot that an open-source maintainer talks to when triaging incoming issues. It classifies issues into bug / feature / docs / question, extracts code-shaped entities, summarizes long threads, and answers questions via advanced RAG over the project's docs and a held-out slice of resolved issues. It carries short-term memory inside a conversation and long-term memory across conversations.

The chatbot is delivered through two frontends that share one FastAPI backend: a Streamlit admin app for the maintainer (login, full chat, memory inspector, widget configuration) and a standalone React widget that any host site embeds via a single `<script>` tag.

### 1.1 Flow of the Final Product

```text
                    MAINTAINER WORKFLOW                        HOST-SITE WORKFLOW
                    ====================                       ==================
                  localhost:8501 (Streamlit)              localhost:8080 (demo host)
                            │                                       │
                       login + chat                       <script src="/widget.js"
                            │                              data-widget-id="abc">
                            │                                       │
                            │                                  loader.js
                            │                                       │
                            │                              injects <iframe> →
                            │                              React widget bundle
                            │                                       │
                            └───────────────┬───────────────────────┘
                                            ▼
                              FastAPI backend (localhost:8000)
                                            │
                  ┌─────────────────────────┼─────────────────────────┐
                  ▼                         ▼                         ▼
        single tool-calling LLM       pgvector RAG              Redis (short)
        (Anthropic Claude)            hybrid + rerank           pgvector (long)
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
  classify    NER + summ.   write_memory
  (modelserver  (modelserver)  (audit-logged)
   FastAPI)
```

The trace tree in Langfuse shows the user message at the root, every tool call as a child span, the LLM call with token counts, retrieved chunks for RAG, and any error paths. Every log line carries the trace ID so logs and traces join. Redaction strips secrets before any of it leaves the service boundary.

## 2. Main Runtime Services

| Service | Purpose |
|---|---|
| `api` | FastAPI application: authentication, chat orchestration, RAG, memory, widget configuration. |
| `chatbot` | Streamlit admin app: login, full chat, memory inspector, widget configuration page. |
| `widget` | Static server for the built React widget bundle and the loader script. |
| `host` | nginx serving the `demo/host/` page that embeds the widget (Friday demo target). |
| `modelserver` | FastAPI inference server hosting the fine-tuned classifier, NER, and summarizer endpoints. The API never loads model weights for request-time inference. |
| `migrate` | Runs `alembic upgrade head` and exits before `api` boots. |
| `db` | Postgres 16 with the `pgvector` extension. Application data and long-term memory live here. |
| `redis` | Redis 7 for short-term conversation state and any service-layer caches. |
| `minio` | S3-compatible blob storage for model artifacts, eval reports, training plots, and per-conversation retrieved-chunks snapshots. |
| `vault` | HashiCorp Vault (dev mode) for runtime secret resolution. |
| `langfuse` | Self-hosted Langfuse for trace storage and the trace-tree UI. |

## 3. Repository Layout

```text
.
├── backend/
│   └── app/
│       ├── api/             # HTTP routers, request/response schemas, route dependencies
│       ├── services/        # Business logic, transaction boundaries, cache/memory invalidation
│       ├── repositories/    # SQL-only data access via async SQLAlchemy
│       ├── domain/          # Pydantic domain models, enums, internal contracts
│       ├── infra/           # External adapters: Vault, Redis, MinIO, LLM provider, tracing, redaction
│       ├── db/              # SQLAlchemy ORM models, sessions, Alembic migrations
│       ├── rag/             # Chunking, retrieval, reranking, query transformation
│       ├── chatbot/         # Tool definitions, single tool-calling loop, prompt loading
│       ├── memory/          # Short-term (Redis) and long-term (pgvector) memory adapters
│       ├── eval/            # Golden sets, eval harnesses for classification and RAG
│       ├── prompts/         # Versioned prompt files
│       └── core/            # Config, logging, startup/lifespan, shared errors
├── frontend-admin/          # Streamlit app
├── frontend-widget/         # React widget (Vite, single-file bundle)
├── demo/
│   └── host/                # One HTML page + nginx config, embeds the widget for Friday demo
├── deliverables/            # ARCH, DECISIONS, RUNBOOK, EVALS, SECURITY, LICENSES
├── .github/workflows/       # CI: lint, type-check, tests, eval gates, smoke
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

## 4. Layer Boundary Rules

This boundary is graded. It will be checked on Friday by being asked to add a new endpoint or tool live.

| Layer | Owns | Must Not Do |
|---|---|---|
| `app/api/` | HTTP concerns only: routers, status codes, request/response models, auth dependencies. | No SQLAlchemy queries, no Redis calls, no MinIO calls, no Vault calls, no LLM calls, no direct cache invalidation. |
| `app/services/` | Business rules, transaction boundaries, tool orchestration, cache/memory invalidation, audit-log writes. | No `HTTPException` as business logic, no route-specific assumptions, no FastAPI `Request` dependency. |
| `app/repositories/` | SQL reads/writes through async SQLAlchemy sessions. | No cache invalidation, no HTTP errors, no external systems, no business decisions. |
| `app/domain/` | Pydantic domain models, enums, service/repository contracts. | No database sessions, no HTTP concepts, no external clients. |
| `app/infra/` | Adapters for Vault, Redis, MinIO, LLM provider, Langfuse, redaction layer, embedding model client. | No business rules beyond adapter-level error wrapping. |
| `app/db/` | ORM models, database session factory, Alembic migrations. | Imported only by repositories and DB setup code. |

## 5. Core Data Flow: One Chatbot Turn

1. User sends a message through Streamlit or the React widget.
2. `api` authenticates the user (JWT), resolves a request ID and trace ID, and calls `chat_service.handle_turn(...)`.
3. `chat_service` loads short-term memory from Redis (recent turns of this conversation) and an optional long-term memory snippet from pgvector (cross-conversation recall).
4. `chat_service` invokes the single tool-calling Claude loop. The model picks tools: `classify_issue`, `extract_entities`, `summarize_thread`, `retrieve_docs`, `write_memory`.
5. Tool calls route through `app/services/` to the right adapter:
   - `classify_issue`, `extract_entities`, `summarize_thread` → `modelserver` HTTP endpoint.
   - `retrieve_docs` → `app/rag/` (hybrid retrieval, rerank, query transform).
   - `write_memory` → long-term memory write + audit-log row.
6. Every LLM call, tool call, and retrieval is a Langfuse span, all rooted at the user message.
7. Every log line, span attribute, and memory write passes through `app/infra/redaction.py` first.
8. `chat_service` returns the assistant message; `api` streams it back to the frontend.
9. Tool failures are caught and recovered. If the classifier endpoint is down, the chatbot says so and falls back; it does not 500.

## 6. Authentication and Authorization

Authentication is `fastapi-users` with JWT (Bearer transport). JWT signing key resolves from Vault at startup.

Registration is admin-invite-only. Public registration is not exposed.

Two roles: `user` and `admin`.

| Role | Permissions |
|---|---|
| `user` | Log in, chat with the bot, view their own memory, delete their own conversations. |
| `admin` | All `user` permissions, plus invite users, create/edit widget configurations, view audit log. |

Role storage and exact enforcement mechanism: TBD (to be filled in by Phase 4.1).

## 7. Endpoint Inventory

Placeholder. Filled in by Phase 4.1 (auth) and Phase 4.2 (chatbot core).

| Method | Endpoint | Roles | Notes |
|---|---|---|---|
| `POST` | `/auth/login` | Public | JWT login. |
| `POST` | `/auth/logout` | Authenticated | Stateless. |
| `GET` | `/me` | Authenticated | Current user. |
| `GET` | `/healthz` | Public | Liveness. |
| `POST` | `/chat/send` | Authenticated | Send a message; streams assistant reply. |
| `GET` | `/conversations` | Authenticated | List own conversations. |
| `GET` | `/conversations/{cid}` | Authenticated | Get conversation history. |
| `DELETE` | `/conversations/{cid}` | Authenticated | Delete conversation (audit-logged). |
| `GET` | `/memory/long` | Authenticated | List own long-term memory entries. |
| `POST` | `/admin/users/invite` | admin | Invite a user. |
| `GET` | `/admin/widgets` | admin | List widget configurations. |
| `POST` | `/admin/widgets` | admin | Create a widget configuration. |
| `PUT` | `/admin/widgets/{wid}` | admin | Update a widget configuration. |
| `GET` | `/admin/audit-log` | admin | Audit log. |
| `GET` | `/widgets/{wid}/config` | Public (origin-gated) | Widget config read by the loader. |
| `GET` | `/widget.js` | Public | Loader script. |

## 8. Memory Plan

### 8.1 Short-Term (Redis)

The last N turns of the active conversation are held in Redis with an explicit TTL. TTL value and justification: TBD (Phase 4.3).

### 8.2 Long-Term (pgvector)

Cross-conversation recall lives in Postgres with pgvector. Memory type (episodic / semantic / procedural) and the defense for that choice: TBD (Phase 4.3).

Every long-term write produces an `audit_log` row: `actor`, `action`, `target`, `timestamp`, `request_id`, `trace_id`.

Writes are explicit only — the chatbot calls the `write_memory` tool. There are no auto-writes.

## 9. Startup and Refuse-to-Boot Checks

The compose boot sequence is:

1. `vault` starts in dev mode.
2. `vault-init` seeds Vault KV paths and exits.
3. `db`, `redis`, `minio`, `langfuse` start.
4. `minio-init` creates required buckets and exits.
5. `migrate` runs `alembic upgrade head` and exits.
6. `modelserver`, `api`, `chatbot`, `widget`, `host` start.

The `api` refuses to boot if any of the following are true:
- Vault is unreachable. *(implemented in Phase 1.4)*
- The Langfuse tracing backend is unreachable or rejects credentials. *(implemented in Phase 1.5)*
- Any committed eval threshold in `backend/eval_thresholds.yaml` is zero or missing. *(implemented in Phase 2.4)*

The `modelserver` refuses to boot if:

- Classifier weights are missing.
- The weights' SHA-256 does not match the committed model card.
- `test_macro_f1` in the model card is below the committed startup threshold.

Startup threshold values: TBD (Phase 2.1).

## 10. Classifier Artifact Contract

Expected paths:

```text
backend/app/classifier/models/classifier.pt
backend/app/classifier/models/model_card.json
backend/app/eval/classification/golden_set.jsonl
backend/app/eval/classification/golden_expected.json
backend/app/eval/classification/run_eval.py
```

`model_card.json` fields: `sha256`, `backbone`, `tokenizer`, `freeze_policy`, `hyperparameters`, `training_data_hash`, `test_accuracy`, `test_macro_f1`, `per_class_f1`, `latency_p50_ms`, `trained_at`, `env_fingerprint`. Schema lives in `app/domain/model_card.py`.

### 10.1 model_card.json contract (Phase 2.1, shipped)

| Field | Value (shipped 2026-05-19) |
|---|---|
| sha256 | `a3bd4cb8f9328ce409169d14ef4585c27f1149ff2c69795de0e8e5759a8f3a59` |
| backbone | `distilbert-base-uncased` |
| tokenizer | `distilbert-base-uncased` |
| freeze_policy | `full_finetune` |
| training_data_sha256 | `1a4e887a580b5289d4b87fcff2890235c95945d78cd768f3e25933b3ca4c3959` |
| test_accuracy | 0.8478 |
| test_macro_f1 | 0.7462 |
| per_class_f1 | bug 0.9255, feature 0.8148, docs 0.8845, question 0.3600 |
| trained_at | 2026-05-19 (W&B run 6vaoq2zd) |

## 11. RAG Architecture

| Concern | Choice | Filled by |
|---|---|---|
| Corpus | scikit-learn docs + held-out slice of resolved issues with maintainer answers. Held-out issues do not appear in classifier training (strict separation). | Phase 3.1 |
| Embedding model | TBD | Phase 3.1 |
| Chunking strategy | Not naive fixed-size. TBD. | Phase 3.2 |
| Vector store | pgvector | Phase 3.2 |
| Sparse retrieval | BM25 | Phase 3.3 |
| Dense + sparse weighting | TBD (tuned on golden set) | Phase 3.3 |
| Reranker | Cross-encoder (TBD model) | Phase 3.3 |
| Query transformation | TBD (HyDE or multi-query) | Phase 3.3 |
| Metadata filtering | At least one filter (e.g. `is_resolved`, `version`) | Phase 3.3 |

## 12. Tracing and Logging

### 12.1 Tracing

Backend: Langfuse v2, self-hosted in the compose stack.

At api startup, `app/infra/tracing.py::init_langfuse(secrets.langfuse)` initializes the SDK and calls `auth_check()` to verify connectivity. If that fails (network error or invalid credentials), api refuses to boot.

A single Langfuse trace is started for every HTTP request by `RequestContextMiddleware`, rooted at the user's request. In later phases, every LLM call, tool call, and RAG retrieval will be a child span of this trace. Span attributes include model name, token counts, latency, and tool inputs/outputs **after redaction** (redaction layer lands in Phase 3.5).

### 12.2 Logging

All services emit structured JSON via `app/core/logging.py::JSONFormatter`. Fields on every log line:

```json
{
  "timestamp": "ISO-8601 (UTC)",
  "level": "info | warning | error | critical | debug",
  "service": "api | modelserver | chatbot",
  "event": "logger name (e.g. app.infra.vault)",
  "message": "human-readable message",
  "request_id": "uuid v4 — empty outside request scope",
  "trace_id": "langfuse trace id — empty outside request scope"
}
```

`request_id` and `trace_id` flow through Python `contextvars` set by `RequestContextMiddleware`, so every log call inside a request automatically carries them with no explicit threading.

Healthcheck access-log noise (`GET /healthz` every 5s) is suppressed by `HealthzFilter` on the uvicorn access logger. Application-level logging from within `/healthz` is preserved.

### 12.3 Redaction

A redaction layer in `app/infra/redaction.py` will run before any log line, trace span, or memory write leaves the service boundary. Patterns are defended in SECURITY.md. *(Phase 3.5.)*

## 13. Frontends

### 13.1 Streamlit Admin (`frontend-admin/`)

Internal-tool surface for the maintainer. Runs on `localhost:8501`. Contains: login form, full chat interface with streamed responses, memory inspector (read-only view of the user's long-term entries), and the admin-only widget configuration page that generates embed snippets.

Authenticates against the same `api` via JWT.

### 13.2 React Widget (`frontend-widget/`)

The production-shaped, embeddable surface. Built with Vite, output to a single bundled JS file. Served either by the `widget` service or from MinIO with proper cache headers.

The widget reads its config at load time from `/widgets/{wid}/config` and styles itself accordingly (theme, primary color, position, greeting, enabled tools).

A `postMessage` channel exists between the widget and its host page, at minimum for iframe resize signals.

### 13.3 Embed Flow and Origin Allowlisting

1. Host pastes `<script src="http://localhost:8000/widget.js" data-widget-id="abc">` into their HTML.
2. The browser fetches `/widget.js` (the loader).
3. The loader injects an iframe whose `src` is the React widget bundle, passing the `widget_id`.
4. The iframe loads the bundle, which fetches its config from `/widgets/{wid}/config`.
5. The widget reads `theme`, `greeting`, and `enabled_tools` from the config and renders itself accordingly.

The CORS allowlist is enforced from the widget's `allowed_origins` field in the database, **not** from a hardcoded env var. The embed route also sets `Content-Security-Policy: frame-ancestors <allowed_origins>` so a host whose origin is not in the allowlist gets blocked by the browser at iframe-embed time.

The Friday demo runs the widget in `demo/host/` on an allowed origin and shows it blocked on a host whose origin is not in the allowlist. Both demos use real browser network and console output.
