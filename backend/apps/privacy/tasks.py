"""Privacy tasks (P09-T02)."""

from __future__ import annotations

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask


@shared_task(name="apps.privacy.tasks.rights_reminders", base=BaseTask)
def rights_reminders() -> int:
    """Remind handlers 5 days before a rights request is due (and once when overdue)."""
    from . import rights

    return rights.send_reminders()


@shared_task(name="apps.privacy.tasks.generate_export", base=BaseTask, acks_late=True)
def generate_export(request_id: str) -> str:
    """Build the export bundle (P09-T03); idempotent while a valid export exists."""
    from . import export

    row = export.build(request_id)
    return "built" if row is not None else "skipped"


@idempotent_consumer("privacy.export_on_confirm", events=["privacy.export_requested"])
def on_export_requested(event: OutboxEvent) -> None:
    generate_export.delay(event.payload["request_id"])


@shared_task(name="apps.privacy.tasks.retention_daily", base=BaseTask)
def retention_daily() -> int:
    """P09-T05: anonymise applications past the organisation's retention period."""
    from . import retention

    return len(retention.run_all(dry_run=False))


@shared_task(name="apps.privacy.tasks.retention_preview", base=BaseTask)
def retention_preview() -> int:
    """Weekly dry run reported to organisation admins."""
    from . import retention

    return len(retention.run_all(dry_run=True))
