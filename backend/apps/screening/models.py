"""Screening runs and versioned evaluations (docs/03 screening, docs/05 §10-12).

An ``Evaluation`` is immutable once written (principle 5): re-evaluation writes version n+1 and
marks the previous one ``superseded``. AI output is decision *support*: nothing here changes an
application's consequential status; bands only route work to people.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel


class Trigger(models.TextChoices):
    AUTO = "auto", "Automatic (after CV reading)"
    MANUAL = "manual", "Started by HR"
    REEVALUATION = "reevaluation", "Re-evaluation (new job version)"
    CORRECTION = "correction", "Candidate correction"
    VERIFICATION = "verification", "Human verification"
    CLARIFICATION = "clarification", "Clarification answered"


class ScreeningRun(TenantModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Completed with failures"

    class Scope(models.TextChoices):
        ALL = "all", "All applications"
        PENDING = "pending", "Not yet evaluated"
        FAILED = "failed", "Failed"
        SELECTED = "selected", "Selected applications"

    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="screening_runs")
    job_version = models.ForeignKey("jobs.JobVersion", on_delete=models.PROTECT, related_name="+")
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.MANUAL)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.ALL)
    reason = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    engine_version = models.CharField(max_length=20)
    config_version = models.CharField(max_length=20, blank=True, default="")
    taxonomy_version = models.CharField(max_length=32, blank=True, default="")
    model_ids = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class Evaluation(TenantModel):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        SUPERSEDED = "superseded", "Superseded"

    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="evaluations"
    )
    screening_run = models.ForeignKey(
        ScreeningRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="evaluations"
    )
    job_version = models.ForeignKey("jobs.JobVersion", on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField()
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.AUTO)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUCCEEDED)
    total_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    coverage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    confidence = models.CharField(max_length=8, default="low")
    band = models.CharField(max_length=24, db_index=True)
    band_reasons = models.JSONField(default=list, blank=True)
    flags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    categories = models.JSONField(default=list, blank=True)  # [{key, label, weight, score, ...}]
    essentials = models.JSONField(default=dict, blank=True)
    conflicts = models.JSONField(default=list, blank=True)  # kinds + criterion ids, no CV text
    explanation = EncryptedTextField(blank=True, default="")  # sentences with quoted evidence
    summary = EncryptedTextField(blank=True, default="")  # optional LLM phrasing (grounded)
    clarification_suggestions = models.JSONField(default=list, blank=True)
    input_hash = models.CharField(max_length=64, db_index=True)
    engine_version = models.CharField(max_length=20)
    config_version = models.CharField(max_length=20, blank=True, default="")
    prompt_hash = models.CharField(max_length=32, blank=True, default="")
    llm_used = models.BooleanField(default=False)
    grounding_dropped = models.PositiveIntegerField(default=0)
    reason = models.TextField(blank=True, default="")  # HR's reason for a re-evaluation

    class Meta:
        ordering = ("application", "-version")
        constraints = [
            models.UniqueConstraint(fields=["application", "version"], name="uniq_eval_version")
        ]
        indexes = [models.Index(fields=["organisation", "band"], name="eval_org_band")]


class CriterionResult(TenantModel):
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="criterion_results"
    )
    criterion = models.ForeignKey("jobs.JobCriterion", on_delete=models.PROTECT, related_name="+")
    category = models.CharField(max_length=16)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    assessable = models.BooleanField(default=False)
    evidence_status = models.CharField(max_length=20)
    match_method = models.CharField(max_length=30, default="rule")
    confidence = models.FloatField(default=0)
    rationale = models.CharField(max_length=120, blank=True, default="")  # reason code
    flags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("evaluation", "criterion__order")


class EvaluationEvidence(TenantModel):
    criterion_result = models.ForeignKey(
        CriterionResult, on_delete=models.CASCADE, related_name="evidence"
    )
    claim = models.ForeignKey(
        "resumes.ExtractedClaim", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    question_response = models.ForeignKey(
        "questionnaires.QuestionResponse",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    document_id = models.UUIDField(null=True, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)
    snippet = EncryptedTextField()
    weight = models.FloatField(default=1.0)


class HumanVerification(TenantModel):
    class Decision(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CORRECTED = "corrected", "Corrected"
        REJECTED = "rejected", "Not supported by the evidence"

    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="verifications"
    )
    claim = models.ForeignKey(
        "resumes.ExtractedClaim",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="verifications",
    )
    criterion_result = models.ForeignKey(
        CriterionResult, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    corrected_payload = EncryptedTextField(blank=True, default="")
    note = EncryptedTextField(blank=True, default="")
    at = models.DateTimeField()

    class Meta:
        ordering = ("-at",)
