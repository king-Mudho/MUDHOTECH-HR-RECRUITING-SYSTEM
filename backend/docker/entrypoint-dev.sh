#!/bin/sh
# Dev entrypoint: apply migrations then run the autoreloading dev server.
set -eu
python manage.py migrate --noinput
exec python manage.py runserver 0.0.0.0:8000
