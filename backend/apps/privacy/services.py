"""Consent services and notice versions (P04-T10)."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings

from apps.audit.services import truncate_ip
from apps.core.time import now

from .models import ConsentRecord, Purpose


def ai_notice_version() -> str:
    """Version of the platform 'How we use AI' notice shown at /how-we-use-ai."""
    return str(getattr(settings, "AI_NOTICE_VERSION", "2026-11-10"))


def privacy_notice_version(org: Any) -> tuple[str, str]:
    """``(version, text)`` of the employer's candidate privacy notice. The version changes
    whenever the text changes, so a record proves exactly which wording was accepted."""
    from apps.organisations.models import OrganisationPolicy

    policy = OrganisationPolicy.objects.filter(organisation=org).first()
    text = policy.privacy_notice if policy else ""
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"org-{getattr(policy, 'version', 0)}-{digest}", text


def record(
    user: Any,
    purpose: str,
    *,
    granted: bool,
    notice_version: str,
    organisation: Any = None,
    ip: str | None = None,
    context: dict[str, Any] | None = None,
) -> ConsentRecord:
    if purpose not in Purpose.values:
        raise ValueError(f"Unknown consent purpose {purpose!r}")
    return ConsentRecord.objects.create(
        user=user,
        organisation_id=getattr(organisation, "pk", organisation),
        purpose=purpose,
        notice_version=notice_version,
        granted=granted,
        granted_at=now(),
        ip_trunc=truncate_ip(ip),
        context=context or {},
    )
