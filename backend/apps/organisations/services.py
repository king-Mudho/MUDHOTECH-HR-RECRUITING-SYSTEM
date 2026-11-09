"""Organisation, team and invitation services (FR-M02, FR-M03).

All writes run in ``transaction.atomic()``, lock the rows they guard, write an audit event and send
email through the outbox. Roles and organisation ids are always derived server-side.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils.text import slugify

from apps.accounts.models import User, normalize_email_address
from apps.audit import services as audit
from apps.core import time
from apps.core.exceptions import ConflictError, DomainError, NotFoundError, StaleVersionError
from apps.core.sanitize import sanitize_html

from .models import (
    PRIVILEGED_ROLES,
    Invitation,
    Membership,
    Organisation,
    OrganisationPolicy,
    Role,
)

INVITATION_TTL = timedelta(days=7)  # FR-M03-01

ORG_EDITABLE_FIELDS = (
    "name",
    "legal_name",
    "registration_number",
    "industry",
    "size_band",
    "country",
    "city",
    "address",
    "website",
    "description",
    "default_timezone",
    "default_currency",
)
POLICY_EDITABLE_FIELDS = (
    "privacy_notice",
    "retention_months",
    "duplicate_policy",
    "shortlist_dual_control",
    "rubric_dual_control",
    "ai_enabled",
    "llm_enabled",
    "blind_review_default",
    "notification_delay_minutes",
    "hide_ai_from_panelists",
    "rights_request_sla_days",
)


# ----------------------------------------------------------------------------------- errors
class LastAdminError(ConflictError):
    code = "conflict.last_admin"
    default_message = "An organisation must keep at least one active company admin."


class AlreadyMemberError(ConflictError):
    code = "already_member"
    default_message = "This person is already a member of the organisation."


class InvitationGoneError(DomainError):
    status_code = 410

    def __init__(self, status: str) -> None:
        messages: dict[str, str] = {
            Invitation.Status.EXPIRED: "This invitation has expired. Ask your admin to resend it.",
            Invitation.Status.REVOKED: "This invitation was revoked.",
            Invitation.Status.ACCEPTED: "This invitation has already been used.",
        }
        super().__init__(
            code=f"invitation_{status}",
            message=messages.get(status, "This invitation is no longer valid."),
        )


class InvitationEmailMismatchError(DomainError):
    code = "invitation_email_mismatch"
    status_code = 403
    default_message = (
        "This invitation was sent to a different email address. Sign in with the invited "
        "address (verified), or ask the admin to allow a different email."
    )


# ----------------------------------------------------------------------------------- helpers
def _snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def unique_slug(name: str) -> str:
    """EC-ORG-01: two orgs may share a name; slugs are de-duplicated (``acme``, ``acme-2``...)."""
    base = slugify(name)[:70] or "organisation"
    slug, n = base, 1
    while Organisation.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _privileged(role: str) -> bool:
    return role in PRIVILEGED_ROLES


def _guard_last_admin(org: Organisation, membership: Membership) -> None:
    if membership.role != Role.ORG_ADMIN or not membership.is_active:
        return
    admins = list(
        Membership.objects.for_org(org)
        .select_for_update()
        .filter(role=Role.ORG_ADMIN, status=Membership.Status.ACTIVE)
        .values_list("pk", flat=True)
    )
    if admins == [membership.pk]:
        raise LastAdminError()


# ----------------------------------------------------------------------------- organisations
@transaction.atomic
def create_organisation(*, user: User, data: dict[str, Any], request: Any = None) -> Organisation:
    """Creator becomes org_admin; status pending_verification (D-01)."""
    values = {k: v for k, v in data.items() if k in ORG_EDITABLE_FIELDS}
    values["description"] = sanitize_html(values.get("description"))
    for _attempt in range(3):
        try:
            with transaction.atomic():
                org = Organisation.objects.create(slug=unique_slug(values["name"]), **values)
            break
        except IntegrityError:  # concurrent creation with the same slug: retry
            continue
    else:  # pragma: no cover
        raise ConflictError(message="Could not allocate a unique organisation URL; try again.")
    OrganisationPolicy.objects.create(organisation=org)
    Membership.objects.create(organisation=org, user=user, role=Role.ORG_ADMIN)
    user.start_mfa_grace()
    audit.record(
        actor=user,
        action="organisation.created",
        target=org,
        after=_snapshot(org, ("name", "slug", "status")),
        request=request,
    )
    return org


@transaction.atomic
def update_organisation(
    *, org: Organisation, actor: User, data: dict[str, Any], request: Any = None
) -> Organisation:
    org = Organisation.objects.select_for_update().get(pk=org.pk)
    changed = tuple(k for k in data if k in ORG_EDITABLE_FIELDS)
    before = _snapshot(org, changed)
    for key in changed:
        value = data[key]
        setattr(org, key, sanitize_html(value) if key == "description" else value)
    org.save()
    audit.record(
        actor=actor,
        action="organisation.updated",
        target=org,
        before=before,
        after=_snapshot(org, changed),
        request=request,
    )
    return org


@transaction.atomic
def update_policy(
    *,
    org: Organisation,
    actor: User,
    data: dict[str, Any],
    lock_version: int,
    request: Any = None,
) -> OrganisationPolicy:
    policy = OrganisationPolicy.objects.select_for_update().get(organisation=org)
    if policy.version != lock_version:
        raise StaleVersionError(details={"current_version": policy.version})
    changed = tuple(k for k in data if k in POLICY_EDITABLE_FIELDS)
    before = _snapshot(policy, changed)
    for key in changed:
        setattr(policy, key, data[key])
    policy.version += 1
    policy.save()
    audit.record(
        actor=actor,
        action="organisation.policy_updated",
        target=policy,
        organisation=org,
        before=before,
        after=_snapshot(policy, changed),
        request=request,
    )
    return policy


# ------------------------------------------------------------------------------- invitations
def _send_invitation_email(invitation: Invitation, token: str) -> None:
    from apps.core.email import queue_email

    org = invitation.organisation
    context = {
        "organisation": org,
        "role": invitation.get_role_display(),
        "accept_url": f"{settings.FRONTEND_URL}/invitations/{token}",
        "expires_at": time.to_tz(invitation.expires_at, org.default_timezone),
    }
    subject = render_to_string("organisations/email/invitation_subject.txt", context).strip()
    queue_email(
        invitation.email,
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}{subject}",
        render_to_string("organisations/email/invitation_message.txt", context),
        category="invitation",
        organisation_id=org.pk,
    )


@dataclass
class IssuedInvitation:
    invitation: Invitation
    token: str  # plaintext - only ever emailed; never stored or returned by the API


@transaction.atomic
def invite_member(
    *,
    org: Organisation,
    actor: User,
    email: str,
    role: str,
    vacancy_ids: list[str] | None = None,
    allow_any_email: bool = False,
    request: Any = None,
) -> IssuedInvitation:
    email = normalize_email_address(email)
    if (
        Membership.objects.for_org(org)
        .filter(user__email__iexact=email, status=Membership.Status.ACTIVE)
        .exists()
    ):
        raise AlreadyMemberError()  # EC-ORG-03
    # Replace any open invitation for the same address (single live token per email).
    Invitation.objects.for_org(org).filter(
        email__iexact=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=time.now())
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        organisation=org,
        email=email,
        role=role,
        token_hash=hash_token(token),
        expires_at=time.now() + INVITATION_TTL,
        invited_by=actor,
        vacancy_ids=[str(v) for v in (vacancy_ids or [])],
        allow_any_email=allow_any_email,
    )
    _send_invitation_email(invitation, token)
    audit.record(
        actor=actor,
        action="invitation.created",
        target=invitation,
        after={"email": email, "role": role, "allow_any_email": allow_any_email},
        request=request,
    )
    return IssuedInvitation(invitation, token)


@transaction.atomic
def resend_invitation(
    *, invitation: Invitation, actor: User, request: Any = None
) -> IssuedInvitation:
    invitation = Invitation.objects.unscoped().select_for_update().get(pk=invitation.pk)
    if invitation.accepted_at or invitation.revoked_at:
        raise InvitationGoneError(invitation.status)
    token = secrets.token_urlsafe(32)  # rotate: old links stop working
    invitation.token_hash = hash_token(token)
    invitation.expires_at = time.now() + INVITATION_TTL
    invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])
    _send_invitation_email(invitation, token)
    audit.record(actor=actor, action="invitation.resent", target=invitation, request=request)
    return IssuedInvitation(invitation, token)


@transaction.atomic
def revoke_invitation(*, invitation: Invitation, actor: User, request: Any = None) -> Invitation:
    invitation = Invitation.objects.unscoped().select_for_update().get(pk=invitation.pk)
    if invitation.accepted_at:
        raise InvitationGoneError(Invitation.Status.ACCEPTED)
    if not invitation.revoked_at:
        invitation.revoked_at = time.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
        audit.record(actor=actor, action="invitation.revoked", target=invitation, request=request)
    return invitation


def get_invitation_by_token(token: str) -> Invitation:
    invitation = (
        Invitation.objects.unscoped()
        .select_related("organisation")
        .filter(token_hash=hash_token(token))
        .first()
    )
    if invitation is None:
        raise NotFoundError(message="This invitation link is not valid.")
    return invitation


@transaction.atomic
def accept_invitation(*, token: str, user: User, request: Any = None) -> Membership:
    found = get_invitation_by_token(token)
    invitation = Invitation.objects.unscoped().select_for_update().get(pk=found.pk)
    if invitation.status != Invitation.Status.PENDING:
        raise InvitationGoneError(invitation.status)  # EC-ORG-04
    email_matches = normalize_email_address(user.email) == invitation.email
    if not user.is_email_verified or not (email_matches or invitation.allow_any_email):
        raise InvitationEmailMismatchError()  # EC-ORG-05
    org = invitation.organisation
    membership = Membership.objects.for_org(org).select_for_update().filter(user=user).first()
    if membership and membership.is_active:
        raise AlreadyMemberError()
    if membership:  # re-joining after deactivation
        membership.role = invitation.role
        membership.status = Membership.Status.ACTIVE
        membership.deactivated_at = None
        membership.invited_by = invitation.invited_by
        membership.joined_at = time.now()
        membership.save()
    else:
        membership = Membership.objects.create(
            organisation=org, user=user, role=invitation.role, invited_by=invitation.invited_by
        )
    invitation.accepted_at = time.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    if _privileged(membership.role):
        user.start_mfa_grace()
    audit.record(
        actor=user,
        action="invitation.accepted",
        target=membership,
        after={"role": membership.role, "invitation_id": str(invitation.pk)},
        request=request,
    )
    return membership


# ------------------------------------------------------------------------------- memberships
ReassignmentProvider = Callable[[Membership], list[dict[str, Any]]]
_REASSIGNMENT_PROVIDERS: list[ReassignmentProvider] = []


def register_reassignment_provider(fn: ReassignmentProvider) -> ReassignmentProvider:
    """EC-ORG-09: apps with assignable work (jobs in Phase 03) list what needs a new owner."""
    if fn not in _REASSIGNMENT_PROVIDERS:
        _REASSIGNMENT_PROVIDERS.append(fn)
    return fn


@dataclass
class DeactivationResult:
    membership: Membership
    sessions_revoked: int
    needs_reassignment: list[dict[str, Any]] = field(default_factory=list)


@transaction.atomic
def change_role(
    *, membership: Membership, actor: User, role: str, reason: str = "", request: Any = None
) -> Membership:
    membership = Membership.objects.unscoped().select_for_update().get(pk=membership.pk)
    if membership.role == role:
        return membership
    if role != Role.ORG_ADMIN:
        _guard_last_admin(membership.organisation, membership)  # EC-ORG-02
    before = {"role": membership.role}
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    if _privileged(role):
        membership.user.start_mfa_grace()
    audit.record(
        actor=actor,
        action="membership.role_changed",
        target=membership,
        before=before,
        after={"role": role},
        reason=reason,
        request=request,
    )
    return membership


@transaction.atomic
def deactivate_member(
    *, membership: Membership, actor: User, reason: str = "", request: Any = None
) -> DeactivationResult:
    from apps.accounts.sessions import revoke_all_sessions

    membership = Membership.objects.unscoped().select_for_update().get(pk=membership.pk)
    if not membership.is_active:
        return DeactivationResult(membership, 0)
    _guard_last_admin(membership.organisation, membership)
    membership.status = Membership.Status.DEACTIVATED
    membership.deactivated_at = time.now()
    membership.save(update_fields=["status", "deactivated_at", "updated_at"])
    revoked = revoke_all_sessions(membership.user)  # EC-ACC-12
    pending = [item for provider in _REASSIGNMENT_PROVIDERS for item in provider(membership)]
    audit.record(
        actor=actor,
        action="membership.deactivated",
        target=membership,
        after={"sessions_revoked": revoked, "needs_reassignment": len(pending)},
        reason=reason,
        request=request,
    )
    return DeactivationResult(membership, revoked, pending)


class OrgUnverifiedError(DomainError):
    code = "org_unverified"
    status_code = 422
    default_message = (
        "Your organisation must be verified before vacancies can be published. "
        "You can keep preparing drafts in the meantime."
    )


def assert_can_publish(org: Organisation) -> None:
    """D-01 / EC-ORG-08: only verified, active organisations may publish vacancies.

    Suspended/closed organisations are read-only (``org_suspended``); unverified ones may draft but
    not publish (``org_unverified``). Called by the jobs publish service (Phase 03).
    """
    from apps.core.exceptions import OrgSuspendedError

    if org.is_read_only:
        raise OrgSuspendedError()
    if org.status != Organisation.Status.ACTIVE or org.verified_at is None:
        raise OrgUnverifiedError()


def user_has_privileged_membership(user: User) -> bool:
    return (
        Membership.objects.unscoped()
        .filter(user=user, status=Membership.Status.ACTIVE, role__in=list(PRIVILEGED_ROLES))
        .exists()
    )
