"""Vacancy beat tasks (P03-T06): scheduled publishing and deadline closing.

Both scan by ``<= now`` rather than "due in the last minute", so jobs missed while the system was
down are caught up on the next run (EC-JOB-18). Each job is handled in its own transaction under a
row lock and the service re-checks state, so overlapping runs and retries are harmless.
Deadlines are stored as aware UTC instants computed from the vacancy's own timezone, so the
comparison is timezone-correct (EC-JOB-05).
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.core.tasks import BaseTask
from apps.core.time import now

from . import services
from .models import Job, JobStatus

logger = logging.getLogger(__name__)
BATCH = 200


def _due(queryset_filter: dict[str, object]) -> list[Job]:
    qs = Job.objects.unscoped().filter(**queryset_filter).select_related("organisation")
    return list(qs.order_by("pk")[:BATCH])


@shared_task(name="apps.jobs.tasks.publish_scheduled_jobs", base=BaseTask, max_retries=0)
def publish_scheduled_jobs() -> dict[str, int]:
    published = skipped = failed = 0
    for job in _due({"status": JobStatus.SCHEDULED, "publish_at__lte": now()}):
        try:
            if services.publish_scheduled(job):
                published += 1
            else:
                skipped += 1
        except Exception:  # one bad job must not block the rest
            failed += 1
            logger.exception("scheduled publish failed", extra={"job_id": str(job.pk)})
    return {"published": published, "skipped": skipped, "failed": failed}


@shared_task(name="apps.jobs.tasks.close_expired_jobs", base=BaseTask, max_retries=0)
def close_expired_jobs() -> dict[str, int]:
    closed = failed = 0
    statuses = [JobStatus.PUBLISHED, JobStatus.PAUSED]
    for job in _due({"status__in": statuses, "closes_at__lte": now()}):
        try:
            if services.auto_close(job):
                closed += 1
        except Exception:
            failed += 1
            logger.exception("auto-close failed", extra={"job_id": str(job.pk)})
    return {"closed": closed, "failed": failed}
