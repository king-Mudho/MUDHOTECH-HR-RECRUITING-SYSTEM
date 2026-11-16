"""Blind review mode (P08-T04, EC-REV-06): server-side redaction and audited reveal."""

from __future__ import annotations

import json
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.blind import alias
from apps.applications.models import (
    Application,
    ApplicationDocument,
    IdentityReveal,
    Status,
)
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.documents.models import Document, ScanStatus
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db
SNAPSHOT = {
    "first_name": "Rudo",
    "last_name": "Moyo",
    "email": "rudo.moyo@example.test",
    "phone": "+263770001111",
    "city": "Harare",
}


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org, title="Software Developer")
    app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    Application.objects.unscoped().filter(pk=app.pk).update(candidate_profile_snapshot=SNAPSHOT)
    doc = Document.objects.create(
        owner_user=app.candidate_user,
        purpose="cv",
        original_filename="Rudo_Moyo_CV.pdf",
        size_bytes=10,
        storage_key="k",
        scan_status=ScanStatus.CLEAN,
    )
    ApplicationDocument.objects.create(
        organisation=team.org, application=app, document=doc, role="cv", required_doc_key="cv"
    )
    app.refresh_from_db()
    return team, job, app, doc


def leaks(payload: Any) -> list[str]:
    text = json.dumps(payload)
    return [v for v in ("Rudo", "Moyo", "rudo.moyo@", "+26377000", "Rudo_Moyo_CV") if v in text]


def test_blind_mode_is_on_by_default_and_redacts_on_the_server(world: Any) -> None:
    team, job, app, _ = world
    c = staff(team.hr_manager, team.org)
    listed = c.get(f"/api/v1/hr/jobs/{job.pk}/applications/").json()
    row = listed["results"][0]
    assert row["candidate_name"] == alias(app.pk) and row["identity_hidden"] is True
    assert row["candidate_email"] == ""
    detail = c.get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert detail["candidate"] == {"alias": alias(app.pk)}
    assert detail["documents"][0]["filename"] == "Document 1 (cv)"
    assert detail["documents"][0]["available"] is False
    assert leaks(listed) == [] and leaks(detail) == []
    assert alias(app.pk) == alias(app.pk) and alias(app.pk).startswith("Candidate #")


def test_original_file_cannot_be_downloaded_until_revealed(world: Any) -> None:
    from apps.applications.hr import staff_can_access_document

    team, _, app, doc = world
    assert staff_can_access_document(team.hr_manager, doc) is False
    c = staff(team.hr_manager, team.org)
    assert (
        c.post(
            f"/api/v1/hr/applications/{app.pk}/reveal-identity/", {"reason": ""}, format="json"
        ).status_code
        == 400
    )
    res = c.post(
        f"/api/v1/hr/applications/{app.pk}/reveal-identity/",
        {"reason": "Checking a reference call"},
        format="json",
    )
    assert res.status_code == 201
    assert staff_can_access_document(team.hr_manager, doc) is True
    # the reveal is per reviewer: a colleague still sees the alias
    assert staff_can_access_document(team.admin, doc) is False
    detail = c.get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert detail["candidate"]["first_name"] == "Rudo" and detail["identity_hidden"] is False
    other = staff(team.admin, team.org).get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert other["candidate"] == {"alias": alias(app.pk)}
    event = AuditEvent.objects.get(action="application.identity_revealed")
    assert event.actor_id == team.hr_manager.pk and event.reason == "Checking a reference call"
    again = c.post(
        f"/api/v1/hr/applications/{app.pk}/reveal-identity/",
        {"reason": "Second time"},
        format="json",
    )
    assert again.status_code == 201
    assert IdentityReveal.objects.for_org(team.org).count() == 1


def test_blind_mode_off_shows_identity(world: Any) -> None:
    team, _, app, doc = world
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=False)
    from apps.applications.hr import staff_can_access_document

    detail = staff(team.hr_manager, team.org).get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert detail["candidate"]["first_name"] == "Rudo" and detail["identity_hidden"] is False
    assert detail["documents"][0]["filename"] == "Rudo_Moyo_CV.pdf"
    assert staff_can_access_document(team.hr_manager, doc) is True


def test_shortlist_entries_are_redacted(world: Any) -> None:
    from apps.organisations.models import Membership
    from apps.shortlisting import services

    team, job, app, _ = world
    member = Membership.objects.get(user=team.hr_manager, organisation=team.org)
    s = services.create_proposal(member, team.hr_manager, job.pk)
    body = staff(team.hr_manager, team.org).get(f"/api/v1/hr/shortlists/{s.pk}/").json()
    entry = body["entries"][0]
    assert entry["candidate_name"] == alias(app.pk) and entry["identity_hidden"] is True
    assert leaks(body) == []


def test_cross_tenant_reveal_is_not_found(world: Any) -> None:
    _, _, app, _ = world
    other = make_org_with_team()
    res = staff(other.hr_manager, other.org).post(
        f"/api/v1/hr/applications/{app.pk}/reveal-identity/",
        {"reason": "Curious about this one"},
        format="json",
    )
    assert res.status_code == 404
    assert not IdentityReveal.objects.unscoped().exists()
