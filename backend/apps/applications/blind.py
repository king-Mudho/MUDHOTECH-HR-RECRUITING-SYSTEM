"""Blind review mode (P08-T04, FR-M12-04, ADR-013, EC-REV-06).

When the organisation's ``blind_review_default`` is on, every HR response about an applicant is
redacted on the server - the browser never receives the name, email, phone, address or original
file names, so CSS cannot leak them. Reviewers see a stable alias ("Candidate #4F2A"). Original
files (which show the person's name) cannot be downloaded until identity is revealed.

"Reveal identity" is per reviewer and per application, needs a reason and is audited; it is
permanent for that reviewer. Organisations may also mask institution names in the extracted
education claims (``blind_mask_institutions``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.organisations.models import OrganisationPolicy

from .models import Application, IdentityReveal

HIDDEN_INSTITUTION = "Institution (hidden in blind review)"


def policy_flags(organisation_id: Any) -> tuple[bool, bool]:
    """(blind mode on, institution masking on) for an organisation."""
    row = (
        OrganisationPolicy.objects.filter(organisation_id=organisation_id)
        .values_list("blind_review_default", "blind_mask_institutions")
        .first()
    )
    return (bool(row[0]), bool(row[1])) if row else (True, False)


def alias(application_id: Any) -> str:
    """Stable, non-identifying label for an application."""
    digest = hashlib.sha256(f"mhrs-blind:{application_id}".encode()).hexdigest()
    return f"Candidate #{digest[:4].upper()}"


def revealed_ids(user: Any, organisation_id: Any, application_ids: Iterable[Any]) -> set[Any]:
    ids = list(application_ids)
    if not ids or user is None:
        return set()
    return set(
        IdentityReveal.objects.for_org(organisation_id)
        .filter(user=user, application_id__in=ids)
        .values_list("application_id", flat=True)
    )


class BlindView:
    """Per-request helper: which applications this user sees blind."""

    def __init__(self, user: Any, organisation_id: Any, application_ids: Iterable[Any]):
        self.enabled, self.mask_institutions = policy_flags(organisation_id)
        ids = list(application_ids)
        self.revealed = revealed_ids(user, organisation_id, ids) if self.enabled else set()

    def hidden(self, application_id: Any) -> bool:
        return self.enabled and application_id not in self.revealed

    def name(self, app: Application) -> str:
        if self.hidden(app.pk):
            return alias(app.pk)
        snap = app.candidate_profile_snapshot or {}
        name = " ".join(p for p in (snap.get("first_name"), snap.get("last_name")) if p)
        return name or str(snap.get("email") or "")

    def email(self, app: Application) -> str:
        return (
            ""
            if self.hidden(app.pk)
            else str((app.candidate_profile_snapshot or {}).get("email") or "")
        )

    def candidate(self, app: Application) -> dict[str, Any]:
        if self.hidden(app.pk):
            return {"alias": alias(app.pk)}
        return dict(app.candidate_profile_snapshot or {})

    def documents(self, app: Application, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.hidden(app.pk):
            return documents
        return [
            {
                **d,
                "filename": f"Document {i} ({d.get('required_doc_key') or d.get('role')})",
                "available": False,  # the original file shows the name: reveal first
            }
            for i, d in enumerate(documents, start=1)
        ]

    def masks_institutions(self, application_id: Any) -> bool:
        return self.mask_institutions and self.hidden(application_id)


def is_hidden_for(user: Any, app: Application) -> bool:
    return BlindView(user, app.organisation_id, [app.pk]).hidden(app.pk)


def reveal(membership: Any, actor: Any, application_id: Any, *, reason: str) -> IdentityReveal:
    from .ats import _visible

    app = _visible(membership, application_id)
    text = (reason or "").strip()
    if len(text) < 5:
        raise DomainError(
            "validation_error",
            "Say why you need to see who this applicant is.",
            details={"reason": ["At least 5 characters."]},
        )
    existing = (
        IdentityReveal.objects.for_org(app.organisation_id)
        .filter(application=app, user=actor)
        .first()
    )
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            row = IdentityReveal.objects.create(
                organisation_id=app.organisation_id,
                application=app,
                user=actor,
                reason=text[:2000],
                at=now(),
            )
            audit.record(
                actor=actor,
                action="application.identity_revealed",
                target=app,
                organisation=app.organisation_id,
                reason=text,
            )
    except IntegrityError:  # double click
        row = IdentityReveal.objects.for_org(app.organisation_id).get(application=app, user=actor)
    return row
