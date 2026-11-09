"""Progressive account lockout (FR-M01-05, EC-ACC-05).

Counted per normalised email in the cache (Redis in dev/prod). After ``ACCOUNT_LOCKOUT_THRESHOLD``
consecutive failures the account is locked for ``ACCOUNT_LOCKOUT_BASE_MINUTES``; each further lock
within 24 h doubles the duration (capped). Locks expire by time or are cleared by a password reset.
Responses stay generic (no enumeration); the account owner is notified by email.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string

from apps.core import time

from .models import User, normalize_email_address

logger = logging.getLogger("mhrs.accounts.lockout")

WINDOW_SECONDS = 24 * 60 * 60


def _key(kind: str, email: str) -> str:
    digest = hashlib.sha256(normalize_email_address(email).encode()).hexdigest()[:32]
    return f"lockout:v1:{kind}:{digest}"


def locked_until(email: str) -> datetime | None:
    if not email:
        return None
    value = cache.get(_key("until", email))
    if value is None:
        return None
    until = datetime.fromisoformat(value)
    if until <= time.now():
        return None
    return until


def is_locked(email: str) -> bool:
    return locked_until(email) is not None


def register_failure(email: str) -> datetime | None:
    """Record a failed login. Returns the lock expiry if this failure triggered a lock."""
    if not email:
        return None
    fkey = _key("failures", email)
    cache.add(fkey, 0, WINDOW_SECONDS)
    try:
        failures = cache.incr(fkey)
    except ValueError:  # pragma: no cover - key evicted between add and incr
        cache.set(fkey, 1, WINDOW_SECONDS)
        failures = 1
    if failures < settings.ACCOUNT_LOCKOUT_THRESHOLD:
        return None

    lkey = _key("level", email)
    cache.add(lkey, 0, WINDOW_SECONDS)
    level = cache.incr(lkey)
    minutes = min(
        settings.ACCOUNT_LOCKOUT_BASE_MINUTES * (2 ** (level - 1)),
        settings.ACCOUNT_LOCKOUT_MAX_MINUTES,
    )
    until = time.now() + timedelta(minutes=minutes)
    cache.set(_key("until", email), until.isoformat(), int(minutes * 60) + 5)
    cache.set(fkey, 0, WINDOW_SECONDS)
    logger.warning("account_locked", extra={"lock_minutes": minutes, "lock_level": level})
    _notify(email, until, minutes)
    return until


def register_success(email: str) -> None:
    cache.delete(_key("failures", email))


def clear(email: str) -> None:
    for kind in ("failures", "level", "until"):
        cache.delete(_key(kind, email))


def _notify(email: str, until: datetime, minutes: int) -> None:
    from apps.core.email import queue_email

    user = User.objects.filter(email__iexact=normalize_email_address(email)).first()
    if user is None:  # unknown account: nothing to notify, response stays generic
        return
    context = {
        "user": user,
        "minutes": minutes,
        "until": time.to_tz(until, user.timezone),
        "reset_url": f"{settings.FRONTEND_URL}/forgot-password",
    }
    subject = render_to_string("account/email/account_locked_subject.txt", context).strip()
    body = render_to_string("account/email/account_locked_message.txt", context)
    queue_email(
        user.email,
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}{subject}",
        body,
        category="security",
        dedupe_key=f"account.locked:{user.pk}:{until.isoformat()}",
    )
