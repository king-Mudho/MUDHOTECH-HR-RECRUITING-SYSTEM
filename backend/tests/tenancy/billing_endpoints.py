"""Billing endpoints (P14) for the cross-tenant suite and the role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Ctx, Endpoint


def invoice_setup(ctx: Ctx) -> None:
    from datetime import timedelta

    from apps.billing import entitlements, invoicing
    from apps.billing.models import Plan, Subscription
    from apps.core.time import now

    sub = entitlements.subscription_for(ctx.team.org.pk)
    Subscription.objects.for_org(ctx.team.org).filter(pk=sub.pk).update(
        plan=Plan.objects.get(code="starter"), status="active"
    )
    sub.refresh_from_db()
    ctx.objects["invoice"] = invoicing.issue_invoice(
        sub, period_start=now(), period_end=now() + timedelta(days=30)
    )


def payment_setup(ctx: Ctx) -> None:
    from apps.billing.models import Payment

    invoice_setup(ctx)
    invoice = ctx.objects["invoice"]
    ctx.objects["payment"] = Payment.objects.create(
        organisation_id=invoice.organisation_id,
        invoice=invoice,
        provider="paynow",
        method="card",
        reference=f"{invoice.number}-1",
        amount=invoice.amount,
        currency=invoice.currency,
    )


BILLING_ENDPOINTS: list[Endpoint] = [
    Endpoint(
        "hr-billing",
        "get",
        lambda c: "/api/v1/hr/billing/",
        "billing.view",
        org_header=True,
        targets_object=False,
    ),
    Endpoint(
        "hr-billing-invoices",
        "get",
        lambda c: "/api/v1/hr/billing/invoices/",
        "billing.view",
        org_header=True,
        targets_object=False,
        setup=invoice_setup,
        needs_s3=True,
    ),
    Endpoint(
        "hr-billing-invoice-pdf",
        "get",
        lambda c: f"/api/v1/hr/billing/invoices/{c.objects['invoice'].pk}/pdf/",
        "billing.view",
        org_header=True,
        setup=invoice_setup,
        needs_s3=True,
    ),
    # Paynow is not configured in tests: permitted roles get 503 "payments_unavailable" (after
    # the invoice lookup, so another organisation's invoice is still a 404)
    Endpoint(
        "hr-billing-invoice-pay",
        "post",
        lambda c: f"/api/v1/hr/billing/invoices/{c.objects['invoice'].pk}/pay/",
        "billing.manage",
        success=503,
        org_header=True,
        setup=invoice_setup,
        needs_s3=True,
        data=lambda c: {"method": "card"},
    ),
    Endpoint(
        "hr-billing-payment",
        "get",
        lambda c: f"/api/v1/hr/billing/payments/{c.objects['payment'].pk}/",
        "billing.view",
        org_header=True,
        setup=payment_setup,
        needs_s3=True,
    ),
    Endpoint(
        "hr-billing-change-plan",
        "post",
        lambda c: "/api/v1/hr/billing/change-plan/",
        "billing.manage",
        success=201,
        org_header=True,
        targets_object=False,
        needs_s3=True,
        data=lambda c: {"plan": "starter"},
    ),
]
