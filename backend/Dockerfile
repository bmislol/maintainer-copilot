# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

# uv is installed from the official image, copied into our base
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ─── Dependency layer ──────────────────────────────────────────────
# Copy ONLY lockfile + pyproject first so dep changes invalidate this layer
# but source changes don't. Big win for build times.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ─── Source layer ──────────────────────────────────────────────────
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

COPY eval_thresholds.yaml ./eval_thresholds.yaml

# Install the project itself (does not re-resolve deps)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Make uv-installed binaries available
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# CMD is overridden per service in docker-compose.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]