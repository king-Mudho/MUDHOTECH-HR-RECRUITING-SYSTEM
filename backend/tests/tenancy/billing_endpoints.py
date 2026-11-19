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
]
