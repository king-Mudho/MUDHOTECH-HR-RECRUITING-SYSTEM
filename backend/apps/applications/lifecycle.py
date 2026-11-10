"""Withdrawal and draft lifecycle around vacancy events (P04-T09).

* EC-APP-12/13 - candidates may withdraw any non-terminal application; background processing calls
  :func:`is_processable` before doing work, so a withdrawn application stops being processed.
  Assigned recruiters are emailed.
* EC-JOB-10 - when a vacancy closes (early or at its deadline) its open drafts are abandoned with
  ``reason_code="vacancy_closed"`` and the candidate is told; submitted applications carry on.
* EC-JOB-08 - pausing keeps drafts (nothing happens here).
* EC-JOB-09 - extending the deadline reactivates drafts abandoned because of the close within
  ``REACTIVATION_WINDOW``, unless the candidate has since started another application.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction

from apps.core.email import queue_email
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.jobs.models import Job, JobAssignment, JobStatus
from apps.organisations.models import Membership

from .models import TERMINAL_STATUSES, Application, ApplicationStatusEvent, Status
from .services import get_own, transition

REACTIVATION_WINDOW = timedelta(days=30)
CLOSED_REASON = "vacancy_closed"


def is_processable(application: Application) -> bool:
    """Processing tasks (screening, extraction) must check this first and stop otherwise."""
    current = (
        Application.objects.unscoped()
        .filter(pk=application.pk)
        .values_list("status", flat=True)
        .first()
    )
    return current in (
        Status.SUBMITTED,
        Status.PROCESSING,
        Status.PROCESSING_ERROR,
        Status.NEEDS_INFORMATION,
    )


def _notify_recruiters(app: Application, reason: str) -> None:
    emails = list(
        JobAssignment.objects.for_org(app.organisation_id)
        .filter(
            job_id=app.job_id, role_on_job="recruiter", membership__status=Membership.Status.ACTIVE
        )
        .values_list("membership__user__email", flat=True)
        .distinct()
    )
    if not emails:
        return
    queue_email(
        emails,
        f"Application withdrawn: {app.reference} ({app.job.title})",
        (
            f"The candidate has withdrawn application {app.reference} for {app.job.title}.\n"
            + (f"Reason given: {reason}\n" if reason else "")
            + "\nMUDHOTECH HR RECRUITING SYSTEM"
        ),
        dedupe_key=f"email.application_withdrawn:{app.pk}",
        organisation_id=app.organisation_id,
    )


def withdraw(user: Any, application_id: Any, reason: str = "") -> Application:
    """Candidate withdrawal. A draft is simply discarded (abandoned); anything non-terminal is
    withdrawn and the recruiters are told (EC-APP-12/13)."""
    with transaction.atomic():
        app = get_own(user, application_id)
        if app.status in TERMINAL_STATUSES:
            raise DomainError(
                "conflict.invalid_transition",
                "This application is already closed.",
                status_code=409,
            )
        if app.status == Status.DRAFT:
            return transition(
                app, Status.ABANDONED, actor=user, reason_code="discarded_by_candidate"
            )
        app = transition(app, Status.WITHDRAWN, actor=user, reason=reason.strip()[:2000])
        _notify_recruiters(app, reason.strip())
    return app


def abandon_drafts(job: Job, *, reason_code: str = CLOSED_REASON) -> int:
    """EC-JOB-10: abandon open drafts of a closed vacancy and tell each candidate once."""
    drafts = list(
        Application.objects.for_org(job.organisation_id)
        .filter(job=job, status=Status.DRAFT)
        .select_related("candidate_user")
    )
    for app in drafts:
        with transaction.atomic():
            transition(app, Status.ABANDONED, actor_type="system", reason_code=reason_code)
            queue_email(
                app.candidate_user.email,
                f"{job.title}: applications have closed",
                (
                    f"Hello,\n\nApplications for {job.title} have closed, so your unfinished "
                    "application could not be submitted. If the employer reopens the vacancy we "
                    "will let you know and your answers will still be there.\n\n"
                    "MUDHOTECH HR RECRUITING SYSTEM"
                ),
                dedupe_key=f"email.draft_abandoned:{app.pk}",
                organisation_id=app.organisation_id,
            )
    return len(drafts)


def reactivate_drafts(job: Job) -> int:
    """EC-JOB-09: deadline extended -> recently abandoned (by the close) drafts come back."""
    if job.status != JobStatus.PUBLISHED:
        return 0
    since = now() - REACTIVATION_WINDOW
    abandoned_ids = (
        ApplicationStatusEvent.objects.for_org(job.organisation_id)
        .filter(
            application__job=job,
            to_status=Status.ABANDONED,
            reason_code=CLOSED_REASON,
            at__gte=since,
        )
        .values_list("application_id", flat=True)
    )
    count = 0
    for app in (
        Application.objects.for_org(job.organisation_id)
        .filter(pk__in=list(abandoned_ids), status=Status.ABANDONED)
        .select_related("candidate_user")
    ):
        try:
            with transaction.atomic():
                transition(app, Status.DRAFT, actor_type="system", reason_code="deadline_extended")
        except DomainError:  # the candidate already started a newer application
            continue
        queue_email(
            app.candidate_user.email,
            f"{job.title}: you can finish your application",
            (
                f"Hello,\n\nThe closing date for {job.title} has been extended. Your unfinished "
                "application is open again - you can complete and submit it now.\n\n"
                "MUDHOTECH HR RECRUITING SYSTEM"
            ),
            dedupe_key=f"email.draft_reactivated:{app.pk}:{now().date().isoformat()}",
            organisation_id=app.organisation_id,
        )
        count += 1
    return count


def sweep_stale_drafts() -> int:
    """Hourly safety net: drafts whose vacancy is no longer open (missed events, downtime)."""
    total = 0
    stale_jobs = (
        Job.objects.unscoped()
        .filter(applications__status=Status.DRAFT)
        .exclude(status__in=[JobStatus.PUBLISHED, JobStatus.PAUSED])
        .distinct()
    )
    for job in stale_jobs:
        total += abandon_drafts(job)
    expired = (
        Job.objects.unscoped()
        .filter(applications__status=Status.DRAFT, status=JobStatus.PUBLISHED, closes_at__lt=now())
        .distinct()
    )
    for job in expired:  # auto-close normally handles these within a minute
        total += abandon_drafts(job)
    return total
