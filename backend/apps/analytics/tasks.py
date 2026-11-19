"""Nightly refresh of the stored reports view (reports queue)."""

from __future__ import annotations

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import services


@shared_task(name="apps.analytics.tasks.refresh_analytics", base=BaseTask)
def refresh_analytics() -> int:
    return services.refresh_all()


@shared_task(name="apps.analytics.tasks.generate_export", base=BaseTask, acks_late=True)
def generate_export(export_id: str) -> str:
    from . import exports

    return "built" if exports.build(export_id) is not None else "skipped"


@idempotent_consumer("analytics.export_on_request", events=["export.requested"])
def on_export_requested(event: OutboxEvent) -> None:
    generate_export.delay(event.payload["export_id"])


@shared_task(name="apps.analytics.tasks.expire_exports", base=BaseTask)
def expire_exports() -> int:
    from . import exports

    return exports.expire_old()
