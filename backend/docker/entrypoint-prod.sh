#!/bin/sh
# Production entrypoint: migrations are run by deploy.sh in a one-off container (docs/10 §4).
# WSGI with threaded workers (ADR-029): every view is synchronous, so ASGI would run them one at a
# time per worker. Connections are bounded by the pool (DB_POOL_MAX per process).
set -eu
python manage.py collectstatic --noinput >/dev/null
exec gunicorn config.wsgi:application \
  --worker-class gthread \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --threads "${GUNICORN_THREADS:-8}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --max-requests 2000 --max-requests-jitter 200 \
  --access-logfile - --forwarded-allow-ips "*"
