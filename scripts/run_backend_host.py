"""Run the Django dev server on the host (outside Docker) against the compose Postgres/Redis.

    backend/.venv/Scripts/python scripts/run_backend_host.py [runserver args...]

Loads ``.env`` (secrets such as FIELD_ENCRYPTION_KEYS) and rewrites the in-network hostnames
(``postgres:5432``, ``redis:6379``, ``mailpit:1025``) to the published host ports, so a low-memory
machine can run only ``docker compose up -d postgres redis mailpit`` plus this process.
Existing environment variables win over ``.env``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REWRITES = {
    "@postgres:5432": f"@localhost:{os.environ.get('POSTGRES_HOST_PORT', '15432')}",
    "redis:6379": f"localhost:{os.environ.get('REDIS_HOST_PORT', '6380')}",
    "mailpit:1025": "localhost:1025",
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        for old, new in REWRITES.items():
            value = value.replace(old, new)
        os.environ.setdefault(key, value)


def main() -> None:
    load_env(ROOT / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT / "backend")
    from django.core.management import execute_from_command_line

    args = sys.argv[1:] or ["runserver", "127.0.0.1:8000", "--noreload"]
    execute_from_command_line(["manage.py", *args])


if __name__ == "__main__":
    main()
