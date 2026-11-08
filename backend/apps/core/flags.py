"""Feature flags: ``is_enabled(key, org=None)`` with a short-lived cache.

Resolution order: per-organisation override -> global row -> ``default`` (False).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.cache import cache

from .models import FeatureFlag

CACHE_TTL_SECONDS = 30
_MISSING = "__missing__"


def _cache_key(key: str) -> str:
    return f"flags:v1:{key}"


def _load(key: str) -> dict[str, bool]:
    cached = cache.get(_cache_key(key))
    if cached is not None:
        return cached
    rows = FeatureFlag.objects.filter(key=key).values_list("organisation_id", "enabled")
    data = {str(org_id) if org_id else "global": enabled for org_id, enabled in rows}
    cache.set(_cache_key(key), data, CACHE_TTL_SECONDS)
    return data


def is_enabled(key: str, org: Any = None, *, default: bool = False) -> bool:
    data = _load(key)
    org_id = getattr(org, "pk", org)
    if org_id is not None and str(org_id) in data:
        return data[str(org_id)]
    return data.get("global", default)


def set_flag(key: str, enabled: bool, org: Any = None) -> FeatureFlag:
    org_id: uuid.UUID | None = getattr(org, "pk", org)
    flag, _ = FeatureFlag.objects.update_or_create(
        key=key, organisation_id=org_id, defaults={"enabled": enabled}
    )
    return flag


def invalidate(key: str) -> None:
    cache.delete(_cache_key(key))
