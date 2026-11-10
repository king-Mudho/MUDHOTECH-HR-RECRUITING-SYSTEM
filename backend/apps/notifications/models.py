"""Notifications (docs/03 notifications, SRS M14).

* ``NotificationTemplate`` - platform defaults (``organisation`` NULL) and per-organisation
  overrides. Templates are versioned: saving creates a new version and deactivates the previous
  one; a version that was used to send is never edited.
* ``Notification`` - one row per recipient x channel x event (``dedupe_key`` unique, EC-NOT-03);
  the delivery pipeline (P05-T03) moves it through ``queued -> sent -> delivered | failed`` or
  ``suppressed``. In-app notifications use ``read_at``.
* ``EmailSuppression`` - addresses that bounced or complained (EC-NOT-01) or were suppressed by
  hand; delivery checks it before every email.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    INAPP = "inapp", "In-app"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"


class NotificationTemplate(BaseModel):
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_templates",
        help_text="NULL = platform default",
    )
    key = models.CharField(max_length=60)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.EMAIL)
    locale = models.CharField(max_length=10, default="en")
    subject = models.CharField(max_length=200, blank=True, default="")
    body_md = models.TextField()
    variables = models.JSONField(default=list, blank=True, help_text="Placeholders used")
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("key", "channel", "locale", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "key", "channel", "locale", "version"],
                name="uniq_template_version",
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                fields=["organisation", "key", "channel", "locale"],
                condition=Q(active=True),
                name="uniq_active_template",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        scope = "default" if self.organisation_id is None else str(self.organisation_id)[:8]
        return f"{self.key}/{self.channel}/{self.locale} v{self.version} ({scope})"


class NotificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    SUPPRESSED = "suppressed", "Suppressed"


class Notification(BaseModel):
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    key = models.CharField(max_length=60)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    payload = models.JSONField(
        default=dict, blank=True, help_text="Template variables (no secrets)"
    )
    template = models.ForeignKey(
        NotificationTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.QUEUED
    )
    dedupe_key = models.CharField(max_length=200, unique=True)
    provider_message_id = models.CharField(max_length=200, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True, default="")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient_user", "channel", "read_at"], name="notif_inbox_idx"),
            models.Index(fields=["status", "scheduled_for"], name="notif_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.key} -> {self.recipient_user_id} [{self.channel}/{self.status}]"


class SuppressionReason(models.TextChoices):
    BOUNCE = "bounce", "Bounced"
    COMPLAINT = "complaint", "Complaint"
    MANUAL = "manual", "Manual"


class EmailSuppression(BaseModel):
    email = models.EmailField(unique=True, help_text="Stored lower-case")
    reason = models.CharField(max_length=16, choices=SuppressionReason.choices)
    at = models.DateTimeField()
    detail = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ("-at",)

    def save(self, *args: object, **kwargs: object) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.email} ({self.reason})"
