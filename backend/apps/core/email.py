"""Transactional email via the outbox (ADR-006).

``queue_email`` records an ``email.requested`` outbox event inside the caller's transaction; the
``core.send_email`` consumer delivers it through the configured Django email backend (Mailpit in
dev, SES/SMTP in prod). A Redis or SMTP outage therefore never loses a verification/reset email -
the relay retries. Bodies are encrypted at rest in the outbox payload because they may contain
one-time links.

Phase 05 (notifications) builds templating, preferences, suppression and delivery logs on top.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

from . import crypto
from .models import OutboxEvent
from .outbox import emit, idempotent_consumer

logger = logging.getLogger("mhrs.email")

EVENT = "email.requested"


def queue_email(
    to: str | Sequence[str],
    subject: str,
    text: str,
    html: str | None = None,
    *,
    category: str = "transactional",
    organisation_id: uuid.UUID | str | None = None,
    dedupe_key: str | None = None,
    from_email: str | None = None,
    headers: dict[str, str] | None = None,
) -> OutboxEvent:
    recipients = [to] if isinstance(to, str) else list(to)
    payload: dict[str, Any] = {
        "to": recipients,
        "subject": subject,
        "text_enc": crypto.encrypt(text),
        "html_enc": crypto.encrypt(html) if html else None,
        "from_email": from_email or settings.DEFAULT_FROM_EMAIL,
        "headers": headers or {},
        "category": category,
    }
    with transaction.atomic():
        return emit(
            EVENT,
            ("email", uuid.uuid4()),
            payload,
            dedupe_key=dedupe_key,
            organisation_id=organisation_id,
        )


def build_message(payload: dict[str, Any]) -> EmailMultiAlternatives:
    msg = EmailMultiAlternatives(
        subject=payload["subject"],
        body=crypto.decrypt(payload["text_enc"]),
        from_email=payload.get("from_email") or settings.DEFAULT_FROM_EMAIL,
        to=payload["to"],
        headers=payload.get("headers") or {},
    )
    if payload.get("html_enc"):
        msg.attach_alternative(crypto.decrypt(payload["html_enc"]), "text/html")
    return msg


@idempotent_consumer("core.send_email", events=[EVENT])
def send_email(event: OutboxEvent) -> int:
    sent = build_message(event.payload).send(fail_silently=False)
    logger.info(
        "email_sent", extra={"event_id": str(event.id), "category": event.payload.get("category")}
    )
    return sent
