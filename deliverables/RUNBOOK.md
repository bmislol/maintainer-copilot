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

## 3. Bootstrap the First Admin User

Filled by Phase 4.1.

```bash
# Step 1 — create the user
docker compose exec api uv run python -m app.entrypoints.bootstrap_admin \
  --email admin@example.com --password <password>

# Step 2 — promote to admin role
docker compose exec api uv run python -m app.entrypoints.bootstrap_admin_role \
  --email admin@example.com
```

Verify login:

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin@example.com&password=<password>"
```

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

10-minute walkthrough. Filled by Phase 5.3.

1. Open Streamlit admin, log in as the admin user.
2. Show the chat: classify, NER, summarize, RAG answer with cited chunks.
3. Show cross-conversation memory recall (write memory in conversation A; recall it in conversation B).
4. Open Langfuse, walk through the trace tree for the most recent conversation, including one error path.
5. Open `http://localhost:8080` (the allowed `demo/host/` page); show the widget appearing in the corner; send a message.
6. Open the second host page on a disallowed origin; show the browser blocking the embed via `frame-ancestors` (open the dev tools console and point to the blocked-by-CSP error).
7. Show CI green on `main` with both eval gates passing.
8. Show the redaction test passing (a fake API key never appears unredacted in logs, traces, or memory).

## 7. Common Issues

Filled as the project grows. Reserved slots:

**Langfuse race condition on fresh boot.** After `docker compose up -d` (especially following a `down -v`), api may refuse to boot because it tried to connect to Langfuse before Langfuse's web server started accepting connections. Langfuse has no docker healthcheck (DECISIONS D-004 explains why), so docker considers it "started" the moment its container exists. Wait ~20 seconds and re-run `docker compose up -d api`. The api's `auth_check()` against Langfuse is the real liveness probe.

- Port collisions on first boot. If docker compose up fails with address already in use, find what's holding the port with sudo lsof -i :<port> and either stop the conflicting process or change the matching *_PORT in .env. The common offenders are 5432 (system Postgres) and 6379 (system Redis).

- Langfuse first-boot signup (create the org and project; copy keys into Vault).
- Postgres pgvector extension creation on first migration.
- MinIO bucket policy mismatch.
- Classifier weight SHA-256 drift after retraining.
- Widget `frame-ancestors` blocking the dev origin during local testing.
