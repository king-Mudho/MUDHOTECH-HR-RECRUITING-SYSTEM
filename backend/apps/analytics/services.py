"""Snapshot refresh for the default reports view (nightly + on demand)."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from apps.core.time import now

from . import selectors
from .models import AnalyticsSnapshot

FRESH_FOR = timedelta(hours=26)


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def refresh(organisation_id: Any) -> dict[str, Any]:
    scope = selectors.scope_from(organisation_id, {})
    data = _jsonable(selectors.report(scope))
    AnalyticsSnapshot.objects.for_org(organisation_id).update_or_create(
        organisation_id=organisation_id,
        key="default",
        defaults={"computed_at": now(), "params": scope.as_params(), "metrics": data},
    )
    return data


def default_report(organisation_id: Any) -> tuple[dict[str, Any], str]:
    """The stored default view when fresh (``snapshot``), otherwise recomputed (``live``)."""
    snap = (
        AnalyticsSnapshot.objects.for_org(organisation_id)
        .filter(key="default", computed_at__gte=now() - FRESH_FOR)
        .first()
    )
    if snap is not None:
        return snap.metrics, "snapshot"
    return refresh(organisation_id), "live"


def refresh_all() -> int:
    from apps.organisations.models import Organisation

    count = 0
    for org_id in Organisation.objects.filter(status=Organisation.Status.ACTIVE).values_list(
        "pk", flat=True
    ):
        refresh(org_id)
        count += 1
    return count
