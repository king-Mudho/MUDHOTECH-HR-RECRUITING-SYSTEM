"""Interview endpoints (P12-T06) for the cross-tenant suite and the role matrix.

The setup puts every team member on the panel of an interview that has already started, so each role
allowed by an endpoint's RBAC action can act (panel-only reads use ``org.view`` + the panel check).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def interview_setup(ctx: Ctx) -> None:
    from apps.applications.models import Application, Status
    from apps.core.time import now
    from apps.interviews.models import Interview, InterviewPanelist, InterviewStatus
    from apps.interviews.services import template_from_job
    from apps.organisations.models import Membership
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    Application.objects.unscoped().filter(pk=app.pk).update(status=Status.INTERVIEW)
    template = template_from_job(app.job, actor=ctx.team.recruiter, extra_competencies=["Teamwork"])
    started = now() - timedelta(hours=1)
    iv = Interview.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        stage="Technical",
        mode="video",
        status=InterviewStatus.SCHEDULED,
        starts_at=started,
        ends_at=started + timedelta(minutes=45),
        scorecard_template=template,
        created_by=ctx.team.recruiter,
    )
    for m in Membership.objects.for_org(app.organisation_id):
        InterviewPanelist.objects.create(
            organisation_id=app.organisation_id,
            interview=iv,
            membership=m,
            role="lead" if m.user_id == ctx.team.hr_manager.pk else "member",
        )
    ctx.objects["interview"] = iv
    ctx.objects["scorecard_template"] = template
    ctx.objects["hr_membership"] = Membership.objects.for_org(app.organisation_id).get(
        user=ctx.team.hr_manager
    )


def _iv(c: Ctx, tail: str = "") -> str:
    return f"/api/v1/hr/interviews/{c.objects['interview'].pk}/{tail}"


def _future(hours: int = 72) -> str:
    from apps.core.time import now

    return (now() + timedelta(hours=hours)).isoformat()


def ep(name: str, method: str, path: Any, action: str, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=interview_setup, **kw)


def full_card(c: Ctx) -> dict[str, Any]:
    keys = c.objects["scorecard_template"].keys
    return {"scores": dict.fromkeys(keys, 4), "overall": 4, "recommendation": "yes"}


INTERVIEW_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-interviews",
        "get",
        lambda c: "/api/v1/hr/interviews/",
        "org.view",
        is_list=True,
        targets_object=False,
    ),
    ep(
        "hr-application-interviews",
        "get",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/interviews/",
        "interviews.view_all",
    ),
    ep(
        "hr-application-interview-create",
        "post",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/interviews/",
        "interviews.manage",
        success=201,
        data=lambda c: {
            "stage": "Final",
            "mode": "phone",
            "starts_at": _future(),
            "panel": [{"membership_id": str(c.objects["hr_membership"].pk), "role": "lead"}],
        },
    ),
    ep("hr-interview", "get", _iv, "org.view"),
    ep(
        "hr-interview-reschedule",
        "post",
        lambda c: _iv(c, "reschedule/"),
        "interviews.manage",
        data=lambda c: {"reason": "Panel member unavailable", "starts_at": _future()},
    ),
    ep(
        "hr-interview-cancel",
        "post",
        lambda c: _iv(c, "cancel/"),
        "interviews.manage",
        data=lambda c: {"reason": "Position on hold"},
    ),
    ep(
        "hr-interview-no-show",
        "post",
        lambda c: _iv(c, "no-show/"),
        "interviews.manage",
        data=lambda c: {"note": "Did not join"},
    ),
    ep("hr-interview-complete", "post", lambda c: _iv(c, "complete/"), "interviews.manage"),
    ep("hr-interview-scorecards", "get", lambda c: _iv(c, "scorecards/"), "org.view"),
    ep(
        "hr-interview-my-scorecard",
        "put",
        lambda c: _iv(c, "scorecard/"),
        "org.view",
        data=lambda c: {"scores": {"c1": 4}},
    ),
    ep(
        "hr-interview-my-scorecard-submit",
        "post",
        lambda c: _iv(c, "scorecard/submit/"),
        "org.view",
        data=full_card,
    ),
    ep("hr-interview-feedback", "get", lambda c: _iv(c, "feedback/"), "interviews.feedback"),
    ep(
        "hr-job-scorecard-templates",
        "get",
        lambda c: f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/scorecard-templates/",
        "interviews.view_all",
    ),
    ep(
        "hr-job-scorecard-template-create",
        "post",
        lambda c: f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/scorecard-templates/",
        "interviews.manage",
        success=201,
        data=lambda c: {"extra_competencies": ["Communication"]},
    ),
]
