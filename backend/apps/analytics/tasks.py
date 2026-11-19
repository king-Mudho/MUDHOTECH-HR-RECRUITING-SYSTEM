"""Nightly refresh of the stored reports view (reports queue)."""

from __future__ import annotations

from celery import shared_task

from apps.core.tasks import BaseTask

from . import services


@shared_task(name="apps.analytics.tasks.refresh_analytics", base=BaseTask)
def refresh_analytics() -> int:
    return services.refresh_all()
