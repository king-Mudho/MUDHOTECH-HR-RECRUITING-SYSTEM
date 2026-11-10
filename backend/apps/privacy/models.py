"""Consent and notice records (docs/03 consent_records, docs/06 §4 - CDPA purpose limitation).

Every record names the purpose, the exact notice version the person saw, and when. A record is
never edited: withdrawing consent sets ``withdrawn_at``; a new decision is a new record.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


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
