#!/bin/sh
# Production entrypoint: migrations are run by deploy.sh in a one-off container (docs/10 §4).
set -eu
python manage.py collectstatic --noinput >/dev/null
exec gunicorn config.asgi:application \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --graceful-timeout 30 \
  --max-requests 2000 --max-requests-jitter 200 \
  --access-logfile - --forwarded-allow-ips "*"
