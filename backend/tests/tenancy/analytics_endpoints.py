"""Recruitment report endpoints (P13-T03) for the cross-tenant suite and the role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Endpoint

ANALYTICS_ENDPOINTS: list[Endpoint] = [
    Endpoint(
        "hr-reports-recruitment",
        "get",
        lambda c: "/api/v1/hr/reports/recruitment/",
        "reports.view",
        org_header=True,
        targets_object=False,
    ),
    Endpoint(
        "hr-reports-recruitment-refresh",
        "post",
        lambda c: "/api/v1/hr/reports/recruitment/refresh/",
        "reports.view",
        org_header=True,
        targets_object=False,
    ),
]
