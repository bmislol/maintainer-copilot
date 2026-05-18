# SECURITY.md

Last updated: 2026-05-18

## 1. Security Goals

The Maintainer's Copilot is an authenticated chatbot whose users paste real issue text into it. That text routinely contains secrets people did not mean to share — stack traces with tokens, environment variables, signed URLs. The security model targets:

- No secrets committed to Git.
- All runtime secrets resolved from Vault at startup.
- JWT-based authentication.
- Role-based authorization (`user`, `admin`).
- Audit logging for every long-term memory write, widget configuration change, and role change.
- A redaction layer that runs before any log line, trace span, or memory write leaves a service boundary.
- Hard refusal to start when required security dependencies are missing.

## 2. Secret Handling

No secret is hardcoded in application code.

`.env` contains only bootstrap values needed to reach Vault and configure local ports:

```env
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=dev-only-root-token
API_PORT=8000
ADMIN_PORT=8501
WIDGET_PORT=8000
HOST_PORT=8080
LANGFUSE_PORT=3001
```

All application secrets are resolved from Vault at startup via `app/infra/vault.py::load_secrets()`.

**Verification:**

```bash
grep -ri 'sk-' backend/app/
grep -ri 'password' backend/app/
```

Expected: zero matches outside Vault-reading adapters and library-required field names.

## 3. Vault KV v2 Layout

Secrets are stored under `secret/data/maintainers-copilot/` in Vault KV v2.

| Path | Contains |
|---|---|
| `secret/data/maintainers-copilot/jwt` | JWT signing secret, algorithm, token lifetime. |
| `secret/data/maintainers-copilot/db` | Postgres URL with password. |
| `secret/data/maintainers-copilot/redis` | Redis URL. |
| `secret/data/maintainers-copilot/minio` | MinIO access key and secret key. |
| `secret/data/maintainers-copilot/anthropic` | Anthropic API key. |
| `secret/data/maintainers-copilot/langfuse` | Langfuse public + secret keys. |

Seeded by `vault-init` at compose startup from docker-compose environment variables (dev-only defaults).

## 4. Authentication

`fastapi-users` with JWT (Bearer transport).

Rules:

- JWT signing key resolves from Vault at startup.
- JWT payload contains user ID and role(s) only — no sensitive information.
- Every protected route requires a valid Bearer token.
- Registration is admin-invite-only. No public `/register` endpoint exists in the final flow.

## 5. Authorization

Two roles:

- `user` — log in, chat, view own memory, delete own conversations.
- `admin` — all user permissions, plus invite users, create/edit widget configurations, view audit log.

Role-enforcement mechanism: TBD (Phase 4.1). Permission checks happen in `app/services/`, never in routers.

## 6. Audit Log

Single `audit_log` table. Schema:

```text
audit_log(
  id           uuid primary key,
  actor        uuid not null,        -- user_id of the acting user
  action       text not null,        -- snake_case event name
  target       text,                 -- target identifier
  request_id   uuid not null,
  trace_id     text,
  metadata     jsonb,
  created_at   timestamptz not null
)
```

Audit-logged actions:

- `user.invited`
- `user.role_changed`
- `conversation.deleted`
- `memory.written` — every long-term memory write
- `widget.created`
- `widget.updated`
- `widget.allowed_origins_changed`

The audit log itself is read-only over HTTP (admin-only) and append-only at the DB level (no `UPDATE` or `DELETE` from the service layer).

## 7. Redaction Layer

A single redaction module at `app/infra/redaction.py` runs before any string leaves a service boundary. It is called by:

- the structured logger before emitting a log line,
- the Langfuse adapter before attaching span input/output attributes,
- the long-term memory writer before persisting embedded text,
- the short-term memory writer before persisting recent turns.

### 7.1 Patterns

Pattern list and defense — filled by Phase 3.5. Reserved categories:

| Category | Examples |
|---|---|
| API keys | OpenAI-style `sk-...`, Anthropic-style `sk-ant-...`, generic high-entropy bearer tokens. |
| GitHub tokens | `ghp_...`, `gho_...`, `ghs_...`, `github_pat_...`. |
| AWS keys | `AKIA...`, secret access keys following the standard 40-char pattern. |
| Signed URLs | Pre-signed S3, MinIO, Azure SAS URLs. |
| Database URLs | URI form with embedded password. |
| JWTs | `eyJ...` three-segment base64-url tokens. |
| Email addresses | Optionally redacted depending on policy; default = preserved with hash. |

The defense for what is in and what is out lives next to the pattern table once Phase 3.5 lands.

### 7.2 Redaction Test

The CI redaction test sends a chatbot message containing a fake API key (`sk-test-FAKE-not-real`) and asserts that the literal string never appears in:

- structured log output captured during the request,
- Langfuse trace spans for that request,
- the short-term Redis entry for the conversation,
- any long-term memory row written by the turn.

If any of those four locations contains the literal, the test fails and merge is blocked.

## 8. CORS and CSP for the Widget

The widget is the only public-facing surface that runs in a host's browser. Two layers protect it.

### 8.1 CORS Allowlist

CORS is enforced from the widget's `allowed_origins` field in the `widgets` table, not from a hardcoded environment variable. When the widget bundle calls `/widgets/{wid}/config` and `/chat/send`, the API reads the widget row, compares the request `Origin` header against `allowed_origins`, and rejects with 403 if it does not match.

### 8.2 Frame-Ancestors CSP

The route that serves the widget bundle (and the loader at `/widget.js`) sets:

```text
Content-Security-Policy: frame-ancestors <space-separated allowed origins from the widget row>
```

A host whose origin is not in the allowlist cannot iframe the widget — the browser blocks the embed at load time with a console error. This is the second layer on top of CORS.

## 9. Refuse-to-Boot Security Checks

The `api` refuses to start if:

- Vault is unreachable.
- Any committed eval threshold is set to zero or disabled (a zero threshold means "no quality gate" and is treated as a security/quality regression).

The `modelserver` refuses to start if:

- Classifier weights are missing.
- Weights' SHA-256 does not match `model_card.json`.
- `test_macro_f1` in `model_card.json` is below the committed startup threshold.

## 10. Defense Notes (Friday)

Questions to be ready to answer in the live review:

- Where does an Anthropic API key resolve from at startup? Show the code path.
- A user pastes a stack trace with a GitHub token. Trace it through logs, traces, short-term memory, long-term memory. Show the redaction test.
- The CORS allowlist lives where? Why not in env? Show the widget row and the service that reads it.
- Vault becomes unreachable while the app is running. What happens, what should happen, where is the policy? (Filled by Phase 1.4.)
