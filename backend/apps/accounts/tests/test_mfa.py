"""MFA: TOTP enrolment, 2FA login, recovery codes, privileged-role enforcement (P02-T03)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)
from django.test import Client

from apps.accounts import mfa
from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.audit.models import AuditEvent
from apps.core import time

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/browser/v1"
GUARDED = "/api/v1/csrf/"  # stand-in staff-prefixed path until staff APIs exist


def totp_code(secret: str) -> str:
    counter = next(iter(yield_hotp_counters_from_time()))
    return format_hotp_value(hotp_value(secret, counter))


def login(client: Client, email: str, password: str = DEFAULT_PASSWORD) -> Any:
    return client.post(
        f"{AUTH}/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
    )


def reauthenticate(client: Client, password: str = DEFAULT_PASSWORD) -> None:
    """Sensitive MFA actions need a recent password confirmation ('reauthenticate' flow)."""
    resp = client.post(
        f"{AUTH}/auth/reauthenticate", {"password": password}, content_type="application/json"
    )
    assert resp.status_code == 200, resp.content


def enrol_totp(client: Client) -> str:
    reauthenticate(client)
    resp = client.get(f"{AUTH}/account/authenticators/totp")
    assert resp.status_code == 404  # not yet enabled; meta carries the provisioning secret
    secret = resp.json()["meta"]["secret"]
    assert resp.json()["meta"]["totp_url"].startswith("otpauth://totp/")
    resp = client.post(
        f"{AUTH}/account/authenticators/totp",
        {"code": totp_code(secret)},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    return secret


def test_totp_enrolment_then_login_requires_second_factor() -> None:
    user = UserFactory(email="mfa@example.test")
    client = Client()
    assert login(client, user.email).status_code == 200
    secret = enrol_totp(client)
    assert mfa.has_mfa(user)

    client2 = Client()
    resp = login(client2, user.email)
    assert resp.status_code == 401
    assert any(f["id"] == "mfa_authenticate" for f in resp.json()["data"]["flows"])
    bad = client2.post(
        f"{AUTH}/auth/2fa/authenticate", {"code": "000000"}, content_type="application/json"
    )
    assert bad.status_code == 400
    ok = client2.post(
        f"{AUTH}/auth/2fa/authenticate",
        {"code": totp_code(secret)},
        content_type="application/json",
    )
    assert ok.status_code == 200, ok.content


def test_recovery_code_login_for_lost_device() -> None:
    """EC-ACC-08 (self-service path)."""
    user = UserFactory(email="lost@example.test")
    client = Client()
    login(client, user.email)
    enrol_totp(client)
    reauthenticate(client)
    codes = client.get(f"{AUTH}/account/authenticators/recovery-codes").json()["data"][
        "unused_codes"
    ]
    assert len(codes) == 10

    client2 = Client()
    login(client2, user.email)
    ok = client2.post(
        f"{AUTH}/auth/2fa/authenticate", {"code": codes[0]}, content_type="application/json"
    )
    assert ok.status_code == 200
    again = Client()
    login(again, user.email)
    reused = again.post(
        f"{AUTH}/auth/2fa/authenticate", {"code": codes[0]}, content_type="application/json"
    )
    assert reused.status_code == 400  # single use


def test_admin_reset_removes_authenticators_and_is_audited() -> None:
    """EC-ACC-08 (assisted path)."""
    user = UserFactory()
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    admin = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
    removed = mfa.reset_mfa(user, actor=admin, reason="Lost phone; identity checked by video call")
    assert removed == 1 and not mfa.has_mfa(user)
    event = AuditEvent.objects.get(action="user.mfa_reset")
    assert event.actor_id == admin.pk and event.target_id == str(user.pk)
    assert "identity checked" in event.reason


def test_status_for_non_privileged_user() -> None:
    status = mfa.mfa_status(UserFactory())
    assert status.as_dict() == {
        "required": False,
        "enabled": False,
        "grace_deadline": None,
        "in_grace": False,
        "enforced": False,
    }


def test_privilege_provider_registry() -> None:
    user = UserFactory()
    flagged: set[Any] = {user.pk}

    def provider(u: Any) -> bool:
        return u.pk in flagged

    mfa.register_privilege_provider(provider)
    mfa.register_privilege_provider(provider)  # idempotent
    try:
        status = mfa.mfa_status(user)
        assert status.required and status.in_grace
        assert user.mfa_grace_started_at is not None
    finally:
        mfa._PROVIDERS.remove(provider)


class TestEnforcementMiddleware:
    @pytest.fixture(autouse=True)
    def _guard_api_root(self, settings: Any) -> None:
        settings.MFA_ENFORCED_PATH_PREFIXES = (GUARDED,)

    def _client(self, user: Any) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def test_non_privileged_user_not_blocked(self) -> None:
        assert self._client(UserFactory()).get(GUARDED).status_code == 200

    def test_privileged_user_in_grace_is_allowed(self) -> None:
        admin = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
        assert self._client(admin).get(GUARDED).status_code == 200
        admin.refresh_from_db()
        assert admin.mfa_grace_deadline is not None  # grace started on first contact

    def test_privileged_user_blocked_after_grace(self) -> None:
        admin = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
        admin.mfa_grace_started_at = time.now() - timedelta(days=8)
        admin.save()
        resp = self._client(admin).get(GUARDED)
        assert resp.status_code == 401
        body = resp.json()["error"]
        assert body["code"] == "mfa_required" and "setup_url" in body["details"]

    def test_enrolled_privileged_user_allowed_after_grace(self) -> None:
        admin = UserFactory(platform_role=PlatformRole.PLATFORM_SUPPORT)
        admin.mfa_grace_started_at = time.now() - timedelta(days=30)
        admin.save()
        Authenticator.objects.create(user=admin, type=Authenticator.Type.TOTP, data={"secret": "x"})
        assert self._client(admin).get(GUARDED).status_code == 200

    def test_anonymous_and_auth_paths_untouched(self) -> None:
        assert Client().get(GUARDED).status_code == 200
        admin = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
        admin.mfa_grace_started_at = time.now() - timedelta(days=8)
        admin.save()
        # MFA setup endpoints live outside the guarded prefixes: never answered with mfa_required.
        resp = self._client(admin).get(f"{AUTH}/account/authenticators")
        assert "error" not in resp.json()


def test_login_starts_grace_for_platform_staff() -> None:
    admin = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
    assert admin.mfa_grace_started_at is None
    assert login(Client(), admin.email).status_code == 200
    admin.refresh_from_db()
    assert admin.mfa_grace_started_at is not None
