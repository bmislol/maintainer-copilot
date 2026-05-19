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

Troubleshooting commands:

```bash
docker compose logs vault-init
docker compose logs migrate
docker compose logs api
docker compose logs modelserver
```

If Vault is restarted, vault-init must also be re-run to re-seed the dev secrets (docker compose up -d --force-recreate vault-init). This is a dev-mode-only concern; production Vault uses persistent storage.

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

- Port collisions on first boot. If docker compose up fails with address already in use, find what's holding the port with sudo lsof -i :<port> and either stop the conflicting process or change the matching *_PORT in .env. The common offenders are 5432 (system Postgres) and 6379 (system Redis).

- Langfuse first-boot signup (create the org and project; copy keys into Vault).
- Postgres pgvector extension creation on first migration.
- MinIO bucket policy mismatch.
- Classifier weight SHA-256 drift after retraining.
- Widget `frame-ancestors` blocking the dev origin during local testing.
