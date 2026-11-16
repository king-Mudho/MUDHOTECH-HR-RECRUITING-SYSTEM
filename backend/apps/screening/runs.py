"""Screening runs (P07-T10, EC-AI-09/10/11, EC-JOB-06).

HR starts a run for a vacancy and a scope: ``all`` evaluable applications, ``pending`` (never
evaluated), ``failed`` (in ``processing_error``) or ``selected`` ids. Work is dispatched in
chunks of 50 and progress is counted per finished task. Each evaluation is a new version only
when its input changed (or HR forced a re-evaluation); earlier versions are kept as
``superseded``. Re-evaluating against a newer job version happens only on HR's explicit choice,
with a reason (EC-JOB-06 / EC-AI-09) - applications otherwise keep the version they applied to.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models import F

from ai_engine import ENGINE_VERSION
from ai_engine.matching.config import DEFAULT_CONFIG
from apps.applications.models import Application, Status
from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.time import now
from apps.jobs.models import Job

from .models import Evaluation, ScreeningRun, Trigger

CHUNK = 50
EVALUABLE = (Status.PROCESSING, Status.UNDER_REVIEW, Status.NEEDS_INFORMATION, Status.ON_HOLD)


def record(run: ScreeningRun, *, failed: bool) -> None:
    with transaction.atomic():
        ScreeningRun.objects.unscoped().filter(pk=run.pk).update(
            done=F("done") + 1, failed=F("failed") + (1 if failed else 0)
        )
        fresh = ScreeningRun.objects.unscoped().select_for_update().get(pk=run.pk)
        if fresh.done >= fresh.total and fresh.finished_at is None:
            fresh.status = (
                ScreeningRun.Status.FAILED if fresh.failed else ScreeningRun.Status.COMPLETED
            )
            fresh.finished_at = now()
            fresh.save(update_fields=["status", "finished_at", "updated_at"])


def _job(membership: Any, job_id: Any) -> Job:
    from apps.jobs.assignments import jobs_visible_to

    job = jobs_visible_to(membership).filter(pk=job_id).first()
    if job is None:
        raise NotFoundError()
    return job


def select(
    membership: Any, job: Job, scope: str, application_ids: Sequence[Any] = ()
) -> list[Application]:
    from apps.applications.hr import applications_visible_to

    qs = applications_visible_to(membership).filter(job=job)
    if scope == ScreeningRun.Scope.FAILED:
        qs = qs.filter(status=Status.PROCESSING_ERROR)
    else:
        qs = qs.filter(status__in=EVALUABLE)
    if scope == ScreeningRun.Scope.PENDING:
        evaluated = (
            Evaluation.objects.for_org(job.organisation_id)
            .filter(application__job=job)
            .values("application_id")
        )
        qs = qs.exclude(pk__in=evaluated)
    if scope == ScreeningRun.Scope.SELECTED:
        qs = qs.filter(pk__in=list(application_ids))
    return list(qs.order_by("submitted_at", "pk"))


def start_run(
    membership: Any,
    actor: Any,
    job_id: Any,
    *,
    scope: str,
    application_ids: Sequence[Any] = (),
    reason: str = "",
    use_current_version: bool = False,
) -> ScreeningRun:
    """Create a run and dispatch its evaluations after commit."""
    from apps.taxonomy.services import current_version

    from .tasks import dispatch_run

    job = _job(membership, job_id)
    version = job.published_version or job.current_version
    if version is None:
        raise ConflictError(code="conflict.no_version", message="This vacancy has no version.")
    trigger = Trigger.REEVALUATION if use_current_version else Trigger.MANUAL
    if use_current_version and len(reason.strip()) < 5:
        raise DomainError(
            "validation_error",
            "Say why the applications should be re-evaluated against the new version.",
            details={"reason": ["At least 5 characters."]},
        )
    if scope == ScreeningRun.Scope.SELECTED and not application_ids:
        raise DomainError(
            "validation_error", "Choose applications.", details={"application_ids": ["Required."]}
        )
    apps = select(membership, job, scope, application_ids)
    with transaction.atomic():
        run = ScreeningRun.objects.create(
            organisation_id=job.organisation_id,
            job=job,
            job_version=version,
            trigger=trigger,
            scope=scope,
            reason=reason.strip()[:2000],
            requested_by=actor,
            engine_version=ENGINE_VERSION,
            config_version=DEFAULT_CONFIG.version,
            taxonomy_version=current_version(),
            status=ScreeningRun.Status.RUNNING if apps else ScreeningRun.Status.COMPLETED,
            total=len(apps),
            started_at=now(),
            finished_at=None if apps else now(),
        )
        audit.record(
            actor=actor,
            action="screening.run_started",
            target=run,
            organisation=job.organisation_id,
            after={"scope": scope, "total": len(apps), "trigger": trigger},
            reason=reason,
        )
        if apps:
            ids = [str(a.pk) for a in apps]
            transaction.on_commit(partial(dispatch_run.delay, str(run.pk), ids))
    return run


def dispatch(run_id: Any, application_ids: Sequence[str]) -> int:
    """Queue evaluations in chunks of 50 (each task is idempotent)."""
    from .tasks import evaluate_application

    run = ScreeningRun.objects.unscoped().get(pk=run_id)
    queued = 0
    for start in range(0, len(application_ids), CHUNK):
        for app_id in application_ids[start : start + CHUNK]:
            evaluate_application.delay(
                app_id,
                run.trigger,
                str(run.pk),
                run.reason,
                str(run.job_version_id) if run.trigger == Trigger.REEVALUATION else None,
            )
            queued += 1
    return queued


def runs_for(membership: Any, job_id: Any) -> list[ScreeningRun]:
    job = _job(membership, job_id)
    return list(ScreeningRun.objects.for_org(job.organisation_id).filter(job=job)[:50])


def run_detail(membership: Any, run_id: Any) -> ScreeningRun:
    run = ScreeningRun.objects.for_org(membership.organisation_id).filter(pk=run_id).first()
    if run is None:
        raise NotFoundError()
    _job(membership, run.job_id)  # visibility of the vacancy
    return run


def failures(run: ScreeningRun) -> list[Application]:
    """Applications of the run's vacancy waiting in processing_error (retry with scope=failed)."""
    return list(
        Application.objects.for_org(run.organisation_id).filter(
            job=run.job, status=Status.PROCESSING_ERROR
        )[:100]
    )
