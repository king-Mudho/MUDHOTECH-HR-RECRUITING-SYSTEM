"""Transactional outbox (ADR-006, docs/02 §5.3).

Writers call :func:`emit` *inside* the business transaction; the event row commits (or rolls
back) together with the business change. A relay (beat every 2 s + an ``on_commit`` kick)
publishes pending events to the Celery consumers registered for the event type. Because the event
lives in PostgreSQL, a Redis/broker outage never loses an event (EC-OPS-01) - the relay simply
retries later.

Consumers are registered with :func:`idempotent_consumer`; each (consumer, event) pair is processed
at most once thanks to the ``ProcessedEvent`` unique constraint.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, connection, transaction
from django.db.models import Model

from . import time
from .context import get_request_id
from .models import OutboxEvent, ProcessedEvent

logger = logging.getLogger("mhrs.outbox")

# event_type -> list of celery task names
_CONSUMERS: dict[str, list[str]] = defaultdict(list)


class OutboxUsageError(RuntimeError):
    pass


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


def emit(
    event_type: str,
    aggregate: Model | tuple[str, Any],
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    *,
    organisation_id: uuid.UUID | str | None = None,
    delay: timedelta | None = None,
) -> OutboxEvent:
    """Record an event in the outbox. MUST be called inside ``transaction.atomic()``.

    ``dedupe_key`` makes emission idempotent: emitting the same key twice returns the first event.
    The default key is unique per call. Convention: ``"<event>:<object_id>:<version>"``.
    """
    if not connection.in_atomic_block:
        raise OutboxUsageError("outbox.emit() must be called inside transaction.atomic().")

    if isinstance(aggregate, Model):
        aggregate_type = aggregate._meta.label_lower
        aggregate_id = str(aggregate.pk)
        if organisation_id is None:
            organisation_id = getattr(aggregate, "organisation_id", None)
    else:
        aggregate_type, raw_id = aggregate
        aggregate_id = str(raw_id)

    now = time.now()
    event, created = OutboxEvent.objects.get_or_create(
        dedupe_key=dedupe_key or f"{event_type}:{aggregate_id}:{uuid.uuid4()}",
        defaults={
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "organisation_id": organisation_id,
            "payload": _json_safe(payload or {}),
            "available_at": now + delay if delay else now,
            "request_id": get_request_id() or "",
        },
    )
    if created:
        transaction.on_commit(kick_relay, robust=True)
    return event


def kick_relay() -> None:
    """Best-effort immediate relay after commit. Failure (e.g. Redis down) is harmless."""
    from .tasks import relay_outbox

    try:
        relay_outbox.apply_async(expires=30)
    except Exception:  # broker unavailable: the beat schedule will pick the event up later.
        logger.warning("outbox_kick_failed", exc_info=True)


# --------------------------------------------------------------------------------------------
# Relay
# --------------------------------------------------------------------------------------------
@dataclass
class RelayResult:
    published: int = 0
    failed: int = 0


Publisher = Callable[[str, OutboxEvent], None]


def _celery_publish(task_name: str, event: OutboxEvent) -> None:
    from config.celery import app

    app.send_task(task_name, args=[str(event.id)], headers={"mhrs_request_id": event.request_id})


def consumers_for(event_type: str) -> list[str]:
    return list(_CONSUMERS.get(event_type, []))


def relay_batch(batch_size: int | None = None, publisher: Publisher | None = None) -> RelayResult:
    """Publish one batch of due events. Safe to run concurrently (``FOR UPDATE SKIP LOCKED``)."""
    publish = publisher or _celery_publish
    size = batch_size or settings.OUTBOX_RELAY_BATCH_SIZE
    max_attempts = settings.OUTBOX_MAX_ATTEMPTS
    result = RelayResult()
    with transaction.atomic():
        events = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, available_at__lte=time.now())
            .order_by("available_at", "created_at")[:size]
        )
        for event in events:
            event.attempts += 1
            try:
                for task_name in consumers_for(event.event_type):
                    publish(task_name, event)
            except Exception as exc:
                backoff = min(2**event.attempts, 600)
                event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                event.available_at = time.now() + timedelta(seconds=backoff)
                if event.attempts >= max_attempts:
                    event.status = OutboxEvent.Status.FAILED
                event.save(update_fields=["attempts", "last_error", "available_at", "status"])
                result.failed += 1
                logger.warning(
                    "outbox_publish_failed",
                    extra={"event_id": str(event.id), "event_type": event.event_type},
                )
                continue
            event.status = OutboxEvent.Status.PUBLISHED
            event.published_at = time.now()
            event.last_error = ""
            event.save(update_fields=["attempts", "status", "published_at", "last_error"])
            result.published += 1
    return result


# --------------------------------------------------------------------------------------------
# Consumers
# --------------------------------------------------------------------------------------------
def idempotent_consumer(
    name: str, events: Iterable[str], **task_options: Any
) -> Callable[[Callable[[OutboxEvent], Any]], Any]:
    """Register ``fn(event)`` as an idempotent Celery consumer of the given event types.

    The handler runs inside ``transaction.atomic()`` together with the ``ProcessedEvent`` insert, so
    a failure rolls back the marker and the task may be retried; a duplicate delivery is a no-op.
    """
    task_name = f"consumer.{name}"

    def decorator(fn: Callable[[OutboxEvent], Any]) -> Any:
        from .tasks import BaseTask

        @shared_task(name=task_name, base=BaseTask, bind=True, **task_options)
        def _consume(self: BaseTask, event_id: str) -> Any:
            event = OutboxEvent.objects.get(pk=event_id)
            with transaction.atomic():
                try:
                    with transaction.atomic():
                        ProcessedEvent.objects.create(consumer=name, event_id=event.id)
                except IntegrityError:
                    logger.info("outbox_duplicate_delivery", extra={"consumer": name})
                    return None
                return fn(event)

        for event_type in events:
            if task_name not in _CONSUMERS[event_type]:
                _CONSUMERS[event_type].append(task_name)
        _consume.handler = fn
        return _consume

    return decorator
