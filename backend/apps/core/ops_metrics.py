"""Operational metrics for alerting (P11-T07, docs/10 §8).

``collect()`` reads the numbers the SLO alerts need from the database, the Celery broker and
clamd; ``publish()`` sends them to CloudWatch (namespace ``OPS_METRICS_NAMESPACE``, e.g.
``MHRS/production``) or, when no namespace is configured (dev, tests), writes them as one
structured log line. A beat task runs it every minute; CloudWatch alarms
(``infrastructure/monitoring/alarms.sh``) turn them into pages.

| Metric | Alert (docs/10 §8, docs/07) |
|---|---|
| ``QueueDepth`` (per queue) | ``documents`` > 500 |
| ``ProcessingBacklogAgeSeconds`` | oldest application still processing > 15 min |
| ``OutboxLagSeconds`` | oldest pending outbox event > 5 min (side effects stuck) |
| ``DeadLettersOpen`` | > 10 (EC-OPS-07) |
| ``EmailFailureRatePercent`` | > 5 % over the last hour |
| ``ClamavSignatureAgeHours`` | > 48 h (EC-OPS-09) |

Every metric is computed independently: one failing source (Redis or clamd down) is reported as
missing (the alarm treats missing data as breaching where that matters) and never hides the others.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from django.conf import settings
from django.db.models import Min

from apps.core import time as mhrs_time

logger = logging.getLogger("mhrs.ops_metrics")

Metric = tuple[str, float, str, dict[str, str]]  # name, value, unit, dimensions

EMAIL_WINDOW = timedelta(hours=1)
CLAMAV_VERSION = re.compile(r"^ClamAV [^/]+/\d+/(?P<date>.+)$")


def _queue_depths() -> list[Metric]:
    from config.celery import app

    names = [q.name for q in settings.CELERY_TASK_QUEUES]
    with app.connection_for_read() as conn:
        client = cast(Any, conn.default_channel).client  # redis-py client of the broker
        return [
            ("QueueDepth", float(client.llen(name)), "Count", {"Queue": name}) for name in names
        ]


def _processing_backlog() -> list[Metric]:
    from apps.applications.models import Application, Status

    oldest = (
        Application.objects.unscoped()
        .filter(status__in=[Status.SUBMITTED, Status.PROCESSING])
        .aggregate(oldest=Min("submitted_at"))["oldest"]
    )
    age = (mhrs_time.now() - oldest).total_seconds() if oldest else 0.0
    return [("ProcessingBacklogAgeSeconds", max(age, 0.0), "Seconds", {})]


def _outbox_lag() -> list[Metric]:
    from apps.core.models import OutboxEvent

    oldest = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING).aggregate(
        oldest=Min("available_at")
    )["oldest"]
    lag = (mhrs_time.now() - oldest).total_seconds() if oldest else 0.0
    return [("OutboxLagSeconds", max(lag, 0.0), "Seconds", {})]


def _dead_letters() -> list[Metric]:
    from apps.core.models import DeadLetter

    open_count = DeadLetter.objects.filter(resolved_at__isnull=True).count()
    return [("DeadLettersOpen", float(open_count), "Count", {})]


def _email_failure_rate() -> list[Metric]:
    from apps.notifications.models import Channel, Notification, NotificationStatus

    since = mhrs_time.now() - EMAIL_WINDOW
    recent = Notification.objects.filter(channel=Channel.EMAIL, updated_at__gte=since)
    done = recent.filter(
        status__in=[
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.FAILED,
        ]
    )
    total = done.count()
    failed = done.filter(status=NotificationStatus.FAILED).count()
    rate = 100.0 * failed / total if total else 0.0
    return [
        ("EmailFailureRatePercent", rate, "Percent", {}),
        ("EmailsProcessedLastHour", float(total), "Count", {}),
    ]


def clamav_signature_age_hours(version: str, now: datetime) -> float | None:
    """Age of the signature database from clamd's VERSION reply
    (``ClamAV 1.5.4/27460/Tue Nov 18 08:20:00 2026``); None if it cannot be parsed."""
    match = CLAMAV_VERSION.match(version.strip())
    if not match:
        return None
    try:
        built = datetime.strptime(match.group("date").strip(), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    # clamd prints the database build time in UTC without a zone
    return max((now.replace(tzinfo=None) - built).total_seconds() / 3600, 0.0)


def _clamav_age() -> list[Metric]:
    if getattr(settings, "DOCUMENT_SCANNER", "clamd") != "clamd":
        return []
    from apps.documents.antivirus import _clamd_command

    version = _clamd_command(b"VERSION").decode(errors="replace")
    age = clamav_signature_age_hours(version, mhrs_time.now().astimezone(UTC))
    if age is None:
        raise ValueError("unrecognised clamd VERSION reply")
    return [("ClamavSignatureAgeHours", age, "None", {})]


SOURCES: dict[str, Callable[[], list[Metric]]] = {
    "queues": _queue_depths,
    "processing_backlog": _processing_backlog,
    "outbox": _outbox_lag,
    "dead_letters": _dead_letters,
    "email": _email_failure_rate,
    "clamav": _clamav_age,
}


def collect() -> tuple[list[Metric], dict[str, str]]:
    """All metrics that could be computed, and the sources that failed (name -> error class)."""
    metrics: list[Metric] = []
    errors: dict[str, str] = {}
    for name, source in SOURCES.items():
        try:
            metrics.extend(source())
        except Exception as exc:  # one broken source must not hide the others
            errors[name] = type(exc).__name__
            logger.warning("ops metric source %s failed: %s", name, type(exc).__name__)
    return metrics, errors


def _cloudwatch_client() -> Any:
    import boto3

    return boto3.client("cloudwatch", region_name=settings.OPS_METRICS_REGION)


def publish(metrics: list[Metric], errors: dict[str, str], client: Any = None) -> int:
    namespace = getattr(settings, "OPS_METRICS_NAMESPACE", "")
    # a failing source is itself a signal (e.g. the broker is unreachable)
    metrics = [*metrics, ("OpsMetricSourceErrors", float(len(errors)), "Count", {})]
    if not namespace:
        logger.info(
            "ops metrics",
            extra={"ops_metrics": {_label(m): m[1] for m in metrics}, "ops_errors": errors},
        )
        return len(metrics)
    client = client or _cloudwatch_client()
    data = [
        {
            "MetricName": name,
            "Value": value,
            "Unit": unit,
            "Dimensions": [{"Name": k, "Value": v} for k, v in dims.items()],
        }
        for name, value, unit, dims in metrics
    ]
    for i in range(0, len(data), 20):  # PutMetricData accepts up to 1000, keep requests small
        client.put_metric_data(Namespace=namespace, MetricData=data[i : i + 20])
    return len(data)


def _label(metric: Metric) -> str:
    name, _value, _unit, dims = metric
    return name + "".join(f"[{v}]" for v in dims.values())


def run() -> dict[str, Any]:
    metrics, errors = collect()
    sent = publish(metrics, errors)
    return {"metrics": sent, "errors": errors, "values": {_label(m): m[1] for m in metrics}}
