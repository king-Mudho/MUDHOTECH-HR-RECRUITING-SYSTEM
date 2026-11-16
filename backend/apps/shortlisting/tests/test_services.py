"""Shortlist workflow services (P08-T02/T03; EC-REV-01..05, 07, 08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.services import ApplicationTransitionError, transition
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.exceptions import (
    ConflictError,
    DomainError,
    PermissionDeniedError,
    StaleVersionError,
)
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.models import Membership, OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.shortlisting import services
from apps.shortlisting.models import Shortlist, ShortlistEntry

pytestmark = pytest.mark.django_db


@dataclass
class World:
    team: Any
    job: Any
    apps: dict[str, Application]

    def m(self, user: Any) -> Membership:
        return Membership.objects.get(user=user, organisation=self.team.org)


def app_with(job: Any, band: str, score: float | None, coverage: float) -> Application:
    app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    Application.objects.unscoped().filter(pk=app.pk).update(
        ai_band=band,
        score=None if score is None else Decimal(str(score)),
        coverage=Decimal(str(coverage)),
    )
    app.refresh_from_db()
    return app


@pytest.fixture
def world() -> World:
    team = make_org_with_team()
    job = published_job(organisation=team.org, title="Software Developer")
    apps = {
        "top": app_with(job, "recommended_for_review", 91, 1.0),
        "second": app_with(job, "recommended_for_review", 84, 0.9),
        "unsure": app_with(job, "review_needed", 60, 0.4),
        "lower": app_with(job, "lower_match", 40, 0.8),
    }
    from apps.jobs.models import JobAssignment

    recruiter = Membership.objects.get(user=team.recruiter, organisation=team.org)
    JobAssignment.objects.create(
        organisation=team.org, job=job, membership=recruiter, role_on_job="recruiter"
    )
    return World(team, job, apps)


def propose(w: World, size: int | None = 1) -> Shortlist:
    return services.create_proposal(
        w.m(w.team.recruiter), w.team.recruiter, w.job.pk, desired_size=size
    )


def decide(w: World, shortlist: Shortlist, *items: dict[str, Any], who: Any = None) -> Shortlist:
    who = who or w.team.recruiter
    return services.set_decisions(w.m(who), who, shortlist.pk, items)


def item(app: Application, decision: str, code: str = "", text: str = "") -> dict[str, Any]:
    return {
        "application_id": app.pk,
        "decision": decision,
        "reason_code": code,
        "reason_text": text,
    }


def ready(w: World) -> Shortlist:
    s = propose(w, 2)
    decide(
        w,
        s,
        item(w.apps["top"], "shortlist"),
        item(w.apps["second"], "shortlist"),
        item(w.apps["lower"], "not_selected", "less_relevant_experience"),
        item(w.apps["unsure"], "hold", "pending_verification"),
    )
    return services.submit(w.m(w.team.recruiter), w.team.recruiter, s.pk)


def test_proposal_prefills_suggestions_never_decisions(world: World) -> None:
    w = world
    s = propose(w, 1)
    entries = {e.application_id: e for e in s.entries.all()}
    assert len(entries) == 4
    assert {e.decision for e in entries.values()} == {"undecided"}  # suggestions only
    assert entries[w.apps["top"].pk].suggestion == "shortlist"
    assert entries[w.apps["second"].pk].suggestion == ""  # beyond the desired size
    assert entries[w.apps["unsure"].pk].suggestion == "review"
    assert entries[w.apps["lower"].pk].suggestion == ""  # never suggests "not selected"
    assert entries[w.apps["top"].pk].ai_band_at_decision == "recommended_for_review"
    with pytest.raises(ConflictError) as exc:
        propose(w)
    assert exc.value.code == "conflict.open_shortlist"
    assert AuditEvent.objects.filter(action="shortlist.proposed").exists()


def test_hiring_manager_cannot_propose(world: World) -> None:
    w = world
    with pytest.raises(PermissionDeniedError):
        services.create_proposal(w.m(w.team.hiring_manager), w.team.hiring_manager, w.job.pk)


def test_reasons_required_for_not_selected_hold_and_overrides(world: World) -> None:
    w = world
    s = propose(w)
    with pytest.raises(DomainError) as exc:
        decide(w, s, item(w.apps["lower"], "not_selected"))
    assert str(w.apps["lower"].pk) in exc.value.details["decisions"]
    with pytest.raises(DomainError):
        decide(w, s, item(w.apps["unsure"], "hold"))
    with pytest.raises(DomainError) as exc:  # EC-REV-05: shortlisting a lower match
        decide(w, s, item(w.apps["lower"], "shortlist"))
    assert "differs from the AI" in exc.value.details["decisions"][str(w.apps["lower"].pk)][0]
    with pytest.raises(DomainError):  # "other" needs an explanation
        decide(w, s, item(w.apps["lower"], "not_selected", "other"))

    decide(
        w,
        s,
        item(w.apps["lower"], "shortlist", "evidence_review_differs"),
        item(w.apps["top"], "not_selected", "essential_not_met"),
    )
    lower = s.entries.get(application=w.apps["lower"])
    top = s.entries.get(application=w.apps["top"])
    assert lower.override and top.override  # both go against the AI band
    assert lower.decided_by == w.team.recruiter and lower.decided_at
    assert lower.score_at_decision == Decimal("40.00")
    assert lower.coverage_at_decision == Decimal("0.80")

    decide(w, s, item(w.apps["lower"], "undecided"))  # clearing is allowed
    cleared = s.entries.get(application=w.apps["lower"])
    assert cleared.decision == "undecided" and cleared.decided_by is None and not cleared.override


def test_stale_version_is_refused(world: World) -> None:
    w = world
    s = propose(w)
    with pytest.raises(StaleVersionError):
        services.set_decisions(
            w.m(w.team.recruiter),
            w.team.recruiter,
            s.pk,
            [item(w.apps["top"], "shortlist")],
            lock_version=s.lock_version + 5,
        )


def test_submit_needs_a_decision_and_shows_uncertain_cases(world: World) -> None:
    w = world
    s = propose(w)
    with pytest.raises(DomainError):
        services.submit(w.m(w.team.recruiter), w.team.recruiter, s.pk)
    decide(
        w,
        s,
        item(w.apps["top"], "shortlist"),
        item(w.apps["second"], "shortlist"),
        item(w.apps["unsure"], "not_selected", "essential_not_met"),
    )
    counts = services.summary(s)
    assert counts["shortlist"] == 2 and counts["undecided"] == 1
    assert counts["above_desired_size"]  # EC-REV-08: allowed, info only
    assert counts["uncertain_not_selected"] == 1 and counts["low_coverage"] == 1  # EC-REV-01
    submitted = services.submit(w.m(w.team.recruiter), w.team.recruiter, s.pk)
    assert submitted.status == "pending_approval" and submitted.submitted_at
    with pytest.raises(ConflictError):
        decide(w, s, item(w.apps["lower"], "hold", "future_round"))  # no edits once submitted


def test_approval_applies_human_decisions_and_schedules_notifications(world: World) -> None:
    w = world
    s = ready(w)
    with pytest.raises(PermissionDeniedError):  # recruiters cannot approve
        services.approve(w.m(w.team.recruiter), w.team.recruiter, s.pk)
    approved = services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    assert approved.status == "approved" and approved.approved_by == [w.team.hr_manager.pk]
    statuses = dict(Application.objects.for_org(w.team.org).values_list("pk", "status"))
    assert statuses[w.apps["top"].pk] == "shortlisted"
    assert statuses[w.apps["lower"].pk] == "not_selected"
    assert statuses[w.apps["unsure"].pk] == "on_hold"
    events = ApplicationStatusEvent.objects.filter(metadata__via="shortlist")
    assert events.count() == 4
    assert all(e.actor_id == w.team.hr_manager.pk and e.actor_type == "human" for e in events)
    notes = Notification.objects.filter(key__in=["shortlisted", "not_selected"])
    assert notes.count() == 3 * 2  # email + in-app for 2 shortlisted + 1 not selected
    assert all(n.scheduled_for == approved.notify_after for n in notes)
    assert approved.notify_after > now()
    with pytest.raises(ConflictError) as exc:  # EC-REV-02: second approver
        services.approve(w.m(w.team.admin), w.team.admin, s.pk)
    assert exc.value.code == "already_processed"


def test_dual_control_forbids_self_approval(world: World) -> None:
    w = world
    OrganisationPolicy.objects.filter(organisation=w.team.org).update(shortlist_dual_control=True)
    s = services.create_proposal(
        w.m(w.team.hr_manager), w.team.hr_manager, w.job.pk, desired_size=2
    )
    decide(w, s, item(w.apps["top"], "shortlist"), who=w.team.hr_manager)
    services.submit(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    with pytest.raises(PermissionDeniedError) as exc:  # EC-REV-03
        services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    assert exc.value.code == "self_approval_forbidden"
    with pytest.raises(DomainError) as exc:  # three applicants are still undecided
        services.approve(w.m(w.team.admin), w.team.admin, s.pk)
    assert exc.value.code == "undecided_remaining"
    approved = services.approve(w.m(w.team.admin), w.team.admin, s.pk, leave_undecided=True)
    assert approved.status == "approved"


def test_withdrawn_before_approval_is_skipped_without_message(world: World) -> None:
    w = world
    s = ready(w)
    top = w.apps["top"]
    transition(top, Status.WITHDRAWN, actor=top.candidate_user, actor_type="candidate")
    services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    entry = s.entries.get(application=top)
    assert entry.apply_note == "withdrawn" and entry.applied_at is None  # EC-REV-07
    assert not Notification.objects.filter(payload__application_id=str(top.pk)).exists()


def test_return_for_changes_goes_back_to_draft(world: World) -> None:
    w = world
    s = ready(w)
    with pytest.raises(DomainError):
        services.return_for_changes(w.m(w.team.hr_manager), w.team.hr_manager, s.pk, reason="")
    back = services.return_for_changes(
        w.m(w.team.hr_manager), w.team.hr_manager, s.pk, reason="Please review the hold"
    )
    assert back.status == "draft" and back.return_reason == "Please review the hold"
    assert not Application.objects.for_org(w.team.org).filter(status="shortlisted").exists()


def test_undo_within_the_window_reverses_and_cancels_notifications(world: World) -> None:
    w = world
    s = ready(w)
    services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    undone = services.undo(
        w.m(w.team.hr_manager), w.team.hr_manager, s.pk, reason="Wrong vacancy version"
    )
    assert undone.status == "undone"  # EC-REV-04
    statuses = set(Application.objects.for_org(w.team.org).values_list("status", flat=True))
    assert statuses == {"under_review"}
    notes = Notification.objects.filter(key__in=["shortlisted", "not_selected"])
    assert notes.count() == 6 and set(notes.values_list("status", flat=True)) == {"suppressed"}
    reversals = ApplicationStatusEvent.objects.filter(metadata__via="shortlist_undo")
    assert reversals.count() == 4 and all(e.actor_type == "human" for e in reversals)
    assert propose(w).status == "draft"  # a new proposal is possible again


def test_undo_after_the_window_is_refused(world: World, monkeypatch: Any) -> None:
    w = world
    s = ready(w)
    services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    later = now() + timedelta(hours=2)
    monkeypatch.setattr(services, "now", lambda: later)
    with pytest.raises(ConflictError) as exc:
        services.undo(w.m(w.team.hr_manager), w.team.hr_manager, s.pk, reason="Too late now")
    assert exc.value.code == "conflict.undo_window_closed"


def test_undo_transition_is_not_offered_on_the_board(world: World) -> None:
    from apps.applications import state_machine as sm

    assert "under_review" not in sm.allowed_targets("shortlisted", sm.STAFF)
    w = world
    top = w.apps["top"]
    transition(top, Status.SHORTLISTED, actor=w.team.hr_manager, reason="Strong evidence")
    with pytest.raises(ApplicationTransitionError):
        transition(top, Status.UNDER_REVIEW, actor=w.team.hr_manager, reason="Change of mind")


def test_no_consequential_transition_without_a_human(world: World) -> None:
    w = world
    s = ready(w)
    services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk)
    consequential = ApplicationStatusEvent.objects.filter(
        to_status__in=["shortlisted", "not_selected", "offer", "hired"]
    )
    assert consequential.exists()
    assert not consequential.filter(actor__isnull=True).exists()
    assert not consequential.exclude(actor_type="human").exists()
    assert (
        ShortlistEntry.objects.filter(applied_at__isnull=False, decided_by__isnull=True).count()
        == 0
    )


def test_cross_tenant_shortlist_is_invisible(world: World) -> None:
    from apps.core.exceptions import NotFoundError

    w = world
    s = propose(w)
    other = make_org_with_team()
    member = Membership.objects.get(user=other.hr_manager, organisation=other.org)
    with pytest.raises(NotFoundError):
        services.approve(member, other.hr_manager, s.pk)


def test_override_analytics_count_only_approved_decisions(world: World) -> None:
    from apps.shortlisting.selectors import override_stats

    w = world
    s = propose(w, 2)
    decide(
        w,
        s,
        item(w.apps["top"], "not_selected", "essential_not_met"),  # against "recommended"
        item(w.apps["lower"], "shortlist", "evidence_review_differs"),  # against "lower match"
        item(w.apps["second"], "shortlist"),
    )
    assert override_stats(w.team.org.pk)["decisions"] == 0  # drafts do not count
    services.submit(w.m(w.team.recruiter), w.team.recruiter, s.pk)
    services.approve(w.m(w.team.hr_manager), w.team.hr_manager, s.pk, leave_undecided=True)
    stats = override_stats(w.team.org.pk, job_id=w.job.pk)
    assert stats["decisions"] == 3 and stats["overrides"] == 2
    assert stats["override_rate"] == round(2 / 3, 4)
    assert stats["shortlisted_against_ai"] == 1 and stats["not_selected_against_ai"] == 1
    assert stats["override_reasons"] == {"essential_not_met": 1, "evidence_review_differs": 1}
    assert stats["by_band"]["recommended_for_review"] == {"not_selected": 1, "shortlist": 1}
    assert override_stats(make_org_with_team().org.pk)["decisions"] == 0  # tenant scoped
