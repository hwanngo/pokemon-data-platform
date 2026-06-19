# syntax=docker/dockerfile:1
# Application image (FastAPI API + CLI), built and run with uv on Alpine.
# All runtime deps (numpy, pandas, pyarrow, psycopg2-binary, uvloop, …) ship
# cp314 musllinux wheels, so no compiler/source build is needed.
FROM ghcr.io/astral-sh/uv:python3.14-alpine AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    # Keep the venv outside /app so the dev bind-mount (../:/app) can't shadow it.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Runtime shared libraries the musllinux wheels link against
# (libstdc++/libgomp for numpy/pandas/pyarrow). psycopg2-binary bundles libpq.
RUN apk add --no-cache libstdc++ libgomp

# 1) Install dependencies first (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra prod

# 2) Install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra prod

# Run as a non-root user (the venv + code are world-readable; the cache dir is
# the only runtime write target and is a bind mount).
RUN adduser -D -u 10001 appuser
USER appuser

# Default command (overridden by docker-compose to run uvicorn).
CMD ["python", "-m", "src.main"]
