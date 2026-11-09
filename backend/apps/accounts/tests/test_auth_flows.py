"""End-to-end auth flows through allauth headless (browser client) - P02-T02."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

import pytest
from django.core import mail
from django.test import Client

from apps.accounts.models import User
from apps.accounts.services import EmailUnverifiedError, require_verified_email
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/browser/v1"
STRONG = "violet-harbour-lantern-42"


@pytest.fixture
def run_on_commit(django_capture_on_commit_callbacks: Any) -> Callable[..., Any]:
    """Execute on_commit hooks so the outbox relay delivers queued email."""

    def _call(fn: Callable[[], Any]) -> Any:
        with django_capture_on_commit_callbacks(execute=True):
            return fn()

    return _call


def post(client: Client, path: str, data: dict[str, Any]) -> Any:
    return client.post(f"{AUTH}{path}", data, content_type="application/json")


def link_key(body: str, route: str) -> str:
    match = re.search(rf"/{route}\?key=([^\s]+)", body)
    assert match, body
    return unquote(match.group(1))


def signup(client: Client, run_on_commit: Any, email: str, password: str = STRONG) -> Any:
    return run_on_commit(
        lambda: post(client, "/auth/signup", {"email": email, "password": password})
    )


def test_csrf_endpoint_sets_cookie(client: Client) -> None:
    resp = client.get("/api/v1/csrf/")
    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies


def test_config_endpoint(client: Client) -> None:
    body = client.get(f"{AUTH}/config").json()
    assert body["data"]["account"]["login_methods"] == ["email"]
    assert set(body["data"]["mfa"]["supported_types"]) == {"totp", "recovery_codes"}


def test_signup_sends_branded_verification_via_outbox_and_verify(
    client: Client, run_on_commit: Any
) -> None:
    resp = signup(client, run_on_commit, "  New.Candidate@Example.TEST ")
    # ADR-023: pending "verify_email" flow - not logged in yet.
    assert resp.status_code == 401, resp.content
    assert any(
        f["id"] == "verify_email" for f in resp.json()["data"]["flows"] if f.get("is_pending")
    )
    user = User.objects.get()
    assert user.email == "new.candidate@example.test"  # EC-ACC-01
    assert user.email_verified_at is None
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.subject.startswith("[MHRS]")
    assert "MUDHOTECH HR RECRUITING SYSTEM" in msg.body
    key = link_key(msg.body, "verify-email")

    resp = post(client, "/auth/email/verify", {"key": key})
    assert resp.status_code == 200, resp.content  # verified + logged in
    assert resp.json()["meta"]["is_authenticated"] is True
    user.refresh_from_db()
    assert user.email_verified_at is not None
    require_verified_email(user)  # no longer raises


def test_verification_key_reuse_and_garbage_rejected(client: Client, run_on_commit: Any) -> None:
    """EC-ACC-04: used/invalid links fail cleanly (frontend shows resend)."""
    signup(client, run_on_commit, "reuse@example.test")
    key = link_key(mail.outbox[0].body, "verify-email")
    assert post(client, "/auth/email/verify", {"key": key}).status_code == 200
    assert post(client, "/auth/email/verify", {"key": key}).status_code in (400, 409)
    assert post(client, "/auth/email/verify", {"key": "not-a-key"}).status_code == 400


def test_unverified_user_blocked_by_helper() -> None:
    """EC-ACC-03."""
    user = UserFactory(verified=False)
    with pytest.raises(EmailUnverifiedError) as exc:
        require_verified_email(user)
    assert exc.value.code == "email_unverified"


def test_duplicate_signup_is_generic_and_emails_owner(client: Client, run_on_commit: Any) -> None:
    """EC-ACC-02: no enumeration; the existing owner gets an 'already have an account' email."""
    UserFactory(email="taken@example.test")
    resp = signup(Client(), run_on_commit, "TAKEN@example.test")
    assert resp.status_code == 401
    assert User.objects.filter(email__iexact="taken@example.test").count() == 1
    assert len(mail.outbox) == 1
    assert "already exists" in mail.outbox[0].body
    fresh = signup(Client(), run_on_commit, "fresh@example.test")
    assert fresh.status_code == resp.status_code  # indistinguishable status


def test_breached_password_rejected_at_signup(client: Client, run_on_commit: Any) -> None:
    resp = signup(client, run_on_commit, "weak@example.test", password="password123")
    assert resp.status_code == 400
    assert not User.objects.filter(email="weak@example.test").exists()


def test_password_reset_unknown_email_is_generic(client: Client, run_on_commit: Any) -> None:
    """EC-ACC-06."""
    resp = run_on_commit(
        lambda: post(client, "/auth/password/request", {"email": "nobody@example.test"})
    )
    assert resp.status_code == 200
    assert mail.outbox == []


def test_password_reset_flow(client: Client, run_on_commit: Any) -> None:
    user = UserFactory(email="reset@example.test")
    resp = run_on_commit(
        lambda: post(client, "/auth/password/request", {"email": "Reset@Example.test"})
    )
    assert resp.status_code == 200
    key = link_key(mail.outbox[0].body, "reset-password")
    resp = run_on_commit(
        lambda: post(client, "/auth/password/reset", {"key": key, "password": STRONG})
    )
    assert resp.status_code in (200, 401), resp.content
    user.refresh_from_db()
    assert user.check_password(STRONG)
    # single-use token
    assert (
        post(client, "/auth/password/reset", {"key": key, "password": STRONG + "x"}).status_code
        == 400
    )


def test_login_logout_and_generic_failure(client: Client) -> None:
    UserFactory(email="login@example.test")
    bad = post(client, "/auth/login", {"email": "login@example.test", "password": "wrong-password"})
    unknown = post(
        client, "/auth/login", {"email": "ghost@example.test", "password": "wrong-password"}
    )
    assert bad.status_code == unknown.status_code == 400
    unverified = UserFactory(email="unverified@example.test", verified=False)
    pending = post(client, "/auth/login", {"email": unverified.email, "password": DEFAULT_PASSWORD})
    assert pending.status_code == 401  # must verify first (ADR-023)
    assert bad.json()["errors"][0]["code"] == unknown.json()["errors"][0]["code"]
    ok = post(client, "/auth/login", {"email": "LOGIN@example.test", "password": DEFAULT_PASSWORD})
    assert ok.status_code == 200
    assert client.get(f"{AUTH}/auth/session").status_code == 200
    assert client.delete(f"{AUTH}/auth/session").status_code == 401
    assert client.get(f"{AUTH}/auth/session").status_code == 401


def test_email_change_requires_reverification_and_notifies_old_address(
    client: Client, run_on_commit: Any
) -> None:
    """FR-M01-07 / EC-ACC-07."""
    signup(client, run_on_commit, "old@example.test")
    post(client, "/auth/email/verify", {"key": link_key(mail.outbox[0].body, "verify-email")})
    mail.outbox.clear()

    resp = run_on_commit(lambda: post(client, "/account/email", {"email": "new@example.test"}))
    assert resp.status_code == 200, resp.content
    user = User.objects.get()
    assert user.email == "old@example.test"  # unchanged until the new address is verified
    assert mail.outbox[-1].to == ["new@example.test"]
    key = link_key(mail.outbox[-1].body, "verify-email")
    mail.outbox.clear()

    run_on_commit(lambda: post(client, "/auth/email/verify", {"key": key}))
    user.refresh_from_db()
    assert user.email == "new@example.test"
    assert user.email_verified_at is not None
    notice = [m for m in mail.outbox if m.to == ["old@example.test"]]
    assert notice and "new@example.test" in notice[0].body
