"""Organisations (tenants).

Phase 01 creates the minimal tenant root so ``TenantModel`` has a FK target; Phase 02 (P02-T06) adds
policies, departments, locations, memberships and invitations.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Organisation(BaseModel):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING_VERIFICATION
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
