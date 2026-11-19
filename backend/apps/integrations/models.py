"""External integrations (docs/01 M21, docs/03 integrations, P15).

``IntegrationConnection`` - one provider connected for an organisation (or for one staff member,
e.g. their own calendar). Credentials are encrypted at rest and never returned by the API; only a
masked hint is shown. Health (last success / last error) is recorded by every adapter call, and a
failing integration never changes core records: integration work runs from outbox consumers after
the business transaction committed.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel


class ConnectionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ERROR = "error", "Failing"
    DISABLED = "disabled", "Disabled"


class IntegrationConnection(TenantModel):
    provider = models.CharField(max_length=40)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="integration_connections",
        help_text="Set for per-person connections (own calendar); empty = organisation-wide.",
    )
    credentials = EncryptedTextField(blank=True, default="", help_text="JSON, encrypted.")
    credentials_hint = models.CharField(max_length=40, blank=True, default="")
    config = models.JSONField(default=dict, blank=True, help_text="Non-secret settings.")
    status = models.CharField(
        max_length=12, choices=ConnectionStatus.choices, default=ConnectionStatus.ACTIVE
    )
    sandbox = models.BooleanField(default=False)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    credentials_rotated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "provider", "owner_user"],
                name="uniq_integration_connection",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider} ({self.status})"


class CalendarEventLink(TenantModel):
    """The event created in a panelist's calendar for an interview (P15-T02)."""

    interview = models.ForeignKey(
        "interviews.Interview", on_delete=models.CASCADE, related_name="calendar_links"
    )
    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.CASCADE, related_name="event_links"
    )
    external_id = models.CharField(max_length=300)
    synced_sequence = models.PositiveIntegerField(default=0)
    cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["interview", "connection"], name="uniq_calendar_link")
        ]


class WebhookEndpoint(TenantModel):
    url = models.URLField(max_length=500)
    secret = EncryptedTextField(help_text="HMAC signing secret, encrypted; shown once.")
    events = models.JSONField(default=list)
    description = models.CharField(max_length=200, blank=True, default="")
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return self.url


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Delivered"
    FAILED = "failed", "Failed"


class WebhookDelivery(TenantModel):
    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=12, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["endpoint", "event_id"], name="uniq_webhook_delivery")
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="webhook_retry_idx")]


class ApiKey(TenantModel):
    """Scoped API key (P15-T06): only the SHA-256 hash of the secret is stored."""

    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} (mhrs_{self.prefix}_…)"
