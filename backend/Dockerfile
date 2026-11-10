# syntax=docker/dockerfile:1.7
# MHRS backend (API, beat, flower). Python 3.12 slim, uv, non-root.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_COMPILE_BYTECODE_TIMEOUT=600 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends curl libpq5 libmagic1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

WORKDIR /app
COPY pyproject.toml uv.lock ./
ARG UV_SYNC_ARGS="--frozen --no-install-project"
RUN --mount=type=cache,target=/root/.cache/uv uv sync ${UV_SYNC_ARGS}

COPY --chown=app:app . .
RUN chmod +x docker/*.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8000/healthz || exit 1
CMD ["sh", "/app/docker/entrypoint-prod.sh"]
