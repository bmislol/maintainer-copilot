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

Last updated: 2026-05-21 (Phase 4.1)

`fastapi-users 13.x` with `BearerTransport` + `JWTStrategy`.

- **JWT signing key** — resolved from Vault at lifespan startup; stored in `app.state.secrets.jwt`. The `get_jwt_strategy` FastAPI dependency reads it from `request.app.state` at request time. It is never present in environment variables, never logged, and never committed to Git.
- **Algorithm** — `HS256` (seeded by `vault-init.sh`; production deployments should replace with a 256-bit random key).
- **Token lifetime** — configurable via Vault (`access_token_lifetime_seconds`); dev default is 3600 s.
- **Token payload** — contains user `id` (UUID) only. No role, no email, no PII in the JWT body.
- **Every protected route** requires a valid `Authorization: Bearer <token>` header. Missing or expired tokens return 401.
- **No public `/register` endpoint** — `fastapi_users.get_register_router()` is not mounted. New users can only be created via `bootstrap_admin.py` (first admin) or a future admin-invite endpoint (Phase 4.4).

## 5. Authorization

Last updated: 2026-05-21 (Phase 4.1)

Two roles stored as `is_superuser: bool` on the `users` table (D-033):

| Role | `is_superuser` | Permissions |
|---|---|---|
| `user` | `False` | Log in, chat, view own memory, delete own conversations. |
| `admin` | `True` | All user permissions + invite users, create/edit widget configs, view audit log. |

**Enforcement:** `current_active_superuser` dependency from `app/infra/auth.py` is applied at the route level for admin-only endpoints. A non-superuser token reaching such a route receives a 403 before the handler function executes. Permission checks are in route dependencies, not in service logic — the service layer trusts that callers are already authorized.

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

Last updated: 2026-05-21 (Phase 3.5 / D-022)

A single redaction module at `app/infra/redaction.py` exposes one function: `redact(text: str) -> str`. It is called before any string crosses a service boundary:

- **Structured logger** — `RedactionFilter` is attached to the root `StreamHandler` in `app/core/logging.py::configure_logging()`. The filter mutates `record.msg` in-place before the `JSONFormatter` runs, so every log line — whether emitted by the `api` service or any child logger — is redacted. (Filter is on the handler, not the root logger; see D-022 for why handler attachment is required.)
- **Langfuse adapter** — `app/infra/tracing.py::redact_metadata()` wraps every `metadata=` dict passed to `langfuse.trace()` and `langfuse.span()` calls. String values are redacted; non-string values are unchanged.
- **Long-term memory writer** — will call `redact()` on the text field before the pgvector `INSERT` (Phase 4.3).
- **Short-term memory writer** — will call `redact()` on the turn content before the Redis `SETEX` (Phase 4.3).

### 7.1 Patterns

Eight patterns, compiled once at import time, applied in most-specific-first order. Full rationale in D-022.

| Pattern | Matches | Notes |
|---|---|---|
| `sk-ant-[A-Za-z0-9\-]+` | Anthropic API keys | Placed before generic `sk-` rule |
| `sk-[A-Za-z0-9\-]{20,}` | Generic `sk-` bearer tokens | Hyphens included; 20-char floor avoids short identifiers |
| `gh[ps]_[A-Za-z0-9]{36}` | GitHub classic PATs and server tokens | Matches `ghp_` and `ghs_` |
| `github_pat_[A-Za-z0-9_]{82}` | GitHub fine-grained PATs | 82-char body per GitHub spec |
| `hvs\.[A-Za-z0-9]+` | HashiCorp Vault service tokens | KV v2 format |
| `postgresql://[^\s]+` | Postgres DSNs | Entire URI redacted (user+password+host) |
| `[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` | JWT tokens | Conservative 3-segment heuristic; 10-char floor avoids version strings |
| `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}` | Email addresses (PII) | Redacted per GDPR principle of data minimisation |

**Intentionally out of scope (deferred until used):** AWS access keys (`AKIA...`), pre-signed URLs (`X-Amz-Signature`, `sig=`). No production path in this project exercises these; adding untested patterns creates false confidence.

### 7.2 Redaction Test

`tests/test_redaction.py` — eight tests, all mandatory for CI green:

| Test | What it proves |
|---|---|
| `test_anthropic_key_is_redacted` | `sk-test-FAKE-not-real` (the graded mandatory string) never appears unredacted |
| `test_postgres_dsn_is_redacted` | Full DSN including password field is replaced |
| `test_clean_text_passes_through` | No false positives on clean prose |
| `test_log_filter_redacts_in_log_output` | `caplog.text` contains `[REDACTED]`, not the raw key; proves filter is active in the live logging pipeline |
| `test_github_token_is_redacted` | `ghp_` + 36-char body is caught |
| `test_vault_token_is_redacted` | `hvs.` prefix token is caught |
| `test_email_is_redacted` | `user@example.com` is caught |
| `test_multiple_secrets_in_one_string` | A single string with three different secret types produces ≥ 3 `[REDACTED]` tokens |

The mandatory grading criterion — `sk-test-FAKE-not-real` must never appear unredacted in any output — is enforced by `test_anthropic_key_is_redacted` and `test_log_filter_redacts_in_log_output`.

## 8. CORS and CSP for the Widget

The widget is the only public-facing surface that runs in a host's browser. Three layers protect it.

### 8.1 CORS Allowlist (D-026)

CORS is enforced from the **union of all `allowed_origins` across every widget row**, not from a hardcoded environment variable. The `DynamicCORSMiddleware` (pure ASGI, `app/api/cors.py`) reads `app.state.allowed_origins` at every request:

- **Non-preflight:** If the request `Origin` is in the set, `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` are added to the response. Otherwise no CORS headers are added (browser rejects the actual request).
- **OPTIONS preflight:** Allowed origins receive a 204 with full CORS headers. Blocked origins receive a 204 with no CORS headers (standard passive block — no 403 that would reveal which origins are known).
- **Live updates:** `app.state.allowed_origins` is loaded from DB at startup and refreshed after every `POST /widgets/` and `PATCH /widgets/{id}` call. No restart required to activate new origins.

The `/widgets/{id}/config` endpoint is intentionally public (no auth). It returns only `{id, theme, greeting, enabled_tools}` — the `allowed_origins` field is **never exposed in the JSON response** and is server-side only.

### 8.2 Frame-Ancestors CSP (D-027)

`GET /static/widget.js` is a dedicated FastAPI endpoint (not a `StaticFiles` mount) that sets:

```text
Content-Security-Policy: frame-ancestors 'self' <space-separated sorted allowed_origins>
```

Example after creating a widget with `allowed_origins: ["http://localhost:8080"]`:

```text
Content-Security-Policy: frame-ancestors 'self' http://localhost:8080
```

A host whose origin is not in the allowlist **cannot embed the widget in an iframe** — the browser blocks the embed at load time with a CSP violation in the console. This is the OWASP-recommended mechanism; `X-Frame-Options: ALLOW-FROM` is deprecated and supports only a single origin.

Like CORS, this header reflects the live database state (refreshed on widget create/update).

### 8.3 Widget Auth (get_widget_user)

Embedded widget sessions use `?widget_id=<UUID>` instead of a Bearer JWT. The `get_widget_user` dependency (Phase 4.6) looks up the widget in the `widgets` table, validates it has an active owner, and returns that owner as the acting user. A `widget_id` that doesn't exist in the database returns 403. This prevents arbitrary UUID guessing from gaining chat access.

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
