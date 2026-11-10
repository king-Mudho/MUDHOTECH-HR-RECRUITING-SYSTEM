"""Application background work (consumers of vacancy events + beat sweep)."""

from __future__ import annotations

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask
from apps.jobs.models import Job

from . import lifecycle


def _job(event: OutboxEvent) -> Job | None:
    return Job.objects.unscoped().filter(pk=event.payload.get("job_id")).first()


@idempotent_consumer("applications.abandon_drafts_on_close", events=["job.closed"])
def on_job_closed(event: OutboxEvent) -> int:
    job = _job(event)
    return lifecycle.abandon_drafts(job) if job else 0


@idempotent_consumer("applications.reactivate_drafts_on_extend", events=["job.deadline_extended"])
def on_deadline_extended(event: OutboxEvent) -> int:
    job = _job(event)
    return lifecycle.reactivate_drafts(job) if job else 0


@shared_task(name="apps.applications.tasks.sweep_stale_drafts", base=BaseTask, max_retries=0)
def sweep_stale_drafts() -> int:
    return lifecycle.sweep_stale_drafts()
