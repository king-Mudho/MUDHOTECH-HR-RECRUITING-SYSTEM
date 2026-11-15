"""HR extraction endpoints (P06-T14) for the cross-tenant suite and role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Ctx, Endpoint


def processing_error_setup(ctx: Ctx) -> None:
    """An application whose CV could not be read (retry is allowed)."""
    from apps.applications.models import Status
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.PROCESSING_ERROR)


def _app(c: Ctx) -> str:
    return f"/api/v1/hr/applications/{c.objects['application'].pk}"


RESUME_ENDPOINTS: list[Endpoint] = [
    Endpoint(
        "hr-application-extraction",
        "get",
        lambda c: f"{_app(c)}/extraction/",
        "applications.view",
        org_header=True,
        setup=processing_error_setup,
    ),
    Endpoint(
        "hr-application-retry-processing",
        "post",
        lambda c: f"{_app(c)}/retry-processing/",
        "applications.transition",
        org_header=True,
        setup=processing_error_setup,
    ),
]
