"""Billing endpoints (P14) for the cross-tenant suite and the role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Endpoint

BILLING_ENDPOINTS: list[Endpoint] = [
    Endpoint(
        "hr-billing",
        "get",
        lambda c: "/api/v1/hr/billing/",
        "billing.view",
        org_header=True,
        targets_object=False,
    ),
]
