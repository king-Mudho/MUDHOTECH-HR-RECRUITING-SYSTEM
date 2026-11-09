"""Account-level business rules shared by other apps."""

from __future__ import annotations

from apps.core.exceptions import DomainError

from .models import User


class EmailUnverifiedError(DomainError):
    code = "email_unverified"
    status_code = 403
    default_message = "Please confirm your email address before continuing."


def require_verified_email(user: User) -> None:
    """EC-ACC-03: drafting is allowed, but submitting needs a verified email."""
    if not user.is_email_verified:
        raise EmailUnverifiedError(
            details={"resend_endpoint": "/api/v1/auth/browser/v1/auth/email/verify/resend"}
        )
