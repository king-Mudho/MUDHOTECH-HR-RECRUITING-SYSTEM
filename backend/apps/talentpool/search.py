"""HR talent search over **consented** pool members only (P13-T02, docs/01 M18).

The base queryset is ``services.searchable(org)`` (active, unexpired, consent not withdrawn) for
the member's own organisation, so another employer's candidates, former members and people who
never opted in cannot appear whatever the filters. Results carry profile facts (headline, skills,
qualifications, latest title) and never documents: a CV is only reachable through the person's
application to this employer.

Full-text search is PostgreSQL FTS over the profile headline and summary, skill names, job titles
and qualification names; skill and minimum-qualification filters narrow it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.postgres.aggregates import StringAgg
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery, TextField, Value
from django.db.models.functions import Coalesce

from apps.applications.models import Application
from apps.audit import services as audit
from apps.candidates.models import CandidateSkill, Education, Experience
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.time import now
from apps.jobs.assignments import jobs_visible_to
from apps.jobs.models import JobStatus
from apps.organisations.models import Membership

from .models import TalentPoolEntry, TalentPoolInvite
from .services import searchable

MAX_TAGS = 10
MAX_TAG_LENGTH = 40


def _agg(model: Any, field: str) -> Subquery:
    return Subquery(
        model.objects.filter(profile__user=OuterRef("candidate_user"))
        .values("profile")
        .annotate(text=StringAgg(field, " "))
        .values("text")[:1]
    )


def search(
    membership: Membership,
    *,
    q: str = "",
    skills: list[str] | None = None,
    min_qualification_rank: int | None = None,
    tag: str = "",
) -> QuerySet[TalentPoolEntry]:
    qs = (
        searchable(membership.organisation_id)
        .select_related("candidate_user", "candidate_user__candidate_profile")
        .prefetch_related(
            "candidate_user__candidate_profile__skills",
            "candidate_user__candidate_profile__educations",
            "candidate_user__candidate_profile__experiences",
            "invites",
        )
    )
    for skill in skills or []:
        name = skill.strip()
        if not name:
            continue
        match = Q(raw_name__iexact=name) | Q(skill__canonical_name__iexact=name)
        if _is_uuid(name):
            match |= Q(skill_id=name)
        qs = qs.filter(
            Exists(
                CandidateSkill.objects.filter(profile__user=OuterRef("candidate_user")).filter(
                    match
                )
            )
        )
    if min_qualification_rank is not None:
        qs = qs.filter(
            Exists(
                Education.objects.filter(
                    profile__user=OuterRef("candidate_user"),
                    qualification_level__rank__gte=min_qualification_rank,
                )
            )
        )
    if tag.strip():
        qs = qs.filter(tags__contains=[tag.strip()])
    text = q.strip()
    if text:
        vector = (
            SearchVector(
                Coalesce(
                    "candidate_user__candidate_profile__headline",
                    Value(""),
                    output_field=TextField(),
                ),
                weight="A",
                config="english",
            )
            + SearchVector(
                Coalesce(_agg(CandidateSkill, "raw_name"), Value(""), output_field=TextField()),
                weight="A",
                config="english",
            )
            + SearchVector(
                Coalesce(_agg(Experience, "title"), Value(""), output_field=TextField()),
                weight="B",
                config="english",
            )
            + SearchVector(
                Coalesce(
                    _agg(Education, "qualification_text"), Value(""), output_field=TextField()
                ),
                weight="B",
                config="english",
            )
            + SearchVector(
                Coalesce(
                    "candidate_user__candidate_profile__summary",
                    Value(""),
                    output_field=TextField(),
                ),
                weight="C",
                config="english",
            )
        )
        query = SearchQuery(text, search_type="websearch", config="english")
        qs = (
            qs.annotate(document=vector, rank=SearchRank(vector, query))
            .filter(document=query)
            .order_by("-rank", "-joined_at")
        )
    else:
        qs = qs.order_by("-joined_at")
    return qs


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def card(entry: TalentPoolEntry) -> dict[str, Any]:
    """Profile facts for the result list - no documents, no contact details, no screening data."""
    user = entry.candidate_user
    profile = getattr(user, "candidate_profile", None)
    skills: list[str] = []
    qualifications: list[str] = []
    latest_title = ""
    if profile is not None:
        # sorted in Python so the prefetched rows are used (no query per result)
        skills = [s.raw_name for s in sorted(profile.skills.all(), key=lambda s: s.order)][:15]
        educations = sorted(
            profile.educations.all(), key=lambda e: e.end_date or date.max, reverse=True
        )
        qualifications = [e.qualification_text for e in educations[:3]]
        experiences = sorted(
            profile.experiences.all(), key=lambda e: (e.is_current, e.start_date), reverse=True
        )
        latest_title = experiences[0].title if experiences else ""
    name = (getattr(profile, "preferred_name", "") or user.full_name or "").strip()
    source = (
        Application.objects.for_org(entry.organisation_id)
        .filter(candidate_user=user)
        .exclude(submitted_at__isnull=True)
        .order_by("-submitted_at")
        .values("pk", "reference", "job__title")
        .first()
    )
    return {
        "id": entry.pk,
        "name": name,
        "headline": getattr(profile, "headline", ""),
        "city": getattr(profile, "city", ""),
        "skills": skills,
        "qualifications": qualifications,
        "latest_title": latest_title,
        "tags": list(entry.tags or []),
        "joined_at": entry.joined_at,
        "expires_at": entry.expires_at,
        "latest_application": (
            {
                "id": source["pk"],
                "reference": source["reference"],
                "job_title": source["job__title"],
            }
            if source
            else None
        ),
        "invited_job_ids": [str(i.job_id) for i in entry.invites.all()],
    }


def _entry(membership: Membership, entry_id: Any) -> TalentPoolEntry:
    entry = searchable(membership.organisation_id).filter(pk=entry_id).first()
    if entry is None:
        raise NotFoundError()
    return entry


def get(membership: Membership, entry_id: Any) -> TalentPoolEntry:
    entry = _entry(membership, entry_id)
    audit.log_view(membership, entry, action="talent_pool_profile")
    return entry


def set_tags(membership: Membership, entry_id: Any, tags: list[str]) -> TalentPoolEntry:
    clean: list[str] = []
    for tag in tags:
        value = " ".join(str(tag).split())
        if not value:
            continue
        if len(value) > MAX_TAG_LENGTH:
            raise DomainError(
                "validation_error", "Tags are too long.", details={"tags": ["Max 40 characters."]}
            )
        if value not in clean:
            clean.append(value)
    if len(clean) > MAX_TAGS:
        raise DomainError("validation_error", "Too many tags.", details={"tags": ["Max 10."]})
    with transaction.atomic():
        entry = _entry(membership, entry_id)
        before = list(entry.tags or [])
        entry.tags = clean
        entry.save(update_fields=["tags", "updated_at"])
        audit.record(
            actor=membership.user,
            action="talent_pool.tags_changed",
            target=entry,
            organisation=membership.organisation_id,
            before={"tags": before},
            after={"tags": clean},
        )
    return entry


def invite(membership: Membership, entry_id: Any, job_id: Any) -> TalentPoolInvite:
    """Invite a pool member to apply for a published vacancy of this employer."""
    from django.conf import settings

    from apps.notifications import delivery as notifications

    with transaction.atomic():
        entry = _entry(membership, entry_id)
        job = jobs_visible_to(membership).filter(pk=job_id).first()
        if job is None:
            raise NotFoundError()
        if job.status != JobStatus.PUBLISHED:
            raise DomainError(
                "job_not_open", "Only vacancies open for applications can be shared.", 409
            )
        if (
            TalentPoolInvite.objects.for_org(membership.organisation_id)
            .filter(entry=entry, job=job)
            .exists()
        ):
            raise ConflictError(code="already_invited", message="Already invited to this vacancy.")
        if (
            Application.objects.for_org(membership.organisation_id)
            .filter(job=job, candidate_user=entry.candidate_user)
            .exclude(submitted_at__isnull=True)
            .exists()
        ):
            raise ConflictError(code="already_applied", message="They already applied.")
        sent = TalentPoolInvite.objects.create(
            organisation_id=membership.organisation_id,
            entry=entry,
            job=job,
            invited_by=membership.user,
            invited_at=now(),
        )
        notifications.notify(
            entry.candidate_user,
            "talent_pool_invitation",
            {
                "organisation_name": job.organisation.name,
                "job_title": job.title,
                "job_url": f"{settings.FRONTEND_URL}/jobs/{job.slug}",
                "privacy_url": f"{settings.FRONTEND_URL}/candidate/privacy#talent-pool",
            },
            dedupe_key=f"talent_pool_invitation:{entry.pk}:{job.pk}",
            organisation=job.organisation,
        )
        audit.record(
            actor=membership.user,
            action="talent_pool.invited",
            target=entry,
            organisation=membership.organisation_id,
            after={"job_id": str(job.pk)},
        )
    return sent
