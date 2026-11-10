"""SES bounce / complaint feedback through Amazon SNS (P05-T04, EC-NOT-01).

The webhook is unauthenticated by nature, so every message must prove itself:

* the topic must be on ``settings.SES_SNS_TOPIC_ARNS`` (empty list = endpoint refuses everything);
* the signing certificate must be served over HTTPS from an Amazon SNS host;
* the RSA signature over SNS's canonical string must verify (SignatureVersion 1 or 2).

A hard bounce or a complaint puts the address on the suppression list (delivery checks it before
every send) and marks the notification that bounced as failed so staff can see it. Soft bounces
are only logged; SES retries them itself.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import logging
import re
import urllib.request
from typing import Any
from urllib.parse import urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.db import transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError
from apps.core.time import now

from .models import EmailSuppression, Notification, NotificationStatus, SuppressionReason

logger = logging.getLogger("mhrs.notifications")

SNS_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")
NOTIFICATION_FIELDS = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
SUBSCRIPTION_FIELDS = (
    "Message",
    "MessageId",
    "SubscribeURL",
    "Timestamp",
    "Token",
    "TopicArn",
    "Type",
)
MAX_BODY = 256 * 1024


class InvalidSnsMessageError(DomainError):
    code = "invalid_signature"
    status_code = 403
    default_message = "The message could not be verified."


def _is_sns_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(SNS_HOST.match(parsed.hostname or ""))


@functools.lru_cache(maxsize=8)
def fetch_certificate(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310  # nosec B310
        return bytes(resp.read(64 * 1024))


def canonical_string(message: dict[str, Any]) -> bytes:
    fields = NOTIFICATION_FIELDS if message.get("Type") == "Notification" else SUBSCRIPTION_FIELDS
    parts: list[str] = []
    for name in fields:
        if name == "Subject" and message.get("Subject") is None:
            continue
        if name not in message:
            raise InvalidSnsMessageError()
        parts += [name, str(message[name])]
    return ("\n".join(parts) + "\n").encode()


def verify(message: dict[str, Any]) -> None:
    """Raise :class:`InvalidSnsMessageError` unless the message is a genuine one for our topics."""
    allowed = set(getattr(settings, "SES_SNS_TOPIC_ARNS", []) or [])
    if not allowed or message.get("TopicArn") not in allowed:
        raise InvalidSnsMessageError()
    cert_url = str(message.get("SigningCertURL") or "")
    if not _is_sns_url(cert_url):
        raise InvalidSnsMessageError()
    algorithm: hashes.HashAlgorithm = (
        hashes.SHA256() if str(message.get("SignatureVersion")) == "2" else hashes.SHA1()  # noqa: S303  # nosec B303
    )
    try:
        certificate = x509.load_pem_x509_certificate(fetch_certificate(cert_url))
        key = certificate.public_key()
        if not isinstance(key, rsa.RSAPublicKey):
            raise InvalidSnsMessageError()
        key.verify(
            base64.b64decode(str(message.get("Signature") or "")),
            canonical_string(message),
            padding.PKCS1v15(),
            algorithm,
        )
    except InvalidSnsMessageError:
        raise
    except (InvalidSignature, ValueError, OSError) as exc:
        raise InvalidSnsMessageError() from exc


def confirm_subscription(message: dict[str, Any]) -> None:
    url = str(message.get("SubscribeURL") or "")
    if not _is_sns_url(url):
        raise InvalidSnsMessageError()
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310  # nosec B310
        resp.read(1024)
    logger.info("sns_subscription_confirmed", extra={"topic": message.get("TopicArn")})


def _fingerprint(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:16]


@transaction.atomic
def suppress(email: str, reason: str, detail: str = "") -> bool:
    """Add ``email`` to the suppression list. Returns ``True`` when it was not there before."""
    address = email.strip().lower()
    if not address or "@" not in address:
        return False
    _, created = EmailSuppression.objects.get_or_create(
        email=address, defaults={"reason": reason, "at": now(), "detail": detail[:300]}
    )
    if created:
        audit.record(
            action="email.suppressed",
            target=("email", _fingerprint(address)),  # no address in the audit trail
            after={"reason": reason},
            actor_type="system",
        )
    return created


def has_delivery_problem(user: Any) -> bool:
    """Drives the in-app banner asking the person to update their email address."""
    return EmailSuppression.objects.filter(
        email=user.email.strip().lower(),
        reason__in=[SuppressionReason.BOUNCE, SuppressionReason.COMPLAINT],
    ).exists()


def _mark_bounced(feedback: dict[str, Any], note: str) -> None:
    mail = feedback.get("mail") or {}
    ours = (mail.get("commonHeaders") or {}).get("messageId") or ""
    if ours:
        Notification.objects.filter(provider_message_id=ours).update(
            status=NotificationStatus.FAILED, last_error=note[:500]
        )


def handle_feedback(feedback: dict[str, Any]) -> int:
    """Process one SES bounce/complaint notification. Returns addresses newly suppressed."""
    kind = feedback.get("notificationType") or feedback.get("eventType") or ""
    count = 0
    if kind == "Bounce":
        bounce = feedback.get("bounce") or {}
        if bounce.get("bounceType") != "Permanent":
            logger.info("email_soft_bounce", extra={"bounce_type": bounce.get("bounceType")})
            return 0
        for recipient in bounce.get("bouncedRecipients") or []:
            detail = str(recipient.get("diagnosticCode") or bounce.get("bounceSubType") or "")
            count += suppress(
                str(recipient.get("emailAddress") or ""), SuppressionReason.BOUNCE, detail
            )
        _mark_bounced(feedback, "bounced")
    elif kind == "Complaint":
        complaint = feedback.get("complaint") or {}
        for recipient in complaint.get("complainedRecipients") or []:
            count += suppress(
                str(recipient.get("emailAddress") or ""),
                SuppressionReason.COMPLAINT,
                str(complaint.get("complaintFeedbackType") or ""),
            )
        _mark_bounced(feedback, "complaint")
    return count


def handle_sns(raw: bytes) -> str:
    """Entry point for the webhook body. Returns what was done (for the response/log)."""
    if len(raw) > MAX_BODY:
        raise InvalidSnsMessageError()
    try:
        message = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidSnsMessageError() from exc
    if not isinstance(message, dict):
        raise InvalidSnsMessageError()
    verify(message)
    kind = message.get("Type")
    if kind == "SubscriptionConfirmation":
        confirm_subscription(message)
        return "subscribed"
    if kind == "Notification":
        try:
            feedback = json.loads(str(message.get("Message") or ""))
        except ValueError:
            return "ignored"
        if not isinstance(feedback, dict):
            return "ignored"
        return f"suppressed:{handle_feedback(feedback)}"
    return "ignored"
