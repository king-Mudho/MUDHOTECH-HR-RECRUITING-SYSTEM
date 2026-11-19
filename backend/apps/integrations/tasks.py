"""Integration background work: webhook retries (P15-T05)."""

from __future__ import annotations

from celery import shared_task

from apps.core.tasks import BaseTask


@shared_task(name="apps.integrations.tasks.retry_webhooks", base=BaseTask)
def retry_webhooks() -> int:
    from . import webhooks

    return webhooks.retry_due()
