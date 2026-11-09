"""DRF permission classes (deny by default, docs/06 §2).

* ``HasOrgRole(*roles)`` / ``HasOrgAction(action)`` - organisation staff endpoints. The organisation
  comes from the URL kwarg ``organisation_id`` (validated against an active membership) or from the
  context middleware. Non-members get **404** (no existence leak, AC of FR-M02); members without
  the role get **403** ``permission_denied``; writes to suspended orgs get **423**.
* ``IsAssignedToJob`` - object-level vacancy assignment check (assignment source plugged in by
  Phase 03; org_admin/hr_manager see all org jobs).
* ``IsPlatformAdmin`` / ``IsPlatformStaff`` - platform roles (support is read-only).
* ``IsCandidateOwner`` - candidates only ever see their own records.
* ``assert_no_conflict_of_interest`` - EC-ACC-09/10 hook (registered checkers, audited 403).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from apps.accounts.models import PlatformRole
from apps.core.exceptions import NotFoundError, OrgSuspendedError, PermissionDeniedError

from . import rbac
from .models import Membership, Role
from .selectors import active_membership

ORG_KWARG = "organisation_id"


def resolve_membership(request: Request, view: Any) -> Membership:
    """Bind ``request.organisation``/``request.membership`` for this view or raise 404/403."""
    user = request.user
    if not user or not user.is_authenticated:
        raise PermissionDeniedError(
            code="not_authenticated", message="Authentication is required.", status_code=401
        )
    org_id = getattr(view, "kwargs", {}).get(ORG_KWARG)
    if org_id is not None:
        membership = active_membership(user, org_id)
        if membership is None:
            raise NotFoundError()
        request.organisation = membership.organisation  # type: ignore[attr-defined]
        request.membership = membership  # type: ignore[attr-defined]
        return membership
    membership = getattr(request, "membership", None)
    if membership is None:
        raise PermissionDeniedError(
            message="An organisation context is required for this endpoint.",
            details={"reason": "org_context_required"},
        )
    return membership


class _OrgPermission(BasePermission):
    allowed_roles: frozenset[str] = frozenset()
    allow_writes_when_suspended = False

    def has_permission(self, request: Request, view: Any) -> bool:
        membership = resolve_membership(request, view)
        if membership.role not in self.allowed_roles:
            raise PermissionDeniedError(details={"required_roles": sorted(self.allowed_roles)})
        if (
            request.method not in SAFE_METHODS
            and membership.organisation.is_read_only
            and not self.allow_writes_when_suspended
        ):
            raise OrgSuspendedError()
        return True


def HasOrgRole(*roles: str) -> type[BasePermission]:  # noqa: N802 (permission factory)
    invalid = set(roles) - set(Role.values)
    if invalid:
        raise ValueError(f"Unknown roles: {sorted(invalid)}")
    return type(
        f"HasOrgRole_{'_'.join(sorted(roles))}",
        (_OrgPermission,),
        {"allowed_roles": frozenset(roles)},
    )


def HasOrgAction(action: str) -> type[BasePermission]:  # noqa: N802 (permission factory)
    roles = rbac.roles_for(action)
    return type(
        f"HasOrgAction_{action.replace('.', '_')}",
        (_OrgPermission,),
        {"allowed_roles": roles, "rbac_action": action},
    )


# ------------------------------------------------------------------------- job assignment
AssignmentChecker = Callable[[Membership, Any], bool]
_assignment_checker: AssignmentChecker | None = None


def register_assignment_checker(fn: AssignmentChecker) -> AssignmentChecker:
    """Phase 03 registers the real check (JobAssignment rows)."""
    global _assignment_checker
    _assignment_checker = fn
    return fn


class IsAssignedToJob(BasePermission):
    """Object permission: org_admin/hr_manager see all org jobs; others only assigned ones."""

    def has_permission(self, request: Request, view: Any) -> bool:
        resolve_membership(request, view)
        return True

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        job = getattr(obj, "job", obj)
        if getattr(job, "organisation_id", None) != membership.organisation_id:
            raise NotFoundError()
        if membership.role in rbac.ADMIN_HR:
            return True
        return bool(_assignment_checker and _assignment_checker(membership, job))


# ------------------------------------------------------------------------------ platform
class IsPlatformAdmin(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "platform_role", None) == PlatformRole.PLATFORM_ADMIN
        )


class IsPlatformStaff(BasePermission):
    """Platform admin (read/write) or platform support (read-only)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        role = getattr(user, "platform_role", None) if user and user.is_authenticated else None
        if role == PlatformRole.PLATFORM_ADMIN:
            return True
        return role == PlatformRole.PLATFORM_SUPPORT and request.method in SAFE_METHODS


# ----------------------------------------------------------------------------- candidates
class IsCandidateOwner(BasePermission):
    """Object permission for candidate-owned records (``candidate_user_id`` or ``user_id``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        owner_id = getattr(obj, "candidate_user_id", None) or getattr(obj, "user_id", None)
        if owner_id != request.user.pk:
            raise NotFoundError()  # never reveal other candidates' records
        return True


# -------------------------------------------------------------------- conflict of interest
ConflictChecker = Callable[[Membership, Any], str | None]
_CONFLICT_CHECKERS: list[ConflictChecker] = []


def register_conflict_checker(fn: ConflictChecker) -> ConflictChecker:
    """A checker returns a reason string when ``membership`` must not act on ``obj``."""
    if fn not in _CONFLICT_CHECKERS:
        _CONFLICT_CHECKERS.append(fn)
    return fn


def assert_no_conflict_of_interest(request: Request, membership: Membership, obj: Any) -> None:
    """EC-ACC-09/10: staff cannot view or evaluate their own application (403 + audit)."""
    for checker in _CONFLICT_CHECKERS:
        reason = checker(membership, obj)
        if reason:
            from apps.audit import services as audit

            audit.record(
                actor=request.user,
                action="conflict_of_interest_blocked",
                target=obj if hasattr(obj, "_meta") else None,
                organisation=membership.organisation,
                reason=reason,
                request=request,
            )
            raise PermissionDeniedError(
                code="conflict_of_interest",
                message="You cannot access this record because of a conflict of interest.",
            )


def _own_application(membership: Membership, obj: Any) -> str | None:
    if getattr(obj, "candidate_user_id", None) == membership.user_id:
        return "staff member is the applicant"
    return None


register_conflict_checker(_own_application)
