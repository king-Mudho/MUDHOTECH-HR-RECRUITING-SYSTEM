"""Talent pool HR endpoints (P13-T02) for the cross-tenant suite and the role matrix."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def pool_setup(ctx: Ctx) -> None:
    from apps.applications.models import Application, Status
    from apps.applications.tests.factories import published_job
    from apps.jobs.models import JobAssignment
    from apps.organisations.models import Membership
    from apps.talentpool import services
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    ctx.objects["entry"] = services.join(app.candidate_user, ctx.team.org.pk)
    # the invite target: another open vacancy the person has not applied to
    ctx.objects["other_job"] = job = published_job(organisation=ctx.team.org)
    recruiter = Membership.objects.for_org(ctx.team.org).get(user=ctx.team.recruiter)
    JobAssignment.objects.create(
        organisation=ctx.team.org, job=job, membership=recruiter, role_on_job="recruiter"
    )
    assert Application.objects.unscoped().filter(pk=app.pk, status=Status.SUBMITTED).exists()


def _entry(c: Ctx, tail: str = "") -> str:
    return f"/api/v1/hr/talent-pool/{c.objects['entry'].pk}/{tail}"


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=pool_setup, **kw)


TALENT_POOL_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-talent-pool",
        "get",
        lambda c: "/api/v1/hr/talent-pool/",
        "talentpool.search",
        is_list=True,
        targets_object=False,
    ),
    ep("hr-talent-pool-entry", "get", _entry, "talentpool.search"),
    ep(
        "hr-talent-pool-tags",
        "patch",
        _entry,
        "talentpool.invite",
        data=lambda c: {"tags": ["Backend"]},
    ),
    ep(
        "hr-talent-pool-invite",
        "post",
        lambda c: _entry(c, "invite/"),
        "talentpool.invite",
        success=201,
        data=lambda c: {"job_id": str(c.objects["other_job"].pk)},
    ),
]
