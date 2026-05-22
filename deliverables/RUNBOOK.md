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

## 6. Demo Flow (Friday)

### 6.1 Pre-demo setup (do before the presentation)

Run these four steps in order. Steps 2 and 3 are idempotent — safe to re-run.

**Step 1 — Start the stack:**

```bash
docker compose up -d
```

Wait ~30 seconds for Langfuse to become ready. Verify:

```bash
docker compose ps
curl -s http://localhost:8000/healthz        # {"status":"ok"}
curl -s http://localhost:8080/               # HTML — Acme OSS Docs
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

Expected output: `Admin user created: admin@maintainer-copilot.dev`

**Step 3 — Bootstrap the demo widget** (skip if already done):

```bash
export DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot"

cd backend
uv run python -m scripts.bootstrap_widget
```

Expected output:
```
Demo widget created: 00000000-0000-0000-0001-000000000001
  name:            Demo Widget
  owner:           admin@maintainer-copilot.dev
  allowed_origins: ['http://localhost:8080']
```

The demo widget UUID `00000000-0000-0000-0001-000000000001` is hardcoded in both the script and `demo/host/public/index.html` — no manual copy-paste required.

**Step 4 — Rebuild the demo host** (only needed after code changes):

```bash
docker compose build host && docker compose up -d host
```

Then open `http://localhost:8080` — the 🤖 bubble should appear in the bottom-right corner.

---

### 6.2 10-minute walkthrough

**1. Streamlit admin login**
- Open `http://localhost:8501`
- Log in: `admin@maintainer-copilot.dev` / `change-me-before-demo`
- Show the sidebar: email display, Logout button, four nav pages

**2. Chat — tool-calling demo**
- Navigate to **Chat** page
- Send: _"Classify this issue: 'np.array crashes with float16 dtype on ARM'"_
- Point out: classification (bug), NER extraction (function name, dtype), RAG context chunks cited
- Show `Conversation: <uuid>` caption below the response
- Open Langfuse (`http://localhost:3001`) — find the trace; walk through the tool call spans

**3. Memory — cross-conversation recall**
- In conversation A (current), send:
  _"Remember: the CI gate requires macro_f1 ≥ 0.90 before any merge"_
  (Claude calls `write_memory`)
- Click **New Conversation** — session B starts
- Send: _"What quality threshold must pass before code is merged?"_
- Claude recalls the stored fact — point to the pgvector similarity match
- Navigate to **Memory Inspector** — show the episodic entry with `created_at`

**4. Widget Config page**
- Navigate to **Widget Configuration**
- Show the form: name, theme, greeting, enabled_tools, allowed_origins
- Show the embed snippet that appears after creation/update
- Explain: `allowed_origins` drives both CORS and `frame-ancestors` CSP

**5. Demo host — widget loads (ALLOWED origin)**
- Open `http://localhost:8080` in a browser
- The 🤖 bubble appears in the bottom-right corner
- Click the bubble — panel opens with "Maintainer's Copilot" header and greeting
- Type "hello" → real LLM response streams in
- In browser DevTools → Network tab: show `loader.js` → `widget.js` → `/chat/send?widget_id=…`
- In DevTools → Response headers for `widget.js`:
  ```
  content-security-policy: frame-ancestors 'self' http://localhost:8080
  ```

**6. Blocked origin demo (CSP violation)**
- Open `http://localhost:8081` (the widget nginx container — NOT in allowed_origins)
- Open DevTools → Console
- Show the CSP violation:
  ```
  Refused to frame 'http://localhost:8000' because an ancestor violates
  the following Content Security Policy directive: "frame-ancestors 'self'
  http://localhost:8080".
  ```
- The bubble does NOT appear — the embed is blocked at the browser level

**7. CI green + eval gates**
- Show GitHub Actions for the `main` branch — all checks green
- Open `backend/eval_thresholds.yaml` — point to `classification.macro_f1: 0.90` and `rag.hit_at_5: 0.8583`
- These are hard gates: if a PR makes the model worse, CI fails before merge

**8. Redaction demo**
- Run: `docker compose exec api pytest tests/test_redaction.py -v`
- Show all assertions pass — API keys, emails, tokens are `[REDACTED]` in logs and traces

---

### 6.3 Expected URLs at demo time

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Streamlit admin | http://localhost:8501 |
| Demo host (allowed) | http://localhost:8080 |
| Widget nginx (blocked) | http://localhost:8081 |
| Langfuse traces | http://localhost:3001 |
| MinIO console | http://localhost:9001 |

## 7. Common Issues

Filled as the project grows. Reserved slots:

**Langfuse race condition on fresh boot.** After `docker compose up -d` (especially following a `down -v`), api may refuse to boot because it tried to connect to Langfuse before Langfuse's web server started accepting connections. Langfuse has no docker healthcheck (DECISIONS D-004 explains why), so docker considers it "started" the moment its container exists. Wait ~20 seconds and re-run `docker compose up -d api`. The api's `auth_check()` against Langfuse is the real liveness probe.

- Port collisions on first boot. If docker compose up fails with address already in use, find what's holding the port with sudo lsof -i :<port> and either stop the conflicting process or change the matching *_PORT in .env. The common offenders are 5432 (system Postgres) and 6379 (system Redis).

- Langfuse first-boot signup (create the org and project; copy keys into Vault).
- Postgres pgvector extension creation on first migration.
- MinIO bucket policy mismatch.
- Classifier weight SHA-256 drift after retraining.
- Widget `frame-ancestors` blocking the dev origin during local testing.
