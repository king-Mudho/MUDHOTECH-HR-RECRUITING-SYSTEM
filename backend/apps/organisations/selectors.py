"""Read-side helpers for organisations (always membership-validated)."""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import QuerySet

from apps.accounts.models import User

from .models import Membership, Organisation


def parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def active_membership(user: User, org_id: Any) -> Membership | None:
    """The caller's active membership in ``org_id`` (None if absent, deactivated or invalid id)."""
    org_uuid = parse_uuid(org_id)
    if org_uuid is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        Membership.objects.for_org(org_uuid)
        .select_related("organisation")
        .filter(user=user, status=Membership.Status.ACTIVE)
        .exclude(organisation__status=Organisation.Status.CLOSED)
        .first()
    )


def memberships_for_user(user: User) -> QuerySet[Membership]:
    # Cross-organisation by design: the user's own memberships (vetted system read).
    return (
        Membership.objects.unscoped()
        .select_related("organisation")
        .filter(user=user, status=Membership.Status.ACTIVE)
        .exclude(organisation__status=Organisation.Status.CLOSED)
        .order_by("organisation__name")
    )
