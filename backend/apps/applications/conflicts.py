"""Conflicts of interest (P08-T09; EC-REV-11, EC-ACC-09/10).

* A reviewer who knows an applicant (relative, friend, former colleague) declares a conflict: the
  application disappears from their lists and pages, any assignment to them is removed, and the
  declaration is audited. It cannot be undone by the reviewer (an HR manager can see it).
* Staff never see their own application (403 + audit when they try) and lose access to every
  application of a vacancy they applied to; staff applications are visible to HR managers and
  organisation admins only.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.audit import services as audit
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.core.time import now
from apps.organisations import rbac
from apps.organisations.models import Membership

from .models import Application, ConflictDeclaration, Status

PRIVATE = (Status.DRAFT, Status.ABANDONED)


def restrict(membership: Membership, qs: QuerySet[Application]) -> QuerySet[Application]:
    """Apply the conflict-of-interest rules to a visibility queryset."""
    user_id = membership.user_id
    org_id = membership.organisation_id
    # own applications, and every application of a vacancy the person applied to (EC-ACC-10)
    applied_jobs = (
        Application.objects.for_org(org_id)
        .filter(candidate_user_id=user_id)
        .exclude(status__in=PRIVATE)
        .values("job_id")
    )
    qs = qs.exclude(Q(candidate_user_id=user_id) | Q(job_id__in=applied_jobs))
    # declared conflicts (EC-REV-11)
    declared = ConflictDeclaration.objects.for_org(org_id).filter(user_id=user_id)
    qs = qs.exclude(pk__in=declared.values("application_id"))
    # staff applications: HR managers and organisation admins only (EC-ACC-10)
    if membership.role not in rbac.ADMIN_HR:
        staff = Membership.objects.for_org(org_id).values("user_id")
        qs = qs.exclude(candidate_user_id__in=staff)
    return qs


def guard_own(membership: Membership, application_id: Any) -> None:
    """403 + audit when staff try to open their own application (EC-ACC-09)."""
    own = (
        Application.objects.for_org(membership.organisation_id)
        .filter(pk=application_id, candidate_user_id=membership.user_id)
        .exists()
    )
    if own:
        audit.record(
            actor=membership.user,
            action="application.conflict_blocked",
            target=("application", str(application_id)),
            organisation=membership.organisation_id,
            reason="own application",
        )
        raise PermissionDeniedError(
            code="conflict_of_interest",
            message="You cannot review your own application.",
        )


def declare(membership: Membership, actor: Any, application_id: Any, *, reason: str) -> Any:
    from .ats import _visible

    text = (reason or "").strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error",
            "Briefly say why (kept confidential to HR).",
            details={"reason": ["At least 5 characters."]},
        )
    app = _visible(membership, application_id, lock=True)
    try:
        with transaction.atomic():
            row = ConflictDeclaration.objects.create(
                organisation_id=app.organisation_id,
                application=app,
                user=actor,
                reason=text[:2000],
                declared_at=now(),
            )
            if app.assigned_recruiter_id == actor.pk:
                app.assigned_recruiter = None
                app.save(update_fields=["assigned_recruiter", "updated_at"])
            audit.record(
                actor=actor,
                action="application.conflict_declared",
                target=app,
                organisation=app.organisation_id,
                reason=text,
            )
    except IntegrityError:
        row = ConflictDeclaration.objects.for_org(app.organisation_id).get(
            application=app, user=actor
        )
    return row
