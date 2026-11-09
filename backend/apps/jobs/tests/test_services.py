"""Job services: drafting, readiness, approval and lifecycle (P03-T05; EC-JOB-01..16)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from apps.audit.models import AuditEvent
from apps.core.exceptions import (
    ConflictError,
    DomainError,
    InvalidTransitionError,
    PermissionDeniedError,
    StaleVersionError,
)
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.jobs import services
from apps.jobs.models import Job, JobEvent, JobStatus, VersionStatus
from apps.organisations.models import Organisation, OrganisationPolicy
from apps.organisations.tests.factories import LocationFactory, OrgTeam, make_org_with_team

pytestmark = pytest.mark.django_db

CRITERIA = [
    {
        "type": "skill",
        "importance": "essential",
        "title": "Python",
        "justification": "Our whole platform is written in Python.",
    },
    {
        "type": "experience",
        "importance": "preferred",
        "title": "2 years web development",
        "min_months": 24,
    },
]
QUESTIONS = [
    {
        "key": "portfolio",
        "type": "yes_no",
        "prompt": "Can you share a code sample or portfolio?",
        "scoring": {"mode": "exact", "expected": "yes"},
    }
]


def draft_job(team: OrgTeam, **extra: Any) -> Job:
    loc = LocationFactory(organisation=team.org)
    data = {
        "title": "Software Developer",
        "closes_at": now() + timedelta(days=14),
        "location_ids": [loc.pk],
        "summary": "Build web applications.",
        "responsibilities_html": "<ul><li>Write code</li></ul><script>alert(1)</script>",
        "required_documents": ["cv"],
        **extra,
    }
    job = services.create_job(team.org, actor=team.recruiter, data=data)
    services.set_criteria(job, actor=team.recruiter, criteria=CRITERIA)
    services.set_questionnaire(job, actor=team.recruiter, questions=QUESTIONS)
    job.refresh_from_db()
    return job


def approved_job(team: OrgTeam) -> Job:
    job = draft_job(team)
    services.submit_for_approval(job, actor=team.recruiter)
    return services.approve(job, actor=team.hr_manager)


def published_job(team: OrgTeam) -> Job:
    return services.publish(approved_job(team), actor=team.hr_manager)


# -- drafting -----------------------------------------------------------------------------------


def test_create_job_defaults_assignment_and_sanitises(team: OrgTeam) -> None:
    job = draft_job(team)
    assert job.status == JobStatus.DRAFT and job.slug.startswith("software-developer-")
    v = job.current_version
    assert v is not None and "<script>" not in v.responsibilities_html
    assert v.rubric.total_weight == 100 and len(v.rubric.categories) == 5
    assert job.assignments.filter(role_on_job="recruiter").count() == 1
    assert JobEvent.objects.for_org(team.org).filter(job=job, action="created").exists()


@pytest.mark.parametrize("role", ["hiring_manager", "panelist", "auditor"])
def test_only_recruiting_roles_create_jobs(team: OrgTeam, role: str) -> None:
    with pytest.raises(PermissionDeniedError):
        services.create_job(team.org, actor=getattr(team, role), data={"title": "X"})


def test_cross_tenant_actor_cannot_touch_job(team: OrgTeam) -> None:
    other = make_org_with_team()
    job = draft_job(team)
    with pytest.raises(PermissionDeniedError):
        services.update_job(job, actor=other.admin, data={"title": "Hacked"}, lock_version=None)
    with pytest.raises(PermissionDeniedError):
        services.approve(job, actor=other.hr_manager)


def test_update_with_stale_lock_conflicts(team: OrgTeam) -> None:
    """EC-JOB-07."""
    job = draft_job(team)
    lock = job.lock_version
    services.update_job(
        job, actor=team.recruiter, data={"title": "Backend Developer"}, lock_version=lock
    )
    with pytest.raises(StaleVersionError):
        services.update_job(job, actor=team.hr_manager, data={"openings": 2}, lock_version=lock)
    job.refresh_from_db()
    assert job.slug.startswith("backend-developer-")


def test_header_validation(team: OrgTeam) -> None:
    job = draft_job(team)
    for bad in (
        {"salary_min": "900", "salary_max": "100"},
        {"openings": 0},
        {"timezone": "Mars/Base"},
        {"title": "  "},
        {"required_documents": ["selfie"]},
    ):
        with pytest.raises(DomainError):
            services.update_job(job, actor=team.recruiter, data=bad, lock_version=None)


def test_essential_criteria_need_justification(team: OrgTeam) -> None:
    job = draft_job(team)
    with pytest.raises(DomainError) as exc:
        services.set_criteria(
            job,
            actor=team.recruiter,
            criteria=[{"type": "skill", "importance": "essential", "title": "Java"}],
        )
    assert "justification" in exc.value.details["0"]


def test_rubric_must_total_100_with_bands(team: OrgTeam) -> None:
    """EC-JOB-02."""
    job = draft_job(team)
    cats = services.default_rubric()
    cats[0]["weight"] = 30
    with pytest.raises(DomainError) as exc:
        services.set_rubric(job, actor=team.recruiter, categories=cats)
    assert "total_weight" in exc.value.details
    cats[0]["weight"] = 35
    cats[1]["bands"] = [{"score": 0, "descriptor": "None"}]
    with pytest.raises(DomainError):
        services.set_rubric(job, actor=team.recruiter, categories=cats)
    cats[1]["bands"] = services.default_rubric()[1]["bands"]
    assert services.set_rubric(job, actor=team.recruiter, categories=cats).total_weight == 100


# -- readiness ----------------------------------------------------------------------------------


def test_readiness_lists_every_failing_check(team: OrgTeam) -> None:
    """EC-JOB-01: each failing check is reported; publish is blocked with 422."""
    OrganisationPolicy.objects.filter(organisation=team.org).update(privacy_notice="")
    job = services.create_job(team.org, actor=team.recruiter, data={"title": "Accountant"})
    job.assignments.all().delete()
    result = services.readiness(job)
    failing = {c["id"] for c in result["checks"] if not c["ok"]}
    assert not result["ready"]
    assert {
        "description",
        "location",
        "required_documents",
        "essential_criterion",
        "deadline",
        "recruiter_assigned",
        "privacy_notice",
        "approved",
    } <= failing
    with pytest.raises(DomainError) as exc:
        services.submit_for_approval(job, actor=team.recruiter)
    assert exc.value.code == "job_not_ready" and exc.value.status_code == 422


def test_readiness_warnings_all_essential_and_short_deadline(team: OrgTeam) -> None:
    """EC-JOB-03 / EC-JOB-04."""
    job = draft_job(team)
    services.set_criteria(job, actor=team.recruiter, criteria=CRITERIA[:1])
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closes_at=now() + timedelta(hours=5))
    job.refresh_from_db()
    ids = {w["id"] for w in services.readiness(job, stage="submit")["warnings"]}
    assert {"all_essential", "short_deadline"} <= ids
    assert services.readiness(job, stage="submit")["ready"]


def test_unjustified_protected_question_blocks_until_exception(team: OrgTeam) -> None:
    from apps.questionnaires.services import record_protected_exception

    job = draft_job(team)
    qn = services.set_questionnaire(
        job,
        actor=team.recruiter,
        questions=[*QUESTIONS, {"key": "age", "type": "number", "prompt": "What is your age?"}],
    )
    check = {c["id"]: c for c in services.readiness(job, stage="submit")["checks"]}["questionnaire"]
    assert not check["ok"] and check["details"]["protected_topics_unresolved"] == ["age"]
    record_protected_exception(
        qn.questions.get(key="age"),
        actor=team.hr_manager,
        reason="Statutory minimum age of 18 for this licensed security role.",
    )
    assert services.readiness(job, stage="submit")["ready"]


# -- approval & publishing ---------------------------------------------------------------------


def test_full_lifecycle_with_events_audit_and_outbox(team: OrgTeam) -> None:
    job = published_job(team)
    assert job.status == JobStatus.PUBLISHED and job.published_version == job.current_version
    v = job.current_version
    assert v is not None and v.status == VersionStatus.APPROVED and v.snapshot["criteria"]
    assert v.rubric.status == "approved" and v.questionnaire.status == "approved"
    services.pause(job, actor=team.hr_manager, reason="Budget review")
    services.resume(job, actor=team.hr_manager)
    services.close(job, actor=team.hr_manager, reason="Position filled internally")
    services.archive(job, actor=team.hr_manager)
    job.refresh_from_db()
    assert job.status == JobStatus.ARCHIVED
    actions = list(
        JobEvent.objects.for_org(team.org).filter(job=job).values_list("action", flat=True)
    )
    assert actions == [
        "created",
        "submitted",
        "approved",
        "published",
        "paused",
        "resumed",
        "closed",
        "archived",
    ]
    assert AuditEvent.objects.filter(action="job.published", target_id=str(job.pk)).exists()
    events = set(
        OutboxEvent.objects.filter(aggregate_id=str(job.pk)).values_list("event_type", flat=True)
    )
    assert {"job.published", "job.closed"} <= events


def test_approval_requires_hr_manager_and_dual_control(team: OrgTeam) -> None:
    job = draft_job(team)
    services.submit_for_approval(job, actor=team.hr_manager)
    with pytest.raises(PermissionDeniedError):
        services.approve(job, actor=team.recruiter)
    OrganisationPolicy.objects.filter(organisation=team.org).update(rubric_dual_control=True)
    with pytest.raises(PermissionDeniedError):
        services.approve(job, actor=team.hr_manager)  # submitter cannot self-approve
    assert services.approve(job, actor=team.admin).status == JobStatus.APPROVED


def test_reject_returns_to_draft_with_reason(team: OrgTeam) -> None:
    job = draft_job(team)
    services.submit_for_approval(job, actor=team.recruiter)
    with pytest.raises(DomainError):
        services.reject(job, actor=team.hr_manager, reason="")
    job = services.reject(job, actor=team.hr_manager, reason="Please add salary details.")
    assert job.status == JobStatus.DRAFT and job.current_version.is_editable  # type: ignore[union-attr]


def test_approved_version_is_immutable(team: OrgTeam) -> None:
    job = approved_job(team)
    with pytest.raises(ConflictError):
        services.set_criteria(job, actor=team.recruiter, criteria=CRITERIA)
    with pytest.raises(ConflictError):
        services.set_rubric(job, actor=team.recruiter, categories=services.default_rubric())
    with pytest.raises(ConflictError):
        services.set_questionnaire(job, actor=team.recruiter, questions=[])


def test_unverified_or_suspended_org_cannot_publish(team: OrgTeam) -> None:
    job = approved_job(team)
    Organisation.objects.filter(pk=team.org.pk).update(verified_at=None)
    with pytest.raises(DomainError) as exc:
        services.publish(job, actor=team.hr_manager)
    assert exc.value.code == "org_unverified"


def test_publish_blocked_when_deadline_passed(team: OrgTeam) -> None:
    job = approved_job(team)
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closes_at=now() - timedelta(minutes=1))
    with pytest.raises(DomainError) as exc:
        services.publish(job, actor=team.hr_manager)
    assert exc.value.details["checks"][0]["id"] == "deadline"


def test_invalid_transitions(team: OrgTeam) -> None:
    job = draft_job(team)
    with pytest.raises(InvalidTransitionError):
        services.publish(job, actor=team.hr_manager)
    with pytest.raises(InvalidTransitionError):
        services.pause(job, actor=team.hr_manager)
    with pytest.raises(InvalidTransitionError):
        services.close(job, actor=team.hr_manager, reason="Not needed anymore")


def test_schedule_and_beat_publish(team: OrgTeam) -> None:
    job = approved_job(team)
    with pytest.raises(DomainError):
        services.schedule(job, actor=team.hr_manager, publish_at=now() - timedelta(minutes=1))
    job = services.schedule(job, actor=team.hr_manager, publish_at=now() + timedelta(hours=1))
    assert job.status == JobStatus.SCHEDULED
    assert services.publish_scheduled(job) is False  # not yet due
    Job.objects.for_org(team.org).filter(pk=job.pk).update(publish_at=now() - timedelta(seconds=1))
    assert services.publish_scheduled(job) is True
    assert services.publish_scheduled(job) is False  # idempotent
    job.refresh_from_db()
    assert job.status == JobStatus.PUBLISHED


def test_auto_close_and_extend_reopens(team: OrgTeam) -> None:
    """EC-JOB-09 / EC-JOB-16."""
    job = published_job(team)
    assert services.auto_close(job) is False
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closes_at=now() - timedelta(seconds=1))
    assert services.auto_close(job) is True and services.auto_close(job) is False
    job.refresh_from_db()
    assert job.status == JobStatus.CLOSED
    with pytest.raises(DomainError):
        services.extend_deadline(
            job,
            actor=team.hr_manager,
            closes_at=now() - timedelta(days=1),
            reason="Extend for more applicants",
        )
    job = services.extend_deadline(
        job, actor=team.hr_manager, closes_at=now() + timedelta(days=7), reason="Too few applicants"
    )
    assert job.status == JobStatus.PUBLISHED and job.closed_at is None


def test_resume_after_deadline_requires_extension(team: OrgTeam) -> None:
    job = published_job(team)
    services.pause(job, actor=team.hr_manager)
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closes_at=now() - timedelta(seconds=1))
    with pytest.raises(DomainError) as exc:
        services.resume(job, actor=team.hr_manager)
    assert exc.value.code == "deadline_passed"


def test_new_version_flow_keeps_live_advert_until_approved(team: OrgTeam) -> None:
    """EC-JOB-06: editing a live vacancy creates v2; v1 stays public until approval."""
    job = published_job(team)
    v1 = job.published_version
    v2 = services.new_version(job, actor=team.hr_manager, reason="Add Django as essential")
    job.refresh_from_db()
    assert v2.number == 2 and job.current_version == v2 and job.published_version == v1
    assert job.status == JobStatus.PUBLISHED
    assert v2.criteria.count() == 2 and v2.questionnaire.questions.count() == 1
    with pytest.raises(ConflictError):
        services.new_version(job, actor=team.hr_manager, reason="Another one")
    services.set_criteria(
        job,
        actor=team.recruiter,
        criteria=[
            *CRITERIA,
            {
                "type": "skill",
                "importance": "essential",
                "title": "Django",
                "justification": "Our backend framework.",
            },
        ],
    )
    services.submit_for_approval(job, actor=team.recruiter)
    job.refresh_from_db()
    assert job.status == JobStatus.PUBLISHED and job.published_version == v1
    services.approve(job, actor=team.hr_manager)
    job.refresh_from_db()
    v1.refresh_from_db()  # type: ignore[union-attr]
    assert job.published_version == v2 and v1.status == VersionStatus.SUPERSEDED  # type: ignore[union-attr]
    assert v1.criteria.count() == 2  # type: ignore[union-attr]  # old version untouched


def test_duplicate_creates_independent_draft(team: OrgTeam) -> None:
    """EC-JOB-14."""
    job = published_job(team)
    services.close(job, actor=team.hr_manager, reason="Filled the role")
    copy = services.duplicate(job, actor=team.recruiter)
    assert copy.pk != job.pk and copy.status == JobStatus.DRAFT and copy.slug != job.slug
    assert copy.closes_at is None
    v = copy.current_version
    assert v is not None and v.criteria.count() == 2 and v.questionnaire.questions.count() == 1
    assert v.rubric.status == "draft"


def test_slug_stable_after_publish(team: OrgTeam) -> None:
    """EC-JOB-13."""
    job = published_job(team)
    slug = job.slug
    services.new_version(job, actor=team.hr_manager, reason="Retitle the role")
    services.update_job(
        job, actor=team.recruiter, data={"title": "Senior Developer"}, lock_version=None
    )
    job.refresh_from_db()
    assert job.slug == slug and job.title == "Senior Developer"


def test_live_deadline_changes_use_extend(team: OrgTeam) -> None:
    job = published_job(team)
    services.new_version(job, actor=team.hr_manager, reason="Change something")
    with pytest.raises(ConflictError):
        services.update_job(
            job,
            actor=team.recruiter,
            data={"closes_at": now() + timedelta(days=60)},
            lock_version=None,
        )
