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

    from .models import PrivacyNotice

    policy = OrganisationPolicy.objects.filter(organisation=org).first()
    text = policy.privacy_notice if policy else ""
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    version = f"org-{getattr(policy, 'version', 0)}-{digest}"
    # keep the exact wording of every version that was shown (EC-PRV-09); idempotent
    PrivacyNotice.objects.get_or_create(
        organisation_id=getattr(org, "pk", org), version=version, defaults={"text": text}
    )
    return version, text


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


# ------------------------------------------------------------------------ legal holds (P09-T01)
def active_holds(organisation_id: Any) -> Any:
    from .models import LegalHold

    return LegalHold.objects.for_org(organisation_id).filter(released_at__isnull=True)


def is_held(
    organisation_id: Any,
    *,
    application_id: Any = None,
    candidate_id: Any = None,
    job_id: Any = None,
) -> bool:
    """True when any active hold covers the application, its candidate or its vacancy."""
    from django.db.models import Q

    query = Q(pk__in=[])
    if application_id is not None:
        query |= Q(target_type="application", target_id=application_id)
    if candidate_id is not None:
        query |= Q(target_type="candidate", target_id=candidate_id)
    if job_id is not None:
        query |= Q(target_type="job", target_id=job_id)
    return active_holds(organisation_id).filter(query).exists()


def place_hold(
    organisation_id: Any, actor: Any, *, target_type: str, target_id: Any, reason: str
) -> Any:
    from django.db import transaction

    from apps.audit import services as audit
    from apps.core.exceptions import DomainError
    from apps.core.time import now

    from .models import LegalHold

    if len(reason.strip()) < 5:
        raise DomainError(
            "validation_error", "Give the legal reason.", details={"reason": ["Required."]}
        )
    with transaction.atomic():
        hold = LegalHold.objects.create(
            organisation_id=organisation_id,
            target_type=target_type,
            target_id=target_id,
            reason=reason.strip()[:2000],
            placed_by=actor,
            placed_at=now(),
        )
        audit.record(
            actor=actor,
            action="privacy.legal_hold_placed",
            target=(target_type, str(target_id)),
            organisation=organisation_id,
        )
    return hold


def release_hold(organisation_id: Any, actor: Any, hold_id: Any) -> Any:
    from django.db import transaction

    from apps.audit import services as audit
    from apps.core.exceptions import NotFoundError
    from apps.core.time import now

    from .models import LegalHold

    with transaction.atomic():
        hold = (
            LegalHold.objects.for_org(organisation_id)
            .select_for_update()
            .filter(pk=hold_id, released_at__isnull=True)
            .first()
        )
        if hold is None:
            raise NotFoundError()
        hold.released_at, hold.released_by = now(), actor
        hold.save(update_fields=["released_at", "released_by", "updated_at"])
        audit.record(
            actor=actor,
            action="privacy.legal_hold_released",
            target=(hold.target_type, str(hold.target_id)),
            organisation=organisation_id,
        )
    return hold
