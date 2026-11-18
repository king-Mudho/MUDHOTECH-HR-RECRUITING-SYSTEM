"""Redis cache that degrades to "no cache" when Redis is unavailable (P10-T07, EC-OPS-01).

Django's ``RedisCache`` raises on connection errors. Every API request reads the cache (rate-limit
throttles, feature flags, the public job board cache), so a Redis outage would turn the whole API
into 500s - including submissions, which must still commit (the outbox lives in PostgreSQL).
Here a Redis error is logged and treated as a miss: reads return the default, writes are skipped.
While Redis is down, throttling is effectively paused and every read goes to the database; both
recover by themselves when Redis is back. Short socket timeouts (settings) keep a dead Redis from
stalling requests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


def _safe[T](call: Callable[[], T], fallback: T, op: str) -> T:
    try:
        return call()
    except RedisError as exc:
        log.warning("cache_unavailable", extra={"op": op, "error": type(exc).__name__})
        return fallback


class ResilientRedisCache(RedisCache):
    def get(self, key: Any, default: Any = None, version: int | None = None) -> Any:
        return _safe(
            lambda: super(ResilientRedisCache, self).get(key, default, version), default, "get"
        )

    def set(self, key: Any, value: Any, timeout: Any = None, version: int | None = None) -> None:
        kwargs: dict[str, Any] = {"version": version}
        if timeout is not None:
            kwargs["timeout"] = timeout
        _safe(lambda: super(ResilientRedisCache, self).set(key, value, **kwargs), None, "set")

    def add(self, key: Any, value: Any, timeout: Any = None, version: int | None = None) -> bool:
        kwargs: dict[str, Any] = {"version": version}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _safe(
            lambda: super(ResilientRedisCache, self).add(key, value, **kwargs), False, "add"
        )

    def delete(self, key: Any, version: int | None = None) -> bool:
        return _safe(lambda: super(ResilientRedisCache, self).delete(key, version), False, "delete")

    def incr(self, key: Any, delta: int = 1, version: int | None = None) -> int:
        try:
            return super().incr(key, delta, version)
        except RedisError as exc:
            log.warning("cache_unavailable", extra={"op": "incr", "error": type(exc).__name__})
            raise ValueError("cache unavailable") from exc  # callers treat as "key missing"

    def get_many(self, keys: Iterable[Any], version: int | None = None) -> dict[Any, Any]:
        return _safe(
            lambda: super(ResilientRedisCache, self).get_many(keys, version), {}, "get_many"
        )

    def set_many(
        self, data: dict[Any, Any], timeout: Any = None, version: int | None = None
    ) -> list[Any]:
        kwargs: dict[str, Any] = {"version": version}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _safe(
            lambda: super(ResilientRedisCache, self).set_many(data, **kwargs),
            list(data),
            "set_many",
        )

    def delete_many(self, keys: Iterable[Any], version: int | None = None) -> None:
        _safe(
            lambda: super(ResilientRedisCache, self).delete_many(keys, version), None, "delete_many"
        )

    def has_key(self, key: Any, version: int | None = None) -> bool:
        return _safe(
            lambda: super(ResilientRedisCache, self).has_key(key, version), False, "has_key"
        )

    def touch(self, key: Any, timeout: Any = None, version: int | None = None) -> bool:
        kwargs: dict[str, Any] = {"version": version}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _safe(lambda: super(ResilientRedisCache, self).touch(key, **kwargs), False, "touch")
