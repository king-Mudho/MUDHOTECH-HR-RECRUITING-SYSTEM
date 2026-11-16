"""Saved list views (P08-T05): private, per person and organisation."""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.core.exceptions import ConflictError, DomainError, NotFoundError

from .models import SavedView

ALLOWED_PARAMS = {
    "applications": {
        "status",
        "band",
        "min_score",
        "max_score",
        "coverage_lt",
        "flags",
        "essentials",
        "tag",
        "assigned",
        "ordering",
    }
}
MAX_VIEWS = 30


def views_for(membership: Any, scope: str) -> list[SavedView]:
    return list(
        SavedView.objects.for_org(membership.organisation_id).filter(
            user_id=membership.user_id, scope=scope
        )
    )


def create(membership: Any, *, name: str, scope: str, params: dict[str, Any]) -> SavedView:
    allowed = ALLOWED_PARAMS.get(scope)
    if allowed is None:
        raise DomainError("validation_error", "Unknown list.", details={"scope": [scope]})
    clean = {k: str(v)[:200] for k, v in params.items() if k in allowed and v not in (None, "")}
    label = name.strip()[:60]
    if not label:
        raise DomainError("validation_error", "Name the view.", details={"name": ["Required."]})
    if len(views_for(membership, scope)) >= MAX_VIEWS:
        raise DomainError(
            "validation_error",
            f"You can keep up to {MAX_VIEWS} saved views.",
            details={"name": ["Too many saved views."]},
        )
    try:
        with transaction.atomic():
            return SavedView.objects.create(
                organisation_id=membership.organisation_id,
                user_id=membership.user_id,
                scope=scope,
                name=label,
                params=clean,
            )
    except IntegrityError:
        raise ConflictError(
            code="conflict.duplicate_name", message="You already have a view with this name."
        ) from None


def delete(membership: Any, view_id: Any) -> None:
    deleted, _ = (
        SavedView.objects.for_org(membership.organisation_id)
        .filter(pk=view_id, user_id=membership.user_id)
        .delete()
    )
    if not deleted:
        raise NotFoundError()
