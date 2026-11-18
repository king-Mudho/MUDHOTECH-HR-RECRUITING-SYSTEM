"""P12-T03: scorecards - validation, independent submission (EC-INT-04), consolidated view,
panel view with AI hidden by default (ADR-019), erasure of interview notes."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import time as mhrs_time
from apps.core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from apps.interviews import scheduling, scorecards
from apps.interviews.models import Interview, Scorecard
from apps.interviews.selectors import panel_view
from apps.interviews.services import template_from_job
from apps.jobs.models import JobCriterion
from apps.organisations.models import Membership, OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def member(team: Any, user: Any) -> Membership:
    return Membership.objects.for_org(team.org).get(user=user)


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
        title="Web projects",
        rubric_category="experience",
    )
    app = make_application(job, status=Status.SHORTLISTED)
    tpl = template_from_job(job, actor=team.recruiter, extra_competencies=["Communication"])
    a, b = member(team, team.panelist), member(team, team.hiring_manager)
    iv = scheduling.create_interview(
        app,
        actor=team.recruiter,
        stage="Technical",
        mode="video",
        panel=[(a, "lead"), (b, "member")],
        scorecard_template=tpl,
        starts_at=mhrs_time.now() + timedelta(days=1),
    ).interview
    # the interview has taken place
    Interview.objects.filter(pk=iv.pk).update(
        starts_at=mhrs_time.now() - timedelta(hours=1),
        ends_at=mhrs_time.now() - timedelta(minutes=15),
    )
    iv.refresh_from_db()
    return {"team": team, "job": job, "app": app, "tpl": tpl, "iv": iv, "a": a, "b": b}


FULL = {"scores": {"c1": 4, "c2": 3, "c3": 5}, "overall": 4, "recommendation": "yes"}


def test_only_panelists_rate_and_a_template_is_needed(ctx: dict[str, Any]) -> None:
    with pytest.raises(PermissionDeniedError):
        scorecards.save_draft(ctx["iv"], member(ctx["team"], ctx["team"].recruiter), FULL)
    Interview.objects.filter(pk=ctx["iv"].pk).update(scorecard_template=None)
    ctx["iv"].refresh_from_db()
    with pytest.raises(DomainError) as err:
        scorecards.save_draft(ctx["iv"], ctx["a"], FULL)
    assert err.value.code == "no_scorecard_template"


@pytest.mark.parametrize(
    "bad",
    [
        {"scores": {"c9": 3}},
        {"scores": {"c1": 0}},
        {"scores": {"c1": 6}},
        {"scores": {"c1": True}},
        {"scores": {"c1": "4"}},
        {"scores": [4]},
        {"overall": 7},
        {"recommendation": "maybe"},
        {"criterion_notes": {"c9": "x"}},
    ],
)
def test_draft_validation(ctx: dict[str, Any], bad: dict[str, Any]) -> None:
    with pytest.raises(DomainError) as err:
        scorecards.save_draft(ctx["iv"], ctx["a"], bad)
    assert err.value.code == "validation_error"


def test_draft_then_submit_locks_template_and_is_final(ctx: dict[str, Any]) -> None:
    card = scorecards.save_draft(
        ctx["iv"],
        ctx["a"],
        {"scores": {"c1": 4}, "criterion_notes": {"c1": "  Clear about Django  "}},
    )
    assert card.submitted_at is None and card.scores == {"c1": 4}
    assert '"c1": "Clear about Django"' in card.criterion_notes
    with pytest.raises(DomainError) as err:  # incomplete
        scorecards.submit(ctx["iv"], ctx["a"])
    assert set(err.value.details) == {"scores", "overall", "recommendation"}
    done = scorecards.submit(ctx["iv"], ctx["a"], FULL)
    assert done.submitted_at and done.overall == 4
    assert '"c1": "Clear about Django"' in done.criterion_notes  # kept from the draft
    ctx["tpl"].refresh_from_db()
    assert ctx["tpl"].locked_at is not None
    assert AuditEvent.objects.filter(action="interviews.scorecard_submitted").exists()
    for call in (scorecards.submit, scorecards.save_draft):
        with pytest.raises(DomainError) as err:
            call(ctx["iv"], ctx["a"], FULL)
        assert err.value.code == "scorecard_submitted"


def test_cannot_submit_before_the_interview(ctx: dict[str, Any]) -> None:
    Interview.objects.filter(pk=ctx["iv"].pk).update(
        starts_at=mhrs_time.now() + timedelta(hours=2), ends_at=mhrs_time.now() + timedelta(hours=3)
    )
    ctx["iv"].refresh_from_db()
    with pytest.raises(DomainError) as err:
        scorecards.submit(ctx["iv"], ctx["a"], FULL)
    assert err.value.code == "interview_not_held"


def test_independent_submission(ctx: dict[str, Any]) -> None:
    """EC-INT-04: nobody sees others' scores before submitting their own; drafts are never shown."""
    iv, a, b = ctx["iv"], ctx["a"], ctx["b"]
    scorecards.save_draft(iv, a, {"scores": {"c1": 2}})
    scorecards.submit(iv, b, FULL)
    # A has not submitted: only A's own draft, not B's submitted card
    seen_by_a = scorecards.visible_scorecards(iv, a)
    assert [c.panelist.membership_id for c in seen_by_a] == [a.pk]
    # B submitted: sees own card; A's draft stays hidden
    assert [c.panelist.membership_id for c in scorecards.visible_scorecards(iv, b)] == [b.pk]
    scorecards.submit(iv, a, FULL)
    assert {c.panelist.membership_id for c in scorecards.visible_scorecards(iv, a)} == {a.pk, b.pk}
    # someone not on the panel and without feedback rights
    with pytest.raises(PermissionDeniedError):
        scorecards.visible_scorecards(iv, member(ctx["team"], ctx["team"].auditor))


def test_hr_sees_submitted_cards_only(ctx: dict[str, Any]) -> None:
    iv = ctx["iv"]
    scorecards.save_draft(iv, ctx["a"], {"scores": {"c1": 2}})
    scorecards.submit(iv, ctx["b"], FULL)
    hr = member(ctx["team"], ctx["team"].hr_manager)
    assert [c.panelist.membership_id for c in scorecards.visible_scorecards(iv, hr)] == [
        ctx["b"].pk
    ]


def test_consolidated_view(ctx: dict[str, Any]) -> None:
    iv = ctx["iv"]
    scorecards.submit(
        iv, ctx["a"], {"scores": {"c1": 5, "c2": 2, "c3": 4}, "overall": 4, "recommendation": "yes"}
    )
    hr = member(ctx["team"], ctx["team"].hr_manager)
    one = scorecards.consolidated(iv, hr)
    assert one["submitted"] == 1 and one["panel_size"] == 2 and len(one["outstanding"]) == 1
    scorecards.submit(
        iv, ctx["b"], {"scores": {"c1": 2, "c2": 2, "c3": 4}, "overall": 2, "recommendation": "no"}
    )
    both = scorecards.consolidated(iv, hr)
    c1 = next(c for c in both["criteria"] if c["key"] == "c1")
    assert (c1["average"], c1["min"], c1["max"], c1["disagreement"]) == (3.5, 2, 5, True)
    assert both["overall_average"] == 3.0 and both["outstanding"] == []
    assert both["recommendations"] == {"strong_yes": 0, "yes": 1, "no": 1, "strong_no": 0}
    with pytest.raises(PermissionDeniedError):  # the panelist role has no consolidated view
        scorecards.consolidated(iv, ctx["a"])


def test_panel_view_hides_ai_by_default(ctx: dict[str, Any]) -> None:
    """ADR-019."""
    team, iv = ctx["team"], ctx["iv"]
    view = panel_view(team.panelist, ctx["a"], iv.pk)
    assert view["ai"] is None and view["application"]["reference"] == ctx["app"].reference
    assert [c["title"] for c in view["scorecard_criteria"]] == [
        "Python",
        "Web projects",
        "Communication",
    ]
    OrganisationPolicy.objects.filter(organisation=team.org).update(hide_ai_from_panelists=False)
    view = panel_view(team.panelist, ctx["a"], iv.pk)
    assert view["ai"] is not None and "requires human review" in view["ai"]["label"]


def test_panel_view_is_limited_to_own_interviews(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    other_app = make_application(ctx["job"], status=Status.SHORTLISTED)
    other = scheduling.create_interview(
        other_app,
        actor=team.recruiter,
        stage="Technical",
        mode="phone",
        panel=[(ctx["b"], "lead")],
        starts_at=mhrs_time.now() + timedelta(days=2),
    ).interview
    with pytest.raises(NotFoundError):  # the panelist is not on this one
        panel_view(team.panelist, ctx["a"], other.pk)
    recruiter = member(team, team.recruiter)
    assert panel_view(team.recruiter, recruiter, other.pk)["interview"].pk == other.pk  # view_all
    outsider = make_org_with_team()
    with pytest.raises(NotFoundError):
        panel_view(outsider.recruiter, member(outsider, outsider.recruiter), other.pk)


def test_erasure_removes_interview_notes(ctx: dict[str, Any]) -> None:
    from apps.privacy.erasure import erase

    scorecards.submit(
        ctx["iv"],
        ctx["a"],
        {**FULL, "criterion_notes": {"c1": "Mentioned family"}, "notes": "Private"},
    )
    counts = erase(ctx["app"].candidate_user, ctx["team"].org.pk, actor=ctx["team"].admin)
    assert counts.get("scorecards") == 1
    card = Scorecard.objects.for_org(ctx["team"].org).get()
    assert card.notes == "" and card.criterion_notes == "" and card.overall == 4
