"""Subscriptions and billing (docs/03 v1.1 billing, docs/01 M20, ADR-015).

``Plan`` rows are platform-wide (editable by platform admins). Everything an organisation owns -
subscription, usage counters, invoices, payments - is a tenant table with row-level security.
Money is ``Decimal`` with an ISO currency; invoices keep a snapshot of the prices they were issued
with (EC-BIL-05). Payments never store card data: Paynow handles cards on its own pages.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, TenantModel


class Currency(models.TextChoices):
    USD = "USD", "US dollar"
    ZWG = "ZWG", "Zimbabwe Gold"


class Metric(models.TextChoices):
    ACTIVE_VACANCIES = "active_vacancies", "Published vacancies"
    SEATS = "seats", "Staff seats"
    AI_EVALUATIONS_MONTH = "ai_evaluations_month", "AI evaluations per month"
    STORAGE_GB = "storage_gb", "Storage (GB)"


class Plan(BaseModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True, default="")
    # {metric: int | null}; null (or missing) = unlimited
    limits = models.JSONField(default=dict, blank=True)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_zwg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    interval = models.CharField(max_length=10, default="month")
    is_trial = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True, help_text="Shown on the change-plan page.")
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "code")

    def __str__(self) -> str:
        return self.name

    def price(self, currency: str) -> object:
        return self.price_usd if currency == Currency.USD else self.price_zwg


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trial"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Payment overdue (grace period)"
    READ_ONLY = "read_only", "Read-only (payment overdue)"
    CANCELLED = "cancelled", "Cancelled"


class Subscription(TenantModel):
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=16, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING
    )
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    grace_until = models.DateTimeField(null=True, blank=True)
    cancel_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation"], name="uniq_subscription_org")
        ]

    def __str__(self) -> str:
        return f"{self.organisation_id}: {self.plan_id} ({self.status})"


class UsageCounter(TenantModel):
    metric = models.CharField(max_length=32, choices=Metric.choices)
    period = models.DateField(help_text="First day of the month.")
    value = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "metric", "period"], name="uniq_usage_counter"
            )
        ]


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


class Invoice(TenantModel):
    number = models.CharField(max_length=32, unique=True)
    subscription = models.ForeignKey(
        Subscription, null=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    currency = models.CharField(max_length=3, choices=Currency.choices)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total due.")
    # price snapshot: [{description, quantity, unit_price, total}] + plan code, tax rate (EC-BIL-05)
    lines = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=8, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    pdf_document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-issued_at", "-created_at")
        indexes = [models.Index(fields=["organisation", "status"], name="invoice_org_status_idx")]

    def __str__(self) -> str:
        return self.number


class PaymentProvider(models.TextChoices):
    PAYNOW = "paynow", "Paynow"
    MANUAL = "manual", "Manual (bank transfer)"
    STRIPE = "stripe", "Stripe"


class PaymentMethod(models.TextChoices):
    ECOCASH = "ecocash", "EcoCash"
    ONEMONEY = "onemoney", "OneMoney"
    CARD = "card", "Card (Visa / Mastercard)"
    BANK = "bank", "Bank transfer"


class PaymentStatus(models.TextChoices):
    CREATED = "created", "Created"
    SENT = "sent", "Waiting for the payer"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    PENDING_MANUAL_CHECK = "pending_manual_check", "Needs a manual check"


class Payment(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=10, choices=PaymentProvider.choices)
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    reference = models.CharField(
        max_length=64, unique=True, help_text="Our reference sent to the provider."
    )
    provider_reference = models.CharField(max_length=100, blank=True, default="")
    poll_url = models.URLField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=24, choices=PaymentStatus.choices, default=PaymentStatus.CREATED
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    raw = models.JSONField(default=dict, blank=True, help_text="Provider responses (no card data).")
    poll_attempts = models.PositiveSmallIntegerField(default=0)
    next_poll_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "next_poll_at"], name="payment_poll_idx")]
