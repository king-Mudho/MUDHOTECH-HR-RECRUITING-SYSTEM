from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.db import connection, transaction

from apps.core import outbox, time
from apps.core.models import OutboxEvent, ProcessedEvent
from apps.core.outbox import OutboxUsageError, emit, idempotent_consumer, relay_batch
from tests.core_testapp.models import Widget

pytestmark = pytest.mark.django_db
_REAL_KICK = outbox.kick_relay


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.lock = threading.Lock()

    def __call__(self, task_name: str, event: OutboxEvent) -> None:
        with self.lock:
            self.calls.append((task_name, str(event.id)))


@pytest.fixture(autouse=True)
def _no_kick() -> Any:
    with mock.patch.object(outbox, "kick_relay"):
        yield


@pytest.fixture
def consumer_registered() -> Any:
    outbox._CONSUMERS["widget.created"] = ["consumer.test_a", "consumer.test_b"]
    yield
    outbox._CONSUMERS.pop("widget.created", None)


@pytest.mark.django_db(transaction=True)
def test_emit_requires_atomic(org: Any) -> None:
    w = Widget.objects.create(organisation=org, name="w")
    with pytest.raises(OutboxUsageError):
        emit("widget.created", w, {"x": 1})


def test_emit_records_aggregate_org_and_payload(org: Any) -> None:
    with transaction.atomic():
        w = Widget.objects.create(organisation=org, name="w")
        event = emit("widget.created", w, {"when": time.now(), "n": 1})
    event.refresh_from_db()
    assert event.aggregate_type == "core_testapp.widget"
    assert event.aggregate_id == str(w.pk)
    assert event.organisation_id == org.pk
    assert event.status == OutboxEvent.Status.PENDING
    assert isinstance(event.payload["when"], str)  # JSON-safe


def test_emit_with_tuple_aggregate_and_delay() -> None:
    with transaction.atomic():
        event = emit("x.y", ("thing", 42), delay=timedelta(minutes=5))
    assert event.aggregate_id == "42"
    assert event.available_at > time.now() + timedelta(minutes=4)


def test_event_not_persisted_when_transaction_rolls_back(org: Any) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        w = Widget.objects.create(organisation=org, name="w")
        emit("widget.created", w, {})
        raise RuntimeError("business failure")
    assert OutboxEvent.objects.count() == 0


def test_dedupe_key_makes_emit_idempotent(org: Any) -> None:
    with transaction.atomic():
        w = Widget.objects.create(organisation=org, name="w")
        e1 = emit("widget.created", w, {}, dedupe_key=f"widget.created:{w.pk}:1")
        e2 = emit("widget.created", w, {"other": True}, dedupe_key=f"widget.created:{w.pk}:1")
    assert e1.pk == e2.pk
    assert OutboxEvent.objects.count() == 1


def test_relay_publishes_to_every_consumer(org: Any, consumer_registered: Any) -> None:
    with transaction.atomic():
        emit("widget.created", ("w", 1), {})
        emit("unrelated.event", ("w", 2), {})
    rec = Recorder()
    result = relay_batch(publisher=rec)
    assert result.published == 2
    assert sorted(name for name, _ in rec.calls) == ["consumer.test_a", "consumer.test_b"]
    assert OutboxEvent.objects.filter(status="published").count() == 2
    assert relay_batch(publisher=rec).published == 0  # nothing left


def test_relay_skips_events_not_yet_available(consumer_registered: Any) -> None:
    with transaction.atomic():
        emit("widget.created", ("w", 1), {}, delay=timedelta(hours=1))
    assert relay_batch(publisher=Recorder()).published == 0


def test_broker_down_keeps_event_pending_and_retries_later(consumer_registered: Any) -> None:
    """EC-OPS-01: Redis down at submit time -> the event survives in the DB and is relayed later."""
    with transaction.atomic():
        event = emit("widget.created", ("w", 1), {})

    def broken(task_name: str, ev: OutboxEvent) -> None:
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    result = relay_batch(publisher=broken)
    assert result.failed == 1
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.PENDING
    assert event.attempts == 1
    assert "ConnectionError" in event.last_error
    assert event.available_at > time.now()

    # Broker back; make the event due again and relay.
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=time.now())
    rec = Recorder()
    assert relay_batch(publisher=rec).published == 1
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.PUBLISHED
    assert event.last_error == ""


def test_event_marked_failed_after_max_attempts(consumer_registered: Any, settings: Any) -> None:
    settings.OUTBOX_MAX_ATTEMPTS = 2
    with transaction.atomic():
        event = emit("widget.created", ("w", 1), {})

    def broken(task_name: str, ev: OutboxEvent) -> None:
        raise ConnectionError("down")

    relay_batch(publisher=broken)
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=time.now())
    relay_batch(publisher=broken)
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.FAILED


def test_kick_relay_swallows_broker_errors() -> None:
    from apps.core import tasks

    with mock.patch.object(tasks.relay_outbox, "apply_async", side_effect=ConnectionError("down")):
        _REAL_KICK()  # must not raise


def test_emit_registers_on_commit_kick() -> None:
    with mock.patch.object(outbox.transaction, "on_commit") as on_commit:
        with transaction.atomic():
            emit("x.y", ("a", 1), {})
        assert on_commit.called


@pytest.mark.django_db(transaction=True)
def test_concurrent_relays_do_not_double_publish(consumer_registered: Any) -> None:
    with transaction.atomic():
        for i in range(40):
            emit("widget.created", ("w", i), {})
    rec = Recorder()
    barrier = threading.Barrier(2)

    def run() -> None:
        try:
            barrier.wait()
            for _ in range(5):
                relay_batch(batch_size=7, publisher=rec)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 40 events x 2 consumers, each published exactly once.
    assert len(rec.calls) == 80
    assert len(set(rec.calls)) == 80
    assert OutboxEvent.objects.filter(status="published").count() == 40


def test_idempotent_consumer_processes_each_event_once() -> None:
    handled: list[str] = []

    @idempotent_consumer("test_once", events=["thing.happened"])
    def handler(event: OutboxEvent) -> str:
        handled.append(str(event.id))
        return "done"

    try:
        assert "consumer.test_once" in outbox.consumers_for("thing.happened")
        with transaction.atomic():
            event = emit("thing.happened", ("t", 1), {})
        assert handler.apply(args=[str(event.id)]).get() == "done"
        assert handler.apply(args=[str(event.id)]).get() is None  # duplicate delivery
        assert handled == [str(event.id)]
        assert ProcessedEvent.objects.filter(consumer="test_once").count() == 1
    finally:
        outbox._CONSUMERS.pop("thing.happened", None)


def test_consumer_failure_rolls_back_marker_so_retry_is_possible(settings: Any) -> None:
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    attempts: list[int] = []

    @idempotent_consumer("test_flaky", events=["flaky.event"], max_retries=0)
    def flaky(event: OutboxEvent) -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("transient")
        return "ok"

    try:
        with transaction.atomic():
            event = emit("flaky.event", ("f", 1), {})
        first = flaky.apply(args=[str(event.id)])
        assert first.failed()
        assert not ProcessedEvent.objects.filter(consumer="test_flaky").exists()
        assert flaky.apply(args=[str(event.id)]).get() == "ok"
        assert ProcessedEvent.objects.filter(consumer="test_flaky").count() == 1
    finally:
        outbox._CONSUMERS.pop("flaky.event", None)


def test_relay_task_and_celery_publisher(consumer_registered: Any) -> None:
    from apps.core.tasks import relay_outbox

    with transaction.atomic():
        emit("widget.created", ("w", 1), {})
    with mock.patch("config.celery.app.send_task") as send_task:
        result = relay_outbox.apply().get()
    assert result == {"published": 1, "failed": 0}
    assert send_task.call_count == 2
