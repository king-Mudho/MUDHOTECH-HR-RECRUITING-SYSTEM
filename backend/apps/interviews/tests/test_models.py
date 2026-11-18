"""P12-T01: interview models, constraints, encryption, RLS and scorecard templates."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction

from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import time as mhrs_time
from apps.core.exceptions import DomainError
from apps.interviews.models import (
    Interview,
    InterviewMode,
    InterviewPanelist,
    InterviewSlot,
    InterviewStatus,
    Recommendation,
    Scorecard,
)
from apps.interviews.services import template_from_job
from apps.jobs.models import JobCriterion
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx() -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    JobCriterion.objects.create(
        organisation=team.org,
        job_version=job.published_version,
        order=2,
        type="experience",
        importance="preferred",
        title="3 years web development",
        rubric_category="experience",
        evidence_guidance="Ask about the largest project they shipped.",
    )
    JobCriterion.objects.create(
        organisation=team.org,
        job_version=job.published_version,
        order=3,
        type="eligibility",
        importance="essential",
        title="Right to work in Zimbabwe",
        justification="Legal requirement.",
        rubric_category="competency",
    )
    app = make_application(job, status=Status.SHORTLISTED)
    return {"team": team, "job": job, "app": app}


def interview(ctx: dict[str, Any], **kw: Any) -> Interview:
    return Interview.objects.create(
        organisation=ctx["team"].org,
        application=ctx["app"],
        stage="Technical",
        mode=InterviewMode.VIDEO,
        created_by=ctx["team"].recruiter,
        **kw,
    )


def test_template_from_job_rates_criteria_but_not_eligibility(ctx: dict[str, Any]) -> None:
    tpl = template_from_job(
        ctx["job"],
        actor=ctx["team"].recruiter,
        extra_competencies=["Communication", " python ", ""],
    )
    titles = [c["title"] for c in tpl.criteria]
    assert titles == ["Python", "3 years web development", "Communication"]  # duplicate dropped
    assert tpl.keys == ["c1", "c2", "c3"]
    assert tpl.criteria[1]["description"] == "Ask about the largest project they shipped."
    assert tpl.criteria[2]["source_criterion_id"] is None
    assert tpl.job_version_id == ctx["job"].published_version_id
    assert AuditEvent.objects.filter(action="interviews.scorecard_template_created").exists()


def test_template_needs_a_published_vacancy(ctx: dict[str, Any]) -> None:
    job = ctx["job"]
    job.published_version = None
    with pytest.raises(DomainError) as err:
        template_from_job(job, actor=ctx["team"].recruiter)
    assert err.value.code == "job_not_published"


def test_interview_time_constraints(ctx: dict[str, Any]) -> None:
    now = mhrs_time.now()
    ok = interview(ctx)  # proposed, no time yet
    assert ok.status == InterviewStatus.PROPOSED and ok.timezone == "Africa/Harare"
    with transaction.atomic(), pytest.raises(IntegrityError):
        interview(ctx, starts_at=now, ends_at=now - timedelta(minutes=5))
    with transaction.atomic(), pytest.raises(IntegrityError):
        interview(ctx, status=InterviewStatus.SCHEDULED)  # scheduled needs a time
    interview(
        ctx, status=InterviewStatus.SCHEDULED, starts_at=now, ends_at=now + timedelta(hours=1)
    )


def test_only_one_booked_slot_per_interview(ctx: dict[str, Any]) -> None:
    iv = interview(ctx)
    start = mhrs_time.now() + timedelta(days=2)
    s1, s2 = (
        InterviewSlot.objects.create(
            organisation=ctx["team"].org,
            interview=iv,
            starts_at=start + timedelta(hours=h),
            ends_at=start + timedelta(hours=h, minutes=45),
        )
        for h in (0, 2)
    )
    InterviewSlot.objects.filter(pk=s1.pk).update(booked=True)
    with transaction.atomic(), pytest.raises(IntegrityError):
        InterviewSlot.objects.filter(pk=s2.pk).update(booked=True)
    with transaction.atomic(), pytest.raises(IntegrityError):  # same start twice
        InterviewSlot.objects.create(
            organisation=ctx["team"].org,
            interview=iv,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
        )


def test_scorecard_unique_complete_and_encrypted(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    tpl = template_from_job(ctx["job"], actor=team.recruiter)
    iv = interview(ctx, scorecard_template=tpl)
    member = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    panelist = InterviewPanelist.objects.create(
        organisation=team.org, interview=iv, membership=member
    )
    with (
        transaction.atomic(),
        pytest.raises(IntegrityError),
    ):  # submitted without overall/recommendation
        Scorecard.objects.create(
            organisation=team.org,
            interview=iv,
            panelist=panelist,
            template=tpl,
            submitted_at=mhrs_time.now(),
        )
    card = Scorecard.objects.create(
        organisation=team.org,
        interview=iv,
        panelist=panelist,
        template=tpl,
        scores={"c1": 4},
        criterion_notes='{"c1": "Explained Django ORM trade-offs clearly"}',
        overall=4,
        recommendation=Recommendation.YES,
        notes="Good candidate",
        submitted_at=mhrs_time.now(),
    )
    with transaction.atomic(), pytest.raises(IntegrityError):
        Scorecard.objects.create(
            organisation=team.org, interview=iv, panelist=panelist, template=tpl
        )
    with connection.cursor() as cur:
        cur.execute(
            "SELECT notes, criterion_notes FROM interviews_scorecard WHERE id = %s", [card.pk]
        )
        notes, crit = cur.fetchone()
    assert "Good candidate" not in notes and "Django" not in crit  # encrypted at rest
    assert Scorecard.objects.get(pk=card.pk).notes == "Good candidate"
    with transaction.atomic(), pytest.raises(IntegrityError):
        InterviewPanelist.objects.create(organisation=team.org, interview=iv, membership=member)


def test_row_level_security_is_forced_on_every_interview_table() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class WHERE relname LIKE 'interviews\\_%%' "
            "AND relkind = 'r' AND relforcerowsecurity ORDER BY relname"
        )
        forced = [r[0] for r in cur.fetchall()]
    assert forced == [
        "interviews_interview",
        "interviews_interviewpanelist",
        "interviews_interviewslot",
        "interviews_scorecard",
        "interviews_scorecardtemplate",
    ]


def test_tenant_manager_scopes_interviews(ctx: dict[str, Any]) -> None:
    interview(ctx)
    other = make_org_with_team()
    assert Interview.objects.for_org(ctx["team"].org).count() == 1
    assert Interview.objects.for_org(other.org).count() == 0
