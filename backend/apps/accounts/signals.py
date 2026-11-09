"""Keep ``User.email_verified_at`` in sync with allauth and clear lockouts on password reset."""

from __future__ import annotations

from typing import Any

from allauth.account.models import EmailAddress
from allauth.account.signals import email_changed, email_confirmed, password_reset, user_logged_in
from django.dispatch import receiver

from apps.core import time

from . import lockout
from .models import User


def sync_email_verified(user: User) -> None:
    user.refresh_from_db(fields=["email", "email_verified_at"])
    verified = EmailAddress.objects.filter(
        user=user, email__iexact=user.email, verified=True
    ).exists()
    if verified and user.email_verified_at is None:
        user.email_verified_at = time.now()
    elif not verified:
        user.email_verified_at = None
    user.save(update_fields=["email_verified_at", "updated_at"])


@receiver(email_confirmed)
def _on_email_confirmed(email_address: EmailAddress, **_: Any) -> None:
    sync_email_verified(email_address.user)


@receiver(email_changed)
def _on_email_changed(user: User, **_: Any) -> None:
    # EC-ACC-07: the new address becomes primary only once verified; record a fresh verification.
    user.refresh_from_db(fields=["email"])
    user.email_verified_at = None
    user.save(update_fields=["email_verified_at", "updated_at"])
    sync_email_verified(user)


@receiver(password_reset)
def _on_password_reset(user: User, **_: Any) -> None:
    lockout.clear(user.email)


@receiver(user_logged_in)
def _on_login(user: User, request: Any = None, **_: Any) -> None:
    # Starts the 7-day MFA grace period the first time a privileged user signs in.
    from .mfa import mfa_status
    from .sessions import notify_if_new_device

    mfa_status(user)
    if request is not None:
        notify_if_new_device(user, request)
