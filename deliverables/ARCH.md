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

Last updated: 2026-05-22 (Phase 4.2 — chatbot core live)

1. User POSTs `{"conversation_id": "<uuid|null>", "message": "<text>"}` to `POST /chat/send` with a Bearer token.
2. `app/api/chat.py` authenticates via `current_active_user` (fastapi-users), injects `AsyncSession` and reads `anthropic_client` / `http_client` from `app.state`.
3. The endpoint calls `chat_service.stream_chat_response(...)` and streams the result as SSE events (`text/event-stream`). A final `data: [DONE]` event closes the stream.
4. `chat_service` (`app/services/chat_service.py`) opens a Langfuse span (`chatbot_turn`), loads the system prompt from disk (cached after first read), and delegates to `app/chatbot/loop.run_stream(...)`.
5. The tool-calling loop (`app/chatbot/loop.py`, D-034) runs up to **MAX_ROUNDS = 5** iterations using `claude-haiku-4-5`. On each round it calls `anthropic_client.messages.stream(...)` with the current message history and tool schemas. On the final round, `tools=[]` forces `end_turn`.
6. Tool calls are dispatched by `app/chatbot/tools.execute_tool(...)`:
   - `classify_issue`, `extract_entities`, `summarize_thread` → `modelserver` HTTP via the shared `httpx.AsyncClient` (stored in `app.state.http_client`).
   - `retrieve_docs` → `app/rag/pipeline.RAGPipeline` (hybrid retrieval, rerank, query transform).
   - `write_memory` → stub returning `{"status": "ok"}` until Phase 4.3.
7. Tool executor failures return `{"error": "…"}` — Claude relays them gracefully; the API never 500s on a tool failure.
8. Every LLM call and tool result is under the Langfuse span opened in step 4.
9. `loop.run_stream` yields text delta strings; `chat_service` re-yields them; the endpoint wraps each in an SSE `data:` line. Phase 4.3 will add Redis short-term memory and pgvector long-term recall between steps 4 and 5.

## 6. Authentication and Authorization

Last updated: 2026-05-21 (Phase 4.1)

**Library:** `fastapi-users[sqlalchemy] 13.x` with `BearerTransport` + `JWTStrategy`.

**JWT signing key:** resolved from Vault at lifespan startup (`secrets.jwt.signing_key`, algorithm `HS256`, lifetime from `secrets.jwt.access_token_lifetime_seconds`). The `get_jwt_strategy` dependency reads from `request.app.state.secrets.jwt` at request time — never at module import time and never from an environment variable.

**Registration:** admin-invite-only. There is no public `/auth/register` endpoint; the `get_register_router()` router from fastapi-users is intentionally not mounted. First admin is created via `app/entrypoints/bootstrap_admin.py` (see RUNBOOK §3).

**Role model:** `is_superuser: bool` on the `users` table (D-033). Two roles map to a single boolean:

| Role | `is_superuser` | Permissions |
|---|---|---|
| `user` | `False` | Log in, chat, view own memory, delete own conversations. |
| `admin` | `True` | All user permissions + invite users, create/edit widget configs, view audit log. |

**Enforcement:** routes requiring admin use the `current_active_superuser` dependency exported from `app/infra/auth.py`. Non-superusers receive a 403 response from fastapi-users before the handler runs.

**DB engine:** the async SQLAlchemy engine and `async_sessionmaker` are created during lifespan startup from `secrets.database.url` (Vault-resolved) and stored in `app.state.db_engine` / `app.state.db_session_factory`. The `get_async_session` dependency in `app/db/session.py` reads from `request.app.state.db_session_factory` per request.

## 7. Endpoint Inventory

Last updated: 2026-05-22 (Phase 4.2 — `/chat/send` live)

| Method | Endpoint | Roles | Notes |
|---|---|---|---|
| `POST` | `/auth/jwt/login` | Public | fastapi-users form-encoded login; returns `access_token`. |
| `POST` | `/auth/jwt/logout` | Authenticated | Invalidates the bearer token (stateless — token just expires). |
| `GET` | `/users/me` | Authenticated | Current user profile. |
| `PATCH` | `/users/me` | Authenticated | Update email / password. |
| `GET` | `/healthz` | Public | Liveness probe. |
| `POST` | `/chat/send` | Authenticated | Send a message; streams assistant reply via SSE. ✅ Phase 4.2 |
| `GET` | `/conversations` | Authenticated | List own conversations. (Phase 4.2) |
| `GET` | `/conversations/{cid}` | Authenticated | Get conversation history. (Phase 4.2) |
| `DELETE` | `/conversations/{cid}` | Authenticated | Delete conversation (audit-logged). (Phase 4.2) |
| `GET` | `/memory/long` | Authenticated | List own long-term memory entries. (Phase 4.3) |
| `POST` | `/admin/users/invite` | admin | Invite a user. (Phase 4.4) |
| `GET` | `/admin/widgets` | admin | List widget configurations. (Phase 4.6) |
| `POST` | `/admin/widgets` | admin | Create a widget configuration. (Phase 4.6) |
| `PUT` | `/admin/widgets/{wid}` | admin | Update a widget configuration. (Phase 4.6) |
| `GET` | `/admin/audit-log` | admin | Audit log. (Phase 4.3) |
| `GET` | `/widgets/{wid}/config` | Public (origin-gated) | Widget config read by the loader. (Phase 4.6) |
| `GET` | `/widget.js` | Public | Loader script. (Phase 4.6) |

## 8. Memory Plan

### 8.1 Short-Term (Redis)

Per-conversation message history stored as a Redis list under the key
`conv:{conversation_id}:messages`. Each element is a JSON-serialized
`{"role": …, "content": …}` dict.

- **TTL: 86 400 s (24 h)** — covers a full work day; long-term persistence
  is handled by pgvector (D-023).
- **Sliding window: 50 messages** — RPUSH + LTRIM(-50, -1) keeps the most
  recent 50 turns. Older turns add noise without value for triage queries (D-023).
- **Module:** `app/memory/short_term.py` — `append_message`, `get_history`, `clear`.
- **Injection:** the Redis client is passed in as a parameter; no global import.

### 8.2 Long-Term (pgvector)

Cross-conversation recall lives in Postgres with the pgvector extension.
Memories are stored in the `memory_long` table with a `vector(384)` embedding
column (all-MiniLM-L6-v2, D-015). An HNSW index serves approximate KNN queries
using cosine distance (`<=>` operator).

**Memory type: episodic (default).** The `write_memory` tool is explicit-only
(user-stated facts). Stated facts are episodic by definition. The column also
accepts `semantic` and `procedural` for user-directed overrides. Full rationale
in D-024.

Every long-term write produces an `audit_log` row: `actor`, `action`, `target`,
`timestamp`, `request_id`, `trace_id` (SECURITY §6).

Writes are explicit only — the chatbot calls the `write_memory` tool. There are no auto-writes.

- **Module:** `app/memory/long_term.py` — `write_entry`, `search`, `list_entries`.
- **Test:** `tests/test_memory_recall.py` — graded cross-conversation recall test using real embeddings.

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

### 10.2 NER and Summarizer Artifacts (Phase 2.5)

NER model: `dslim/bert-base-NER` is fetched from HuggingFace Hub directly at modelserver startup. No MinIO involvement — defended in D-014: third-party public weights have no meaningful SHA-against-self contract.

Summarizer: no model artifact; calls Anthropic Haiku via the SDK. Authentication is the existing `secrets.anthropic.api_key` from Vault.

The artifact contract pattern (refuse-to-boot on SHA mismatch from D-009) applies to fine-tuned models only. Third-party loaded models refuse to boot if HF Hub is unreachable, but not on hash verification.

## 11. RAG Architecture

| Concern | Choice | Filled by |
|---|---|---|
| Corpus | 176 scikit-learn `.rst` docs (tag `1.6.0`) + 465 closed issues with maintainer comment threads (2024-09 → 2026-05). Strict separation from classifier splits. | Phase 3.1 (D-015) |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` — 384 dim, tied hit@5 with `BAAI/bge-base-en-v1.5` (88.89% on 18-query proxy set) at 7.5× lower encode latency. | Phase 3.1 (D-015) |
| Chunking strategy | Structural: RST docs split at section headings; issues split body + per-comment. Sliding-window fallback at 220 tokens / 50-token overlap. 641 items → 9,701 chunks (docs=4,846, issues=4,855). | Phase 3.2 (D-016) |
| Vector store | pgvector `rag_chunks` table — `vector(384)`, HNSW index (m=16, ef_construction=64), GIN on metadata JSONB. Baseline: hit@1=83.33%, hit@5=94.44% (18-query proxy set). | Phase 3.2 (D-016) |
| Sparse retrieval | BM25Okapi (rank_bm25), three in-memory indexes (docs/issues/all), built at startup in ~0.5 s / ~50 MB RAM. Degenerate chunks (n_tokens < 5) deleted before indexing. | Phase 3.3 (D-017) |
| Dense + sparse weighting | RRF (k=60) — no tuned weights, rank-based fusion. Hybrid gains: hit@5 94.44% → 100.00% (+5.56 pp), MRR@10 0.8889 → 0.9074, recall@10 92.59% → 100.00% on 18-query proxy set. | Phase 3.3 (D-017) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2`, inline singleton (not modelserver). **Not used by default** — domain mismatch with scikit-learn docs/issues causes regression (hit@1 83.33% → 44.44%). Available as `use_rerank=True` flag in RAGPipeline. | Phase 3.3 (D-018) |
| Query transformation | HyDE augment (not replace): three-stream RRF — dense(query) + dense(hyde_passage) + BM25(query). Gains over hybrid: hit@1 83.33% → 88.89% (+5.56 pp), MRR@10 0.9074 → 0.9444. HyDE via `claude-haiku-4-5`, ≤256 tokens. `use_hyde=True` default. | Phase 3.3 (D-019) |
| Metadata filtering | `SourceFilterLiteral["docs","issues","all"]` on `RAGPipeline`. Maps to pgvector WHERE clause + BM25 index selection. Zero-overhead filter since three BM25 indexes are pre-built. | Phase 3.3 (D-020) |

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

Internal-tool surface for the maintainer. Runs on `localhost:8501` (host-side,
not in Docker). Install with `pip install -r requirements.txt`, run with
`streamlit run app.py`.

**Pages:**
- **Home (`app.py`)** — login form; email + password → `POST /auth/jwt/login`;
  JWT stored in `st.session_state`. After login shows sidebar with email and
  Logout button (present on all pages via `utils/auth_guard.py`).
- **Chat (`pages/chat.py`)** — `st.chat_input` + `st.write_stream()` over the
  SSE response from `POST /chat/send`. Conversation ID generated client-side on
  the first turn and displayed with `st.caption`. New Conversation button resets
  state.
- **Memory Inspector (`pages/memory.py`)** — read-only list of the user's
  long-term memory entries from `GET /memory/entries`, rendered as expandable
  cards showing content, type, timestamp, and ID.
- **Widget Config (`pages/widget_config.py`)** — placeholder; full
  implementation in Phase 4.6.

**SSE streaming:** `send_message_stream()` in `utils/api_client.py` uses
`requests` with `stream=True` and parses `data: <chunk>` lines manually.
`st.write_stream()` (Streamlit ≥1.31) consumes the generator and renders
output incrementally.

**New API endpoint:** `GET /memory/entries` — returns the authenticated user's
long-term memory entries newest-first. Implemented in `app/api/memory.py`.

### 13.2 React Widget (`frontend-widget/`)

The production-shaped, embeddable surface. Built with Vite in **iife** library mode, output as a single self-contained JS file (`backend/app/static/widget.js`). Served from FastAPI's `/static` mount. Served via `StaticFiles` in development; Phase 4.6 wires the loader script.

**Bundle format — iife:** Executes on `<script>` load with no module system required on the host. `inlineDynamicImports: true` ensures no code-splitting so a single file is fetched. (See D-025.)

**Framework — Preact (not React):** Preact implements the same hooks API as React but is ~3 KB vs ~144 KB for React + ReactDOM. Full bundle gzips to **10.16 KB** — within the brief's graded size target. The `react` → `preact/compat` alias in `vite.config.js` makes React-style JSX work unchanged. (See D-025.)

**Shadow DOM isolation:** The widget creates a host `<div>` and calls `.attachShadow({mode: 'open'})`. All widget HTML and styles live inside the shadow root, preventing host-page CSS from leaking in and widget CSS from leaking out. Styles are injected via a `<style>` element inside the shadow (CSS loaded as `?inline` string). (See D-025.)

**SSE streaming:** Uses `fetch()` + `response.body.getReader()` + `TextDecoder({stream: true})` instead of `EventSource`. The `/chat/send` endpoint requires POST; `EventSource` is GET-only. Line-by-line `data:` parsing is identical to the EventSource protocol. (See D-025.)

**Auth:** Widget passes `?widget_id=<uuid>` as a query parameter. The `get_current_user_or_widget` FastAPI dependency tries Bearer JWT first, then falls back to `widget_id`. Phase 4.5 stub validates UUID format only; Phase 4.6 performs a database lookup.

**Config fallback:** At load time the widget fetches `/widgets/{wid}/config`. If the fetch fails (CORS block in dev, unreachable API), it falls back to `DEFAULT_CONFIG` (`theme: dark`, `greeting: "Hello! How can I help?"`, `enabled_tools: ["retrieve_docs"]`).

**CSP `frame-ancestors`:** Deferred to Phase 4.6. The `allowed_origins` database column and the `frame-ancestors` header are implemented together so origin enforcement is database-driven, not hardcoded. (See D-025.)

**Running the dev harness:**
```bash
cd frontend-widget
npm install
npm run dev   # http://localhost:5174
```
`index.html` sets `window.__WIDGET_DEV_CONFIG__` before loading `main.jsx` as an ES module, because `document.currentScript` is `null` inside ES modules.

**Tests:** 8 vitest tests covering `Widget.jsx` render/open/close and `useSSEChat` streaming + error handling.

**File layout:**
```
frontend-widget/
  src/
    main.jsx          # IIFE entry — reads data-widget-id or __WIDGET_DEV_CONFIG__
    Widget.jsx        # Root component — bubble toggle, shadow DOM, config fetch
    ChatPanel.jsx     # Panel, message list, input row
    useSSEChat.js     # fetch+ReadableStream SSE hook
    api.js            # fetchConfig, createChatStream, DEFAULT_CONFIG
    styles.css        # All widget styles (injected into shadow root)
    __tests__/        # vitest + @testing-library/preact
  index.html          # Dev harness
  vite.config.js      # iife library mode, Preact alias, jsdom test env
```

The widget reads its config at load time from `/widgets/{wid}/config` and styles itself accordingly (theme, greeting, enabled tools).

### 13.3 Embed Flow and Origin Allowlisting

1. Host pastes `<script src="http://localhost:8000/widget.js" data-widget-id="abc">` into their HTML.
2. The browser fetches `/widget.js` (the loader).
3. The loader injects an iframe whose `src` is the React widget bundle, passing the `widget_id`.
4. The iframe loads the bundle, which fetches its config from `/widgets/{wid}/config`.
5. The widget reads `theme`, `greeting`, and `enabled_tools` from the config and renders itself accordingly.

The CORS allowlist is enforced from the widget's `allowed_origins` field in the database, **not** from a hardcoded env var. The embed route also sets `Content-Security-Policy: frame-ancestors <allowed_origins>` so a host whose origin is not in the allowlist gets blocked by the browser at iframe-embed time.

The Friday demo runs the widget in `demo/host/` on an allowed origin and shows it blocked on a host whose origin is not in the allowlist. Both demos use real browser network and console output.
