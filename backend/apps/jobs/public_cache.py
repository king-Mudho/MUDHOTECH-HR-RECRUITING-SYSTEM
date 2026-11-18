"""Short-lived cache for the anonymous public job board API (P10-T05, NFR-PERF-01).

Every visitor sees the same public list, vacancy and questionnaire, so their JSON is cached in
Redis for ``PUBLIC_API_CACHE_SECONDS`` (default 30 s, 0 disables) keyed by the full URL. A
generation counter is bumped whenever a job or an organisation is saved (publish, close, pause,
edit, suspend, close account), so changes show immediately instead of after the TTL. Only
successful responses are cached; redirects, 404 and 410 are computed every time.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.request import Request
from rest_framework.response import Response

GENERATION_KEY = "pubjobs:generation"


def _ttl() -> int:
    return int(getattr(settings, "PUBLIC_API_CACHE_SECONDS", 30))


def generation() -> int:
    value = cache.get(GENERATION_KEY)
    if value is None:
        cache.add(GENERATION_KEY, 1, timeout=None)
        value = cache.get(GENERATION_KEY, 1)
    return int(value)


def bump() -> None:
    try:
        cache.incr(GENERATION_KEY)
    except ValueError:  # not set yet (or evicted): start a fresh generation
        cache.set(GENERATION_KEY, generation() + 1, timeout=None)


def cached(request: Request, build: Callable[[], Response]) -> Response:
    """Serve ``build()``'s 200 response from the cache for anonymous visitors."""
    ttl = _ttl()
    if ttl <= 0 or request.user.is_authenticated:
        return build()
    digest = hashlib.sha256(request.get_full_path().encode()).hexdigest()[:32]
    key = f"pubjobs:{generation()}:{digest}"
    hit = cache.get(key)
    if hit is not None:
        return Response(hit)
    response = build()
    if response.status_code == 200:
        cache.set(key, response.data, timeout=ttl)
    return response


@receiver(post_save, sender="jobs.Job")
def _job_saved(**_: Any) -> None:
    bump()


@receiver(post_save, sender="organisations.Organisation")
def _organisation_saved(**_: Any) -> None:
    bump()
