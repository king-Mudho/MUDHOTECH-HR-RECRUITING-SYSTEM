"""Interviews and scorecards (docs/01 M16, docs/03 v1.1; P12-T01).

* ``ScorecardTemplate`` - the criteria panelists rate (1-5 + evidence notes), derived from the
  vacancy's criteria (plus competencies HR adds). Frozen once a scorecard is submitted against it.
* ``Interview`` - one interview of one application at a stage (screening call, technical,
  final...): mode, place or link, time in UTC plus the IANA timezone it was arranged in
  (EC-INT-02), status.
* ``InterviewSlot`` - times HR offers for candidate self-booking; at most one slot per interview
  is booked (partial unique constraint; booking locks the rows, P12-T02).
* ``InterviewPanelist`` - staff members (memberships) on the panel; they see only their interviews.
* ``Scorecard`` - one per panelist per interview; others' scorecards stay hidden until a panelist
  has submitted their own (EC-INT-04). AI scores are hidden from panelists by default (ADR-019).

A no-show is recorded as a status, never as a rejection (EC-INT-03). Notes are personal data about
the candidate: encrypted at rest (ADR-011).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel


class InterviewMode(models.TextChoices):
    IN_PERSON = "in_person", "In person"
    VIDEO = "video", "Video call"
    PHONE = "phone", "Phone"


class InterviewStatus(models.TextChoices):
    PROPOSED = "proposed", "Proposed (waiting for a booking)"
    SCHEDULED = "scheduled", "Scheduled"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No-show"


OPEN_STATUSES = (InterviewStatus.PROPOSED, InterviewStatus.SCHEDULED)


class PanelRole(models.TextChoices):
    LEAD = "lead", "Lead"
    MEMBER = "member", "Member"


class Recommendation(models.TextChoices):
    STRONG_YES = "strong_yes", "Strong yes"
    YES = "yes", "Yes"
    NO = "no", "No"
    STRONG_NO = "strong_no", "Strong no"


class ScorecardTemplate(TenantModel):
    """``criteria``: ``[{"key", "title", "description", "source_criterion_id"}]``, display order."""

    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="scorecard_templates"
    )
    job_version = models.ForeignKey(
        "jobs.JobVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=120)
    criteria = models.JSONField(default=list)
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the first scorecard is submitted; then immutable.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta(TenantModel.Meta):
        indexes = [models.Index(fields=["organisation", "job"], name="scorecard_tpl_job_idx")]

    def __str__(self) -> str:
        return self.name

    @property
    def keys(self) -> list[str]:
        return [str(c["key"]) for c in self.criteria]


class Interview(TenantModel):
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="interviews"
    )
    stage = models.CharField(max_length=60, help_text="e.g. Screening call, Technical, Final")
    mode = models.CharField(max_length=16, choices=InterviewMode.choices)
    location = models.CharField(max_length=300, blank=True, default="")
    video_link = models.URLField(max_length=500, blank=True, default="")
    duration_minutes = models.PositiveSmallIntegerField(
        default=45, validators=[MinValueValidator(5), MaxValueValidator(480)]
    )
    starts_at = models.DateTimeField(null=True, blank=True)  # UTC; null until a slot is booked
    ends_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Harare", help_text="IANA zone")
    status = models.CharField(
        max_length=16, choices=InterviewStatus.choices, default=InterviewStatus.PROPOSED
    )
    scorecard_template = models.ForeignKey(
        ScorecardTemplate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="interviews",
    )
    instructions = models.TextField(
        blank=True, default="", help_text="Shown to the candidate (what to bring, parking...)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status_reason = models.CharField(max_length=500, blank=True, default="")  # cancel / reschedule
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_1h_sent_at = models.DateTimeField(null=True, blank=True)
    sequence = models.PositiveIntegerField(
        default=0, help_text="ICS SEQUENCE: incremented on every reschedule/cancel"
    )
    lock_version = models.PositiveIntegerField(default=0)

    class Meta(TenantModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(starts_at__isnull=True, ends_at__isnull=True)
                | Q(starts_at__isnull=False, ends_at__gt=F("starts_at")),
                name="interview_times_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status="scheduled") | Q(starts_at__isnull=False),
                name="interview_scheduled_has_time",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "starts_at"], name="interview_org_starts_idx"),
            models.Index(fields=["application", "status"], name="interview_app_status_idx"),
            models.Index(fields=["status", "starts_at"], name="interview_status_starts_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.stage} ({self.get_status_display()})"


class InterviewSlot(TenantModel):
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="slots")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    booked = models.BooleanField(default=False)
    booked_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ("starts_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="slot_times_valid"
            ),
            models.UniqueConstraint(
                fields=["interview"],
                condition=Q(booked=True),
                name="slot_one_booking_per_interview",
            ),
            models.UniqueConstraint(fields=["interview", "starts_at"], name="slot_unique_start"),
        ]

    def __str__(self) -> str:
        return f"{self.starts_at:%Y-%m-%d %H:%M} UTC"


class InterviewPanelist(TenantModel):
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="panelists")
    membership = models.ForeignKey(
        "organisations.Membership", on_delete=models.PROTECT, related_name="interview_panels"
    )
    role = models.CharField(max_length=8, choices=PanelRole.choices, default=PanelRole.MEMBER)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["interview", "membership"], name="panelist_unique"),
        ]
        indexes = [models.Index(fields=["membership"], name="panelist_membership_idx")]

    def __str__(self) -> str:
        return f"{self.membership_id} ({self.role})"


class Scorecard(TenantModel):
    """``scores``: ``{key: 1..5}``; ``criterion_notes``: encrypted JSON ``{key: text}``."""

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="scorecards")
    panelist = models.ForeignKey(
        InterviewPanelist, on_delete=models.CASCADE, related_name="scorecards"
    )
    template = models.ForeignKey(ScorecardTemplate, on_delete=models.PROTECT, related_name="+")
    scores = models.JSONField(default=dict, blank=True)
    criterion_notes = EncryptedTextField(blank=True, default="")
    overall = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    recommendation = models.CharField(
        max_length=16, choices=Recommendation.choices, blank=True, default=""
    )
    notes = EncryptedTextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["interview", "panelist"], name="scorecard_unique"),
            models.CheckConstraint(
                condition=Q(overall__isnull=True) | Q(overall__gte=1, overall__lte=5),
                name="scorecard_overall_1_5",
            ),
            models.CheckConstraint(
                condition=Q(submitted_at__isnull=True)
                | (Q(overall__isnull=False) & ~Q(recommendation="")),
                name="scorecard_submitted_complete",
            ),
        ]

    def __str__(self) -> str:
        return f"Scorecard {self.panelist_id} ({'submitted' if self.submitted_at else 'draft'})"
