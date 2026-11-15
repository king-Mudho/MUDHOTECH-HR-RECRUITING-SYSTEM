"""Extraction results for application documents (docs/03 resumes, docs/05 §1-7).

``ExtractionRun`` is one engine pass over one document for one application, versioned by engine
and taxonomy (principle 5: re-extraction makes a new run, nothing is overwritten). CV text and
claim payloads are personal data and stored encrypted; the plain columns on ``ExtractedClaim``
hold only what queries and analytics need (type, section, method, confidence, location).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, TenantModel


class RunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class ExtractionRun(TenantModel):
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="extraction_runs"
    )
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT, related_name="extraction_runs"
    )
    engine_version = models.CharField(max_length=20)
    taxonomy_version = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(
        max_length=12, choices=RunStatus.choices, default=RunStatus.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=40, blank=True, default="")
    flags = models.JSONField(default=list, blank=True)
    parser_used = models.CharField(max_length=40, blank=True, default="")
    language = models.CharField(max_length=10, blank=True, default="")
    quality_score = models.FloatField(null=True, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    claim_count = models.PositiveIntegerField(default=0)
    timings_ms = models.JSONField(default=dict, blank=True)
    reused_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )  # EC-DOC-25: identical file already extracted for this candidate
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["application", "document", "engine_version"],
                name="uniq_extraction_run_version",
            )
        ]
        indexes = [models.Index(fields=["organisation", "status"], name="extraction_org_status")]

    def __str__(self) -> str:
        return f"{self.document_id} @ {self.engine_version} ({self.status})"

    @property
    def usable(self) -> bool:
        return self.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL)


class DocumentText(TenantModel):
    """The extracted text and layout (``ai_engine.contracts.DocumentText`` JSON), encrypted."""

    run = models.OneToOneField(ExtractionRun, on_delete=models.CASCADE, related_name="text")
    payload = EncryptedTextField()
    sections = models.JSONField(default=list, blank=True)  # [{kind, heading, page, start, end}]
    char_count = models.PositiveIntegerField(default=0)


class ExtractedClaim(TenantModel):
    run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="claims")
    ordinal = models.PositiveIntegerField()
    claim_type = models.CharField(max_length=20, db_index=True)
    section = models.CharField(max_length=20, blank=True, default="")
    method = models.CharField(max_length=20)
    confidence = models.FloatField()
    evidence = models.CharField(max_length=10, default="explicit")
    excluded_reason = models.CharField(max_length=30, blank=True, default="")
    page = models.PositiveIntegerField(null=True, blank=True)
    char_start = models.PositiveIntegerField(null=True, blank=True)
    char_end = models.PositiveIntegerField(null=True, blank=True)
    skill_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payload = EncryptedTextField()  # ai_engine.contracts.ExtractedClaim JSON (data + source)

    class Meta:
        ordering = ("run", "ordinal")
        constraints = [
            models.UniqueConstraint(fields=["run", "ordinal"], name="uniq_claim_ordinal")
        ]

    @property
    def evaluable(self) -> bool:
        return not self.excluded_reason and self.claim_type not in ("contact", "protected")


class ClaimCorrection(TenantModel):
    """A candidate's correction of an extracted claim (EC-DOC-27). The original is kept."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        DISCARDED = "discarded", "Discarded"

    claim = models.ForeignKey(ExtractedClaim, on_delete=models.CASCADE, related_name="corrections")
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    payload = EncryptedTextField()  # corrected claim data JSON
    note = EncryptedTextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ("-created_at",)


class ResumeParse(BaseModel):
    """A candidate's own preview of what we read from one of their CVs (P06-T13).

    Candidate data, not tenant data: parsed on request against the platform taxonomy, shown only
    to the owner (wizard review step, documents page) and used for "import to profile". The
    employer's evaluation always uses its own ``ExtractionRun`` for the submitted application.
    """

    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resume_parses"
    )
    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="resume_parses"
    )
    engine_version = models.CharField(max_length=20)
    status = models.CharField(max_length=12, choices=RunStatus.choices, default=RunStatus.PENDING)
    error_code = models.CharField(max_length=40, blank=True, default="")
    flags = models.JSONField(default=list, blank=True)
    claims = EncryptedTextField(blank=True, default="")  # JSON list of contract claims
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["document", "engine_version"], name="uniq_resume_parse_version"
            )
        ]
