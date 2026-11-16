"""Shortlist endpoints (P08-T02) for the cross-tenant suite and role matrix."""

from __future__ import annotations

from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def _shortlist(ctx: Ctx, status: str, *, decided: bool = False) -> None:
    from datetime import timedelta

    from apps.applications.models import Status
    from apps.core.time import now
    from apps.shortlisting.models import Shortlist, ShortlistEntry
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(
        status=Status.UNDER_REVIEW, ai_band="recommended_for_review"
    )
    shortlist = Shortlist.objects.create(
        organisation_id=app.organisation_id,
        job=app.job,
        job_version=app.job_version,
        proposed_by=ctx.team.recruiter,
        status=status,
        notify_after=now() + timedelta(hours=1) if status == "approved" else None,
    )
    ShortlistEntry.objects.create(
        organisation_id=app.organisation_id,
        shortlist=shortlist,
        application=app,
        ai_band_at_decision="recommended_for_review",
        **(
            {"decision": "shortlist", "decided_by": ctx.team.recruiter, "decided_at": now()}
            if status != "draft" or decided
            else {}
        ),
    )
    if status == "approved":
        type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.SHORTLISTED)
        shortlist.entries.update(applied_at=now())
    ctx.objects["shortlist"] = shortlist


def draft_setup(ctx: Ctx) -> None:
    _shortlist(ctx, "draft")


def decided_setup(ctx: Ctx) -> None:
    _shortlist(ctx, "draft", decided=True)


def pending_setup(ctx: Ctx) -> None:
    _shortlist(ctx, "pending_approval")


def approved_setup(ctx: Ctx) -> None:
    _shortlist(ctx, "approved")


def under_review_setup(ctx: Ctx) -> None:
    from apps.applications.models import Status
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.UNDER_REVIEW)


def _sl(c: Ctx) -> str:
    return f"/api/v1/hr/shortlists/{c.objects['shortlist'].pk}"


def _job(c: Ctx) -> str:
    return f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/shortlists/"


def ep(name: str, method: str, path: Any, action: str, setup: Any, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=setup, **kw)


SHORTLIST_ENDPOINTS: list[Endpoint] = [
    ep("hr-job-shortlists", "get", _job, "applications.view", draft_setup),
    ep(
        "hr-job-shortlist-propose",
        "post",
        _job,
        "applications.transition",
        under_review_setup,
        success=201,
        data=lambda c: {"desired_size": 5},
    ),
    ep("hr-shortlist", "get", lambda c: f"{_sl(c)}/", "applications.view", draft_setup),
    ep(
        "hr-shortlist-entries",
        "patch",
        lambda c: f"{_sl(c)}/entries/",
        "applications.transition",
        draft_setup,
        data=lambda c: {
            "decisions": [
                {"application_id": str(c.objects["application"].pk), "decision": "shortlist"}
            ]
        },
    ),
    ep(
        "hr-shortlist-refresh",
        "post",
        lambda c: f"{_sl(c)}/refresh/",
        "applications.transition",
        draft_setup,
    ),
    ep(
        "hr-shortlist-submit",
        "post",
        lambda c: f"{_sl(c)}/submit/",
        "applications.transition",
        decided_setup,
    ),
    ep(
        "hr-shortlist-approve",
        "post",
        lambda c: f"{_sl(c)}/approve/",
        "applications.decide",
        pending_setup,
        idempotent=True,
    ),
    ep(
        "hr-shortlist-reject",
        "post",
        lambda c: f"{_sl(c)}/reject/",
        "applications.decide",
        pending_setup,
        data=lambda c: {"reason": "Please review the holds"},
    ),
    ep(
        "hr-shortlist-undo",
        "post",
        lambda c: f"{_sl(c)}/undo/",
        "applications.decide",
        approved_setup,
        data=lambda c: {"reason": "Approved by mistake"},
    ),
]
