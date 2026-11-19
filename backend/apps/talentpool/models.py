"""Consent-based talent pool (docs/01 M18, docs/03 talent_pool_entries, P13-T01).

A candidate joins one employer's pool at a time (never cross-organisation). Each entry points at
the ``talent_pool`` consent record that allows it; the entry is searchable by that employer only
while it is ``active`` and not past ``expires_at``. Leaving withdraws the consent; deleting also
removes the entry and HR's tags.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class EntryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    WITHDRAWN = "withdrawn", "Withdrawn"


class TalentPoolEntry(TenantModel):
    candidate_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="talent_pool_entries"
    )
    consent_record = models.ForeignKey(
        "privacy.ConsentRecord", on_delete=models.CASCADE, related_name="+"
    )
    source_application = models.ForeignKey(
        "applications.Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    status = models.CharField(
        max_length=16, choices=EntryStatus.choices, default=EntryStatus.ACTIVE
    )
    joined_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    reconfirmed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-joined_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "candidate_user"], name="uniq_talent_pool_candidate"
            )
        ]
        indexes = [
            models.Index(fields=["organisation", "status", "expires_at"], name="tp_org_status_idx")
        ]

    def __str__(self) -> str:
        return f"{self.candidate_user_id} in {self.organisation_id} ({self.status})"


class TalentPoolInvite(TenantModel):
    """HR invited a pool member to apply for a vacancy (one invitation per person and vacancy)."""

    entry = models.ForeignKey(TalentPoolEntry, on_delete=models.CASCADE, related_name="invites")
    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="+")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    invited_at = models.DateTimeField()

    class Meta:
        ordering = ("-invited_at",)
        constraints = [
            models.UniqueConstraint(fields=["entry", "job"], name="uniq_talent_pool_invite")
        ]
