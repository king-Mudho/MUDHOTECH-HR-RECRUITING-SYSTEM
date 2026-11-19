"""Recruitment report and export endpoints (P13-T03, P13-T06) for the cross-tenant suite and the
role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Ctx, Endpoint


def export_setup(ctx: Ctx) -> None:
    from datetime import timedelta

    from apps.analytics.models import ExportJob
    from apps.core import storage
    from apps.core.time import now

    key = f"exports/{ctx.team.org.pk}/test.csv"
    storage.put_bytes("exports", key, b"a,b\n", "text/csv")
    ctx.objects["export"] = ExportJob.objects.create(
        organisation=ctx.team.org,
        kind="report",
        format="csv",
        status="ready",
        requested_by=ctx.team.hr_manager,
        storage_key=key,
        filename="report.csv",
        finished_at=now(),
        expires_at=now() + timedelta(hours=24),
    )


def _export(c: Ctx, tail: str = "") -> str:
    return f"/api/v1/hr/exports/{c.objects['export'].pk}/{tail}"


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
    Endpoint(
        "hr-exports",
        "get",
        lambda c: "/api/v1/hr/exports/",
        "reports.export",
        org_header=True,
        targets_object=False,
        is_list=False,
        setup=export_setup,
        needs_s3=True,
    ),
    Endpoint(
        "hr-exports-create",
        "post",
        lambda c: "/api/v1/hr/exports/",
        "reports.export",
        success=202,
        org_header=True,
        targets_object=False,
        data=lambda c: {"kind": "report", "format": "csv"},
    ),
    Endpoint(
        "hr-export",
        "get",
        _export,
        "reports.export",
        org_header=True,
        setup=export_setup,
        needs_s3=True,
    ),
    Endpoint(
        "hr-export-download",
        "post",
        lambda c: _export(c, "download/"),
        "reports.export",
        org_header=True,
        setup=export_setup,
        needs_s3=True,
    ),
]
