"""Append-only audit trail (ADR-018, docs/03 audit).

``AuditEvent`` rows form one hash chain per organisation (``chain`` = organisation id) plus a
``platform`` chain. ``hash = sha256(canonical_json(event) + prev_hash)``. A database trigger rejects
UPDATE/DELETE (see migration 0002); ``verify_audit_chain`` recomputes every chain.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core import time
from apps.core.models import BaseModel

PLATFORM_CHAIN = "platform"


class ActorType(models.TextChoices):
    HUMAN = "human", "Human"
    SYSTEM = "system", "System"
    PLATFORM_SUPPORT = "platform_support", "Platform support"


class AuditEvent(BaseModel):
    # Explicit (not auto_now_add): the timestamp is part of the hashed payload, so the value we
    # hash must be exactly the value stored.
    created_at = models.DateTimeField(default=time.now, db_index=True)
    chain = models.CharField(max_length=64, db_index=True)
    seq = models.BigIntegerField()
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor_type = models.CharField(max_length=32, choices=ActorType.choices)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    ip_trunc = models.CharField(max_length=64, blank=True, default="")
    user_agent_hash = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ("chain", "seq")
        constraints = [
            models.UniqueConstraint(fields=["chain", "seq"], name="uniq_audit_chain_seq"),
        ]
        indexes = [
            models.Index(fields=["organisation", "created_at"], name="audit_org_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.chain}#{self.seq} {self.action}"


class AccessLog(BaseModel):
    """High-volume log of PII views/downloads (partitioning considered in Phase 09)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=32, default="view")
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=64)
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["organisation", "created_at"], name="access_org_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="access_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"
