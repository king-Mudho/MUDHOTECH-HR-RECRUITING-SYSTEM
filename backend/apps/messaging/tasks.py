"""Messaging tasks and consumers."""

from __future__ import annotations

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import services


@shared_task(name="apps.messaging.tasks.clarifications_due", base=BaseTask, max_retries=0)
def clarifications_due() -> dict[str, int]:
    return services.process_due()


@idempotent_consumer("messaging.resume_review_after_answer", events=["clarification.answered"])
def on_clarification_answered(event: OutboxEvent) -> None:
    services.resume_review(event.payload["application_id"])
