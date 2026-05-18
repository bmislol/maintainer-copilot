# Maintainer's Copilot

Authenticated chatbot for OSS maintainers — classifies issues (bug/feature/docs/question), extracts entities, summarizes threads, and answers questions via advanced RAG over the project's docs and resolved issues. Streamlit admin app + embeddable React widget on a single FastAPI backend.

Week 7 of the AIE Program. Solo project.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Full operational guide: [`deliverables/RUNBOOK.md`](deliverables/RUNBOOK.md).

## Project Documents

| Doc | What's inside |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Project description, phase plan, daily quickstart. **Start here.** |
| [`deliverables/ARCH.md`](deliverables/ARCH.md) | System architecture, flow diagram, services, layer rules. |
| [`deliverables/DECISIONS.md`](deliverables/DECISIONS.md) | Architecture and implementation decisions (D-XXX format). |
| [`deliverables/RUNBOOK.md`](deliverables/RUNBOOK.md) | Local startup, admin bootstrap, demo flow. |
| [`deliverables/EVALS.md`](deliverables/EVALS.md) | Classification + RAG golden sets and CI gates. |
| [`deliverables/SECURITY.md`](deliverables/SECURITY.md) | Vault layout, redaction, CORS/CSP, audit log. |
| [`deliverables/LICENSES.md`](deliverables/LICENSES.md) | Licenses for code, models, dataset, dependencies. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branch naming, commit conventions, PR workflow. |

## Tech Stack (Locked Decisions)

| | |
|---|---|
| Language | Python 3.12 (`uv`-managed) |
| API | FastAPI |
| Auth | fastapi-users + JWT |
| Database | Postgres 16 + pgvector |
| Cache / short-term memory | Redis 7 |
| Blob | MinIO |
| Secrets | HashiCorp Vault (dev mode) |
| Tracing | Langfuse (self-hosted) |
| LLM | Anthropic Claude |
| Admin UI | Streamlit |
| Widget | React + Vite |