"""Break-glass support access (P09-T06, EC-PRV-07)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AccessLog, AuditEvent
from apps.core.time import now
from apps.organisations.models import SupportAccessGrant
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def client(user: Any, org: Any = None) -> APIClient:
    c = APIClient()
    c.force_login(user)
    if org is not None:
        c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    support = UserFactory(verified=True, platform_role=PlatformRole.PLATFORM_SUPPORT)
    admin = UserFactory(verified=True, platform_role=PlatformRole.PLATFORM_ADMIN)
    return team, job, support, admin


def request_grant(support: Any, org: Any, minutes: int = 60) -> Any:
    return client(support).post(
        "/api/v1/platform/support-access/",
        {
            "organisation_id": str(org.pk),
            "reason": "Customer reports a stuck shortlist",
            "minutes": minutes,
        },
        format="json",
    )


def test_request_approve_read_only_and_logged(world: Any) -> None:
    team, job, support, admin = world
    applicants = f"/api/v1/hr/jobs/{job.pk}/applications/"
    # without a grant: 404 like any other stranger (and audited as a violation)
    assert client(support, team.org).get(applicants).status_code == 404
    assert request_grant(support, team.org, minutes=300).status_code == 400  # > 4 h
    res = request_grant(support, team.org)
    assert res.status_code == 201 and res.json()["active"] is False
    grant_id = res.json()["id"]
    # the requester cannot approve their own request; an admin can
    assert (
        client(support).post(f"/api/v1/platform/support-access/{grant_id}/approve/").status_code
        == 403
    )
    approved = client(admin).post(f"/api/v1/platform/support-access/{grant_id}/approve/")
    assert approved.status_code == 200 and approved.json()["active"] is True
    sc = client(support, team.org)
    listed = sc.get(applicants)
    assert listed.status_code == 200 and listed.json()["count"] == 1  # read access
    write = sc.post(f"/api/v1/hr/jobs/{job.pk}/shortlists/", {"desired_size": 2}, format="json")
    assert write.status_code == 403 and write.json()["error"]["code"] == "support_read_only"
    assert AccessLog.objects.filter(user=support, action="support_read").count() == 2
    # the organisation sees the grant, its reason and how often it was used, plus the banner
    org_view = client(team.admin, team.org).get("/api/v1/hr/support-access/").json()
    assert org_view[0]["reason"].startswith("Customer reports") and org_view[0]["accesses"] == 2
    banner = client(team.recruiter, team.org).get("/api/v1/hr/support-access/active/").json()
    assert banner["active"] is True and banner["until"]
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"support_access.requested", "support_access.approved"} <= actions


def test_expiry_and_revocation_end_access(world: Any) -> None:
    team, job, support, admin = world
    grant_id = request_grant(support, team.org).json()["id"]
    client(admin).post(f"/api/v1/platform/support-access/{grant_id}/approve/")
    applicants = f"/api/v1/hr/jobs/{job.pk}/applications/"
    sc = client(support, team.org)
    assert sc.get(applicants).status_code == 200
    SupportAccessGrant.objects.filter(pk=grant_id).update(expires_at=now() - timedelta(seconds=1))
    assert sc.get(applicants).status_code == 404  # auto-expiry
    SupportAccessGrant.objects.filter(pk=grant_id).update(expires_at=now() + timedelta(hours=1))
    assert sc.get(applicants).status_code == 200
    revoked = client(team.admin, team.org).post(f"/api/v1/hr/support-access/{grant_id}/revoke/")
    assert revoked.status_code == 200
    assert sc.get(applicants).status_code == 404
    assert (
        client(team.recruiter, team.org).get("/api/v1/hr/support-access/active/").json()["active"]
        is False
    )


def test_grant_is_scoped_to_one_organisation(world: Any) -> None:
    team, _, support, admin = world
    other = make_org_with_team()
    other_job = published_job(organisation=other.org)
    grant_id = request_grant(support, team.org).json()["id"]
    client(admin).post(f"/api/v1/platform/support-access/{grant_id}/approve/")
    assert (
        client(support, other.org).get(f"/api/v1/hr/jobs/{other_job.pk}/applications/").status_code
        == 404
    )
    assert client(other.admin, other.org).get("/api/v1/hr/support-access/").json() == []
    # ordinary users cannot request access
    res = client(team.recruiter).post(
        "/api/v1/platform/support-access/",
        {
            "organisation_id": str(team.org.pk),
            "reason": "Just curious about the data",
            "minutes": 30,
        },
        format="json",
    )
    assert res.status_code == 403
