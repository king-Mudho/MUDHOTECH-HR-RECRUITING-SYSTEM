"""Read queries for vacancies (public board + HR lists)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, Prefetch, Q, QuerySet

from apps.core.time import now
from apps.organisations.models import Location, Organisation

from .models import Job, JobCriterion, JobSlugRedirect, JobStatus, Visibility

CLOSED_GRACE = timedelta(days=90)
PUBLIC_DETAIL_STATUSES = (JobStatus.PUBLISHED, JobStatus.PAUSED, JobStatus.CLOSED)
ORDERINGS = {"newest": "-published_at", "closing": "closes_at", "title": "title"}


def _base() -> QuerySet[Job]:
    # Public reads span organisations by design (the job board), so they use ``unscoped()``
    # with explicit status/visibility/organisation filters instead of tenant scoping.
    return (
        Job.objects.unscoped()
        .filter(organisation__status=Organisation.Status.ACTIVE)
        .select_related("organisation", "published_version")
        .prefetch_related(
            # Same-organisation rows of the jobs above; prefetching across orgs needs unscoped().
            Prefetch("locations", queryset=Location.objects.unscoped()),
            Prefetch(
                "published_version__criteria",
                queryset=JobCriterion.objects.unscoped().order_by("order"),
            ),
        )
    )


def public_jobs(params: dict[str, Any] | None = None) -> QuerySet[Job]:
    """Listed, published vacancies with filters (docs/04: q, location, workplace_type,
    employment_type, org, posted_within, closing_within, seniority, ordering)."""
    p = params or {}
    qs = _base().filter(
        status=JobStatus.PUBLISHED, visibility=Visibility.PUBLIC, closes_at__gt=now()
    )
    q = str(p.get("q") or "").strip()[:200]
    if q:
        query = SearchQuery(q, search_type="websearch", config="english")
        qs = qs.filter(search_vector=query).annotate(rank=SearchRank(F("search_vector"), query))
    location = str(p.get("location") or "").strip()
    if location:
        try:
            qs = qs.filter(locations__id=uuid.UUID(location))
        except ValueError:
            qs = qs.filter(
                Q(locations__city__iexact=location) | Q(locations__name__icontains=location)
            )
    for name in ("workplace_type", "employment_type", "seniority"):
        values = [v for v in str(p.get(name) or "").split(",") if v]
        if values:
            qs = qs.filter(**{f"{name}__in": values})
    if p.get("org"):
        qs = qs.filter(organisation__slug=str(p["org"]))
    for name, field_name, sign in (
        ("posted_within", "published_at__gte", -1),
        ("closing_within", "closes_at__lte", 1),
    ):
        try:
            days = int(p.get(name) or 0)
        except (TypeError, ValueError):
            days = 0
        if 0 < days <= 365:
            qs = qs.filter(**{field_name: now() + sign * timedelta(days=days)})
    ordering = str(p.get("ordering") or ("relevance" if q else "newest"))
    if ordering == "relevance" and q:
        qs = qs.order_by("-rank", "-published_at", "pk")
    else:
        qs = qs.order_by(ORDERINGS.get(ordering, "-published_at"), "pk")
    return qs.distinct() if location else qs


@dataclass
class PublicLookup:
    job: Job | None = None
    redirect_slug: str | None = None
    gone: bool = False


def public_job(slug_or_id: str) -> PublicLookup:
    """Detail lookup: published/paused (incl. unlisted) or closed within 90 days.

    Older closed vacancies are ``gone`` (410); renamed slugs redirect (EC-JOB-13).
    """
    qs = _base().filter(status__in=PUBLIC_DETAIL_STATUSES)
    try:
        job_id: uuid.UUID | None = uuid.UUID(slug_or_id)
    except ValueError:
        job_id = None
    if job_id is not None:
        job = qs.filter(pk=job_id).first()
    else:
        job = qs.filter(slug=slug_or_id).first()
        if job is None:
            redirect = (
                JobSlugRedirect.objects.filter(old_slug=slug_or_id).select_related("job").first()
            )
            if redirect and redirect.job.status in PUBLIC_DETAIL_STATUSES:
                return PublicLookup(redirect_slug=redirect.job.slug)
    if job is None:
        return PublicLookup()
    if job.status == JobStatus.CLOSED and (
        job.closed_at is None or job.closed_at < now() - CLOSED_GRACE
    ):
        return PublicLookup(gone=True)
    return PublicLookup(job=job)


def company_open_jobs(org: Organisation) -> QuerySet[Job]:
    return public_jobs({"org": org.slug})


def public_questions(job: Job) -> list[Any]:
    from apps.questionnaires.models import Question, Questionnaire, QuestionOption

    if job.published_version_id is None:
        return []
    qn = (
        Questionnaire.objects.for_org(job.organisation_id)
        .filter(job_version_id=job.published_version_id)
        .first()
    )
    if qn is None:
        return []
    return list(
        Question.objects.for_org(job.organisation_id)
        .filter(questionnaire=qn)
        .order_by("order")
        .prefetch_related(
            Prefetch(
                "options",
                queryset=QuestionOption.objects.for_org(job.organisation_id).order_by("order"),
            )
        )
    )


def sitemap_jobs() -> QuerySet[Job]:
    return public_jobs().order_by("-published_at")[:5000]
