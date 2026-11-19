"""Offers and hire records (docs/01 M17, docs/03 v1.1; P12-T04).

Flow: ``draft -> pending_approval -> approved -> issued -> accepted | declined | expired``;
``withdrawn`` from any open state. An offer is **never issued without the required approvals** (EC-
OFF-01): the number comes from ``OrganisationPolicy.offer_approvals_required``, approvers need
``offers.approve`` and cannot be the person who drafted it. Returning an offer for changes starts a
new approval ``round``.

Acceptance is an electronic record (``acceptance_meta``): the name the candidate typed, that they
ticked the acceptance statement, the time, a truncated IP address and a hash of the user agent. The
hire record is separate from screening data (M17 AC) and is created by HR when the person is
confirmed (P12-T05).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel
from apps.jobs.models import Currency, EmploymentType, SalaryPeriod


class OfferStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Waiting for approval"
    APPROVED = "approved", "Approved"
    ISSUED = "issued", "Issued to the candidate"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"
    WITHDRAWN = "withdrawn", "Withdrawn"


LIVE_STATUSES = (
    OfferStatus.DRAFT,
    OfferStatus.PENDING_APPROVAL,
    OfferStatus.APPROVED,
    OfferStatus.ISSUED,
    OfferStatus.ACCEPTED,
)


class ApprovalDecision(models.TextChoices):
    APPROVED = "approved", "Approved"
    RETURNED = "returned", "Returned for changes"


class Offer(TenantModel):
    application = models.ForeignKey(
        "applications.Application", on_delete=models.PROTECT, related_name="offers"
    )
    status = models.CharField(max_length=20, choices=OfferStatus.choices, default=OfferStatus.DRAFT)
    salary_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    period = models.CharField(max_length=10, choices=SalaryPeriod.choices)
    start_date = models.DateField()
    contract_type = models.CharField(max_length=16, choices=EmploymentType.choices)
    conditions = models.TextField(blank=True, default="", help_text="Shown in the letter.")
    expires_at = models.DateTimeField()
    required_approvals = models.PositiveSmallIntegerField(default=1)
    approval_round = models.PositiveSmallIntegerField(default=1)
    letter_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    expiry_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    acceptance_meta = models.JSONField(default=dict, blank=True)
    counter_offer_note = models.TextField(blank=True, default="")
    declined_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)  # expired / withdrawn
    close_reason = models.CharField(max_length=500, blank=True, default="")
    lock_version = models.PositiveIntegerField(default=0)

    class Meta(TenantModel.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(salary_amount__gt=0), name="offer_salary_positive"),
            models.CheckConstraint(
                condition=Q(required_approvals__gte=1, required_approvals__lte=5),
                name="offer_approvals_range",
            ),
            # one live offer per application at a time (a new one after expiry/decline/withdrawal)
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(
                    status__in=["draft", "pending_approval", "approved", "issued", "accepted"]
                ),
                name="offer_one_live_per_application",
            ),
            models.CheckConstraint(
                condition=~Q(status="issued") | Q(issued_at__isnull=False),
                name="offer_issued_has_time",
            ),
            models.CheckConstraint(
                condition=~Q(status="accepted") | Q(accepted_at__isnull=False),
                name="offer_accepted_has_time",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "status"], name="offer_org_status_idx"),
            models.Index(fields=["status", "expires_at"], name="offer_status_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"Offer {self.pk} ({self.status})"


class OfferApproval(TenantModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="approvals")
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    round = models.PositiveSmallIntegerField(default=1)
    decision = models.CharField(max_length=10, choices=ApprovalDecision.choices)
    comment = models.TextField(blank=True, default="")
    at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        ordering = ("at",)
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "approver", "round"], name="offer_approval_once_per_round"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.decision} by {self.approver_id} (round {self.round})"


class HireRecord(TenantModel):
    application = models.OneToOneField(
        "applications.Application", on_delete=models.PROTECT, related_name="hire_record"
    )
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT, related_name="hire_records")
    start_date = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    recorded_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta(TenantModel.Meta):
        pass

    def __str__(self) -> str:
        return f"Hire {self.application_id}"
