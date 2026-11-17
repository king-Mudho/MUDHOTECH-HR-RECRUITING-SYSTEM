"""Privacy tasks (P09-T02)."""

from __future__ import annotations

from celery import shared_task

from apps.core.tasks import BaseTask


@shared_task(name="apps.privacy.tasks.rights_reminders", base=BaseTask)
def rights_reminders() -> int:
    """Remind handlers 5 days before a rights request is due (and once when overdue)."""
    from . import rights

    return rights.send_reminders()
