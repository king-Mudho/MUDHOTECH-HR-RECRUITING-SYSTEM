"""Operator actions on dead letters (EC-OPS-07, docs/runbooks/processing-backlog.md).

A dead letter is a task that failed all its retries. Operators either **retry** it (same task name,
args and kwargs queued again - every task is idempotent) or **resolve** it without retrying (e.g.
the object no longer exists). Both mark the record resolved and write an audit event.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import time as mhrs_time

from .models import DeadLetter


def _send(task_name: str, args: list[Any], kwargs: dict[str, Any]) -> None:
    from config.celery import app

    app.send_task(task_name, args=args, kwargs=kwargs)  # routed by CELERY_TASK_ROUTES


def retry(dead_letter: DeadLetter, actor: Any) -> bool:
    """Queue the task again (after commit). False if it was already resolved."""
    with transaction.atomic():
        dl = DeadLetter.objects.select_for_update().get(pk=dead_letter.pk)
        if dl.resolved_at:
            return False
        dl.resolved_at = mhrs_time.now()
        dl.resolved_by = actor
        dl.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
        audit.record(
            actor=actor,
            action="dead_letter.retried",
            target=dl,
            after={"task_name": dl.task_name, "task_id": dl.task_id},
            actor_type="human",
        )
        args, kwargs, name = list(dl.args or []), dict(dl.kwargs or {}), dl.task_name
        transaction.on_commit(lambda: _send(name, args, kwargs))
    return True


def resolve(dead_letter: DeadLetter, actor: Any, reason: str) -> bool:
    """Close without retrying. False if it was already resolved."""
    with transaction.atomic():
        dl = DeadLetter.objects.select_for_update().get(pk=dead_letter.pk)
        if dl.resolved_at:
            return False
        dl.resolved_at = mhrs_time.now()
        dl.resolved_by = actor
        dl.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
        audit.record(
            actor=actor,
            action="dead_letter.resolved",
            target=dl,
            after={"task_name": dl.task_name, "task_id": dl.task_id},
            reason=reason,
            actor_type="human",
        )
    return True
