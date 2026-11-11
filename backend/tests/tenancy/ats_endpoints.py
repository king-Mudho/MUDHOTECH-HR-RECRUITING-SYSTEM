"""HR applicant-tracking endpoints for the cross-tenant suite and role matrix (P05-T07)."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def ats_setup(ctx: Ctx) -> None:
    from apps.applications.models import Status
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.UNDER_REVIEW)


def _app(c: Ctx) -> str:
    return f"/api/v1/hr/applications/{c.objects['application'].pk}"


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=ats_setup, **kw)


ATS_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-application-transition",
        "post",
        lambda c: f"{_app(c)}/transition/",
        "applications.transition",
        data=lambda c: {"to_status": "on_hold", "reason_code": "awaiting_budget"},
    ),
    ep("hr-application-notes", "get", lambda c: f"{_app(c)}/notes/", "applications.view"),
    ep(
        "hr-application-notes",
        "post",
        lambda c: f"{_app(c)}/notes/",
        "applications.view",
        success=201,
        data=lambda c: {"body": "Good communication skills."},
    ),
    ep(
        "hr-application-tags",
        "put",
        lambda c: f"{_app(c)}/tags/",
        "applications.transition",
        data=lambda c: {"tags": ["senior"]},
    ),
    ep(
        "hr-application-assign",
        "post",
        lambda c: f"{_app(c)}/assign/",
        "applications.assign",
        data=lambda c: {"user_id": None},
    ),
    ep(
        "hr-decision-reasons",
        "get",
        lambda c: "/api/v1/hr/decision-reasons/",
        "applications.view",
        targets_object=False,
    ),
]
