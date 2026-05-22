# RUNBOOK.md

Operational guide for the Maintainer's Copilot.

## 1. First-Time Local Startup

```bash
git clone <repo-url>
cd maintainers-copilot
cp .env.example .env
docker compose up --build
```

`.env.example` contains only the Vault dev root token and port assignments. No application secrets live in `.env`.

Expected startup order:

1. `vault` starts in dev mode.
2. `vault-init` seeds Vault KV paths with dev secrets and exits.
3. `db`, `redis`, `minio`, `langfuse` start.
4. `minio-init` creates required buckets and exits.
5. `migrate` runs `alembic upgrade head` and exits.
6. `modelserver`, `api`, `chatbot`, `widget`, `host` start.

Access points:

| Service | URL |
|---|---|
| Streamlit admin | http://localhost:8501 |
| API + Swagger | http://localhost:8000/docs |
| Demo host page (embed target) | http://localhost:8080 |
| Widget bundle | http://localhost:8081 |
| Langfuse UI | http://localhost:3001 |
| MinIO console | http://localhost:9001 |
| Vault UI | http://localhost:8200 |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

## 2. Refuse-to-Boot Checks

The `api` refuses to boot if:
- Vault is unreachable.
- Langfuse is misconfigured.
- Any committed threshold in `eval_thresholds.yaml` is zero or disabled.

The `modelserver` refuses to boot if:
- Classifier weights are missing.
- Weights' SHA-256 does not match `model_card.json`.
- `test_macro_f1` in `model_card.json` is below the committed startup threshold.

**Manually proving eval-threshold refuse-to-boot:**

```bash
# Temporarily zero out a threshold
sed -i 's/macro_f1: 0.90/macro_f1: 0/' backend/eval_thresholds.yaml

docker compose restart api
docker compose logs api --tail=15
# Expect: "REFUSING TO BOOT: backend/eval_thresholds.yaml has classification.macro_f1=0 (must be > 0)"
# api container in Exited (3) state.

# Restore
sed -i 's/macro_f1: 0/macro_f1: 0.90/' backend/eval_thresholds.yaml
docker compose up -d api
```

Troubleshooting commands:

```bash
docker compose logs vault-init
docker compose logs migrate
docker compose logs api
docker compose logs modelserver
```

If Vault is restarted, vault-init must also be re-run...

**Manually proving Vault refuse-to-boot:** ...

**Manually proving Langfuse refuse-to-boot:** ...

**Manually proving modelserver refuse-to-boot:**

modelserver downloads `classifier.pt`, `tokenizer/`, and `model_card.json` from MinIO at startup. The refuse-to-boot conditions listed above are demonstrated as follows:

```bash
docker compose stop minio
docker compose restart modelserver
docker compose logs modelserver --tail=15
# Expect: "could not download model_card.json" + REFUSING TO BOOT + Exited (3)

docker compose start minio
docker compose up -d modelserver
```

If Vault is restarted, vault-init must also be re-run to re-seed the dev secrets (docker compose up -d --force-recreate vault-init). This is a dev-mode-only concern; production Vault uses persistent storage.

**Manually proving Langfuse-refuse-to-boot:**

```bash
docker compose stop langfuse
docker compose restart api
docker compose logs api --tail=20
# Expect: "REFUSING TO BOOT: Could not reach Langfuse at http://langfuse:3000: ..."
# api container will be in Exited (3) state.

# Restore:
docker compose start langfuse
sleep 10
docker compose up -d api
```

modelserver downloads `classifier.pt`, `tokenizer/`, and `model_card.json` from MinIO at startup. It refuses to boot if:
1. MinIO is unreachable.
2. The downloaded `classifier.pt` SHA-256 does not match `model_card.json`.
3. `test_macro_f1` in `model_card.json` is below the committed threshold (0.60).
4. **The NER model `dslim/bert-base-NER` cannot be loaded from HuggingFace Hub.** *(Phase 2.5)*

## 3. Bootstrap the First Admin User

Last updated: 2026-05-21 (Phase 4.1)

`bootstrap_admin.py` runs host-side and connects directly via `DATABASE_URL`. It does not go through Vault or the API. Run it once after `docker compose up` has the DB migrated.

**Prerequisites:** compose stack is up; `migrate` service has exited 0 (`docker compose ps migrate`).

```bash
# Obtain the DB URL (same credentials used in .env.example dev defaults)
export DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot"
export BOOTSTRAP_EMAIL="admin@maintainer-copilot.dev"
export BOOTSTRAP_PASSWORD="change-me-before-demo"

cd backend
uv run python -m app.entrypoints.bootstrap_admin
```

Expected output:
```
Admin user created: admin@maintainer-copilot.dev
```

The script exits non-zero if `DATABASE_URL`, `BOOTSTRAP_EMAIL`, or `BOOTSTRAP_PASSWORD` are missing, or if a user with that email already exists.

**Verify login:**

```bash
curl -s -X POST http://localhost:8000/auth/jwt/login \
  -d "username=admin@maintainer-copilot.dev&password=change-me-before-demo" \
  | python3 -m json.tool
```

Expected: JSON with `access_token` and `token_type: bearer`.

**Verify /users/me:**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/jwt/login \
  -d "username=admin@maintainer-copilot.dev&password=change-me-before-demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/users/me \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

Expected: user JSON with `"is_superuser": true`.

## 4. Running the Eval Suites

Filled by Phase 2.4 (classification) and Phase 3.4 (RAG).

```bash
# Classification eval (25-item golden set)
docker compose exec api uv run python -m app.eval.classification.run_eval

# RAG eval (25-item golden set)
docker compose exec api uv run python -m app.eval.rag.run_eval
```

Each run writes an `eval_report.json` to MinIO and diffs against the previous green build. CI fails if any committed threshold regresses.

## 5. Reset to a Clean State

Wipes all persistent volumes (Postgres data, Redis state, MinIO objects, Vault state, Langfuse data).

```bash
docker compose down -v
```

After a reset, re-run the first-time startup (Section 1) and the admin bootstrap (Section 3).

### Classification eval gate (Phase 2.4)

Run from `backend/`:

```bash
set -a; source ../.env; set +a
uv run pytest -m eval -v -s
```

Cost: ~$0.05 per invocation against Anthropic API. Skip in regular development; the CI workflow runs it automatically on path-relevant PRs.

For local Anthropic-free runs (skip the gate test):

```bash
uv run pytest        # default skips @pytest.mark.eval
```

## 6. Friday Demo Script

### 6.1 Prerequisites (run before presenting — ~5 min)

Steps 2 and 3 are idempotent: safe to re-run if unsure.

**Step 1 — Start the stack:**

```bash
docker compose up -d
```

Wait ~30 seconds for Langfuse to initialise. Verify everything is up:

```bash
docker compose ps
curl -s http://localhost:8000/healthz        # {"status":"ok"}
curl -s http://localhost:8080/               # HTML — Acme OSS Docs
curl -s http://localhost:8090/blocked.html   # HTML — Blocked Host
curl -s http://localhost:8501/_stcore/health # ok
```

**Step 2 — Bootstrap the admin user** (skip if already done):

```bash
export DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot"
export BOOTSTRAP_EMAIL="admin@maintainer-copilot.dev"
export BOOTSTRAP_PASSWORD="change-me-before-demo"

cd backend
uv run python -m app.entrypoints.bootstrap_admin
```

Expected: `Admin user created: admin@maintainer-copilot.dev`

**Step 3 — Bootstrap the demo widget** (skip if already done):

```bash
export DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot"
cd backend
uv run python -m scripts.bootstrap_widget
```

Expected:
```
Demo widget created: 00000000-0000-0000-0001-000000000001
  name:            Demo Widget
  owner:           admin@maintainer-copilot.dev
  allowed_origins: ['http://localhost:8080']
```

The UUID `00000000-0000-0000-0001-000000000001` is hardcoded in both the script and `demo/host/public/index.html` — no manual copy-paste required.

**Step 4 — Rebuild demo host** (only if code changed since last run):

```bash
docker compose build host && docker compose up -d host
```

Open `http://localhost:8080` — the 🤖 bubble should appear.

---

### 6.2 Demo flow (10 minutes)

---

#### 1. Architecture overview (1 min)

_Open `docker-compose.yml` in the IDE._

> "Eleven services. Secrets in Vault — nothing in `.env` except the Vault root token
> and port assignments. Artifacts in MinIO. Traces in Langfuse. Logs redacted before
> they leave the process."

Point to the startup order: vault → vault-init seeds secrets → db/redis/minio/langfuse
→ migrate runs Alembic → api/modelserver/chatbot/widget/host start.

---

#### 2. Refuse-to-boot proof (30 sec)

_Open `backend/app/core/lifespan.py` — show the startup checks._

> "The API won't start unless Vault is reachable, Langfuse is reachable, and every
> eval threshold in `eval_thresholds.yaml` is non-zero. If a PR zeroes out a threshold
> the container exits with code 3 before serving a single request."

---

#### 3. Classification demo (1 min)

_Open Swagger at `http://localhost:8000/docs` → `POST /classify`._

Paste:
```json
{"text": "AdaBoost crashes with negative sample weights on sparse input"}
```

Expected response: `{"label": "bug", "confidence": ~0.57}`

> "Three classifiers compared on the same 578-item test set: TF-IDF + LogisticRegression,
> fine-tuned DistilBERT, and Claude Haiku. Haiku won on macro-F1. The modelserver
> serves the DistilBERT proof — both are live. Decision in DECISIONS.md D-012."

---

#### 4. Streamlit admin — chat + tool-calling (2 min)

_Open `http://localhost:8501`. Log in: `admin@maintainer-copilot.dev` / `change-me-before-demo`._

Send:
> _"Classify this issue: 'np.array crashes with float16 dtype on ARM processors'"_

Point out:
- Classification result (bug), NER entities extracted (function name, dtype, platform)
- RAG context chunks cited in the answer
- `Conversation: <uuid>` caption below — that UUID traces directly to Langfuse

_Switch to Langfuse at `http://localhost:3001`. Find the trace. Walk through spans:_
- `chatbot_turn` span wrapping the full turn
- `tool_use` → `classify_issue` → modelserver call
- `tool_use` → `extract_entities` → modelserver call
- `tool_use` → `retrieve_docs` → pgvector query

---

#### 5. Memory — write and recall pipeline (1 min)

_Back in Streamlit Chat._

Send:
> _"Please remember: the CI gate requires macro_f1 ≥ 0.90 before any merge."_

Claude calls `write_memory`. Show the acknowledgement in the response.

_Click **New Conversation** (session B)._

Send:
> _"What quality threshold must pass before code is merged?"_

Claude should not recall this in-chat (no `search_memory` tool yet — deferred to
Phase 5). Instead, navigate to **Memory Inspector** — show the episodic entry written
in session A with its `created_at` timestamp. Then demonstrate the underlying pipeline:

```bash
# From backend/
DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot" \
uv run python -m scripts.demo_memory_recall
```

Expected output (measured 2026-05-23):
```
[Step 1] Conversation A  (id=158b13db…)
  → Sending: 'Please remember this for me: My name is Alex…'
  ← Claude replied: "Got it, Alex! I've saved that you prefer detailed explanations…"
  ✅ write_memory tool was called

[Step 2] Conversation B  (id=fd41461e…)
  → Querying pgvector: "What do I know about this user's background…"
  ← 2 entry/entries recalled from long-term memory:
     1. 'User name: Alex. Preference: Provide detailed explanations when debugging.'
     2. "User's name is Alex and prefers detailed explanations when debugging issues."
✅ PASS — written fact recalled via semantic similarity
```

> "Write is explicit-only — Claude only calls `write_memory` when asked. Every write
> produces an `audit_log` row with actor, action, target, request_id, trace_id.
> Retrieval is pgvector cosine similarity over all-MiniLM-L6-v2 embeddings (384-dim).
> In-chat recall would be wired in Phase 5 via a `search_memory` tool."

---

#### 6. Widget Config + embed snippet (30 sec)

_Navigate to **Widget Configuration** in Streamlit._

> "Admin-only page. Name, theme, greeting, tools list, allowed origins. On save the
> API refreshes `app.state.allowed_origins` in-process — no restart needed to activate
> a new origin. The embed snippet is generated here and pasted into any host page."

Show the snippet:
```html
<script
  src="http://localhost:8000/loader.js"
  data-widget-id="00000000-0000-0000-0001-000000000001"
  data-api-base="http://localhost:8000">
</script>
```

---

#### 7. Widget — allowed origin (1 min)

_Open `http://localhost:8080` in a browser._

- The 🤖 bubble appears in the bottom-right corner (Shadow DOM — CSS isolated)
- Click the bubble → dark panel opens, greeting streams in
- Type "hello" → LLM response streams via SSE over POST

_Open DevTools → Network tab._
- `loader.js` → 200
- `widget.js` → 200 — show the `content-security-policy` response header:
  ```
  frame-ancestors 'self' http://localhost:8080
  ```
- `/chat/send?widget_id=…` → 200 (streaming)

> "The widget is 10.16 KB gzipped. Preact instead of React — 93% bundle reduction.
> Shadow DOM for CSS isolation. SSE over POST via `fetch` + `ReadableStream` because
> `EventSource` is GET-only."

---

#### 8. Widget — blocked origin CSP violation (1 min)

_Open `http://localhost:8090/blocked.html` in a NEW tab._

- The 🤖 bubble does NOT appear
- Open DevTools → Console:
  ```
  Refused to frame 'http://localhost:8000' because an ancestor violates
  the following Content Security Policy directive:
  "frame-ancestors 'self' http://localhost:8080"
  ```

> "The block is enforced at the browser level by the `frame-ancestors` directive on
> `widget.js`. `http://localhost:8090` is not in `allowed_origins` so the header
> excludes it. The allowed_origins set lives in the `widgets` DB row — not in an
> env variable — so a new origin activates immediately after a widget update with
> no restart."

---

#### 9. Eval gates (1 min)

_Open `backend/eval_thresholds.yaml`._

```yaml
classification:
  macro_f1: 0.90
  per_class_min_f1: 0.50
rag:
  hit_at_5: 0.8583
  reciprocal_rank: 0.7532
```

> "These are hard gates committed to the repo. CI runs the classification gate on
> every path-relevant PR. If a code change makes the model worse, CI fails before
> merge."

Last measured results (run 2026-05-23):

| Gate | Metric | Measured | Threshold | Status |
|---|---|---|---|---|
| Classification | macro-F1 | **1.0000** | 0.90 | ✓ |
| Classification | per-class min | **1.0000** | 0.50 | ✓ |
| RAG | hit@5 | **0.9583** (23/24) | 0.8583 | ✓ |
| RAG | MRR@10 | **0.8139** | 0.7532 | ✓ |

---

#### 10. Redaction proof (30 sec)

```bash
docker compose exec api uv run pytest tests/test_redaction.py -v
```

Expected: 8 passed.

> "A `RedactionFilter` is attached to the root log handler. It runs before the
> `JSONFormatter` so every log line — regardless of which logger emitted it — is
> redacted before it leaves the process. The mandatory grading criterion:
> `sk-test-FAKE-not-real` never appears unredacted in any output."

---

### 6.3 Fallback talking points if the live demo breaks

**Widget doesn't load (bubble doesn't appear):**
> "The widget is served from localhost:8000 via a dedicated route with
> `frame-ancestors` CSP headers. Let me show the curl output instead."

```bash
curl -s -I http://localhost:8000/widget.js
# Expected: HTTP/1.1 200 OK + content-security-policy: frame-ancestors 'self' http://localhost:8080
```

**Chat doesn't stream (typing indicator spins indefinitely):**
> "The SSE endpoint streams via POST + `fetch` + `ReadableStream`, not `EventSource` —
> that's intentional because `EventSource` is GET-only. Let me show the Swagger demo
> instead."
Navigate to `http://localhost:8000/docs` → `POST /classify` to show a live API response.

**Blocked host doesn't show a CSP error in the console:**
> "The enforcement is server-side via the `frame-ancestors` header. Let me show the
> CORS preflight block for an unknown origin directly."

```bash
curl -v -X OPTIONS http://localhost:8000/chat/send \
  -H "Origin: http://evil.com" \
  -H "Access-Control-Request-Method: POST" 2>&1 | grep -E "< HTTP|access-control"
# Expected: 204 with NO access-control-allow-origin header (passive block — origin not in allowlist)
```

---

### 6.4 URL reference

| Service | URL | Notes |
|---|---|---|
| API + Swagger | http://localhost:8000/docs | |
| Streamlit admin | http://localhost:8501 | login: admin@maintainer-copilot.dev / change-me-before-demo |
| Demo host (allowed) | http://localhost:8080 | widget loads, chat works |
| Blocked host (CSP demo) | http://localhost:8090/blocked.html | widget blocked, console CSP error |
| Widget bundle | http://localhost:8081 | raw nginx serving widget.js |
| Langfuse traces | http://localhost:3001 | |
| MinIO console | http://localhost:9001 | |
| Vault UI | http://localhost:8200 | |

## 7. Common Issues

Filled as the project grows. Reserved slots:

**Langfuse race condition on fresh boot.** After `docker compose up -d` (especially following a `down -v`), api may refuse to boot because it tried to connect to Langfuse before Langfuse's web server started accepting connections. Langfuse has no docker healthcheck (DECISIONS D-004 explains why), so docker considers it "started" the moment its container exists. Wait ~20 seconds and re-run `docker compose up -d api`. The api's `auth_check()` against Langfuse is the real liveness probe.

- Port collisions on first boot. If docker compose up fails with address already in use, find what's holding the port with sudo lsof -i :<port> and either stop the conflicting process or change the matching *_PORT in .env. The common offenders are 5432 (system Postgres) and 6379 (system Redis).

- Langfuse first-boot signup (create the org and project; copy keys into Vault).
- Postgres pgvector extension creation on first migration.
- MinIO bucket policy mismatch.
- Classifier weight SHA-256 drift after retraining.
- Widget `frame-ancestors` blocking the dev origin during local testing.
