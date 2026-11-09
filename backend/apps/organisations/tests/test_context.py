"""Organisation context middleware + /me/active-org - P02-T07 (EC-ORG-06, EC-ORG-07)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory

from apps.audit.models import AuditEvent
from apps.organisations.middleware import SESSION_KEY, OrganisationContextMiddleware
from apps.organisations.models import Membership, Organisation
from apps.organisations.tests.factories import MembershipFactory, make_org_with_team

pytestmark = pytest.mark.django_db

seen: dict[str, Any] = {}


def probe(request: HttpRequest) -> HttpResponse:
    seen["organisation"] = request.organisation  # type: ignore[attr-defined]
    seen["membership"] = request.membership  # type: ignore[attr-defined]
    return HttpResponse("ok")


def run(
    user: Any,
    *,
    method: str = "get",
    path: str = "/api/v1/hr/jobs/",
    header: str | None = None,
    session_org: str | None = None,
) -> HttpResponse:
    seen.clear()
    extra = {"HTTP_X_ORG_ID": header} if header else {}
    request = getattr(RequestFactory(), method)(path, **extra)
    request.user = user
    request.session = SessionStore()
    if session_org:
        request.session[SESSION_KEY] = session_org
    return OrganisationContextMiddleware(probe)(request)


def test_header_resolves_active_membership() -> None:
    team = make_org_with_team()
    resp = run(team.recruiter, header=str(team.org.pk))
    assert resp.status_code == 200
    assert seen["organisation"] == team.org
    assert seen["membership"].role == "recruiter"


def test_session_active_org_used_without_header() -> None:
    team = make_org_with_team()
    run(team.hr_manager, session_org=str(team.org.pk))
    assert seen["organisation"] == team.org


def test_stale_session_org_is_cleared() -> None:
    team = make_org_with_team()
    Membership.objects.for_org(team.org).filter(user=team.auditor).update(status="deactivated")
    seen.clear()
    request = RequestFactory().get("/api/v1/hr/jobs/")
    request.user = team.auditor
    request.session = SessionStore()
    request.session[SESSION_KEY] = str(team.org.pk)
    OrganisationContextMiddleware(probe)(request)
    assert seen["organisation"] is None and SESSION_KEY not in request.session


def test_no_context_for_anonymous_or_no_membership() -> None:
    run(AnonymousUser())
    assert seen["organisation"] is None
    team = make_org_with_team()
    other = make_org_with_team()
    run(other.recruiter)
    assert seen["organisation"] is None
    assert team.org != other.org


@pytest.mark.parametrize("kind", ["foreign", "garbage", "random", "deactivated"])
def test_header_for_org_user_does_not_belong_to_is_404_and_audited(kind: str) -> None:
    """EC-ORG-06."""
    mine, theirs = make_org_with_team(), make_org_with_team()
    header = {
        "foreign": str(theirs.org.pk),
        "garbage": "not-a-uuid",
        "random": str(uuid.uuid4()),
        "deactivated": str(mine.org.pk),
    }[kind]
    if kind == "deactivated":
        Membership.objects.for_org(mine.org).filter(user=mine.recruiter).update(
            status="deactivated"
        )
    resp = run(mine.recruiter, header=header)
    assert resp.status_code == 404
    assert json.loads(resp.content)["error"]["code"] == "not_found"
    event = AuditEvent.objects.get(action="tenant_violation_attempt")
    assert event.actor_id == mine.recruiter.pk and event.target_id == header[:64]
    assert event.after == {"path": "/api/v1/hr/jobs/", "method": "GET"}
    assert "organisation" not in seen  # request never reached the view


def test_closed_org_gives_no_context() -> None:
    team = make_org_with_team(status=Organisation.Status.CLOSED)
    assert run(team.admin, header=str(team.org.pk)).status_code == 404


@pytest.mark.parametrize("status", [Organisation.Status.SUSPENDED])
def test_suspended_org_is_read_only_for_staff(status: str) -> None:
    """EC-ORG-07: staff read-only."""
    team = make_org_with_team(status=status)
    assert run(team.hr_manager, header=str(team.org.pk)).status_code == 200  # reads ok
    resp = run(team.hr_manager, method="post", header=str(team.org.pk))
    assert resp.status_code == 423
    assert json.loads(resp.content)["error"]["code"] == "org_suspended"
    # Non context-scoped paths are not blocked here (path-scoped APIs enforce it themselves).
    assert (
        run(
            team.hr_manager, method="post", path="/api/v1/me/active-org/", header=str(team.org.pk)
        ).status_code
        == 200
    )


class TestActiveOrgEndpoint:
    def test_switch_between_orgs(self) -> None:
        a = make_org_with_team()
        b_org = make_org_with_team().org
        MembershipFactory(organisation=b_org, user=a.recruiter, role="hiring_manager")
        client = Client()
        client.force_login(a.recruiter)
        resp = client.post(
            "/api/v1/me/active-org/",
            {"organisation_id": str(b_org.pk)},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"organisation_id": str(b_org.pk), "role": "hiring_manager"}
        assert client.session[SESSION_KEY] == str(b_org.pk)

    def test_cannot_switch_to_foreign_org(self) -> None:
        a, b = make_org_with_team(), make_org_with_team()
        client = Client()
        client.force_login(a.recruiter)
        resp = client.post(
            "/api/v1/me/active-org/",
            {"organisation_id": str(b.org.pk)},
            content_type="application/json",
        )
        assert resp.status_code == 404
        assert SESSION_KEY not in client.session

    def test_validation_and_auth(self) -> None:
        client = Client()
        assert client.post(
            "/api/v1/me/active-org/", {}, content_type="application/json"
        ).status_code in (401, 403)
        team = make_org_with_team()
        client.force_login(team.recruiter)
        resp = client.post(
            "/api/v1/me/active-org/", {"organisation_id": "x"}, content_type="application/json"
        )
        assert resp.status_code == 400
        assert "organisation_id" in resp.json()["error"]["details"]
