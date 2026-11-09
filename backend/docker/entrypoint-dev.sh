#!/bin/sh
# Dev entrypoint: apply migrations then run the dev server.
# RUNSERVER_ARGS lets you pass e.g. "--noreload" when the autoreloader's file scanning is too heavy
# for the host (Windows bind mounts under memory pressure) or for E2E runs.
set -eu
python manage.py migrate --noinput
# shellcheck disable=SC2086
exec python manage.py runserver 0.0.0.0:8000 ${RUNSERVER_ARGS:-}
