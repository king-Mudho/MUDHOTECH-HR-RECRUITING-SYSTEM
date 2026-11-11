"""HR applicant tracking (P05-T07): transitions with reason codes, notes, tags, assignment."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import ApplicationNote, ApplicationStatusEvent, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.time import now
from apps.jobs.models import JobAssignment
from apps.notifications import delivery
from apps.notifications.models import Notification, NotificationStatus
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    for user, role in ((team.recruiter, "recruiter"), (team.hiring_manager, "hiring_manager")):
        JobAssignment.objects.get_or_create(
            organisation=team.org,
            job=job,
            membership=Membership.objects.for_org(team.org).get(user=user),
            defaults={"role_on_job": role},
        )
    app = make_application(job, UserFactory(verified=True), status=Status.UNDER_REVIEW)
    return team, app


def hr(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def move(client: APIClient, app: Any, **body: Any) -> Any:
    return client.post(f"/api/v1/hr/applications/{app.pk}/transition/", body, format="json")


def test_hold_and_resume_with_reason_codes_are_audited(world: Any) -> None:
    team, app = world
    c = hr(team.recruiter, team.org)
    detail = c.get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert "on_hold" in detail["allowed_transitions"]
    assert "shortlisted" not in detail["allowed_transitions"]  # recruiter cannot decide
    no_reason = move(c, app, to_status="on_hold")
    assert no_reason.status_code == 400 and "reason_code" in no_reason.json()["error"]["details"]
    held = move(c, app, to_status="on_hold", reason_code="awaiting_budget")
    assert held.status_code == 200 and held.json()["status"] == "on_hold"
    event = ApplicationStatusEvent.objects.for_org(team.org).filter(application=app).last()
    assert event is not None
    assert (event.reason_code, event.reason_text) == (
        "awaiting_budget",
        "Waiting for budget or approval",
    )
    assert event.actor_id == team.recruiter.pk and event.actor_type == "human"
    assert move(c, app, to_status="under_review").status_code == 200
    assert (
        AuditEvent.objects.filter(
            action="application.status_changed", target_id=str(app.pk)
        ).count()
        == 2
    )


def test_invalid_moves_are_rejected_with_allowed_targets(world: Any) -> None:
    """Exit criterion: invalid transitions are rejected (the kanban relies on this)."""
    team, app = world
    res = move(hr(team.hr_manager, team.org), app, to_status="hired")
    assert res.status_code == 409
    error = res.json()["error"]
    assert (
        error["code"] == "conflict.invalid_transition"
        and "shortlisted" in error["details"]["allowed"]
    )
    assert move(hr(team.recruiter, team.org), app, to_status="processing").status_code == 409
    stale = move(
        hr(team.recruiter, team.org),
        app,
        to_status="on_hold",
        reason_code="other",
        reason_text="Budget meeting first",
        lock_version=app.lock_version - 1,
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "conflict.stale_version"
    other_needs_text = move(
        hr(team.recruiter, team.org), app, to_status="on_hold", reason_code="other"
    )
    assert other_needs_text.status_code == 400


def test_outcomes_need_hr_manager_and_candidate_hears_after_delay(world: Any) -> None:
    team, app = world
    denied = move(
        hr(team.recruiter, team.org), app, to_status="not_selected", reason_code="essential_not_met"
    )
    assert denied.status_code == 403
    res = move(
        hr(team.hr_manager, team.org),
        app,
        to_status="not_selected",
        reason_code="essential_not_met",
    )
    assert res.status_code == 200, res.content
    rows = Notification.objects.filter(recipient_user=app.candidate_user, key="not_selected")
    assert {n.status for n in rows} == {NotificationStatus.QUEUED}  # nothing visible yet
    email = rows.get(channel="email")
    assert email.scheduled_for and email.scheduled_for > now() + timedelta(minutes=14)
    candidate = APIClient()
    candidate.force_login(app.candidate_user)
    assert candidate.get("/api/v1/notifications/unread-count/").json() == {"count": 0}
    assert delivery.deliver(email.pk) == "deferred"
    with mock.patch.object(
        delivery, "now", return_value=email.scheduled_for + timedelta(minutes=1)
    ):
        delivery.due_ids()
    assert candidate.get("/api/v1/notifications/unread-count/").json() == {"count": 1}
    # reopening needs an HR manager and an override reason
    assert move(
        hr(team.recruiter, team.org), app, to_status="under_review", reason_code="decided_in_error"
    ).status_code in (403, 409)
    reopen = move(
        hr(team.hr_manager, team.org), app, to_status="under_review", reason_code="decided_in_error"
    )
    assert reopen.status_code == 200 and reopen.json()["status"] == "under_review"


def test_notes_mentions_and_privacy(world: Any) -> None:
    team, app = world
    c = hr(team.recruiter, team.org)
    url = f"/api/v1/hr/applications/{app.pk}/notes/"
    note = c.post(
        url,
        {
            "body": "<b>Strong</b> Django work - @manager please look",
            "mentions": [str(team.hiring_manager.pk)],
        },
        format="json",
    )
    assert (
        note.status_code == 201
        and note.json()["body"] == "Strong Django work - @manager please look"
    )
    mention = Notification.objects.get(recipient_user=team.hiring_manager, key="note_mention")
    assert mention.channel == "inapp" and mention.status == NotificationStatus.DELIVERED
    private = c.post(url, {"body": "My own reminder", "visibility": "private"}, format="json")
    assert private.status_code == 201
    assert [n["body"] for n in c.get(url).json()] == ["My own reminder", note.json()["body"]]
    assert len(hr(team.hr_manager, team.org).get(url).json()) == 1  # private stays private
    bad = c.post(url, {"body": "x", "mentions": [str(team.panelist.pk)]}, format="json")
    assert bad.status_code == 400  # panelists cannot see applications
    private_mention = c.post(
        url,
        {"body": "x", "visibility": "private", "mentions": [str(team.hr_manager.pk)]},
        format="json",
    )
    assert private_mention.status_code == 400
    assert not AuditEvent.objects.filter(after__icontains="Django").exists()  # bodies not audited
    candidate = APIClient()
    candidate.force_login(app.candidate_user)
    assert candidate.get(url).status_code in (403, 404)
    assert ApplicationNote.objects.for_org(team.org).count() == 2


def test_tags_and_assignment(world: Any) -> None:
    team, app = world
    c = hr(team.recruiter, team.org)
    res = c.put(
        f"/api/v1/hr/applications/{app.pk}/tags/",
        {"tags": ["Senior Dev", "senior-dev", " remote!! ", ""]},
        format="json",
    )
    assert res.status_code == 200 and res.json()["tags"] == ["senior-dev", "remote"]
    too_many = c.put(
        f"/api/v1/hr/applications/{app.pk}/tags/",
        {"tags": [f"t{i}" for i in range(11)]},
        format="json",
    )
    assert too_many.status_code == 400
    assign_url = f"/api/v1/hr/applications/{app.pk}/assign/"
    assert c.post(assign_url, {"user_id": str(team.recruiter.pk)}, format="json").status_code == 403
    m = hr(team.hr_manager, team.org)
    ok = m.post(assign_url, {"user_id": str(team.recruiter.pk)}, format="json")
    assert ok.status_code == 200 and ok.json()["assigned_recruiter"] == str(team.recruiter.pk)
    outsider = make_org_with_team().recruiter
    assert m.post(assign_url, {"user_id": str(outsider.pk)}, format="json").status_code == 400
    assert m.post(assign_url, {"user_id": str(team.panelist.pk)}, format="json").status_code == 400
    assert m.post(assign_url, {"user_id": None}, format="json").json()["assigned_recruiter"] is None
    assert AuditEvent.objects.filter(action="application.assigned").count() == 2


def test_decision_reasons_list(world: Any) -> None:
    team, _ = world
    rows = (
        hr(team.recruiter, team.org)
        .get("/api/v1/hr/decision-reasons/?applies_to=not_selected")
        .json()
    )
    codes = [r["code"] for r in rows]
    assert "essential_not_met" in codes and "other" in codes
    assert all(r["applies_to"] == "not_selected" for r in rows)
    assert not any("age" in r["label"].lower().split() for r in rows)
