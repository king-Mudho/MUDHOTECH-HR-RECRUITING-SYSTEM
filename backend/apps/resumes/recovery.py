"""Recover work lost when a whole worker dies (P10-T07, EC-OPS-04).

``acks_late`` + ``reject_on_worker_lost`` re-queue a task when a worker *process* dies, but when a
whole worker container is killed the broker only redelivers its unacknowledged task after the
Redis ``visibility_timeout`` (1 hour). This sweeper (beat, every 5 minutes) re-dispatches work
that has been stuck for longer than the task hard time limit allows, so it cannot still be
running:

* extraction runs left ``running`` (or ``pending`` and never started) on applications that are
  still ``processing`` -> ``extract_resume`` again (idempotent: a finished run is skipped);
* applications still ``processing`` whose CV runs all finished but that were never screened
  -> ``evaluate_application`` again (idempotent per input hash).

A late redelivery of the original task is harmless for the same reasons. Nothing here changes an
application's status itself.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.applications.models import Application, Status
from apps.core.time import now

from .models import ExtractionRun, RunStatus

STUCK_AFTER = timedelta(minutes=15)  # > CELERY_TASK_TIME_LIMIT (6 min) with retries' head-room


def recover(at: Any = None) -> dict[str, int]:
    from ai_engine import ENGINE_VERSION
    from apps.screening.tasks import evaluate_application

    from .tasks import extract_resume

    cutoff = (at or now()) - STUCK_AFTER
    counts: Counter[str] = Counter()
    if getattr(settings, "RESUMES_AUTOSTART", True):
        stuck = (
            ExtractionRun.objects.unscoped()
            .filter(application__status=Status.PROCESSING, engine_version=ENGINE_VERSION)
            .filter(
                Q(status=RunStatus.RUNNING, started_at__lt=cutoff)
                | Q(status=RunStatus.PENDING, created_at__lt=cutoff)
            )
            .values_list("document_id", "application_id")
        )
        for document_id, application_id in stuck:
            extract_resume.delay(str(document_id), str(application_id))
            counts["extraction"] += 1
    if getattr(settings, "SCREENING_AUTOSTART", True):
        unscreened = (
            Application.objects.unscoped()
            .filter(
                status=Status.PROCESSING, updated_at__lt=cutoff, current_evaluation_id__isnull=True
            )
            .exclude(
                extraction_runs__status__in=[
                    RunStatus.PENDING,
                    RunStatus.RUNNING,
                    RunStatus.FAILED,
                ]
            )
            .filter(extraction_runs__isnull=False)
            .distinct()
            .values_list("pk", flat=True)
        )
        for application_id in unscreened:
            evaluate_application.delay(str(application_id))
            counts["screening"] += 1
    return dict(counts)
