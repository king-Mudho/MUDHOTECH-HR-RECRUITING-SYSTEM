"""Applicants table endpoints (P08-T05) for the cross-tenant suite and role matrix."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def bulk_setup(ctx: Ctx) -> None:
    from apps.applications.models import Status
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.UNDER_REVIEW)


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, **kw)


APPLICANT_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-saved-views",
        "get",
        lambda c: "/api/v1/hr/saved-views/",
        "applications.view",
        targets_object=False,
    ),
    ep(
        "hr-saved-views",
        "post",
        lambda c: "/api/v1/hr/saved-views/",
        "applications.view",
        success=201,
        data=lambda c: {"name": "Recommended", "params": {"band": "recommended_for_review"}},
        targets_object=False,
    ),
    ep(
        "hr-job-applications-bulk",
        "post",
        lambda c: f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/applications/bulk/",
        "applications.transition",
        data=lambda c: {
            "action": "tag",
            "application_ids": [str(c.objects["application"].pk)],
            "tags": ["priority"],
        },
        setup=bulk_setup,
    ),
    ep(
        "hr-dashboard-summary",
        "get",
        lambda c: "/api/v1/hr/dashboard/summary/",
        "applications.view",
        targets_object=False,
    ),
    ep(
        "hr-job-funnel",
        "get",
        lambda c: f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/funnel/",
        "applications.view",
        setup=bulk_setup,
    ),
    ep(
        "hr-application-declare-conflict",
        "post",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/declare-conflict/",
        "applications.view",
        success=201,
        data=lambda c: {"reason": "Former colleague"},
        setup=bulk_setup,
    ),
    ep(
        "hr-audit-events",
        "get",
        lambda c: "/api/v1/hr/audit-events/",
        "audit.view",
        targets_object=False,
    ),
    ep(
        "hr-audit-events-export",
        "get",
        lambda c: "/api/v1/hr/audit-events/export/",
        "audit.view",
        targets_object=False,
    ),
    ep(
        "hr-application-reconstruct",
        "get",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/reconstruct/",
        "applications.reconstruct",
        setup=bulk_setup,
    ),
]
