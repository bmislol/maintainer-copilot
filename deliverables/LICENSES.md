# LICENSES.md

Last updated: 2026-05-18

This document tracks third-party software, model weights, and data sources used by the Maintainers' Copilot, with their licenses.

## 1. Project License

The Maintainer's Copilot source code: TBD (filled by Phase 5.1 — likely MIT for academic submission).

## 2. Dataset

### FastAPI Closed Issues

- Source: `https://github.com/tiangolo/fastapi`
- Used: closed issues fetched via the GitHub REST API for classifier training and a held-out slice as part of the RAG corpus.
- Repository license: MIT.
- Issue text license: GitHub Terms of Service allow reuse for research and tooling purposes; attribution preserved in dataset metadata.
- Local dataset cache stored at `backend/data/issues/` — not committed (in `.gitignore`).

### FastAPI Documentation

- Source: `https://github.com/tiangolo/fastapi/tree/master/docs`
- Used: RAG corpus.
- License: MIT (repository-wide).

## 3. Models

| Model | Use | License | Filled by |
|---|---|---|---|
| Fine-tuned encoder (backbone TBD) | Issue classification | Inherits backbone license. | Phase 2.1 |
| NER model | Code-shaped entity extraction | TBD | Phase 2.5 |
| Summarization model | Thread summarization | TBD | Phase 2.5 |
| Embedding model | RAG retrieval | TBD | Phase 3.1 |
| Cross-encoder reranker | RAG reranking | TBD | Phase 3.3 |
| Anthropic Claude (API) | Chatbot generation, classification baseline, optional judge | Anthropic commercial terms. | Phase 1.x |

## 4. Python Dependencies

Top-level Python dependencies and their licenses. Final list filled by Phase 5.1. Reserved table:

| Package | Purpose | License |
|---|---|---|
| `fastapi` | API framework | MIT |
| `pydantic` | Schemas | MIT |
| `sqlalchemy` | ORM | MIT |
| `alembic` | Migrations | MIT |
| `fastapi-users` | Auth | MIT |
| `pgvector` | Vector store | Apache-2.0 |
| `redis` | Cache and short-term memory | MIT |
| `minio` | S3-compatible client | Apache-2.0 |
| `hvac` | Vault client | Apache-2.0 |
| `anthropic` | LLM SDK | MIT |
| `langfuse` | Tracing | MIT |
| `streamlit` | Admin UI | Apache-2.0 |
| `ruff` | Lint + format | MIT |
| `mypy` | Type-check | MIT |
| `pytest` | Tests | MIT |
| `ragas` (if used) | RAG eval | Apache-2.0 |

## 5. JavaScript Dependencies

Filled by Phase 4.5.

| Package | Purpose | License |
|---|---|---|
| `react` | Widget UI | MIT |
| `react-dom` | Widget UI | MIT |
| `vite` | Bundler | MIT |
| `tailwindcss` (if used) | Styling | MIT |

## 6. Infrastructure Images

| Image | License |
|---|---|
| `postgres:16` | PostgreSQL License (permissive) |
| `redis:7` | BSD-3-Clause (Redis core licensing transition noted; pinned tag uses BSD) |
| `minio/minio` | AGPL-3.0 (used locally, not redistributed) |
| `hashicorp/vault` (dev) | BSL-1.1 (HashiCorp; used as a dev-mode local dependency) |
| `langfuse/langfuse` | MIT |
| `nginx` | BSD-2-Clause |
