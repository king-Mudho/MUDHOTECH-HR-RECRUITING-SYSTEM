"""Platform admin: tenant list/verify/suspend/reactivate + create_platform_admin - P02-T10."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole, User
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.core.models import OutboxEvent
from apps.organisations.models import Organisation
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db
URL = "/api/v1/platform/organisations/"


def client(role: str = PlatformRole.PLATFORM_ADMIN) -> tuple[APIClient, User]:
    user = UserFactory(platform_role=role)
    c = APIClient()
    c.force_login(user)
    return c, user


def test_list_filters_and_member_counts() -> None:
    a = make_org_with_team(status=Organisation.Status.PENDING_VERIFICATION, name="Pending Co")
    make_org_with_team(name="Active Co")
    c, _ = client()
    body = c.get(URL).json()
    assert body["count"] == 2
    assert {r["member_count"] for r in body["results"]} == {6}
    pending = c.get(URL, {"status": "pending_verification"}).json()["results"]
    assert [r["id"] for r in pending] == [str(a.org.pk)]
    assert c.get(URL, {"search": "Active"}).json()["count"] == 1


def test_verify_suspend_reactivate_lifecycle() -> None:
    team = make_org_with_team(status=Organisation.Status.PENDING_VERIFICATION)
    c, admin = client()
    detail = f"{URL}{team.org.pk}/"
    verified = c.post(f"{detail}verify/", {"reason": "Registration docs checked"}, format="json")
    assert verified.status_code == 200, verified.content
    assert verified.json()["status"] == "active"
    assert verified.json()["verified_by_email"] == admin.email

    assert c.post(f"{detail}suspend/", {}, format="json").status_code == 400  # reason required
    suspended = c.post(
        f"{detail}suspend/", {"reason": "Fraudulent job adverts reported"}, format="json"
    )
    assert suspended.json()["status"] == "suspended"
    again = c.post(
        f"{detail}suspend/", {"reason": "Fraudulent job adverts reported"}, format="json"
    )
    assert (
        again.status_code == 409 and again.json()["error"]["code"] == "conflict.invalid_transition"
    )

    back = c.post(f"{detail}reactivate/", {"reason": "Resolved"}, format="json")
    assert back.json()["status"] == "active"  # was verified before suspension

    actions = list(
        AuditEvent.objects.filter(chain=str(team.org.pk))
        .order_by("seq")
        .values_list("action", flat=True)
    )
    assert actions[-3:] == [
        "organisation.verified",
        "organisation.suspended",
        "organisation.reactivated",
    ]
    events = set(OutboxEvent.objects.values_list("event_type", flat=True))
    assert {"organisation.verified", "organisation.suspended", "organisation.reactivated"} <= events


def test_reactivating_never_verified_org_returns_to_pending() -> None:
    team = make_org_with_team(status=Organisation.Status.PENDING_VERIFICATION)
    c, _ = client()
    c.post(f"{URL}{team.org.pk}/suspend/", {"reason": "Spam signup"}, format="json")
    resp = c.post(f"{URL}{team.org.pk}/reactivate/", {}, format="json")
    assert resp.json()["status"] == "pending_verification"


def test_verifying_active_org_is_invalid() -> None:
    team = make_org_with_team()
    c, _ = client()
    assert c.post(f"{URL}{team.org.pk}/verify/", {}, format="json").status_code == 409


@pytest.mark.parametrize(
    ("role", "read", "write"),
    [
        (PlatformRole.PLATFORM_ADMIN, 200, 200),
        (PlatformRole.PLATFORM_SUPPORT, 200, 403),
        (PlatformRole.NONE, 403, 403),
    ],
)
def test_platform_permissions(role: str, read: int, write: int) -> None:
    team = make_org_with_team(status=Organisation.Status.PENDING_VERIFICATION)
    c, _ = client(role)
    assert c.get(URL).status_code == read
    assert c.post(f"{URL}{team.org.pk}/verify/", {}, format="json").status_code == write


def test_org_admin_cannot_use_platform_api() -> None:
    team = make_org_with_team()
    c = APIClient()
    c.force_login(team.admin)
    assert c.get(URL).status_code == 403
    assert APIClient().get(URL).status_code in (401, 403)


class TestCreatePlatformAdmin:
    def test_creates_verified_admin_from_env(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("PLATFORM_ADMIN_EMAIL", " Ops@MudhoTech.test ")
        monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "orchard-velvet-compass-91")
        out = StringIO()
        call_command("create_platform_admin", stdout=out)
        user = User.objects.get(email="ops@mudhotech.test")
        assert user.platform_role == PlatformRole.PLATFORM_ADMIN and user.is_staff
        assert user.is_email_verified and user.check_password("orchard-velvet-compass-91")
        assert user.mfa_grace_started_at is not None
        assert "Created" in out.getvalue()
        call_command("create_platform_admin", stdout=out)  # idempotent
        assert "Promoted" in out.getvalue()
        assert User.objects.filter(email="ops@mudhotech.test").count() == 1

    def test_promotes_existing_user_without_password(self, monkeypatch: Any) -> None:
        existing = UserFactory(email="lead@example.test")
        monkeypatch.setenv("PLATFORM_ADMIN_EMAIL", "lead@example.test")
        monkeypatch.delenv("PLATFORM_ADMIN_PASSWORD", raising=False)
        call_command("create_platform_admin", stdout=StringIO())
        existing.refresh_from_db()
        assert existing.platform_role == PlatformRole.PLATFORM_ADMIN

    @pytest.mark.parametrize(
        ("email", "password"),
        [("", "x"), ("new@example.test", ""), ("new@example.test", "password123")],
    )
    def test_validation(self, monkeypatch: Any, email: str, password: str) -> None:
        monkeypatch.setenv("PLATFORM_ADMIN_EMAIL", email)
        monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", password)
        with pytest.raises(CommandError):
            call_command("create_platform_admin", stdout=StringIO())
