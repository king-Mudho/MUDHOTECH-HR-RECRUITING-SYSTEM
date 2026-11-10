"""Organisations (tenants), policies, structure, memberships, invitations - docs/03."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core import time
from apps.core.models import BaseModel, TenantModel


class Organisation(BaseModel):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    class SizeBand(models.TextChoices):
        MICRO = "1-9", "1-9"
        SMALL = "10-49", "10-49"
        MEDIUM = "50-249", "50-249"
        LARGE = "250-999", "250-999"
        ENTERPRISE = "1000+", "1000+"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    legal_name = models.CharField(max_length=255, blank=True, default="")
    registration_number = models.CharField(max_length=100, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="")
    size_band = models.CharField(max_length=16, choices=SizeBand.choices, blank=True, default="")
    country = models.CharField(max_length=2, default="ZW")
    city = models.CharField(max_length=100, blank=True, default="")
    address = models.TextField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    logo_key = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="", help_text="Sanitised HTML.")
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING_VERIFICATION
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    default_timezone = models.CharField(max_length=64, default="Africa/Harare")
    default_currency = models.CharField(max_length=3, default="USD")
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_read_only(self) -> bool:
        """FR-M02-04: suspended/closed organisations are read-only for staff."""
        return self.status in (self.Status.SUSPENDED, self.Status.CLOSED)


class DuplicatePolicy(models.TextChoices):
    ONE_ACTIVE = "one_active", "One active application per vacancy"
    ALLOW_RESUBMIT_REPLACE = "allow_resubmit_replace", "Resubmit replaces previous"
    ALLOW_MULTIPLE = "allow_multiple", "Allow multiple"


class OrganisationPolicy(BaseModel):
    """Org-level policies (FR-M02-03). Defaults follow docs/03 and the decisions log."""

    organisation = models.OneToOneField(
        Organisation, on_delete=models.CASCADE, related_name="policy"
    )
    privacy_notice = models.TextField(blank=True, default="")
    retention_months = models.PositiveSmallIntegerField(default=12)  # D-03
    duplicate_policy = models.CharField(
        max_length=32,
        choices=DuplicatePolicy.choices,
        default=DuplicatePolicy.ONE_ACTIVE,  # D-04
    )
    shortlist_dual_control = models.BooleanField(default=False)  # D-02
    rubric_dual_control = models.BooleanField(default=False)
    ai_enabled = models.BooleanField(default=True)
    llm_enabled = models.BooleanField(default=False)  # D-06
    blind_review_default = models.BooleanField(default=True)  # ADR-013
    notification_delay_minutes = models.PositiveSmallIntegerField(default=15)  # ADR-014
    hide_ai_from_panelists = models.BooleanField(default=True)  # ADR-019
    rights_request_sla_days = models.PositiveSmallIntegerField(default=30)
    upload_limits_mb = models.JSONField(
        default=dict, blank=True, help_text='Per-purpose upload limit in MB, e.g. {"cv": 5}.'
    )
    version = models.PositiveIntegerField(default=1, help_text="Optimistic lock (lock_version).")

    def __str__(self) -> str:
        return f"Policy for {self.organisation_id}"


class Department(TenantModel):
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                "organisation", Lower("name"), name="uniq_department_org_name_ci"
            )
        ]

    def __str__(self) -> str:
        return self.name


class WorkplaceType(models.TextChoices):
    ON_SITE = "on_site", "On-site"
    HYBRID = "hybrid", "Hybrid"
    REMOTE = "remote", "Remote"


class Location(TenantModel):
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=2, default="ZW")
    workplace_type_default = models.CharField(
        max_length=16, choices=WorkplaceType.choices, default=WorkplaceType.ON_SITE
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Role(models.TextChoices):
    ORG_ADMIN = "org_admin", "Company admin"
    HR_MANAGER = "hr_manager", "HR manager"
    RECRUITER = "recruiter", "Recruiter"
    HIRING_MANAGER = "hiring_manager", "Hiring manager"
    PANELIST = "panelist", "Interview panel member"
    AUDITOR = "auditor", "Auditor"


PRIVILEGED_ROLES = frozenset({Role.ORG_ADMIN, Role.HR_MANAGER})


class Membership(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEACTIVATED = "deactivated", "Deactivated"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    joined_at = models.DateTimeField(default=time.now)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("organisation", "joined_at")
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"], name="uniq_membership_org_user"
            )
        ]
        indexes = [models.Index(fields=["user", "status"], name="membership_user_status_idx")]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.organisation_id} ({self.role})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class Invitation(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    email = models.EmailField(max_length=254)
    role = models.CharField(max_length=32, choices=Role.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    vacancy_ids = models.JSONField(default=list, blank=True)
    # EC-ORG-05: org_admin may explicitly allow acceptance from a different (verified) email.
    allow_any_email = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(Lower("email"), "organisation", name="invitation_email_org_idx")]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                "organisation",
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="uniq_open_invitation_per_email",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} -> {self.organisation_id} ({self.role})"

    @property
    def status(self) -> str:
        if self.accepted_at:
            return self.Status.ACCEPTED
        if self.revoked_at:
            return self.Status.REVOKED
        if self.expires_at <= time.now():
            return self.Status.EXPIRED
        return self.Status.PENDING
