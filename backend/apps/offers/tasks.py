"""Offer background work: expiry sweep (beat) and the EC-OFF-04 consumer."""

from __future__ import annotations

from celery import shared_task

from apps.applications.models import Status
from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import services


@shared_task(name="apps.offers.tasks.process_offer_expiry", base=BaseTask)
def process_offer_expiry() -> dict[str, int]:
    return services.expire_due()


@idempotent_consumer("offers.close_on_application_withdrawn", events=["application.status_changed"])
def on_status_changed(event: OutboxEvent) -> int:
    if event.payload.get("to") != Status.WITHDRAWN:
        return 0
    return services.on_application_withdrawn(event.payload.get("application_id"))
