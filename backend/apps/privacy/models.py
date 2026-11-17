"""Consent and notice records (docs/03 consent_records, docs/06 §4 - CDPA purpose limitation).

Every record names the purpose, the exact notice version the person saw, and when. A record is
never edited: withdrawing consent sets ``withdrawn_at``; a new decision is a new record.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, TenantModel


class Purpose(models.TextChoices):
    APPLICATION_PROCESSING = "application_processing", "Processing my application"
    AI_ASSISTED_SCREENING = "ai_assisted_screening", "AI-assisted screening (human decides)"
    TALENT_POOL = "talent_pool", "Keeping my details for future vacancies"
    MARKETING = "marketing", "Marketing"
    SMS = "sms", "SMS messages"
    WHATSAPP = "whatsapp", "WhatsApp messages"


class ConsentRecord(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consent_records"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    notice_version = models.CharField(max_length=80)
    granted = models.BooleanField()
    granted_at = models.DateTimeField()
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    ip_trunc = models.CharField(max_length=50, blank=True, default="")
    context = models.JSONField(default=dict, blank=True, help_text="e.g. {application_id}")

    class Meta:
        ordering = ("-granted_at",)
        indexes = [models.Index(fields=["user", "purpose"], name="consent_user_purpose_idx")]

    def __str__(self) -> str:
        return f"{self.purpose} {'granted' if self.granted else 'declined'} ({self.notice_version})"


# ------------------------------------------------------------------------ notices (EC-PRV-09)
class PrivacyNotice(BaseModel):
    """The exact wording of every privacy notice version shown to candidates. ``organisation``
    NULL = platform notice. Consent records point at ``version``; the text is kept for proof."""

    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    version = models.CharField(max_length=80)
    text = models.TextField()
    first_shown_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-first_shown_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "version"],
                name="uniq_privacy_notice_version",
                nulls_distinct=False,
            )
        ]


# ------------------------------------------------------------------------ rights (CDPA)
class RightsRequest(BaseModel):
    """A data subject's request (docs/03 rights_requests). ``organisation`` NULL = platform-wide
    (the person's account); otherwise routed to that employer. Never "rejected": a request the
    controller cannot fulfil is ``declined`` with the legal reason."""

    class Type(models.TextChoices):
        ACCESS = "access", "Access to my data"
        EXPORT = "export", "Export my data"
        CORRECTION = "correction", "Correct my data"
        DELETION = "deletion", "Delete my data"
        OBJECTION_AUTOMATED = "objection_automated", "Object to automated processing"
        CONSENT_WITHDRAWAL = "consent_withdrawal", "Withdraw consent"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        VERIFYING = "verifying", "Waiting for email confirmation"
        IN_PROGRESS = "in_progress", "In progress"
        ON_HOLD = "on_hold", "On hold (legal hold)"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined with reason"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    type = models.CharField(max_length=24, choices=Type.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    details = EncryptedTextField(blank=True, default="")  # the person's own words
    reference = models.CharField(max_length=24, unique=True)
    verify_token_hash = models.CharField(max_length=64, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField()
    reminded_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolution = EncryptedTextField(blank=True, default="")
    statement = EncryptedTextField(blank=True, default="")  # EC-PRV-04: candidate's own statement
    export_document_id = models.UUIDField(null=True, blank=True)
    export_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organisation", "status", "due_at"], name="rights_org_status_idx"),
            models.Index(fields=["user", "type"], name="rights_user_type_idx"),
        ]


# ------------------------------------------------------------------------ retention / holds
class RetentionRun(BaseModel):
    organisation = models.ForeignKey(
        "organisations.Organisation", on_delete=models.CASCADE, related_name="+"
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    dry_run = models.BooleanField(default=True)

    class Meta:
        ordering = ("-started_at",)


class LegalHold(TenantModel):
    """Data under a legal hold is never deleted or anonymised until the hold is released
    (EC-PRV-01). Targets: an application, a candidate (user) or a whole vacancy."""

    class Target(models.TextChoices):
        APPLICATION = "application", "Application"
        CANDIDATE = "candidate", "Candidate"
        JOB = "job", "Vacancy"

    target_type = models.CharField(max_length=16, choices=Target.choices)
    target_id = models.UUIDField()
    reason = EncryptedTextField()
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    placed_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-placed_at",)
        indexes = [models.Index(fields=["target_type", "target_id"], name="legal_hold_target_idx")]
