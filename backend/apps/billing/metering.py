"""Usage metering (P14-T04).

Monthly ``UsageCounter`` rows per organisation and metric:

* event counters, incremented by outbox consumers (exactly once per event):
  ``ai_evaluations_month`` (``screening.completed``) and ``applications_month``
  (``application.submitted``);
* gauges, rolled up daily as the month's peak: ``active_vacancies``, ``seats`` and
  ``storage_gb`` (stored in **megabytes** so the integer column keeps precision).

Limits are enforced from live data (``entitlements``); these counters are the monthly history
shown on the usage page and used for invoices.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F

from .entitlements import month_start, usage
from .models import Metric, Subscription, UsageCounter

GAUGES = (Metric.ACTIVE_VACANCIES, Metric.SEATS, Metric.STORAGE_GB)


def _period(day: date | None = None) -> date:
    return (day or month_start().date()).replace(day=1)


def increment(organisation_id: Any, metric: str, by: int = 1, day: date | None = None) -> None:
    period = _period(day)
    rows = UsageCounter.objects.for_org(organisation_id).filter(metric=metric, period=period)
    if rows.update(value=F("value") + by):
        return
    try:
        with transaction.atomic():
            UsageCounter.objects.create(
                organisation_id=organisation_id, metric=metric, period=period, value=by
            )
    except IntegrityError:  # created concurrently
        rows.update(value=F("value") + by)


def _gauge_value(organisation_id: Any, metric: str) -> int:
    value = usage(organisation_id, metric)
    return round(value * 1024) if metric == Metric.STORAGE_GB else int(value)


def rollup(organisation_id: Any) -> dict[str, int]:
    """Record this month's peak of each gauge (idempotent; never lowers a recorded peak)."""
    period = _period()
    out: dict[str, int] = {}
    for metric in GAUGES:
        current = _gauge_value(organisation_id, metric)
        with transaction.atomic():
            row, _ = (
                UsageCounter.objects.for_org(organisation_id)
                .select_for_update()
                .get_or_create(
                    organisation_id=organisation_id,
                    metric=metric,
                    period=period,
                    defaults={"value": current},
                )
            )
            if current > row.value:
                row.value = current
                row.save(update_fields=["value", "updated_at"])
        out[metric] = max(row.value, current)
    return out


def rollup_all() -> int:
    count = 0
    for org_id in Subscription.objects.unscoped().values_list("organisation_id", flat=True):
        rollup(org_id)
        count += 1
    return count


def history(organisation_id: Any, months: int = 6) -> list[dict[str, Any]]:
    rows = (
        UsageCounter.objects.for_org(organisation_id)
        .order_by("-period", "metric")
        .values("period", "metric", "value")
    )
    by_period: dict[date, dict[str, int]] = {}
    for r in rows:
        if r["period"] not in by_period and len(by_period) >= months:
            break
        by_period.setdefault(r["period"], {})[r["metric"]] = r["value"]
    return [{"period": p.isoformat(), "values": v} for p, v in by_period.items()]
