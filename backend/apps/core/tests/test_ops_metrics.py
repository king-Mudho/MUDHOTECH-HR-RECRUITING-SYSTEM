"""P11-T07: operational metrics behind the CloudWatch alarms (docs/10 §8)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application
from apps.core import ops_metrics
from apps.core import time as mhrs_time
from apps.core.models import DeadLetter, OutboxEvent
from apps.notifications.models import Channel, Notification, NotificationStatus

pytestmark = pytest.mark.django_db


def values(metrics: list[ops_metrics.Metric]) -> dict[str, float]:
    return {ops_metrics._label(m): m[1] for m in metrics}


def test_dead_letters_count_only_unresolved() -> None:
    DeadLetter.objects.create(task_name="a", error="x")
    DeadLetter.objects.create(task_name="b", error="y")
    DeadLetter.objects.create(task_name="c", error="z", resolved_at=mhrs_time.now())
    assert values(ops_metrics._dead_letters()) == {"DeadLettersOpen": 2.0}


def test_outbox_lag_is_age_of_oldest_pending_event() -> None:
    now = mhrs_time.now()
    OutboxEvent.objects.create(
        event_type="e",
        aggregate_type="t",
        aggregate_id="1",
        dedupe_key="k1",
        available_at=now - timedelta(minutes=10),
    )
    OutboxEvent.objects.create(
        event_type="e",
        aggregate_type="t",
        aggregate_id="2",
        dedupe_key="k2",
        available_at=now - timedelta(hours=3),
        status=OutboxEvent.Status.PUBLISHED,
    )
    lag = values(ops_metrics._outbox_lag())["OutboxLagSeconds"]
    assert 590 <= lag <= 700
    OutboxEvent.objects.all().delete()
    assert values(ops_metrics._outbox_lag()) == {"OutboxLagSeconds": 0.0}


def test_processing_backlog_age_of_oldest_unfinished_application() -> None:
    app = make_application(status=Status.PROCESSING)
    Application.objects.unscoped().filter(pk=app.pk).update(
        submitted_at=mhrs_time.now() - timedelta(minutes=20)
    )
    done = make_application(status=Status.UNDER_REVIEW)
    Application.objects.unscoped().filter(pk=done.pk).update(
        submitted_at=mhrs_time.now() - timedelta(days=2)
    )
    age = values(ops_metrics._processing_backlog())["ProcessingBacklogAgeSeconds"]
    assert 1190 <= age <= 1300  # the under-review one (2 days old) does not count


def test_email_failure_rate_over_the_last_hour() -> None:
    user = UserFactory()
    for i, status in enumerate(
        [
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.SENT,
            NotificationStatus.FAILED,
            NotificationStatus.QUEUED,
        ]
    ):
        Notification.objects.create(
            recipient_user=user, key="k", channel=Channel.EMAIL, status=status, dedupe_key=f"d{i}"
        )
    Notification.objects.create(  # in-app notifications are not email
        recipient_user=user,
        key="k",
        channel=Channel.INAPP,
        status=NotificationStatus.FAILED,
        dedupe_key="inapp",
    )
    got = values(ops_metrics._email_failure_rate())
    assert got == {"EmailFailureRatePercent": 25.0, "EmailsProcessedLastHour": 4.0}


def test_email_failure_rate_is_zero_without_traffic() -> None:
    assert values(ops_metrics._email_failure_rate())["EmailFailureRatePercent"] == 0.0


def test_clamav_signature_age_from_version_reply() -> None:
    now = datetime(2026, 11, 18, 12, 20, tzinfo=UTC)
    assert ops_metrics.clamav_signature_age_hours(
        "ClamAV 1.5.4/27460/Tue Nov 17 08:20:00 2026", now
    ) == pytest.approx(28.0)
    assert ops_metrics.clamav_signature_age_hours("ClamAV 1.5.4", now) is None
    assert ops_metrics.clamav_signature_age_hours("ClamAV 1.5.4/1/not a date", now) is None


def test_clamav_metric_reads_clamd(monkeypatch: pytest.MonkeyPatch, settings: Any) -> None:
    settings.DOCUMENT_SCANNER = "clamd"
    built = (mhrs_time.now().astimezone(UTC) - timedelta(hours=50)).strftime("%a %b %d %H:%M:%S %Y")
    from apps.documents import antivirus

    monkeypatch.setattr(antivirus, "_clamd_command", lambda cmd: f"ClamAV 1.5.4/1/{built}".encode())
    age = values(ops_metrics._clamav_age())["ClamavSignatureAgeHours"]
    assert 49.9 <= age <= 50.1  # > 48 h -> the alarm fires (EC-OPS-09)
    settings.DOCUMENT_SCANNER = "fake"
    assert ops_metrics._clamav_age() == []


def test_queue_depths_per_celery_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.celery import app

    depths = {"documents": 7, "ai": 3}

    class Client:
        def llen(self, name: str) -> int:
            return depths.get(name, 0)

    class Conn:
        default_channel = type("Channel", (), {"client": Client()})()

    @contextmanager
    def fake_connection() -> Any:
        yield Conn()

    monkeypatch.setattr(app, "connection_for_read", fake_connection)
    got = values(ops_metrics._queue_depths())
    assert got["QueueDepth[documents]"] == 7.0 and got["QueueDepth[ai]"] == 3.0
    assert {"QueueDepth[default]", "QueueDepth[notifications]", "QueueDepth[reports]"} <= set(got)


def test_one_failing_source_does_not_hide_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> list[ops_metrics.Metric]:
        raise ConnectionError("redis down")

    monkeypatch.setattr(
        ops_metrics, "SOURCES", {"queues": broken, "dead_letters": ops_metrics._dead_letters}
    )
    metrics, errors = ops_metrics.collect()
    assert errors == {"queues": "ConnectionError"}
    assert values(metrics) == {"DeadLettersOpen": 0.0}


def test_publish_to_cloudwatch_in_batches(settings: Any) -> None:
    settings.OPS_METRICS_NAMESPACE = "MHRS/test"
    calls: list[dict[str, Any]] = []

    class Client:
        def put_metric_data(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    metrics = [("QueueDepth", float(i), "Count", {"Queue": f"q{i}"}) for i in range(25)]
    sent = ops_metrics.publish(metrics, {"clamav": "OSError"}, client=Client())
    assert sent == 26  # + OpsMetricSourceErrors
    assert [len(c["MetricData"]) for c in calls] == [20, 6]
    assert {c["Namespace"] for c in calls} == {"MHRS/test"}
    last = calls[-1]["MetricData"][-1]
    assert last == {
        "MetricName": "OpsMetricSourceErrors",
        "Value": 1.0,
        "Unit": "Count",
        "Dimensions": [],
    }
    assert calls[0]["MetricData"][0]["Dimensions"] == [{"Name": "Queue", "Value": "q0"}]


def test_without_namespace_metrics_are_only_logged(
    settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    settings.OPS_METRICS_NAMESPACE = ""
    with caplog.at_level("INFO", logger="mhrs.ops_metrics"):
        sent = ops_metrics.publish([("DeadLettersOpen", 3.0, "Count", {})], {})
    assert sent == 2
    record = next(r for r in caplog.records if r.getMessage() == "ops metrics")
    assert record.ops_metrics == {"DeadLettersOpen": 3.0, "OpsMetricSourceErrors": 0.0}


def test_beat_runs_the_task_every_minute(settings: Any) -> None:
    entry = settings.CELERY_BEAT_SCHEDULE["ops-metrics"]
    assert entry["task"] == "apps.core.tasks.publish_ops_metrics"
    assert entry["schedule"] == timedelta(minutes=1)
    from apps.core.tasks import publish_ops_metrics

    result = publish_ops_metrics.apply().get()
    assert result["metrics"] >= 1 and "DeadLettersOpen" in result["values"]
