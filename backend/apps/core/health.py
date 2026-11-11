"""Liveness (`/healthz`) and readiness (`/readyz`) endpoints."""

from __future__ import annotations

import time as _time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="readyz")


def check_database() -> None:
    timeout_ms = int(settings.HEALTHCHECK_TIMEOUT_SECONDS * 1000)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, false)", [str(timeout_ms)])
            cursor.execute("SELECT 1")
            cursor.fetchone()
    finally:
        connection.close()  # thread-local connection opened by the executor thread


def check_redis() -> None:
    import redis

    t = settings.HEALTHCHECK_TIMEOUT_SECONDS
    client = redis.Redis.from_url(
        settings.CELERY_BROKER_URL, socket_connect_timeout=t, socket_timeout=t
    )
    try:
        client.ping()
    finally:
        client.close()


def check_storage() -> None:
    from .storage import check_bucket

    check_bucket("documents")


CHECKS: dict[str, Callable[[], None]] = {
    "database": check_database,
    "redis": check_redis,
    "storage": check_storage,
}


def run_checks(checks: dict[str, Callable[[], None]] | None = None) -> dict[str, dict[str, object]]:
    checks = checks or CHECKS
    timeout = settings.HEALTHCHECK_TIMEOUT_SECONDS
    futures = {name: (_executor.submit(fn), _time.monotonic()) for name, fn in checks.items()}
    results: dict[str, dict[str, object]] = {}
    for name, (future, started) in futures.items():
        try:
            future.result(timeout=timeout)
            results[name] = {"status": "ok"}
        except FutureTimeout:
            results[name] = {"status": "error", "error": "timeout"}
        except Exception as exc:
            results[name] = {"status": "error", "error": type(exc).__name__}
        results[name]["latency_ms"] = round((_time.monotonic() - started) * 1000, 1)
    return results


@never_cache
@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    results = run_checks()
    healthy = all(r["status"] == "ok" for r in results.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": results},
        status=200 if healthy else 503,
    )
