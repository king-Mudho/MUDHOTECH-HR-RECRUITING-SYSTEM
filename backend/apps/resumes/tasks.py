"""Resume extraction tasks (``documents`` queue) and outbox consumers."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.conf import settings

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import services

MAX_RETRIES = 3


@shared_task(
    name="apps.resumes.tasks.extract_resume",
    base=BaseTask,
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def extract_resume(self: Any, document_id: str, application_id: str) -> str:
    """Idempotent per (application, document, engine version). Storage outages retry with
    backoff; the last attempt records a failure so the application lands in processing_error."""
    final = self.request.retries >= MAX_RETRIES
    try:
        return services.extract(document_id, application_id, final_attempt=final)
    except Exception as exc:
        if final:
            raise
        raise self.retry(exc=exc, countdown=min(60 * 2**self.request.retries, 900)) from exc


@idempotent_consumer("resumes.start_on_submit", events=["application.submitted"])
def on_application_submitted(event: OutboxEvent) -> None:
    if settings.RESUMES_AUTOSTART:
        services.start(event.payload["application_id"])


@idempotent_consumer("resumes.extract_on_accept", events=["document.accepted"])
def on_document_accepted(event: OutboxEvent) -> None:
    if settings.RESUMES_AUTOSTART:
        services.on_document_accepted(event.payload["document_id"])


@idempotent_consumer("resumes.fail_on_reject", events=["document.rejected"])
def on_document_rejected(event: OutboxEvent) -> None:
    if settings.RESUMES_AUTOSTART:
        services.on_document_rejected(event.payload["document_id"])


@shared_task(
    name="apps.resumes.tasks.parse_resume_preview",
    base=BaseTask,
    acks_late=True,
    autoretry_for=(OSError, ConnectionError),
    retry_backoff=True,
    max_retries=3,
)
def parse_resume_preview(parse_id: str) -> str:
    """A candidate's own CV preview (P06-T13). Idempotent per (document, engine version)."""
    from . import candidate

    return candidate.run_preview(parse_id)
