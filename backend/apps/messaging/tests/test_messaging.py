"""Clarifications and message threads (P05-T06, EC-NOT-07/08)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.documents import services as documents
from apps.documents.models import Document, ScanStatus
from apps.jobs.models import JobAssignment
from apps.messaging import services
from apps.messaging.models import ClarificationRequest, ClarificationStatus, Message
from apps.notifications.models import Notification
from apps.notifications.testing import emails_for
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    recruiter = Membership.objects.for_org(team.org).get(user=team.recruiter)
    JobAssignment.objects.get_or_create(
        organisation=team.org, job=job, membership=recruiter, defaults={"role_on_job": "recruiter"}
    )
    app = make_application(job, UserFactory(first_name="Tendai"), status=Status.UNDER_REVIEW)
    app.candidate_profile_snapshot = {"first_name": "Tendai", "last_name": "Moyo"}
    app.save(update_fields=["candidate_profile_snapshot"])
    return team, app


def hr(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def me(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def ask(team: Any, app: Application, **over: Any) -> Any:
    body = {
        "questions": [
            {"prompt": "Which year did you finish your BSc?"},
            {"prompt": "Please upload the certificate.", "allow_upload": True},
        ],
        "due_at": (now() + timedelta(days=3)).isoformat(),
        "message": "Thanks for applying - two quick questions.",
        **over,
    }
    return hr(team.recruiter, team.org).post(
        f"/api/v1/hr/applications/{app.pk}/clarifications/", body, format="json"
    )


def doc(user: Any, purpose: str = "supporting", scan: str = ScanStatus.CLEAN) -> Document:
    return Document.objects.create(
        owner_user=user,
        purpose=purpose,
        original_filename="certificate.pdf",
        size_bytes=10,
        storage_key=f"k/{purpose}/{user.pk}",
        scan_status=scan,
    )


def test_clarification_round_trip(world: Any, django_capture_on_commit_callbacks: Any) -> None:
    """Exit criterion: HR asks -> candidate notified -> answers -> HR notified, application back to
    review; every step audited."""
    team, app = world
    res = ask(team, app)
    assert res.status_code == 201, res.content
    clarification = res.json()
    app.refresh_from_db()
    assert app.status == Status.NEEDS_INFORMATION
    [mail] = emails_for(app.candidate_user, "clarification_requested")
    assert "Which year" not in mail  # the question itself stays in the portal
    assert "#clarifications" in mail
    candidate = me(app.candidate_user)
    [seen] = candidate.get(f"/api/v1/applications/{app.pk}/clarifications/").json()
    q1, q2 = seen["questions"]
    assert q2["allow_upload"] is True
    missing = candidate.post(
        f"/api/v1/applications/{app.pk}/clarifications/{clarification['id']}/answer/",
        {"answers": [{"id": q1["id"], "text": "2021"}]},
        format="json",
    )
    assert missing.status_code == 400 and q2["id"] in missing.json()["error"]["details"]
    cert = doc(app.candidate_user)
    with django_capture_on_commit_callbacks(execute=True):
        answered = candidate.post(
            f"/api/v1/applications/{app.pk}/clarifications/{clarification['id']}/answer/",
            {
                "answers": [
                    {"id": q1["id"], "text": "<b>2021</b>"},
                    {"id": q2["id"], "text": "", "document_id": str(cert.pk)},
                ]
            },
            format="json",
        )
    assert answered.status_code == 200, answered.content
    assert answered.json()["answers"][0]["text"] == "2021"  # stored as plain text
    req = ClarificationRequest.objects.unscoped().get(pk=clarification["id"])
    assert req.status == ClarificationStatus.ANSWERED and req.answered_at
    assert OutboxEvent.objects.filter(event_type="clarification.answered").exists()
    [staff_mail] = emails_for(team.recruiter, "clarification_answered")
    assert "Tendai Moyo" in staff_mail and app.reference in staff_mail
    events = list(
        ApplicationStatusEvent.objects.for_org(team.org)
        .filter(application=app)
        .values_list("to_status", flat=True)
    )
    assert events[-3:] == ["needs_information", "processing", "under_review"]
    assert {"clarification.requested", "clarification.answered"} <= set(
        AuditEvent.objects.values_list("action", flat=True)
    )
    assert documents.can_access(team.recruiter, cert)  # HR may open the uploaded answer
    again = candidate.post(
        f"/api/v1/applications/{app.pk}/clarifications/{clarification['id']}/answer/",
        {"answers": [{"id": q1["id"], "text": "2022"}]},
        format="json",
    )
    assert again.status_code == 409


def test_clarification_validation_and_rules(world: Any) -> None:
    team, app = world
    assert ask(team, app, questions=[]).status_code == 400
    assert ask(team, app, questions=[{"prompt": f"Q{i}"} for i in range(6)]).status_code == 400
    assert ask(team, app, due_at=(now() + timedelta(minutes=5)).isoformat()).status_code == 400
    assert ask(team, app, due_at=(now() + timedelta(days=40)).isoformat()).status_code == 400
    assert ask(team, app).status_code == 201
    second = ask(team, app)
    assert second.status_code == 409  # one open request at a time
    shortlisted = make_application(app.job, UserFactory(), status=Status.SHORTLISTED)
    assert ask(team, shortlisted).status_code == 409
    assert (
        hr(team.hiring_manager, team.org)
        .post(f"/api/v1/hr/applications/{app.pk}/clarifications/", {}, format="json")
        .status_code
        == 403
    )
    templates = hr(team.recruiter, team.org).get("/api/v1/hr/clarification-templates/").json()
    assert len(templates) >= 5 and all(t["prompt"] for t in templates)


def test_cancel_returns_application_to_review(world: Any) -> None:
    team, app = world
    cid = ask(team, app).json()["id"]
    res = hr(team.recruiter, team.org).post(
        f"/api/v1/hr/applications/{app.pk}/clarifications/{cid}/cancel/"
    )
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    app.refresh_from_db()
    assert app.status == Status.UNDER_REVIEW


def test_expiry_and_reminder(world: Any) -> None:
    """EC-NOT-07: overdue -> expired, recruiter told and decides; the candidate can still write."""
    team, app = world
    cid = ask(team, app, due_at=(now() + timedelta(hours=20)).isoformat()).json()["id"]
    assert services.process_due() == {"reminded": 1, "expired": 0}
    assert services.process_due() == {"reminded": 0, "expired": 0}  # reminded once
    assert len(emails_for(app.candidate_user, "clarification_reminder")) == 1
    assert services.process_due(now() + timedelta(days=1)) == {"reminded": 0, "expired": 1}
    req = ClarificationRequest.objects.unscoped().get(pk=cid)
    assert req.status == ClarificationStatus.EXPIRED
    assert len(emails_for(team.recruiter, "clarification_expired")) == 1
    app.refresh_from_db()
    assert app.status == Status.NEEDS_INFORMATION  # no automatic decision
    late = me(app.candidate_user).post(
        f"/api/v1/applications/{app.pk}/clarifications/{cid}/answer/",
        {"answers": []},
        format="json",
    )
    assert late.status_code == 409 and "message" in late.json()["error"]["message"]
    msg = me(app.candidate_user).post(
        f"/api/v1/applications/{app.pk}/messages/", {"body": "Sorry, I was away."}, format="json"
    )
    assert msg.status_code == 201


def test_message_thread_both_ways(world: Any) -> None:
    team, app = world
    candidate = me(app.candidate_user)
    staff = hr(team.recruiter, team.org)
    first = candidate.post(
        f"/api/v1/applications/{app.pk}/messages/",
        {"body": "<script>x()</script>Is the role remote?"},
        format="json",
    )
    assert first.status_code == 201 and first.json()["body"] == "Is the role remote?"
    assert len(emails_for(team.recruiter, "new_message")) == 1
    rows = staff.get(f"/api/v1/hr/applications/{app.pk}/messages/").json()
    assert [r["sender_role"] for r in rows] == ["candidate"] and rows[0]["mine"] is False
    assert Message.objects.unscoped().get().read_at is not None  # staff opened it
    reply = staff.post(
        f"/api/v1/hr/applications/{app.pk}/messages/", {"body": "Hybrid, 3 days."}, format="json"
    )
    assert reply.status_code == 201
    [mail] = emails_for(app.candidate_user, "new_message")
    assert "Hybrid" not in mail  # message bodies never travel by email
    seen = candidate.get(f"/api/v1/applications/{app.pk}/messages/").json()
    assert [r["sender_name"] for r in seen][1] == team.org.name  # staff names hidden
    assert not AuditEvent.objects.filter(after__icontains="remote").exists()
    assert Notification.objects.filter(key="new_message", channel="inapp").count() == 2


def test_attachments_must_be_own_clean_message_files(world: Any) -> None:
    """EC-NOT-08: attachments go through the same upload scan; unsafe files are refused."""
    team, app = world
    candidate = me(app.candidate_user)
    url = f"/api/v1/applications/{app.pk}/messages/"
    good = doc(app.candidate_user, "message_attachment")
    infected = doc(app.candidate_user, "message_attachment", ScanStatus.INFECTED)
    someone_elses = doc(UserFactory(), "message_attachment")
    for bad in (infected, someone_elses):
        res = candidate.post(
            url, {"body": "See file", "attachment_ids": [str(bad.pk)]}, format="json"
        )
        assert res.status_code == 400
    ok = candidate.post(url, {"body": "See file", "attachment_ids": [str(good.pk)]}, format="json")
    assert ok.status_code == 201 and ok.json()["attachment_document_ids"] == [str(good.pk)]
    assert documents.can_access(team.recruiter, good)
    assert not documents.can_access(make_org_with_team().admin, good)
    assert not documents.can_access(UserFactory(), good)


def test_isolation_and_state_rules(world: Any) -> None:
    team, app = world
    stranger = me(UserFactory())
    assert stranger.get(f"/api/v1/applications/{app.pk}/messages/").status_code == 404
    assert stranger.get(f"/api/v1/applications/{app.pk}/clarifications/").status_code == 404
    other = make_org_with_team()
    foreign = hr(other.admin, other.org)
    assert foreign.get(f"/api/v1/hr/applications/{app.pk}/messages/").status_code == 404
    assert ask(other, app).status_code == 404
    draft = make_application(app.job, UserFactory())
    res = me(draft.candidate_user).post(
        f"/api/v1/applications/{draft.pk}/messages/", {"body": "hi"}, format="json"
    )
    assert res.status_code == 409
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.WITHDRAWN)
    res = hr(team.recruiter, team.org).post(
        f"/api/v1/hr/applications/{app.pk}/messages/", {"body": "hello"}, format="json"
    )
    assert res.status_code == 409
