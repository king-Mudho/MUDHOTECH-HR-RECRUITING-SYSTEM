"""CV library (FR-M06-03): list, set default, remove. Owner-only."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now
from apps.documents.models import Document, ScanStatus

from .models import CandidateProfile
from .services import get_or_create_profile, recompute_completeness


def resumes(user: Any) -> QuerySet[Document]:
    return Document.objects.filter(owner_user=user, purpose="cv", deleted_at__isnull=True).order_by(
        "-created_at"
    )


def _own_cv(user: Any, document_id: Any) -> Document:
    doc = resumes(user).filter(pk=document_id).first()
    if doc is None:
        raise NotFoundError()
    return doc


@transaction.atomic
def set_default(user: Any, document_id: Any) -> CandidateProfile:
    doc = _own_cv(user, document_id)
    if doc.scan_status not in (ScanStatus.CLEAN, ScanStatus.SKIPPED, ScanStatus.PENDING):
        raise DomainError(
            "validation_error",
            "This file was not accepted, so it can't be your default CV.",
            details={"document_id": ["Not accepted."]},
        )
    profile = get_or_create_profile(user)
    profile.default_resume = doc
    profile.save(update_fields=["default_resume", "updated_at"])
    return recompute_completeness(profile)


@transaction.atomic
def remove(user: Any, document_id: Any) -> None:
    """Remove from the library. Files used by a submitted application stay with that application
    (the employer's copy is governed by retention, not by the candidate's library)."""
    from apps.applications.models import ApplicationDocument, Status

    doc = _own_cv(user, document_id)
    in_use = (
        ApplicationDocument.objects.unscoped()
        .filter(document=doc)
        .exclude(application__status__in=[Status.DRAFT, Status.ABANDONED])
        .exists()
    )
    if in_use:
        raise DomainError(
            "conflict.document_in_use",
            "This CV is part of a submitted application and can't be removed from it.",
            status_code=409,
        )
    ApplicationDocument.objects.unscoped().filter(
        document=doc, application__status=Status.DRAFT
    ).delete()
    Document.objects.filter(pk=doc.pk).update(deleted_at=now())
    profile = get_or_create_profile(user)
    if profile.default_resume_id == doc.pk:
        profile.default_resume = None
        profile.save(update_fields=["default_resume", "updated_at"])
        recompute_completeness(profile)
