"""Applications (SRS M07 & §3.3, docs/03 applications).

* A draft *is* an ``Application`` in status ``draft`` (autosaved, resumable across devices).
* ``active_key`` carries the duplicate policy into the database: for ``one_active`` /
  ``allow_resubmit_replace`` jobs it is ``"<job>:<candidate>"`` while the application is active and
  NULL otherwise; a partial unique constraint then makes a second active application impossible
  even under concurrent requests (EC-APP-02).
* Status changes only go through ``applications.services.transition`` (state machine, P04-T06),
  which writes an append-only ``ApplicationStatusEvent`` + audit event.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    PROCESSING = "processing", "Processing"
    PROCESSING_ERROR = "processing_error", "Processing problem"
    NEEDS_INFORMATION = "needs_information", "Clarification requested"
    UNDER_REVIEW = "under_review", "Under review"
    ON_HOLD = "on_hold", "On hold"
    SHORTLISTED = "shortlisted", "Shortlisted"
    INTERVIEW = "interview", "Interview"
    OFFER = "offer", "Offer"
    HIRED = "hired", "Hired"
    NOT_SELECTED = "not_selected", "Not selected"
    WITHDRAWN = "withdrawn", "Withdrawn"
    OFFER_DECLINED = "offer_declined", "Offer declined"
    ABANDONED = "abandoned", "Abandoned"


# Statuses that free the candidate to apply again under the one_active policy.
INACTIVE_STATUSES = frozenset({Status.WITHDRAWN, Status.ABANDONED})
TERMINAL_STATUSES = frozenset(
    {Status.HIRED, Status.NOT_SELECTED, Status.WITHDRAWN, Status.OFFER_DECLINED, Status.ABANDONED}
)


class Application(TenantModel):
    job = models.ForeignKey("jobs.Job", on_delete=models.PROTECT, related_name="applications")
    job_version = models.ForeignKey(
        "jobs.JobVersion", on_delete=models.PROTECT, related_name="applications"
    )
    candidate_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    candidate_profile_snapshot = models.JSONField(default=dict, blank=True)
    reference = models.CharField(max_length=40, unique=True, null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    source = models.JSONField(default=dict, blank=True, help_text="utm_* and referrer")
    channel = models.CharField(max_length=32, blank=True, default="web")
    contact = models.JSONField(default=dict, blank=True, help_text="Wizard step 1 (draft only).")
    last_step = models.PositiveSmallIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdraw_reason = models.TextField(blank=True, default="")
    assigned_recruiter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_assisted = models.BooleanField(default=False)
    assisted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    consent_record_id = models.UUIDField(null=True, blank=True)
    # docs/06 §4: the candidate asked for a fully manual review (AI evaluation hidden; Phases 7/8).
    objects_to_automated_processing = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    current_evaluation_id = models.UUIDField(null=True, blank=True)
    ai_band = models.CharField(max_length=24, blank=True, default="")
    coverage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    flags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    # NULL = not active; the partial unique constraint relies on NULLs (see module docstring).
    active_key = models.CharField(max_length=80, null=True, blank=True)  # noqa: DJ001
    lock_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organisation", "job", "status"], name="app_org_job_status_idx"),
            models.Index(fields=["organisation", "ai_band"], name="app_org_band_idx"),
            models.Index(fields=["candidate_user", "status"], name="app_candidate_idx"),
            models.Index(fields=["status", "job"], name="app_status_job_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["active_key"],
                condition=Q(active_key__isnull=False),
                name="uniq_active_application",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "abandoned"]) | Q(reference__isnull=False),
                name="application_reference_after_submit",
            ),
        ]

    def __str__(self) -> str:
        return self.reference or f"draft {self.pk}"


class ReferenceCounter(TenantModel):
    """Per-organisation, per-year sequence for ``MHRS-<ORG>-<YYYY>-<NNNNNN>`` (row-locked)."""

    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "year"], name="uniq_reference_counter")
        ]


class DocumentRole(models.TextChoices):
    CV = "cv", "CV"
    COVER_LETTER = "cover_letter", "Cover letter"
    CERTIFICATE = "certificate", "Certificate"
    TRANSCRIPT = "transcript", "Transcript"
    PORTFOLIO = "portfolio", "Portfolio"
    OTHER = "other", "Other"


class ApplicationDocument(TenantModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=16, choices=DocumentRole.choices)
    required_doc_key = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["application", "document"], name="uniq_application_doc")
        ]


class AppendOnlyError(RuntimeError):
    """Status events are history: they are never updated or deleted."""


class ApplicationStatusEvent(TenantModel):
    class ActorType(models.TextChoices):
        HUMAN = "human", "Person"
        SYSTEM = "system", "System"

    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name="status_events"
    )
    from_status = models.CharField(max_length=24, blank=True, default="")
    to_status = models.CharField(max_length=24)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_type = models.CharField(max_length=8, choices=ActorType.choices)
    reason_code = models.CharField(max_length=40, blank=True, default="")
    reason_text = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField()

    class Meta:
        ordering = ("application", "at")
        indexes = [models.Index(fields=["application", "at"], name="app_event_timeline_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Application status events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise AppendOnlyError("Application status events are append-only.")
