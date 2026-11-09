"""Lockout (EC-ACC-05), sessions API, revoke-all (EC-ACC-12), new device (EC-ACC-11) - P02-T04."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from allauth.usersessions.models import UserSession
from django.core import mail
from django.test import Client

from apps.accounts import lockout
from apps.accounts.sessions import revoke_all_sessions
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.audit.models import AuditEvent
from apps.core import time

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/browser/v1"


_capture: Any = None


@pytest.fixture(autouse=True)
def _isolate(settings: Any, django_capture_on_commit_callbacks: Any) -> None:
    # Disable allauth's own IP/key rate limits so the progressive lockout is what we observe.
    settings.ACCOUNT_RATE_LIMITS = False
    global _capture
    _capture = django_capture_on_commit_callbacks


def login(
    client: Client, email: str, password: str, ua: str = "UA-1", ip: str = "196.1.1.1"
) -> Any:
    # Run on_commit hooks per request so outbox email is delivered like after a real commit.
    with _capture(execute=True):
        return client.post(
            f"{AUTH}/auth/login",
            {"email": email, "password": password},
            content_type="application/json",
            HTTP_USER_AGENT=ua,
            REMOTE_ADDR=ip,
        )


class TestProgressiveLockout:
    def test_locks_after_ten_failures_even_with_correct_password(self) -> None:
        user = UserFactory(email="brute@example.test")
        client = Client()
        for _ in range(9):
            assert login(client, user.email, "wrong-password-x").status_code == 400
        assert not lockout.is_locked(user.email)
        assert login(client, user.email, "wrong-password-x").status_code == 400  # 10th -> lock
        assert lockout.is_locked("  BRUTE@example.test ")
        resp = login(client, user.email, DEFAULT_PASSWORD)
        assert resp.status_code == 400
        assert resp.json()["errors"][0]["code"] == "too_many_login_attempts"
        locked_mail = [m for m in mail.outbox if "temporarily locked" in m.subject]
        assert locked_mail and locked_mail[0].to == [user.email]
        assert "15 minutes" in locked_mail[0].body

    def test_unknown_account_gets_identical_response_and_no_email(self) -> None:
        client = Client()
        for _ in range(10):
            login(client, "ghost@example.test", "nope-nope-nope")
        resp = login(client, "ghost@example.test", "nope-nope-nope")
        assert resp.json()["errors"][0]["code"] == "too_many_login_attempts"
        assert mail.outbox == []

    def test_lock_expires_by_time_and_doubles_on_repeat(self) -> None:
        user = UserFactory(email="timed@example.test")
        first = None
        for _ in range(10):
            first = lockout.register_failure(user.email) or first
        assert first is not None
        later = time.now() + timedelta(minutes=16)
        with mock.patch("apps.accounts.lockout.time.now", return_value=later):
            assert not lockout.is_locked(user.email)
            second = None
            for _ in range(10):
                second = lockout.register_failure(user.email) or second
        assert second is not None
        assert round((second - later).total_seconds() / 60) == 30  # doubled

    def test_success_resets_failure_counter(self) -> None:
        user = UserFactory(email="ok@example.test")
        client = Client()
        for _ in range(9):
            login(client, user.email, "wrong-password-x")
        assert login(client, user.email, DEFAULT_PASSWORD).status_code == 200
        assert lockout.register_failure(user.email) is None  # counter restarted

    def test_password_reset_clears_lock(self) -> None:
        user = UserFactory(email="reset-lock@example.test")
        for _ in range(10):
            lockout.register_failure(user.email)
        assert lockout.is_locked(user.email)
        from allauth.account.signals import password_reset

        password_reset.send(sender=type(user), request=None, user=user)
        assert not lockout.is_locked(user.email)

    def test_locked_account_rejected_by_backend_for_admin_login(self) -> None:
        from django.contrib.auth import authenticate

        user = UserFactory(email="admin-path@example.test")
        assert authenticate(None, email=user.email, password=DEFAULT_PASSWORD) is not None
        for _ in range(10):
            lockout.register_failure(user.email)
        assert authenticate(None, email=user.email, password=DEFAULT_PASSWORD) is None

    def test_empty_identifier_is_ignored(self) -> None:
        assert lockout.register_failure("") is None
        assert lockout.locked_until("") is None


class TestSessionsApi:
    def test_list_and_revoke_other_sessions(self) -> None:
        user = UserFactory(email="multi@example.test")
        laptop, phone = Client(), Client()
        assert login(laptop, user.email, DEFAULT_PASSWORD, ua="Laptop").status_code == 200
        assert (
            login(phone, user.email, DEFAULT_PASSWORD, ua="Phone", ip="41.2.3.4").status_code == 200
        )

        sessions = laptop.get("/api/v1/me/sessions/").json()
        assert len(sessions) == 2
        assert sum(s["is_current"] for s in sessions) == 1
        assert all(s["ip"].endswith("/24") for s in sessions)  # truncated

        resp = laptop.post("/api/v1/me/sessions/revoke-others/")
        assert resp.json() == {"revoked": 1}
        assert phone.get(f"{AUTH}/auth/session").status_code == 401  # phone signed out
        assert laptop.get(f"{AUTH}/auth/session").status_code == 200
        assert AuditEvent.objects.filter(action="user.sessions_revoked_others").exists()

    def test_revoke_single_session_and_cross_user_404(self) -> None:
        user, other = UserFactory(), UserFactory()
        a, b = Client(), Client()
        login(a, user.email, DEFAULT_PASSWORD, ua="A")
        login(b, user.email, DEFAULT_PASSWORD, ua="B")
        intruder = Client()
        login(intruder, other.email, DEFAULT_PASSWORD)
        target = UserSession.objects.filter(user=user, user_agent="B").get()
        assert intruder.delete(f"/api/v1/me/sessions/{target.pk}/").status_code == 404
        assert a.delete(f"/api/v1/me/sessions/{target.pk}/").status_code == 204
        assert b.get(f"{AUTH}/auth/session").status_code == 401

    def test_requires_authentication(self) -> None:
        resp = Client().get("/api/v1/me/sessions/")
        assert resp.status_code == 403 or resp.status_code == 401
        assert resp.json()["error"]["code"] in ("not_authenticated", "permission_denied")


def test_revoke_all_sessions_for_deactivated_staff() -> None:
    """EC-ACC-12."""
    user = UserFactory()
    clients = [Client(), Client()]
    for i, c in enumerate(clients):
        login(c, user.email, DEFAULT_PASSWORD, ua=f"UA-{i}")
    assert revoke_all_sessions(user) == 2
    assert all(c.get(f"{AUTH}/auth/session").status_code == 401 for c in clients)


def test_new_device_sign_in_notifies_user() -> None:
    """EC-ACC-11."""
    user = UserFactory(email="device@example.test")
    login(Client(), user.email, DEFAULT_PASSWORD, ua="Chrome-Laptop", ip="196.1.1.10")
    assert not [m for m in mail.outbox if "New sign-in" in m.subject]  # first ever sign-in
    login(Client(), user.email, DEFAULT_PASSWORD, ua="Chrome-Laptop", ip="196.1.1.99")
    assert not [m for m in mail.outbox if "New sign-in" in m.subject]  # same browser + /24
    login(Client(), user.email, DEFAULT_PASSWORD, ua="Unknown-Phone", ip="102.68.0.5")
    notices = [m for m in mail.outbox if "New sign-in" in m.subject]
    assert len(notices) == 1 and "102.68.0.0/24" in notices[0].body


def test_drf_default_throttles_configured() -> None:
    from rest_framework.settings import api_settings

    names = [c.__name__ for c in api_settings.DEFAULT_THROTTLE_CLASSES]
    assert names == ["AnonRateThrottle", "UserRateThrottle"]
    assert api_settings.DEFAULT_THROTTLE_RATES["auth"] == "10/min"
