from __future__ import annotations

from celery import shared_task

from apps.core.tasks import BaseTask


@shared_task(name="apps.interviews.tasks.send_interview_reminders", base=BaseTask)
def send_interview_reminders() -> int:
    """24 h and 1 h reminders for scheduled interviews (beat, every 5 minutes)."""
    from .scheduling import send_due_reminders

    return send_due_reminders()
