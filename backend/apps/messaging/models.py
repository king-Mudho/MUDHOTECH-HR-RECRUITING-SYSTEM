"""Clarification requests and message threads (docs/03 messaging, SRS M13/M14).

A clarification is a structured question round: HR asks, the application waits in
``needs_information``, the candidate answers (stored as candidate-reported evidence), and the
application returns to processing. Messages are the free-form channel between the candidate and
the people assigned to the vacancy. Everything is tenant-scoped and tied to one application.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel


class ClarificationStatus(models.TextChoices):
    OPEN = "open", "Waiting for the candidate"
    ANSWERED = "answered", "Answered"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class ClarificationRequest(TenantModel):
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="clarifications"
    )
    criterion_id = models.UUIDField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    questions = models.JSONField(default=list, help_text="[{id, prompt, allow_upload}]")
    answers = models.JSONField(default=list, blank=True, help_text="[{id, text, document_id}]")
    due_at = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=ClarificationStatus.choices, default=ClarificationStatus.OPEN
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    previous_status = models.CharField(max_length=24, blank=True, default="")
    answered_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(status="open"),
                name="uniq_open_clarification",
            )
        ]
        indexes = [models.Index(fields=["status", "due_at"], name="clarification_due_idx")]

    def __str__(self) -> str:
        return f"clarification {self.pk} [{self.status}]"


class MessageThread(TenantModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    application = models.OneToOneField(
        "applications.Application", on_delete=models.CASCADE, related_name="message_thread"
    )
    subject = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    def __str__(self) -> str:
        return f"thread for {self.application_id}"


class SenderRole(models.TextChoices):
    STAFF = "staff", "Employer"
    CANDIDATE = "candidate", "Candidate"
    SYSTEM = "system", "System"


class Message(TenantModel):
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name="messages")
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    sender_role = models.CharField(max_length=16, choices=SenderRole.choices)
    body = models.TextField(help_text="Plain text (sanitised)")
    attachment_document_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, help_text="Read by the other side")

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["thread", "created_at"], name="message_thread_idx")]

    def __str__(self) -> str:
        return f"{self.sender_role} message {self.pk}"
