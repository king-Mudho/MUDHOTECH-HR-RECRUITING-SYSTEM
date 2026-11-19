"""SMS and WhatsApp notifications (P15-T04, ADR-032).

* **Opt-in only**: a candidate gets SMS/WhatsApp copies of action-needed messages (interview
  invitations and changes, clarification requests, offers) only after explicitly opting in
  (consent purpose ``sms`` / ``whatsapp``) with a mobile number on their profile. Consent is
  re-checked at send time.
* **Approved templates only**: the text/template for each message type is fixed configuration
  (``MOBILE_TEMPLATES``); WhatsApp uses pre-approved template names with positional parameters.
* **STOP / opt-out**: an inbound "STOP" (SMS or WhatsApp) withdraws that channel's consent at once.
* **Receipts and cost**: delivery receipts update the notification; each send is metered on the
  organisation's usage counters.
* Sending happens after commit from the outbox; a provider failure marks the message failed and
  never affects the application or the email/in-app copies.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction

from apps.audit import services as audit
from apps.core.models import OutboxEvent
from apps.core.outbox import emit, idempotent_consumer
from apps.core.time import now

from . import services

EVENT = "notification.mobile"
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "QUIT", "END", "CANCEL", "OPTOUT"}

# Approved templates (WhatsApp names must match templates approved in Meta Business Manager)
MOBILE_TEMPLATES: dict[str, dict[str, Any]] = {
    "interview_invitation": {
        "sms": "{organisation_name}: you are invited to an interview for {job_title}. "
        "Details in your MHRS account. Reply STOP to opt out.",
        "whatsapp": {
            "name": "mhrs_interview_invitation",
            "params": ["organisation_name", "job_title"],
        },
    },
    "interview_reminder": {
        "sms": "Reminder: {job_title} interview {interview_when}. Reply STOP to opt out.",
        "whatsapp": {"name": "mhrs_interview_reminder", "params": ["job_title", "interview_when"]},
    },
    "interview_rescheduled": {
        "sms": "{organisation_name}: your {job_title} interview moved to {interview_when}. "
        "Reply STOP to opt out.",
        "whatsapp": {
            "name": "mhrs_interview_rescheduled",
            "params": ["organisation_name", "job_title", "interview_when"],
        },
    },
    "interview_cancelled": {
        "sms": "{organisation_name}: your {job_title} interview was cancelled. See your MHRS "
        "account. Reply STOP to opt out.",
        "whatsapp": {
            "name": "mhrs_interview_cancelled",
            "params": ["organisation_name", "job_title"],
        },
    },
    "clarification_requested": {
        "sms": "{organisation_name} has a question about your {job_title} application. Please "
        "answer in your MHRS account by {due_date}. Reply STOP to opt out.",
        "whatsapp": {
            "name": "mhrs_clarification_requested",
            "params": ["organisation_name", "job_title", "due_date"],
        },
    },
    "offer_issued": {
        "sms": "{organisation_name} has sent you a job offer for {job_title}. Respond in your "
        "MHRS account by {deadline}. Reply STOP to opt out.",
        "whatsapp": {
            "name": "mhrs_offer_issued",
            "params": ["organisation_name", "job_title", "deadline"],
        },
    },
}


def has_consent(user: Any, channel: str) -> bool:
    from apps.privacy.models import ConsentRecord

    latest = (
        ConsentRecord.objects.filter(user=user, purpose=channel, organisation__isnull=True)
        .order_by("-granted_at")
        .first()
    )
    return bool(latest and latest.granted and latest.withdrawn_at is None)


def phone_for(user: Any) -> str:
    if getattr(user, "phone_e164", ""):
        return str(user.phone_e164)
    profile = getattr(user, "candidate_profile", None)
    return str(getattr(profile, "phone_e164", "") or "")


def queue_mobile_copies(
    user: Any, key: str, payload: dict[str, str], org_id: Any, dedupe: str
) -> None:
    """Called by ``notify`` inside the business transaction: SMS/WhatsApp rows for opted-in
    candidates; the send itself happens after commit."""
    from apps.notifications.models import Channel, Notification, NotificationStatus

    if key not in MOBILE_TEMPLATES or not org_id or not phone_for(user):
        return
    for channel in (Channel.SMS, Channel.WHATSAPP):
        if not has_consent(user, channel):
            continue
        full_key = f"{dedupe}:{channel}"[:200]
        if Notification.objects.filter(dedupe_key=full_key).exists():
            continue
        n = Notification.objects.create(
            recipient_user=user,
            organisation_id=org_id,
            key=key,
            channel=channel,
            payload=payload,
            dedupe_key=full_key,
            status=NotificationStatus.QUEUED,
        )
        emit(EVENT, n, {"notification_id": str(n.pk)}, dedupe_key=f"{EVENT}:{n.pk}")


class _Blank(dict[str, str]):
    """Missing placeholders render as empty text instead of failing."""

    def __missing__(self, key: str) -> str:
        return ""


def _render_sms(key: str, payload: dict[str, str]) -> str:
    template = MOBILE_TEMPLATES[key]["sms"]
    return str(template).format_map(_Blank(payload))


def send(notification_id: Any) -> str:
    from apps.billing.metering import increment
    from apps.notifications.models import Channel, Notification, NotificationStatus

    with transaction.atomic():
        n = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("recipient_user", "recipient_user__candidate_profile")
            .filter(pk=notification_id, status=NotificationStatus.QUEUED)
            .first()
        )
        if n is None or n.channel not in (Channel.SMS, Channel.WHATSAPP):
            return "skipped"
        if not has_consent(n.recipient_user, n.channel):
            n.status, n.last_error = NotificationStatus.SUPPRESSED, "consent withdrawn"
            n.save(update_fields=["status", "last_error", "updated_at"])
            return n.status
        provider = "sms" if n.channel == Channel.SMS else "whatsapp"
        conn = services.org_connection(n.organisation_id, provider)
        phone = phone_for(n.recipient_user)
        if conn is None or not phone:
            n.status = NotificationStatus.SUPPRESSED
            n.last_error = "channel not connected" if conn is None else "no mobile number"
            n.save(update_fields=["status", "last_error", "updated_at"])
            return n.status
        n.status, n.attempts = NotificationStatus.SENDING, n.attempts + 1
        n.save(update_fields=["status", "attempts", "updated_at"])
    reference = str(n.pk)
    payload = dict(n.payload or {})
    if provider == "sms":
        text = _render_sms(n.key, payload)
        reply = services.call(conn, lambda a: a.send(phone, text, reference))  # type: ignore[attr-defined]
        message_id = (reply or {}).get("id", "")
    else:
        spec = MOBILE_TEMPLATES[n.key]["whatsapp"]
        params = [payload.get(p, "") for p in spec["params"]]
        language = settings.LANGUAGE_CODE.split("-")[0] or "en"
        reply = services.call(
            conn,
            lambda a: a.send_template(phone, spec["name"], language, params, reference),  # type: ignore[attr-defined]
        )
        message_id = ((reply or {}).get("messages") or [{}])[0].get("id", "")
    if reply is None:
        Notification.objects.filter(pk=n.pk).update(
            status=NotificationStatus.FAILED, last_error=(conn.last_error or "provider error")[:500]
        )
        return NotificationStatus.FAILED
    Notification.objects.filter(pk=n.pk).update(
        status=NotificationStatus.SENT, sent_at=now(), provider_message_id=str(message_id)[:200]
    )
    increment(n.organisation_id, f"{provider}_messages")
    return NotificationStatus.SENT


@idempotent_consumer("integrations.mobile_send", events=[EVENT])
def on_mobile(event: OutboxEvent) -> None:
    send(event.payload.get("notification_id"))


def record_receipt(message_id: str, status: str) -> int:
    from apps.notifications.models import Notification, NotificationStatus

    mapped = {
        "delivered": NotificationStatus.DELIVERED,
        "read": NotificationStatus.DELIVERED,
        "failed": NotificationStatus.FAILED,
        "undelivered": NotificationStatus.FAILED,
    }.get(status.strip().lower())
    if not message_id or mapped is None:
        return 0
    return Notification.objects.filter(provider_message_id=message_id).update(status=mapped)


def opt_out(phone: str, channel: str, source: str) -> int:
    """Inbound STOP: withdraw the channel consent of every account with that number (the account
    number or the candidate profile number)."""
    from apps.accounts.models import User
    from apps.candidates.models import CandidateProfile
    from apps.privacy.models import ConsentRecord

    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 9:
        return 0
    tail = digits[-9:]

    # numbers are stored normalised (E.164: "+" and digits), so a suffix match is exact enough
    users = set(User.objects.filter(phone_e164__endswith=tail).values_list("pk", flat=True)) | set(
        CandidateProfile.objects.filter(phone_e164__endswith=tail).values_list("user_id", flat=True)
    )
    changed = ConsentRecord.objects.filter(
        user_id__in=users, purpose=channel, withdrawn_at__isnull=True
    ).update(withdrawn_at=now())
    for user_id in users:
        audit.record(
            actor=None,
            actor_type="system",
            action="messaging.opted_out",
            target=("user", str(user_id)),
            after={"channel": channel, "source": source},
        )
    return changed


def set_preferences(
    user: Any, *, sms: bool, whatsapp: bool, ip: str | None = None
) -> dict[str, bool]:
    from apps.core.exceptions import DomainError
    from apps.privacy import services as privacy
    from apps.privacy.models import ConsentRecord

    if (sms or whatsapp) and not phone_for(user):
        raise DomainError(
            "validation_error",
            "Add your mobile number to your profile first.",
            details={"phone": ["Required for SMS or WhatsApp updates."]},
        )
    for channel, wanted in (("sms", sms), ("whatsapp", whatsapp)):
        current = has_consent(user, channel)
        if wanted and not current:
            privacy.record(
                user,
                channel,
                granted=True,
                notice_version=settings.MESSAGING_NOTICE_VERSION,
                ip=ip,
                context={"source": "candidate_settings"},
            )
        elif not wanted and current:
            ConsentRecord.objects.filter(
                user=user, purpose=channel, organisation__isnull=True, withdrawn_at__isnull=True
            ).update(withdrawn_at=now())
    return {"sms": has_consent(user, "sms"), "whatsapp": has_consent(user, "whatsapp")}
