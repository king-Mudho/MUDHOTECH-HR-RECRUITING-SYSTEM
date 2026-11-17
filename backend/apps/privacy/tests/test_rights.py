"""Data-subject rights requests (P09-T02)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import rights
from apps.privacy.models import ConsentRecord, RightsRequest

pytestmark = pytest.mark.django_db
PASSWORD = "lantern-orchard-velvet-27"


def client(user: Any, org: Any = None) -> APIClient:
    c = APIClient()
    c.force_login(user)
    if org is not None:
        c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def world() -> Any:
    a, b = make_org_with_team(), make_org_with_team()
    OrganisationPolicy.objects.filter(organisation=a.org).update(rights_request_sla_days=14)
    candidate = UserFactory(verified=True)
    candidate.set_password(PASSWORD)
    candidate.save()
    make_application(published_job(organisation=a.org), candidate, status=Status.UNDER_REVIEW)
    make_application(published_job(organisation=b.org), candidate, status=Status.SUBMITTED)
    return a, b, candidate


def token_from_email(candidate: Any) -> str:
    n = Notification.objects.filter(recipient_user=candidate, key="rights_request_confirm").latest(
        "created_at"
    )
    match = re.search(r"token=([\w-]+)", n.payload["confirm_url"])
    assert match
    return match.group(1)


def test_request_needs_password_then_email_confirmation(world: Any) -> None:
    a, b, candidate = world
    c = client(candidate)
    body = {"type": "export", "scope": "all", "password": "wrong"}
    assert c.post("/api/v1/privacy/requests/", body, format="json").status_code == 403
    res = c.post("/api/v1/privacy/requests/", {**body, "password": PASSWORD}, format="json")
    assert res.status_code == 201
    rows = res.json()
    assert {r["organisation_id"] for r in rows} == {str(a.org.pk), str(b.org.pk), None}
    assert {r["status"] for r in rows} == {"verifying"}
    # nobody is told before the requester confirms
    assert not Notification.objects.filter(key="rights_request_received").exists()
    token = token_from_email(candidate)
    confirmed = c.post("/api/v1/privacy/requests/confirm/", {"token": token}, format="json")
    assert confirmed.status_code == 200
    assert {r["status"] for r in confirmed.json()} == {"received"}
    due = RightsRequest.objects.get(organisation=a.org).due_at
    assert timedelta(days=13) < due - now() <= timedelta(days=14)  # org SLA
    assert Notification.objects.filter(
        recipient_user=a.admin, key="rights_request_received"
    ).exists()
    assert Notification.objects.filter(
        recipient_user=b.admin, key="rights_request_received"
    ).exists()
    # a used token cannot be replayed
    again = c.post("/api/v1/privacy/requests/confirm/", {"token": token}, format="json")
    assert again.status_code == 404
    assert AuditEvent.objects.filter(action="privacy.rights_request_confirmed").count() == 3


def test_scope_validation(world: Any) -> None:
    a, _, candidate = world
    other = make_org_with_team()
    c = client(candidate)
    bad = c.post(
        "/api/v1/privacy/requests/",
        {
            "type": "access",
            "scope": "organisation",
            "organisation_id": str(other.org.pk),
            "password": PASSWORD,
        },
        format="json",
    )
    assert bad.status_code == 400  # only employers the person applied to
    no_text = c.post(
        "/api/v1/privacy/requests/",
        {
            "type": "correction",
            "scope": "organisation",
            "organisation_id": str(a.org.pk),
            "password": PASSWORD,
        },
        format="json",
    )
    assert no_text.status_code == 400
    employers = {e["id"] for e in c.get("/api/v1/privacy/employers/").json()}
    assert str(a.org.pk) in employers and str(other.org.pk) not in employers


def test_staff_handle_requests_and_requester_is_told(world: Any) -> None:
    a, b, candidate = world
    (row,) = rights.create(
        candidate,
        type="correction",
        password=PASSWORD,
        scope="organisation",
        organisation_id=a.org.pk,
        details="My degree year is 2019, not 2018.",
    )
    rights.confirm(candidate, token_from_email(candidate))
    admin = client(a.admin, a.org)
    listed = admin.get("/api/v1/hr/privacy/requests/").json()
    assert [r["reference"] for r in listed] == [row.reference] and listed[0]["requester"]
    url = f"/api/v1/hr/privacy/requests/{row.pk}/action/"
    assert admin.post(url, {"action": "decline"}, format="json").status_code == 400  # reason needed
    assert admin.post(url, {"action": "start"}, format="json").status_code == 200
    res = admin.post(
        url,
        {"action": "decline", "resolution": "The certificate you uploaded shows 2018."},
        format="json",
    )
    assert res.status_code == 200 and res.json()["status"] == "declined"
    update = Notification.objects.filter(recipient_user=candidate, key="rights_request_update")
    assert update.exists()
    # EC-PRV-04: the requester may add a statement to the declined correction
    c = client(candidate)
    stmt = c.post(
        f"/api/v1/privacy/requests/{row.pk}/statement/",
        {"statement": "I graduated in 2019; the certificate was reissued."},
        format="json",
    )
    assert stmt.status_code == 200 and stmt.json()["statement"].startswith("I graduated")
    # other organisations cannot see or act on it; recruiters cannot either
    assert client(b.admin, b.org).get("/api/v1/hr/privacy/requests/").json() == []
    assert client(b.admin, b.org).post(url, {"action": "start"}, format="json").status_code == 404
    assert client(a.recruiter, a.org).get("/api/v1/hr/privacy/requests/").status_code == 403


def test_platform_requests_go_to_platform_admins(world: Any) -> None:
    _, _, candidate = world
    platform_admin = UserFactory(verified=True, platform_role=PlatformRole.PLATFORM_ADMIN)
    (row,) = rights.create(candidate, type="deletion", password=PASSWORD, scope="platform")
    rights.confirm(candidate, token_from_email(candidate))
    assert Notification.objects.filter(
        recipient_user=platform_admin, key="rights_request_received"
    ).exists()
    pc = client(platform_admin)
    assert [r["reference"] for r in pc.get("/api/v1/platform/privacy/requests/").json()] == [
        row.reference
    ]
    res = pc.post(
        f"/api/v1/platform/privacy/requests/{row.pk}/action/", {"action": "start"}, format="json"
    )
    assert res.status_code == 200
    assert client(candidate).get("/api/v1/platform/privacy/requests/").status_code == 403


def test_reminders_before_due_date(world: Any) -> None:
    a, _, candidate = world
    (row,) = rights.create(
        candidate, type="access", password=PASSWORD, scope="organisation", organisation_id=a.org.pk
    )
    rights.confirm(candidate, token_from_email(candidate))
    assert rights.send_reminders() == 0
    RightsRequest.objects.filter(pk=row.pk).update(due_at=now() + timedelta(days=3))
    assert rights.send_reminders() == 1
    assert rights.send_reminders() == 0  # once
    assert Notification.objects.filter(recipient_user=a.admin, key="rights_request_due").exists()


def test_consents_listed_and_withdrawn(world: Any) -> None:
    a, _, candidate = world
    consent = ConsentRecord.objects.create(
        user=candidate,
        organisation=a.org,
        purpose="ai_assisted_screening",
        notice_version="v1",
        granted=True,
        granted_at=now(),
    )
    c = client(candidate)
    listed = c.get("/api/v1/privacy/consents/").json()
    assert listed[0]["purpose"] == "ai_assisted_screening" and listed[0]["withdrawn_at"] is None
    res = c.post(f"/api/v1/privacy/consents/{consent.pk}/withdraw/")
    assert res.status_code == 200 and res.json()["withdrawn_at"]
    assert c.post(f"/api/v1/privacy/consents/{consent.pk}/withdraw/").status_code == 404
    assert (
        client(UserFactory()).post(f"/api/v1/privacy/consents/{consent.pk}/withdraw/").status_code
        == 404
    )
    assert AuditEvent.objects.filter(action="privacy.consent_withdrawn").exists()
