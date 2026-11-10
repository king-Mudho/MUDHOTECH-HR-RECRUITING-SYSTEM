"""Notification tasks (``notifications`` queue)."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import transaction

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import delivery


class SendTask(BaseTask):
    """Retries provider failures with exponential backoff for roughly 24 hours (EC-NOT-02);
    the final failure writes a dead letter (BaseTask) and marks the notification failed."""

    autoretry_for = (delivery.DeliveryError,)
    max_retries = 13
    retry_backoff = 60
    retry_backoff_max = 4 * 3600

    def on_failure(
        self, exc: BaseException, task_id: str, args: Any, kwargs: Any, einfo: Any
    ) -> None:
        if args:
            delivery.mark_failed(args[0], f"{type(exc).__name__}: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(name="apps.notifications.tasks.send_notification", base=SendTask)
def send_notification(notification_id: str) -> str:
    return delivery.deliver(notification_id)


@idempotent_consumer("notifications.deliver", events=[delivery.EVENT])
def on_notification_queued(event: OutboxEvent) -> None:
    notification_id: Any = event.payload["notification_id"]
    transaction.on_commit(lambda: send_notification.delay(notification_id))


@shared_task(name="apps.notifications.tasks.send_due", base=BaseTask, max_retries=0)
def send_due() -> int:
    """Every few minutes: deliver deferred (quiet hours / scheduled) emails that are now due and
    re-queue rows left in ``sending`` by a crashed worker."""
    ids = delivery.due_ids()
    for notification_id in ids:
        send_notification.delay(notification_id)
    return len(ids)
