"""P15-T03: staff SSO rules - no sign-up through SSO, verified email required, only members of an
organisation that enabled SSO for that email domain."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from rest_framework.test import APIClient

from apps.accounts.social import SocialAdapter, sso_allowed
from apps.accounts.tests.factories import UserFactory
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


class FakeLogin:
    def __init__(self, email: str, verified: bool = True) -> None:
        self.email_addresses = [SimpleNamespace(email=email, verified=verified)]
        self.is_existing = False
        self.user = None
        self.connected: Any = None

    def connect(self, request: Any, user: Any) -> None:
        self.connected = user


def enable(team: Any, *domains: str) -> None:
    OrganisationPolicy.objects.filter(organisation=team.org).update(
        sso_enabled=True, sso_domains=list(domains)
    )


def test_sso_links_only_members_of_orgs_that_enabled_their_domain() -> None:
    team = make_org_with_team()
    team.recruiter.email = "rudo@acme.co.zw"
    team.recruiter.save()
    adapter = SocialAdapter()
    with pytest.raises(ImmediateHttpResponse):  # SSO not enabled yet
        adapter.pre_social_login(None, FakeLogin("rudo@acme.co.zw"))
    enable(team, "acme.co.zw")
    login = FakeLogin("Rudo@ACME.co.zw")
    adapter.pre_social_login(None, login)
    assert login.connected == team.recruiter
    assert sso_allowed(team.recruiter, "rudo@acme.co.zw")
    with pytest.raises(ImmediateHttpResponse):  # unverified at the provider
        adapter.pre_social_login(None, FakeLogin("rudo@acme.co.zw", verified=False))
    stranger = UserFactory(email="someone@acme.co.zw")  # same domain, not a member
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(None, FakeLogin(stranger.email))
    with pytest.raises(ImmediateHttpResponse):  # nobody is created through SSO
        adapter.pre_social_login(None, FakeLogin("new.person@acme.co.zw"))
    assert adapter.is_open_for_signup(None, FakeLogin("x@acme.co.zw")) is False


def test_policy_accepts_clean_domains_only() -> None:
    team = make_org_with_team()
    admin = APIClient()
    admin.force_login(team.admin)
    url = f"/api/v1/organisations/{team.org.pk}/policies/"
    current = admin.get(url).json()
    ok = admin.patch(
        url,
        {
            "lock_version": current["version"],
            "sso_enabled": True,
            "sso_domains": ["@Acme.co.zw", "acme.co.zw"],
        },
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["sso_domains"] == ["acme.co.zw"]
    bad = admin.patch(
        url,
        {"lock_version": ok.json()["version"], "sso_domains": ["not a domain"]},
        format="json",
    )
    assert bad.status_code == 400
