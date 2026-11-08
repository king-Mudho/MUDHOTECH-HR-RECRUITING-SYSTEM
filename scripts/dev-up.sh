#!/usr/bin/env bash
# MUDHOTECH HR RECRUITING SYSTEM - start the local development stack (Git Bash / WSL / Linux / macOS).
# Usage: ./scripts/dev-up.sh [--full] [--no-seed]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FULL=0
SEED=1
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --no-seed) SEED=0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null || { echo "Docker is not installed." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop." >&2; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

PROFILE_ARGS=()
[ "$FULL" -eq 1 ] && PROFILE_ARGS=(--profile full)

echo "Building and starting the stack (project 'mhrs')..."
docker compose "${PROFILE_ARGS[@]}" up -d --build

echo "Waiting for the backend to become healthy..."
deadline=$((SECONDS + 600))
until [ "$(docker inspect --format '{{.State.Health.Status}}' mhrs-backend-1 2>/dev/null)" = "healthy" ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "Backend did not become healthy in time. See: docker compose logs backend" >&2
    exit 1
  fi
  sleep 5
done

docker compose exec -T backend python manage.py migrate --noinput
if [ "$SEED" -eq 1 ]; then
  if docker compose exec -T backend python manage.py help seed_demo >/dev/null 2>&1; then
    docker compose exec -T backend python manage.py seed_demo
  else
    echo "seed_demo not available yet (added in later phases) - skipping."
  fi
fi

cat <<'MSG'

MUDHOTECH HR RECRUITING SYSTEM is up:
  Frontend   http://localhost:3000
  API docs   http://localhost:8000/api/docs/
  Ready      http://localhost:8000/readyz
  Mailpit    http://localhost:8025
  S3 (dev)   http://localhost:9000
  Flower     http://localhost:5555
MSG
