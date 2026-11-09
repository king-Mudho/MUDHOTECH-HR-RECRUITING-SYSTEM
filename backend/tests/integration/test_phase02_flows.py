"""Phase 02 cross-cutting flows: MFA enforcement on staff APIs, audit chain over API activity."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from allauth.mfa.models import Authenticator
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.audit.services import iter_chains, verify_chain
from apps.core import time
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("role", ["admin", "hr_manager"])
def test_privileged_member_without_mfa_blocked_after_grace(role: str) -> None:
    team = make_org_with_team()
    user = getattr(team, role)
    client = APIClient()
    client.force_login(user)
    url = f"/api/v1/organisations/{team.org.pk}/"
    assert client.get(url).status_code == 200  # grace period starts on first contact
    user.refresh_from_db()
    user.mfa_grace_started_at = time.now() - timedelta(days=7, minutes=1)
    user.save()
    blocked = client.get(url)
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "mfa_required"
    assert client.get("/api/v1/me/").json()["mfa"]["enforced"] is True  # /me stays reachable
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    assert client.get(url).status_code == 200


def test_non_privileged_roles_never_blocked() -> None:
    team = make_org_with_team()
    team.recruiter.mfa_grace_started_at = time.now() - timedelta(days=30)
    team.recruiter.save()
    client = APIClient()
    client.force_login(team.recruiter)
    assert client.get(f"/api/v1/organisations/{team.org.pk}/").status_code == 200


def test_audit_chain_verifies_after_api_activity() -> None:
    team = make_org_with_team()
    client = APIClient()
    client.force_login(team.admin)
    base = f"/api/v1/organisations/{team.org.pk}"
    client.patch(f"{base}/", {"city": "Chinhoyi"}, format="json")
    client.post(f"{base}/departments/", {"name": "Finance"}, format="json")
    client.post(
        f"{base}/invitations/", {"email": "q@example.test", "role": "auditor"}, format="json"
    )
    client.patch(f"{base}/policies/", {"lock_version": 1, "ai_enabled": False}, format="json")
    chains = list(iter_chains())
    assert str(team.org.pk) in chains
    assert all(list(verify_chain(c)) == [] for c in chains)
    out = StringIO()
    call_command("verify_audit_chain", stdout=out)
    assert "OK" in out.getvalue()
