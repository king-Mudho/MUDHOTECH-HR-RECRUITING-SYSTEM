"""Data-subject rights requests (P09-T02; CDPA [Ch. 12:07] s.14-17, SI 155 of 2024; docs/06 §4).

Lifecycle:  verifying --(email link)--> received --(staff)--> in_progress --> completed | declined
            (legal hold: on_hold until released, EC-PRV-01)

* The requester re-authenticates (password) and then confirms by email, so a stolen session alone
  cannot export or delete someone's data.
* A request is routed to one employer (``organisation``) or to the platform (account-level,
  ``organisation`` NULL). "All employers" creates one request per employer the person applied to,
  plus the platform one.
* Due date = confirmation time + the organisation's ``rights_request_sla_days`` (platform: 30).
  A daily task reminds the organisation's admins 5 days before the due date and when overdue.
* Staff never "reject": they decline with the legal reason, and the requester is told.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from apps.core.time import now

from .models import RightsRequest

Status = RightsRequest.Status
Type = RightsRequest.Type
PLATFORM_SLA_DAYS = 30
REMIND_BEFORE = timedelta(days=5)
OPEN = (Status.VERIFYING, Status.RECEIVED, Status.IN_PROGRESS, Status.ON_HOLD)
TOKEN_TTL = timedelta(hours=48)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _reference() -> str:
    return f"RR-{now():%Y}-{secrets.token_hex(3).upper()}"


def _sla_days(organisation_id: Any) -> int:
    if organisation_id is None:
        return PLATFORM_SLA_DAYS
    from apps.organisations.models import OrganisationPolicy

    days = (
        OrganisationPolicy.objects.filter(organisation_id=organisation_id)
        .values_list("rights_request_sla_days", flat=True)
        .first()
    )
    return int(days or PLATFORM_SLA_DAYS)


def employers_of(user: Any) -> list[Any]:
    """Organisations the person has a (non-draft) application with."""
    from apps.applications.models import Application

    return list(
        Application.objects.unscoped()
        .filter(candidate_user=user)
        .exclude(status__in=["draft", "abandoned"])
        .values_list("organisation_id", flat=True)
        .distinct()
    )


def _org_name(organisation_id: Any) -> str:
    if organisation_id is None:
        return str(getattr(settings, "APP_NAME", "MUDHOTECH HR RECRUITING SYSTEM"))
    from apps.organisations.models import Organisation

    return str(
        Organisation.objects.filter(pk=organisation_id).values_list("name", flat=True).first()
    )


# ------------------------------------------------------------------------ requester side
def create(
    user: Any,
    *,
    type: str,
    password: str,
    scope: str,
    organisation_id: Any = None,
    details: str = "",
) -> list[RightsRequest]:
    """``scope``: ``organisation`` (one employer), ``platform`` (my account) or ``all``."""
    from apps.notifications import delivery as notifications

    if type not in Type.values:
        raise DomainError("validation_error", "Unknown request type.", details={"type": [type]})
    if not user.check_password(password):  # re-authentication
        raise PermissionDeniedError(
            code="reauth_failed",
            message="That password is not correct.",
            details={"password": ["Incorrect."]},
        )
    employers = employers_of(user)
    if scope == "organisation":
        if str(organisation_id) not in {str(o) for o in employers}:
            raise DomainError(
                "validation_error",
                "Choose an employer you applied to.",
                details={"organisation_id": ["Not one of your employers."]},
            )
        targets: list[Any] = [organisation_id]
    elif scope == "platform":
        targets = [None]
    elif scope == "all":
        targets = [*employers, None]
    else:
        raise DomainError("validation_error", "Unknown scope.", details={"scope": [scope]})
    if type == Type.CORRECTION and len(details.strip()) < 5:
        raise DomainError(
            "validation_error",
            "Say what should be corrected.",
            details={"details": ["Required for a correction."]},
        )
    token = secrets.token_urlsafe(32)
    created = []
    with transaction.atomic():
        for org in targets:
            row = RightsRequest.objects.create(
                user=user,
                organisation_id=org,
                type=type,
                status=Status.VERIFYING,
                details=details.strip()[:4000],
                reference=_reference(),
                verify_token_hash=_hash(token),
                due_at=now() + timedelta(days=_sla_days(org)),
            )
            audit.record(
                actor=user,
                action="privacy.rights_request_created",
                target=("rights_request", str(row.pk)),
                organisation=org,
                after={"type": type, "reference": row.reference},
            )
            created.append(row)
        notifications.notify(
            user,
            "rights_request_confirm",
            {
                "request_reference": ", ".join(r.reference for r in created),
                "request_type": Type(type).label,
                "confirm_url": f"{settings.FRONTEND_URL}/candidate/privacy/confirm?token={token}",
            },
            dedupe_key=f"rights_request_confirm:{created[0].pk}",
            channels=("email",),
        )
    return created


def confirm(user: Any, token: str) -> list[RightsRequest]:
    """The email link: starts the clock and routes the requests to their handlers."""
    from apps.notifications import delivery as notifications

    rows = list(
        RightsRequest.objects.filter(
            user=user, verify_token_hash=_hash(token), status=Status.VERIFYING
        )
    )
    if not rows:
        raise NotFoundError(message="This link is no longer valid.")
    if now() - rows[0].created_at > TOKEN_TTL:
        raise ConflictError(code="conflict.link_expired", message="This link has expired.")
    with transaction.atomic():
        for row in rows:
            row.status = Status.RECEIVED
            row.verified_at = now()
            row.due_at = now() + timedelta(days=_sla_days(row.organisation_id))
            row.verify_token_hash = ""
            row.save(
                update_fields=["status", "verified_at", "due_at", "verify_token_hash", "updated_at"]
            )
            audit.record(
                actor=user,
                action="privacy.rights_request_confirmed",
                target=("rights_request", str(row.pk)),
                organisation=row.organisation_id,
            )
            if row.type in (Type.ACCESS, Type.EXPORT):  # P09-T03: build the bundle now
                from apps.core import outbox

                outbox.emit(
                    "privacy.export_requested",
                    ("rights_request", str(row.pk)),
                    {"request_id": str(row.pk)},
                    dedupe_key=f"privacy.export_requested:{row.pk}",
                    organisation_id=row.organisation_id,
                )
            for handler in handlers(row.organisation_id):
                notifications.notify(
                    handler,
                    "rights_request_received",
                    {
                        "organisation_name": _org_name(row.organisation_id),
                        "request_reference": row.reference,
                        "request_type": Type(row.type).label,
                        "due_date": f"{row.due_at:%d %B %Y}",
                        "privacy_url": f"{settings.FRONTEND_URL}/hr/settings/privacy",
                    },
                    dedupe_key=f"rights_request_received:{row.pk}:{handler.pk}",
                    organisation=row.organisation_id,
                )
    return rows


def mine(user: Any) -> QuerySet[RightsRequest]:
    return RightsRequest.objects.filter(user=user).order_by("-created_at")


def add_statement(user: Any, request_id: Any, statement: str) -> RightsRequest:
    """EC-PRV-04: after a declined correction the person may add their own statement."""
    row = RightsRequest.objects.filter(user=user, pk=request_id).first()
    if row is None:
        raise NotFoundError()
    if row.type != Type.CORRECTION or row.status != Status.DECLINED:
        raise ConflictError(
            code="conflict.statement_not_allowed",
            message="A statement can be added to a declined correction request.",
        )
    row.statement = statement.strip()[:4000]
    row.save(update_fields=["statement", "updated_at"])
    audit.record(
        actor=user,
        action="privacy.rights_statement_added",
        target=("rights_request", str(row.pk)),
        organisation=row.organisation_id,
    )
    return row


# ------------------------------------------------------------------------ handler side
def handlers(organisation_id: Any) -> list[Any]:
    """Who handles requests: the organisation's admins, or platform admins for the platform."""
    if organisation_id is None:
        from apps.accounts.models import PlatformRole, User

        return list(User.objects.filter(platform_role=PlatformRole.PLATFORM_ADMIN, is_active=True))
    from apps.organisations.models import Membership, Role

    return [
        m.user
        for m in Membership.objects.for_org(organisation_id)
        .filter(role=Role.ORG_ADMIN, status=Membership.Status.ACTIVE)
        .select_related("user")
    ]


def for_org(organisation_id: Any) -> QuerySet[RightsRequest]:
    return RightsRequest.objects.filter(organisation_id=organisation_id).exclude(
        status=Status.VERIFYING
    )


def _get(organisation_id: Any, request_id: Any, *, lock: bool = False) -> RightsRequest:
    qs = for_org(organisation_id)
    if lock:
        qs = qs.select_for_update()
    row = qs.filter(pk=request_id).first()
    if row is None:
        raise NotFoundError()
    return row


ACTIONS = {
    "start": ((Status.RECEIVED, Status.ON_HOLD), Status.IN_PROGRESS),
    "hold": ((Status.RECEIVED, Status.IN_PROGRESS), Status.ON_HOLD),
    "complete": ((Status.RECEIVED, Status.IN_PROGRESS), Status.COMPLETED),
    "decline": ((Status.RECEIVED, Status.IN_PROGRESS, Status.ON_HOLD), Status.DECLINED),
}


def act(
    organisation_id: Any, actor: Any, request_id: Any, *, action: str, resolution: str = ""
) -> RightsRequest:
    from apps.notifications import delivery as notifications

    if action not in ACTIONS:
        raise DomainError("validation_error", "Unknown action.", details={"action": [action]})
    sources, target = ACTIONS[action]
    text = resolution.strip()
    if action in ("decline", "hold", "complete") and len(text) < 5:
        raise DomainError(
            "validation_error",
            "Explain the outcome (the requester sees it).",
            details={"resolution": ["At least 5 characters."]},
        )
    with transaction.atomic():
        row = _get(organisation_id, request_id, lock=True)
        if row.status not in sources:
            raise ConflictError(
                code="conflict.invalid_transition",
                message="This request cannot be changed that way now.",
                details={"from": row.status, "action": action},
            )
        if (
            target == Status.COMPLETED
            and row.type in (Type.ACCESS, Type.EXPORT)
            and not row.export_document_id
        ):
            raise ConflictError(
                code="conflict.export_not_ready",
                message="The export is still being prepared. Try again shortly.",
            )
        before = row.status
        row.status = target
        row.handled_by = actor
        if text:
            row.resolution = text[:4000]
        if target in (Status.COMPLETED, Status.DECLINED):
            row.completed_at = now()
        row.save(update_fields=["status", "handled_by", "resolution", "completed_at", "updated_at"])
        audit.record(
            actor=actor,
            action=f"privacy.rights_request_{action}",
            target=("rights_request", str(row.pk)),
            organisation=organisation_id,
            before={"status": before},
            after={"status": target},
            reason=text,
        )
        if row.user is not None:
            notifications.notify(
                row.user,
                "rights_request_update",
                {
                    "organisation_name": _org_name(organisation_id),
                    "request_reference": row.reference,
                    "request_status": Status(target).label,
                },
                dedupe_key=f"rights_request_update:{row.pk}:{target}",
                organisation=organisation_id,
            )
    return row


# ------------------------------------------------------------------------ reminders (beat)
def send_reminders() -> int:
    from apps.notifications import delivery as notifications

    moment = now()
    due = RightsRequest.objects.filter(
        status__in=[Status.RECEIVED, Status.IN_PROGRESS, Status.ON_HOLD],
        due_at__lte=moment + REMIND_BEFORE,
        reminded_at__isnull=True,
    )
    sent = 0
    for row in due:
        with transaction.atomic():
            for handler in handlers(row.organisation_id):
                notifications.notify(
                    handler,
                    "rights_request_due",
                    {
                        "organisation_name": _org_name(row.organisation_id),
                        "request_reference": row.reference,
                        "due_date": f"{row.due_at:%d %B %Y}",
                        "privacy_url": f"{settings.FRONTEND_URL}/hr/settings/privacy",
                    },
                    dedupe_key=f"rights_request_due:{row.pk}:{handler.pk}",
                    organisation=row.organisation_id,
                )
            RightsRequest.objects.filter(pk=row.pk).update(reminded_at=moment)
            sent += 1
    return sent
