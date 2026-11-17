"""HR dashboard (P08-T10, FR-M15-01..03).

Everything is counted from the same tenant-scoped, visibility-filtered querysets the lists use,
so the numbers reconcile with what the person can open (reconciliation tests compare them with
direct queries). AI suggestions (bands of applications still in review) and human decisions
(status changes made by people) are reported separately and never mixed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils.dateparse import parse_date

from apps.core.exceptions import NotFoundError
from apps.core.time import now
from apps.jobs.assignments import jobs_visible_to
from apps.jobs.models import Job, JobStatus
from apps.organisations.models import Membership

from .hr import applications_visible_to
from .models import Application, ApplicationStatusEvent, Status

OPEN_JOB_STATUSES = (JobStatus.PUBLISHED, JobStatus.PAUSED)
IN_REVIEW = (Status.UNDER_REVIEW, Status.ON_HOLD, Status.NEEDS_INFORMATION)
DECISIONS = (Status.SHORTLISTED, Status.NOT_SELECTED, Status.ON_HOLD)
FUNNEL_REVIEWED = (
    Status.ON_HOLD,
    Status.SHORTLISTED,
    Status.NOT_SELECTED,
    Status.INTERVIEW,
    Status.OFFER,
    Status.HIRED,
    Status.OFFER_DECLINED,
)
SHORTLIST_ONWARD = (
    Status.SHORTLISTED,
    Status.INTERVIEW,
    Status.OFFER,
    Status.HIRED,
    Status.OFFER_DECLINED,
)


def _range(params: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    from datetime import time

    from django.utils import timezone

    start = parse_date(str(params.get("from") or "")) if params.get("from") else None
    end = parse_date(str(params.get("to") or "")) if params.get("to") else None
    tz = timezone.get_default_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), tz) if start else None,
        timezone.make_aware(datetime.combine(end, time.max), tz) if end else None,
    )


def scoped(
    membership: Membership, params: dict[str, Any]
) -> tuple[QuerySet[Job], QuerySet[Application]]:
    jobs = jobs_visible_to(membership)
    apps = applications_visible_to(membership)
    if department := params.get("department"):
        jobs = jobs.filter(department_id=department)
        apps = apps.filter(job__department_id=department)
    if job := params.get("job"):
        jobs = jobs.filter(pk=job)
        apps = apps.filter(job_id=job)
    if recruiter := params.get("recruiter"):
        apps = apps.filter(assigned_recruiter_id=recruiter)
    start, end = _range(params)
    if start:
        apps = apps.filter(submitted_at__gte=start)
    if end:
        apps = apps.filter(submitted_at__lte=end)
    return jobs, apps


def summary(membership: Membership, params: dict[str, Any]) -> dict[str, Any]:
    from apps.messaging.models import ClarificationRequest
    from apps.shortlisting.models import Shortlist

    jobs, apps = scoped(membership, params)
    moment = now()
    today = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    counts = apps.aggregate(
        today=Count("pk", filter=Q(submitted_at__gte=today)),
        week=Count("pk", filter=Q(submitted_at__gte=moment - timedelta(days=7))),
        processing=Count("pk", filter=Q(status__in=[Status.SUBMITTED, Status.PROCESSING])),
        errors=Count("pk", filter=Q(status=Status.PROCESSING_ERROR)),
        pending=Count("pk", filter=Q(status=Status.UNDER_REVIEW)),
    )
    clarifications = ClarificationRequest.objects.for_org(membership.organisation_id).filter(
        status="open", application__in=apps.values("pk")
    )
    approvals = Shortlist.objects.for_org(membership.organisation_id).filter(
        status=Shortlist.Status.PENDING_APPROVAL, job__in=jobs.values("pk")
    )
    bands = dict(
        apps.filter(status__in=IN_REVIEW)
        .exclude(ai_band="")
        .values_list("ai_band")
        .annotate(n=Count("pk"))
        .values_list("ai_band", "n")
    )
    start, end = _range(params)
    events = ApplicationStatusEvent.objects.for_org(membership.organisation_id).filter(
        application__in=apps.values("pk"), actor_type="human", to_status__in=DECISIONS
    )
    if start:
        events = events.filter(at__gte=start)
    if end:
        events = events.filter(at__lte=end)
    decisions = dict(
        events.values_list("to_status").annotate(n=Count("pk")).values_list("to_status", "n")
    )

    def rows(qs: QuerySet[Application]) -> list[dict[str, Any]]:
        return [
            {
                "application_id": a.pk,
                "reference": a.reference,
                "job_title": a.job.title,
                "status": a.status,
                "at": a.submitted_at,
            }
            for a in qs.select_related("job")[:10]
        ]

    return {
        "cards": {
            "open_vacancies": jobs.filter(status__in=OPEN_JOB_STATUSES).count(),
            "applications_today": counts["today"],
            "applications_7d": counts["week"],
            "processing_queue": counts["processing"],
            "processing_errors": counts["errors"],
            "pending_reviews": counts["pending"],
            "clarifications_outstanding": clarifications.count(),
            "shortlist_approvals_pending": approvals.count(),
        },
        "ai_suggestions": {
            "ai_notice": "AI-assisted suggestion — requires human review",
            "bands": bands,
        },
        "human_decisions": {
            "shortlisted": decisions.get(Status.SHORTLISTED, 0),
            "not_selected": decisions.get(Status.NOT_SELECTED, 0),
            "on_hold": decisions.get(Status.ON_HOLD, 0),
        },
        "queues": {
            "failed_processing": rows(
                apps.filter(status=Status.PROCESSING_ERROR).order_by("submitted_at")
            ),
            "pending_reviews": rows(
                apps.filter(status=Status.UNDER_REVIEW).order_by("submitted_at")
            ),
            "clarifications_due": [
                {
                    "application_id": c.application_id,
                    "due_at": c.due_at,
                    "job_title": c.application.job.title,
                }
                for c in clarifications.select_related("application__job").order_by("due_at")[:10]
            ],
            "approvals": [
                {
                    "shortlist_id": s.pk,
                    "job_id": s.job_id,
                    "job_title": s.job.title,
                    "submitted_at": s.submitted_at,
                }
                for s in approvals.select_related("job").order_by("submitted_at")[:10]
            ],
        },
    }


def funnel(membership: Membership, job_id: Any) -> dict[str, Any]:
    """submitted -> processed -> reviewed -> shortlisted (FR-M15-02)."""
    if not jobs_visible_to(membership).filter(pk=job_id).exists():
        raise NotFoundError()
    apps = applications_visible_to(membership).filter(job_id=job_id)
    counts = apps.aggregate(
        submitted=Count("pk"),
        processed=Count(
            "pk",
            filter=Q(current_evaluation_id__isnull=False)
            | Q(status__in=[*IN_REVIEW, *FUNNEL_REVIEWED]),
        ),
        reviewed=Count("pk", filter=Q(status__in=FUNNEL_REVIEWED)),
        shortlisted=Count("pk", filter=Q(status__in=SHORTLIST_ONWARD)),
        withdrawn=Count("pk", filter=Q(status=Status.WITHDRAWN)),
    )
    return {
        "job_id": job_id,
        "stages": [
            {"stage": k, "count": counts[k]}
            for k in ("submitted", "processed", "reviewed", "shortlisted")
        ],
        "withdrawn": counts["withdrawn"],
    }
