"""Notification delivery (P05-T03).

``notify()`` is called inside a business transaction: it writes one ``Notification`` per channel
(``dedupe_key`` unique, EC-NOT-03) and emits ``notification.queued`` through the outbox, so the
message exists exactly when the business change commits. In-app notifications are complete at
that point. Emails are delivered by ``deliver()`` (the ``send_notification`` task):

1. claim the row (``queued -> sending``, committed) - a replayed event or a second worker finds
   nothing to do;
2. checks: recipient still active and verified (EC-ACC-07), not on the suppression list
   (EC-NOT-01), application not withdrawn (EC-NOT-04), quiet hours for non-urgent candidate
   mail (EC-NOT-09);
3. render (organisation override, falling back to the platform default, EC-NOT-05) and send with
   a deterministic ``Message-ID`` so a resend after a crash is recognisable as the same message;
4. mark ``sent``. Provider errors put the row back to ``queued`` and the task retries with
   backoff for about 24 hours (EC-NOT-02), then a dead letter is written and the row is ``failed``.
"""

from __future__ import annotations

import logging
import zoneinfo
from datetime import datetime, time, timedelta
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction

from apps.core.outbox import emit
from apps.core.time import now

from . import registry, services
from .models import Channel, EmailSuppression, Notification, NotificationStatus

logger = logging.getLogger("mhrs.notifications")

EVENT = "notification.queued"
QUIET_START = time(20, 0)
QUIET_END = time(7, 0)
STALE_SENDING = timedelta(minutes=15)
# Messages a withdrawn applicant should still get.
ALLOWED_AFTER_WITHDRAWAL = {"application_withdrawn_confirmation", "rights_request_update"}


class DeliveryError(Exception):
    """Temporary provider failure: the task retries."""


def common_context(user: Any) -> dict[str, str]:
    site = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return {
        "recipient_name": user.display_name,
        "portal_url": site,
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
        "platform_name": services.BRAND,
    }


def notify(
    user: Any,
    key: str,
    context: dict[str, Any] | None = None,
    *,
    dedupe_key: str,
    organisation: Any = None,
    channels: tuple[str, ...] = (Channel.EMAIL, Channel.INAPP),
    scheduled_for: datetime | None = None,
) -> list[Notification]:
    """Queue ``key`` for ``user``. Must run inside ``transaction.atomic()``. Calling it again with
    the same ``dedupe_key`` creates nothing (EC-NOT-03)."""
    kind = registry.get(key)
    payload = {
        k: str(v) for k, v in (context or {}).items() if k in kind.allowed or k.endswith("_id")
    }
    org_id = getattr(organisation, "pk", organisation)
    later = (
        scheduled_for is not None and scheduled_for > now()
    )  # in-app also waits (e.g. outcome delay)
    created: list[Notification] = []
    for channel in channels:
        full_key = f"{dedupe_key}:{channel}"[:200]
        if Notification.objects.filter(dedupe_key=full_key).exists():
            continue
        try:
            with transaction.atomic():
                n = Notification.objects.create(
                    recipient_user=user,
                    organisation_id=org_id,
                    key=key,
                    channel=channel,
                    payload=payload,
                    dedupe_key=full_key,
                    scheduled_for=scheduled_for,
                    status=(
                        NotificationStatus.DELIVERED
                        if channel == Channel.INAPP and not later
                        else NotificationStatus.QUEUED
                    ),
                    sent_at=now() if channel == Channel.INAPP and not later else None,
                )
        except IntegrityError:  # a concurrent transaction queued the same message
            continue
        created.append(n)
        if channel == Channel.EMAIL:
            emit(EVENT, n, {"notification_id": str(n.pk)}, dedupe_key=f"{EVENT}:{n.pk}")
    return created


def render_inapp(n: Notification) -> str:
    """One-line text for the notification centre (never raises: falls back to the description)."""
    context = {**common_context(n.recipient_user), **n.payload}
    try:
        rendered, _ = services.render_for(n.organisation_id, n.key, context, channel=Channel.INAPP)
        return rendered.text.split("\n--\n")[0].strip()
    except Exception:  # missing template or value: still show something useful
        kind = registry.KINDS.get(n.key)
        return kind.description if kind else n.key


def _local_now(user: Any, at: datetime) -> datetime:
    try:
        tz = zoneinfo.ZoneInfo(getattr(user, "timezone", "") or settings.TIME_ZONE)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        tz = zoneinfo.ZoneInfo("Africa/Harare")
    return at.astimezone(tz)


def quiet_until(user: Any, key: str, at: datetime | None = None) -> datetime | None:
    """When a non-urgent candidate email must wait for the morning (EC-NOT-09), else ``None``."""
    kind = registry.get(key)
    if kind.urgent or kind.audience != "candidate":
        return None
    local = _local_now(user, at or now())
    if QUIET_END <= local.time() < QUIET_START:
        return None
    morning = local.replace(hour=QUIET_END.hour, minute=0, second=0, microsecond=0)
    if local.time() >= QUIET_START:
        morning += timedelta(days=1)
    return morning


def _suppression_reason(n: Notification) -> str:
    user = n.recipient_user
    if not user.is_active:
        return "recipient_inactive"
    if not user.is_email_verified:
        return "email_unverified"  # EC-ACC-07: only ever to a verified address
    if EmailSuppression.objects.filter(email=user.email.strip().lower()).exists():
        return "address_suppressed"
    application_id = n.payload.get("application_id")
    if application_id and n.key not in ALLOWED_AFTER_WITHDRAWAL:
        from apps.applications.models import Application, Status

        status = (
            Application.objects.unscoped()
            .filter(pk=application_id)
            .values_list("status", flat=True)
            .first()
        )
        if status == Status.WITHDRAWN:
            return "application_withdrawn"  # EC-NOT-04
    return ""


def _finish(n: Notification, status: str, **fields: Any) -> str:
    Notification.objects.filter(pk=n.pk).update(status=status, **fields)
    return status


def message_id(n: Notification) -> str:
    domain = settings.DEFAULT_FROM_EMAIL.rsplit("@", 1)[-1].strip("> ") or "mhrs.local"
    return f"<{n.pk}@{domain}>"


def deliver(notification_id: Any) -> str:
    """Send one queued email. Returns the resulting status, or ``skipped``/``deferred``."""
    with transaction.atomic():
        n = (
            Notification.objects.select_for_update(skip_locked=True)
            .select_related("recipient_user")
            .filter(pk=notification_id, channel=Channel.EMAIL, status=NotificationStatus.QUEUED)
            .first()
        )
        if n is None:
            return "skipped"  # already sent, being sent, suppressed or unknown
        reason = _suppression_reason(n)
        if reason:
            n.status, n.last_error = NotificationStatus.SUPPRESSED, reason
            n.save(update_fields=["status", "last_error", "updated_at"])
            return NotificationStatus.SUPPRESSED
        wait = quiet_until(n.recipient_user, n.key)
        if n.scheduled_for and n.scheduled_for > now():
            wait = max(wait, n.scheduled_for) if wait else n.scheduled_for
        if wait is not None:
            n.scheduled_for = wait
            n.save(update_fields=["scheduled_for", "updated_at"])
            return "deferred"
        n.status = NotificationStatus.SENDING
        n.attempts += 1
        n.save(update_fields=["status", "attempts", "updated_at"])

    context = {**common_context(n.recipient_user), **n.payload}
    try:
        rendered, template = services.render_for(n.organisation_id, n.key, context)
    except Exception as exc:  # no template or a missing value: permanent failure
        logger.error("notification_render_failed", extra={"notification_id": str(n.pk)})
        return _finish(n, NotificationStatus.FAILED, last_error=f"render: {exc}"[:500])
    msg = EmailMultiAlternatives(
        subject=rendered.subject,
        body=rendered.text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[n.recipient_user.email],
        headers={
            "Message-ID": message_id(n),
            "Auto-Submitted": "auto-generated",
            "X-MHRS-Notification": n.key,
        },
    )
    msg.attach_alternative(rendered.html, "text/html")
    try:
        msg.send(fail_silently=False)
    except Exception as exc:  # SMTP/SES outage: back to the queue, the task retries
        _finish(n, NotificationStatus.QUEUED, last_error=f"{type(exc).__name__}: {exc}"[:500])
        raise DeliveryError(str(exc)) from exc
    logger.info("notification_sent", extra={"notification_id": str(n.pk), "key": n.key})
    return _finish(
        n,
        NotificationStatus.SENT,
        sent_at=now(),
        template=template,
        provider_message_id=message_id(n),
        last_error="",
    )


def mark_failed(notification_id: Any, error: str) -> None:
    Notification.objects.filter(
        pk=notification_id, status__in=[NotificationStatus.QUEUED, NotificationStatus.SENDING]
    ).update(status=NotificationStatus.FAILED, last_error=error[:500])


def due_ids(limit: int = 200) -> list[str]:
    """Deferred emails whose time has come, plus rows a crashed worker left in ``sending``.
    Scheduled in-app notifications that are due are published here as well."""
    moment = now()
    Notification.objects.filter(
        channel=Channel.INAPP,
        status=NotificationStatus.QUEUED,
        scheduled_for__lte=moment,
    ).update(status=NotificationStatus.DELIVERED, sent_at=moment)
    Notification.objects.filter(
        status=NotificationStatus.SENDING, updated_at__lt=moment - STALE_SENDING
    ).update(status=NotificationStatus.QUEUED)
    rows = Notification.objects.filter(
        channel=Channel.EMAIL,
        status=NotificationStatus.QUEUED,
        scheduled_for__isnull=False,
        scheduled_for__lte=moment,
    ).values_list("pk", flat=True)[:limit]
    return [str(pk) for pk in rows]
