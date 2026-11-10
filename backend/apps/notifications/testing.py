"""Test helpers: what a user was (or will be) told."""

from __future__ import annotations

from typing import Any

from . import delivery, services
from .models import Channel, Notification


def emails_for(user: Any, key: str | None = None) -> list[str]:
    """Rendered plain-text bodies (subject on the first line) of email notifications queued for
    ``user``, oldest first."""
    rows = Notification.objects.filter(recipient_user=user, channel=Channel.EMAIL)
    if key:
        rows = rows.filter(key=key)
    out = []
    for n in rows.order_by("created_at"):
        context = {**delivery.common_context(user), **n.payload}
        rendered, _ = services.render_for(n.organisation_id, n.key, context)
        out.append(f"{rendered.subject}\n{rendered.text}")
    return out
