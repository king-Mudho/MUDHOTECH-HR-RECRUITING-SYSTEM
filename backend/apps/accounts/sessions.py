"""User session management on top of ``allauth.usersessions`` (FR-M01-03, EC-ACC-11, EC-ACC-12)."""

from __future__ import annotations

import logging
from typing import Any

from allauth.usersessions.models import UserSession
from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string

from apps.audit.services import truncate_ip
from apps.core import time

from .models import User

logger = logging.getLogger("mhrs.accounts.sessions")


def list_sessions(user: User) -> list[UserSession]:
    """Active sessions (expired ones are purged), most recent first."""
    sessions = UserSession.objects.purge_and_list(user)
    return sorted(sessions, key=lambda s: s.last_seen_at, reverse=True)


def revoke_session(user: User, session_id: int) -> bool:
    session = UserSession.objects.filter(user=user, pk=session_id).first()
    if session is None:
        return False
    session.end()
    return True


def revoke_other_sessions(user: User, current_session_key: str | None) -> int:
    count = 0
    for session in UserSession.objects.filter(user=user).exclude(session_key=current_session_key):
        session.end()
        count += 1
    return count


def revoke_all_sessions(user: User) -> int:
    """EC-ACC-12: used when a member is deactivated or an account is compromised."""
    return revoke_other_sessions(user, current_session_key=None)


def notify_if_new_device(user: User, request: HttpRequest) -> bool:
    """EC-ACC-11: email the user when a sign-in comes from an unseen browser + network."""
    current_key = getattr(getattr(request, "session", None), "session_key", None)
    previous = UserSession.objects.filter(user=user).exclude(session_key=current_key)
    if not previous.exists():
        return False  # first ever sign-in: nothing to compare with
    ua = request.META.get("HTTP_USER_AGENT", "")[:200]
    net = truncate_ip(request.META.get("REMOTE_ADDR"))
    for s in previous.only("ip", "user_agent"):
        if s.user_agent[:200] == ua and truncate_ip(s.ip) == net:
            return False

    from apps.core.email import queue_email

    context: dict[str, Any] = {
        "user": user,
        "ip": net or "unknown",
        "user_agent": ua or "unknown",
        "when": time.to_tz(time.now(), user.timezone),
        "sessions_url": f"{settings.FRONTEND_URL}/account/security",
    }
    subject = render_to_string("account/email/new_device_subject.txt", context).strip()
    queue_email(
        user.email,
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}{subject}",
        render_to_string("account/email/new_device_message.txt", context),
        category="security",
    )
    logger.info("new_device_sign_in")
    return True
