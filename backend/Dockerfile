# syntax=docker/dockerfile:1.7
# MHRS backend (API, beat, flower). Multi-stage: `builder` resolves the locked environment with uv,
# `runtime` carries only the virtualenv + source and runs as the unprivileged `app` user.
# Bases are pinned to exact versions (bump deliberately; Dependabot proposes updates).
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie

FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM ${PYTHON_IMAGE} AS builder
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_COMPILE_BYTECODE_TIMEOUT=600 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# production builds pass --no-dev (CI, deploy); the dev compose keeps the default (with dev tools)
ARG UV_SYNC_ARGS="--frozen --no-install-project"
RUN --mount=type=cache,target=/root/.cache/uv uv sync ${UV_SYNC_ARGS}

FROM ${PYTHON_IMAGE} AS runtime
ARG MHRS_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MHRS_VERSION=${MHRS_VERSION}
LABEL org.opencontainers.image.title="mhrs-backend" \
      org.opencontainers.image.vendor="MudhoTech Solutions (Pvt) Ltd" \
      org.opencontainers.image.version="${MHRS_VERSION}"

RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends curl libpq5 libmagic1 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app . .
RUN chmod +x docker/*.sh && mkdir -p /app/staticfiles && chown app:app /app/staticfiles

USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1
CMD ["sh", "/app/docker/entrypoint-prod.sh"]
