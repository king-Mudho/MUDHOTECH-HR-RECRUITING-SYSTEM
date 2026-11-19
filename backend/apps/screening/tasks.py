"""Screening tasks (``ai`` queue) and outbox consumers (P07-T09/T10)."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.conf import settings

from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.tasks import BaseTask

from . import services
from .models import Trigger

MAX_RETRIES = 3


@shared_task(
    name="apps.screening.tasks.evaluate_application",
    base=BaseTask,
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def evaluate_application(
    self: Any,
    application_id: str,
    trigger: str = Trigger.AUTO,
    run_id: str | None = None,
    reason: str = "",
    job_version_id: str | None = None,
) -> str:
    """Idempotent per evaluation input; transient failures retry with backoff, the last failure
    leaves the application in ``processing_error`` for HR."""
    from .models import ScreeningRun

    run = ScreeningRun.objects.unscoped().filter(pk=run_id).first() if run_id else None
    try:
        evaluation = services.evaluate_application(
            application_id,
            trigger=trigger,
            run=run,
            reason=reason,
            job_version_id=job_version_id,
        )
    except Exception as exc:
        if self.request.retries >= MAX_RETRIES:
            services.mark_failed(application_id, type(exc).__name__)
            if run is not None:
                from . import runs

                runs.record(run, failed=True)
            raise
        raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 600)) from exc
    if run is not None:
        from . import runs

        runs.record(run, failed=False)
    return "skipped" if evaluation is None else f"v{evaluation.version}"


@idempotent_consumer("screening.evaluate_on_evidence", events=["application.evidence_ready"])
def on_evidence_ready(event: OutboxEvent) -> None:
    if settings.SCREENING_AUTOSTART:
        evaluate_application.delay(event.payload["application_id"])


@idempotent_consumer(
    "screening.reevaluate_on_correction", events=["application.evidence_corrected"]
)
def on_evidence_corrected(event: OutboxEvent) -> None:
    if settings.SCREENING_AUTOSTART:
        evaluate_application.delay(event.payload["application_id"], Trigger.CORRECTION)


@shared_task(name="apps.screening.tasks.dispatch_run", base=BaseTask, acks_late=True)
def dispatch_run(run_id: str, application_ids: list[str]) -> int:
    from . import runs

    return runs.dispatch(run_id, application_ids)


@idempotent_consumer("screening.reevaluate_on_clarification", events=["clarification.answered"])
def on_clarification_answered(event: OutboxEvent) -> None:
    if settings.SCREENING_AUTOSTART:
        evaluate_application.delay(event.payload["application_id"], Trigger.CLARIFICATION)


@shared_task(name="apps.screening.tasks.ai_quality_override_alerts", base=BaseTask)
def ai_quality_override_alerts() -> int:
    """P13-T07: daily - alert HR when a vacancy's override rate is above 30 %."""
    from . import monitoring

    return monitoring.check_override_alerts()


@shared_task(name="apps.screening.tasks.ai_quality_platform_report", base=BaseTask)
def ai_quality_platform_report() -> str:
    """P13-T07: weekly - platform drift indicators (parse failures, score shifts by version)."""
    from . import monitoring

    return str(monitoring.store_platform_report().pk)
