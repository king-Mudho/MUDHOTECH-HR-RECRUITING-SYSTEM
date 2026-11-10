"""Uploaded documents (docs/03 documents, docs/06 §3).

Flow: ``UploadSession`` (presigned PUT into the private *quarantine* bucket) -> ``complete`` ->
``Document`` with ``scan_status=pending`` -> scan pipeline (P04-T03) promotes clean files to the
*documents* bucket or rejects them. Files are never served from quarantine and never public.
Documents belong to the uploading user; employers reach them only through an application link.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Purpose(models.TextChoices):
    CV = "cv", "CV / résumé"
    SUPPORTING = "supporting", "Supporting document"
    MESSAGE_ATTACHMENT = "message_attachment", "Message attachment"
    OFFER_LETTER = "offer_letter", "Offer letter"


class UploadSession(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for upload"
        UPLOADED = "uploaded", "Uploaded"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="upload_sessions"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    declared_name = models.CharField(max_length=200)
    declared_mime = models.CharField(max_length=120)
    declared_size = models.PositiveBigIntegerField()
    object_key = models.CharField(max_length=300, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField(db_index=True)
    document = models.OneToOneField(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="upload_session",
    )
    rejected_reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["status", "expires_at"], name="upload_status_expiry_idx")]

    def __str__(self) -> str:
        return f"{self.purpose} upload {self.pk} ({self.status})"


class ScanStatus(models.TextChoices):
    PENDING = "pending", "Being checked"
    CLEAN = "clean", "Accepted"
    INFECTED = "infected", "Rejected (security)"
    ERROR = "error", "Could not be checked"
    SKIPPED = "skipped", "Not scanned"


class Document(BaseModel):
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    original_filename = models.CharField(max_length=200)
    declared_mime = models.CharField(max_length=120, blank=True, default="")
    mime_detected = models.CharField(max_length=120, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    storage_key = models.CharField(max_length=300)
    bucket = models.CharField(max_length=16, default="quarantine")  # quarantine | documents
    page_count = models.PositiveIntegerField(null=True, blank=True)
    scan_status = models.CharField(
        max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING, db_index=True
    )
    scan_engine_version = models.CharField(max_length=100, blank=True, default="")
    scanned_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=200, blank=True, default="")
    encrypted = models.BooleanField(default=False)
    language_detected = models.CharField(max_length=10, blank=True, default="")
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["owner_user", "sha256"], name="document_owner_sha_idx")]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def is_available(self) -> bool:
        return self.scan_status == ScanStatus.CLEAN and self.deleted_at is None
