"""Redis cache outage (P10-T07, EC-OPS-01): the API keeps working without its cache."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.cache import ResilientRedisCache

DOWN = "redis://127.0.0.1:1/0"  # nothing listens on port 1


def down_cache() -> ResilientRedisCache:
    return ResilientRedisCache(
        DOWN, {"OPTIONS": {"socket_connect_timeout": 0.2, "socket_timeout": 0.2}}
    )


def test_every_operation_degrades_to_a_miss() -> None:
    c = down_cache()
    assert c.get("k", "default") == "default"
    c.set("k", 1, timeout=30)
    assert c.add("k", 1) is False
    assert c.get_many(["a", "b"]) == {}
    assert c.has_key("k") is False
    assert c.delete("k") is False
    c.delete_many(["a"])
    with pytest.raises(ValueError):
        c.incr("k")  # callers treat ValueError as "key missing"


@pytest.mark.django_db
def test_api_requests_succeed_while_redis_is_down(monkeypatch: Any) -> None:
    """Throttles, feature flags and the public cache all read the cache on every request."""
    from django.core import cache as cache_module

    monkeypatch.setattr(cache_module.caches, "__getitem__", lambda self, alias: down_cache())
    monkeypatch.setattr(cache_module, "cache", down_cache())
    import apps.core.flags as flags
    import apps.jobs.public_cache as public_cache

    monkeypatch.setattr(flags, "cache", down_cache())
    monkeypatch.setattr(public_cache, "cache", down_cache())
    from rest_framework import throttling

    monkeypatch.setattr(throttling.SimpleRateThrottle, "cache", down_cache())
    res = APIClient().get("/api/v1/jobs/")
    assert res.status_code == 200
