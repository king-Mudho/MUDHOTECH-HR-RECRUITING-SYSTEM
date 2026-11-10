"""Document tasks (``documents`` queue)."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import transaction

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import cleanup, pipeline
from .antivirus import ScannerUnavailableError


@shared_task(
    name="apps.documents.tasks.scan_document",
    base=BaseTask,
    autoretry_for=(ScannerUnavailableError,),
    retry_backoff=True,
    max_retries=5,
)
def scan_document(document_id: str) -> str:
    return pipeline.scan_document(document_id)


@idempotent_consumer("documents.scan_on_upload", events=["document.uploaded"])
def on_document_uploaded(event: OutboxEvent) -> None:
    # Scan outside the consumer's transaction: storage + network I/O, idempotent on its own.
    document_id: Any = event.payload["document_id"]
    transaction.on_commit(lambda: scan_document.delay(document_id))


@shared_task(name="apps.documents.tasks.cleanup_uploads", base=BaseTask, max_retries=0)
def cleanup_uploads() -> dict[str, int]:
    """Hourly: expire stale sessions, purge rejected files and quarantine orphans (EC-APP-08)."""
    r = cleanup.run()
    return {
        "expired": r.sessions_expired,
        "purged": r.rejected_purged,
        "orphans": r.orphans_deleted,
    }
