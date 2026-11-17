"""Break-glass support access (P09-T06, EC-PRV-07).

1. A platform support person requests access to one organisation with a reason (<= 4 hours).
2. A *different* platform admin approves it; the clock starts then.
3. While active, the organisation context middleware lets that person **read** the
   organisation's HR endpoints (``X-Org-Id``) as an HR manager would see them; any write is 403.
4. Every request is written to the access log and the organisation's admins see the grant, its
   reason and every access (``/hr/support-access``) - plus a banner while it is active.
5. Grants expire on their own and can be revoked by either side at any time.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.accounts.models import PlatformRole
from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from apps.core.time import now

from .models import Membership, Organisation, Role, SupportAccessGrant

MAX_MINUTES = 240
SUPPORT_ROLES = (PlatformRole.PLATFORM_SUPPORT, PlatformRole.PLATFORM_ADMIN)


def request_access(
    user: Any, organisation_id: Any, *, reason: str, minutes: int
) -> SupportAccessGrant:
    if getattr(user, "platform_role", None) not in SUPPORT_ROLES:
        raise PermissionDeniedError(message="Only platform support can request access.")
    if not 5 <= minutes <= MAX_MINUTES:
        raise DomainError(
            "validation_error",
            f"Access lasts between 5 and {MAX_MINUTES} minutes.",
            details={"minutes": [f"Between 5 and {MAX_MINUTES}."]},
        )
    if len(reason.strip()) < 10:
        raise DomainError(
            "validation_error",
            "Explain what needs investigating (the organisation will see it).",
            details={"reason": ["At least 10 characters."]},
        )
    org = Organisation.objects.filter(pk=organisation_id).first()
    if org is None:
        raise NotFoundError()
    with transaction.atomic():
        grant = SupportAccessGrant.objects.create(
            platform_user=user,
            organisation=org,
            reason=reason.strip()[:2000],
            requested_at=now(),
            duration_minutes=minutes,
        )
        audit.record(
            actor=user,
            action="support_access.requested",
            target=grant,
            organisation=org.pk,
            reason=reason,
            after={"minutes": minutes},
        )
    return grant


def approve(approver: Any, grant_id: Any) -> SupportAccessGrant:
    if getattr(approver, "platform_role", None) != PlatformRole.PLATFORM_ADMIN:
        raise PermissionDeniedError(message="Only a platform admin can approve support access.")
    with transaction.atomic():
        grant = SupportAccessGrant.objects.select_for_update().filter(pk=grant_id).first()
        if grant is None:
            raise NotFoundError()
        if grant.platform_user_id == approver.pk:
            raise PermissionDeniedError(
                code="self_approval_forbidden",
                message="Someone other than the requester must approve.",
            )
        if grant.approved_at is not None or grant.revoked_at is not None:
            raise ConflictError(
                code="already_processed", message="This request was already handled."
            )
        grant.approved_by = approver
        grant.approved_at = now()
        grant.expires_at = grant.approved_at + timedelta(minutes=grant.duration_minutes)
        grant.save(update_fields=["approved_by", "approved_at", "expires_at", "updated_at"])
        audit.record(
            actor=approver,
            action="support_access.approved",
            target=grant,
            organisation=grant.organisation_id,
            after={"expires_at": grant.expires_at.isoformat()},
        )
    return grant


def revoke(actor: Any, grant_id: Any, *, organisation_id: Any = None) -> SupportAccessGrant:
    with transaction.atomic():
        qs = SupportAccessGrant.objects.select_for_update().filter(
            pk=grant_id, revoked_at__isnull=True
        )
        if organisation_id is not None:  # an organisation admin revoking access to their org
            qs = qs.filter(organisation_id=organisation_id)
        grant = qs.first()
        if grant is None:
            raise NotFoundError()
        grant.revoked_at, grant.revoked_by = now(), actor
        grant.save(update_fields=["revoked_at", "revoked_by", "updated_at"])
        audit.record(
            actor=actor,
            action="support_access.revoked",
            target=grant,
            organisation=grant.organisation_id,
        )
    return grant


def active_grant(user: Any, organisation_id: Any) -> SupportAccessGrant | None:
    if getattr(user, "platform_role", None) not in SUPPORT_ROLES:
        return None
    moment = now()
    return (
        SupportAccessGrant.objects.filter(
            platform_user=user,
            organisation_id=organisation_id,
            approved_at__isnull=False,
            revoked_at__isnull=True,
            expires_at__gt=moment,
        )
        .select_related("organisation")
        .first()
    )


def support_membership(user: Any, grant: SupportAccessGrant) -> Membership:
    """An in-memory, read-only HR-manager context for the grant's organisation."""
    membership = Membership(
        user=user,
        organisation=grant.organisation,
        role=Role.HR_MANAGER,
        status=Membership.Status.ACTIVE,
    )
    membership.support_grant = grant  # type: ignore[attr-defined]
    return membership


def grants_for(organisation_id: Any) -> QuerySet[SupportAccessGrant]:
    return SupportAccessGrant.objects.filter(organisation_id=organisation_id).select_related(
        "platform_user", "approved_by"
    )
