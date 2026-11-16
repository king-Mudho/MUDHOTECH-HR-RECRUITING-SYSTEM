"""Shortlists (docs/03 shortlisting, docs/01 M12; P08-T01).

A ``Shortlist`` is HR's proposal for one vacancy version: one ``ShortlistEntry`` per application
with a human decision (``shortlist`` / ``not_selected`` / ``hold``), a structured reason and a
snapshot of what the AI suggested when the person decided (so overrides are measurable and every
decision can be reconstructed). AI bands only pre-fill *suggestions*; entries are decisions only
once a person sets them. Approving a shortlist applies the status changes through the state
machine (P08-T02). Reason codes come from ``apps.applications.DecisionReason`` (shared with the
pipeline's single-application decisions).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel


class Shortlist(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Returned for changes"  # the proposal, never a candidate
        SUPERSEDED = "superseded", "Superseded"
        UNDONE = "undone", "Undone"

    OPEN = (Status.DRAFT, Status.PENDING_APPROVAL)

    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="shortlists")
    job_version = models.ForeignKey("jobs.JobVersion", on_delete=models.PROTECT, related_name="+")
    desired_size = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    # dual control (D-02): every approver is listed; approval completes when enough have signed
    approved_by = ArrayField(models.UUIDField(), default=list, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    return_reason = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    # notifications go out after the organisation's delay (ADR-014); undo is allowed until then
    notify_after = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    undo_reason = models.TextField(blank=True, default="")
    lock_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["job"],
                condition=Q(status__in=["draft", "pending_approval"]),
                name="one_open_shortlist_per_job",
            )
        ]

    def __str__(self) -> str:
        return f"Shortlist {self.pk} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN


class ShortlistEntry(TenantModel):
    class Decision(models.TextChoices):
        UNDECIDED = "undecided", "Not decided yet"
        SHORTLIST = "shortlist", "Shortlist"
        NOT_SELECTED = "not_selected", "Not selected"
        HOLD = "hold", "On hold"

    shortlist = models.ForeignKey(Shortlist, on_delete=models.CASCADE, related_name="entries")
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="shortlist_entries"
    )
    # pre-filled from the AI band; a suggestion only, never a decision
    suggestion = models.CharField(max_length=16, blank=True, default="")
    decision = models.CharField(max_length=16, choices=Decision.choices, default=Decision.UNDECIDED)
    reason = models.ForeignKey(
        "applications.DecisionReason",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reason_code = models.SlugField(max_length=40, blank=True, default="")
    reason_text = models.TextField(blank=True, default="")
    # what the AI said when the person decided (P08-T03)
    evaluation = models.ForeignKey(
        "screening.Evaluation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ai_band_at_decision = models.CharField(max_length=24, blank=True, default="")
    score_at_decision = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    coverage_at_decision = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    override = models.BooleanField(default=False)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)  # status change made on approval
    # why an approved decision was not applied (e.g. the candidate withdrew first, EC-REV-07)
    apply_note = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        ordering = ("shortlist", "-score_at_decision", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["shortlist", "application"], name="uniq_shortlist_application"
            ),
            models.CheckConstraint(
                condition=Q(decision="undecided")
                | (Q(decided_by__isnull=False) & Q(decided_at__isnull=False)),
                name="decision_has_human_actor",
            ),
            models.CheckConstraint(
                condition=~Q(decision="not_selected") | ~Q(reason_code=""),
                name="not_selected_needs_reason",
            ),
        ]
        indexes = [models.Index(fields=["organisation", "decision"], name="sl_entry_org_decision")]

    def __str__(self) -> str:
        return f"{self.application_id}: {self.decision}"
