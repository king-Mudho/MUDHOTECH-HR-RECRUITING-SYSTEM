"""HR application endpoints for the cross-tenant suite and the permission matrix (P04-T15)."""

from __future__ import annotations

from typing import Any

from tests.tenancy.jobs_endpoints import jobs_setup
from tests.tenancy.registry import Ctx, Endpoint


def applications_setup(ctx: Ctx) -> None:
    from apps.accounts.tests.factories import UserFactory
    from apps.applications.models import Status
    from apps.applications.tests.factories import make_application

    jobs_setup(ctx, ("live_job",))
    app = make_application(ctx.objects["live_job"], UserFactory(), status=Status.SUBMITTED)
    app.candidate_profile_snapshot = {"first_name": "Rudo", "last_name": "Moyo"}
    app.save(update_fields=["candidate_profile_snapshot"])
    ctx.objects["application"] = app


def _job_apps(c: Ctx) -> str:
    return f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/applications/"


def _app(c: Ctx) -> str:
    return f"/api/v1/hr/applications/{c.objects['application'].pk}/"


def ep(name: str, path: Any, **kw: Any) -> Endpoint:
    return Endpoint(
        name, "get", path, "applications.view", org_header=True, setup=applications_setup, **kw
    )


APPLICATION_ENDPOINTS: list[Endpoint] = [
    ep("hr-job-applications", _job_apps, is_list=True),
    ep("hr-application", _app),
]
