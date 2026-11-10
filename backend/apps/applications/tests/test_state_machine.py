"""Exhaustive state machine tests (P04-T06, SRS §3.3, principle 1)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from apps.applications import state_machine as sm
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.services import (
    ApplicationTransitionError,
    next_reference,
    transition,
)
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.core.models import OutboxEvent
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db

ALL = list(Status.values)

# The SRS §3.3 table, written out independently of the implementation.
EXPECTED = {
    "draft": {"submitted", "abandoned"},
    "submitted": {"processing", "withdrawn"},
    "processing": {"under_review", "needs_information", "processing_error", "withdrawn"},
    "processing_error": {"processing", "under_review", "withdrawn"},
    "needs_information": {"processing", "under_review", "withdrawn"},
    "under_review": {"shortlisted", "on_hold", "not_selected", "needs_information", "withdrawn"},
    "on_hold": {"under_review", "shortlisted", "not_selected", "withdrawn"},
    "shortlisted": {"interview", "not_selected", "withdrawn"},
    "interview": {"offer", "not_selected", "withdrawn"},
    "offer": {"hired", "offer_declined", "withdrawn"},
    "hired": {"under_review"},
    "not_selected": {"under_review"},
    "withdrawn": {"under_review"},
    "offer_declined": {"under_review"},
    "abandoned": {"under_review", "draft"},  # draft: EC-JOB-09 reactivation (system only)
}


@pytest.mark.parametrize(("frm", "to"), list(itertools.product(ALL, ALL)))
def test_transition_table_matches_srs(frm: str, to: str) -> None:
    assert (sm.rule_for(frm, to) is not None) == (to in EXPECTED[frm]), (frm, to)


def test_consequential_outcomes_and_reopens_are_human_with_reason() -> None:
    for (frm, to), rule in sm.TRANSITIONS.items():
        if to in sm.HUMAN_ONLY_TARGETS or sm.is_reopen(frm, to):
            assert rule.actors == {sm.STAFF} and rule.reason_required, (frm, to)
        if sm.SYSTEM in rule.actors:
            assert to not in sm.HUMAN_ONLY_TARGETS


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    return team, job


def at(status: str, job: Any) -> Application:
    app = make_application(job)
    if status != Status.DRAFT:
        Application.objects.for_org(job.organisation).filter(pk=app.pk).update(
            status=status, reference=app.reference or next_reference(job.organisation)
        )
        app.refresh_from_db()
    return app


def actor_for(kind: str, team: Any, app: Application) -> tuple[Any, str]:
    if kind == sm.SYSTEM:
        return None, "system"
    if kind == sm.CANDIDATE:
        return app.candidate_user, "human"
    return team.hr_manager, "human"


@pytest.mark.parametrize(
    ("frm", "to", "kind"),
    [
        (frm, to, kind)
        for (frm, to), rule in sorted(sm.TRANSITIONS.items())
        for kind in (sm.CANDIDATE, sm.STAFF, sm.SYSTEM)
    ],
)
def test_every_transition_for_every_actor_kind(world: Any, frm: str, to: str, kind: str) -> None:
    team, job = world
    app = at(frm, job)
    actor, actor_type = actor_for(kind, team, app)
    rule = sm.rule_for(frm, to)
    assert rule is not None
    if (frm, to) == (Status.DRAFT, Status.SUBMITTED):  # the submit service assigns it first
        app.reference = next_reference(job.organisation)
        app.save(update_fields=["reference"])
    if kind not in rule.actors:
        with pytest.raises((ApplicationTransitionError, PermissionDeniedError)):
            transition(app, to, actor=actor, actor_type=actor_type, reason="Recorded reason")
        assert Application.objects.for_org(job.organisation).get(pk=app.pk).status == frm
        return
    done = transition(app, to, actor=actor, actor_type=actor_type, reason="Recorded reason")
    assert done.status == to
    event = ApplicationStatusEvent.objects.for_org(job.organisation).get(application=app)
    assert (event.from_status, event.to_status) == (frm, to)
    assert event.actor_type == ("system" if kind == sm.SYSTEM else "human")
    assert (event.actor_id is None) == (kind == sm.SYSTEM)


@pytest.mark.parametrize(("frm", "to"), [(f, t) for f in ALL for t in ALL if t not in EXPECTED[f]])
def test_disallowed_pairs_are_rejected(world: Any, frm: str, to: str) -> None:
    team, job = world
    app = at(frm, job)
    with pytest.raises(ApplicationTransitionError) as exc:
        transition(app, to, actor=team.hr_manager, reason="Recorded reason")
    assert exc.value.status_code == 409


def test_decision_requires_reason_and_writes_audit_and_outbox(world: Any) -> None:
    team, job = world
    app = at(Status.UNDER_REVIEW, job)
    with pytest.raises(DomainError) as exc:
        transition(app, Status.SHORTLISTED, actor=team.recruiter, reason="")
    assert exc.value.code == "validation_error"
    transition(app, Status.SHORTLISTED, actor=team.recruiter, reason="Strong Django evidence")
    audit = AuditEvent.objects.get(action="application.status_changed", target_id=str(app.pk))
    assert audit.reason == "Strong Django evidence" and audit.actor == team.recruiter
    assert OutboxEvent.objects.filter(
        event_type="application.status_changed", aggregate_id=str(app.pk)
    ).exists()


@pytest.mark.parametrize("role", ["hiring_manager", "panelist", "auditor"])
def test_staff_without_transition_permission_cannot_act(world: Any, role: str) -> None:
    team, job = world
    app = at(Status.UNDER_REVIEW, job)
    with pytest.raises(PermissionDeniedError):
        transition(app, Status.ON_HOLD, actor=getattr(team, role))


def test_other_organisations_staff_cannot_act(world: Any) -> None:
    _, job = world
    other = make_org_with_team()
    app = at(Status.UNDER_REVIEW, job)
    with pytest.raises(PermissionDeniedError):
        transition(app, Status.ON_HOLD, actor=other.hr_manager)


def test_withdraw_frees_slot_and_reopen_needs_hr_manager(world: Any) -> None:
    team, job = world
    app = at(Status.UNDER_REVIEW, job)
    assert app.active_key is not None
    app = transition(app, Status.WITHDRAWN, actor=app.candidate_user, reason="Took another job")
    assert app.active_key is None and app.withdrawn_at is not None
    assert app.withdraw_reason == "Took another job"
    with pytest.raises(PermissionDeniedError):
        transition(app, Status.UNDER_REVIEW, actor=team.recruiter, reason="Candidate asked")
    app = transition(app, Status.UNDER_REVIEW, actor=team.hr_manager, reason="Candidate asked")
    assert app.status == Status.UNDER_REVIEW and app.active_key is not None


def test_reopen_conflicts_with_newer_active_application(world: Any) -> None:
    team, job = world
    old = at(Status.UNDER_REVIEW, job)
    old = transition(old, Status.WITHDRAWN, actor=old.candidate_user)
    make_application(job, old.candidate_user)  # re-applied
    with pytest.raises(ApplicationTransitionError):
        transition(old, Status.UNDER_REVIEW, actor=team.hr_manager, reason="Mistaken withdrawal")


def test_anonymous_human_actor_is_refused(world: Any) -> None:
    _, job = world
    app = at(Status.SUBMITTED, job)
    with pytest.raises(ApplicationTransitionError):
        transition(app, Status.WITHDRAWN, actor=None, actor_type="human")
