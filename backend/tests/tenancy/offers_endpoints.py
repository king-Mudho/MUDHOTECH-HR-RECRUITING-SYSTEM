"""Offer and hiring endpoints (P12-T06) for the cross-tenant suite and the role matrix.

Offers are drafted by the recruiter, so every role with ``offers.approve`` (admin, HR manager) may
approve them (the drafter never can). States other than draft are set directly so each setup stays
small.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from tests.tenancy.registry import Ctx, Endpoint


def interview_app_setup(ctx: Ctx) -> None:
    from apps.applications.models import Application, Status
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    Application.objects.unscoped().filter(pk=app.pk).update(status=Status.INTERVIEW)
    app.refresh_from_db()


def _offer(ctx: Ctx, status: str) -> None:
    from apps.applications.models import Application, Status
    from apps.core.time import now
    from apps.documents.models import Document, ScanStatus
    from apps.offers import services
    from apps.offers.models import Offer

    interview_app_setup(ctx)
    app = ctx.objects["application"]
    offer = services.create_draft(
        app,
        actor=ctx.team.recruiter,
        data={
            "salary_amount": "1500",
            "currency": "USD",
            "period": "month",
            "start_date": (now() + timedelta(days=30)).date(),
            "contract_type": "full_time",
            "expires_at": now() + timedelta(days=7),
        },
    )
    extra: dict[str, Any] = {"status": status}
    if status in ("issued", "accepted"):
        Application.objects.unscoped().filter(pk=app.pk).update(status=Status.OFFER)
        letter = Document.objects.create(
            owner_user=app.candidate_user,
            organisation_id=app.organisation_id,
            purpose="offer_letter",
            original_filename="Offer letter.pdf",
            size_bytes=10,
            storage_key=f"offers/{offer.pk}/letter.pdf",
            bucket="documents",
            scan_status=ScanStatus.CLEAN,
        )
        extra.update(issued_at=now(), issued_by=ctx.team.recruiter, letter_document=letter)
    if status == "accepted":
        extra["accepted_at"] = now()
    Offer.objects.for_org(app.organisation_id).filter(pk=offer.pk).update(**extra)
    ctx.objects["offer"] = Offer.objects.for_org(app.organisation_id).get(pk=offer.pk)


def draft_setup(ctx: Ctx) -> None:
    _offer(ctx, "draft")


def pending_setup(ctx: Ctx) -> None:
    _offer(ctx, "pending_approval")


def approved_setup(ctx: Ctx) -> None:
    _offer(ctx, "approved")


def issued_setup(ctx: Ctx) -> None:
    _offer(ctx, "issued")


def accepted_setup(ctx: Ctx) -> None:
    _offer(ctx, "accepted")


def closeout_setup(ctx: Ctx) -> None:
    from apps.applications.models import Status
    from apps.applications.tests.factories import make_application

    interview_app_setup(ctx)
    make_application(ctx.objects["live_job"], status=Status.UNDER_REVIEW)


def _o(c: Ctx, tail: str = "") -> str:
    return f"/api/v1/hr/offers/{c.objects['offer'].pk}/{tail}"


def _closeout(c: Ctx) -> str:
    return f"/api/v1/hr/jobs/{c.objects['live_job'].pk}/closeout/"


def _fingerprint(c: Ctx) -> dict[str, Any]:
    from apps.offers import hiring
    from apps.organisations.models import Membership

    hr = Membership.objects.for_org(c.team.org).get(user=c.team.hr_manager)
    return {"fingerprint": hiring.closeout_preview(hr, c.objects["live_job"].pk)["fingerprint"]}


def ep(name: str, method: str, path: Any, action: str, setup: Any, **kw: Any) -> Endpoint:
    return Endpoint(name, method, path, action, org_header=True, setup=setup, **kw)


def _terms(c: Ctx) -> dict[str, Any]:
    from apps.core.time import now

    return {
        "salary_amount": "1700.00",
        "currency": "USD",
        "period": "month",
        "start_date": (now() + timedelta(days=40)).date().isoformat(),
        "contract_type": "full_time",
        "expires_at": (now() + timedelta(days=7)).isoformat(),
    }


OFFER_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-offers",
        "get",
        lambda c: "/api/v1/hr/offers/",
        "offers.view",
        draft_setup,
        is_list=True,
        targets_object=False,
    ),
    ep(
        "hr-application-offers",
        "get",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/offers/",
        "offers.view",
        draft_setup,
    ),
    ep(
        "hr-application-offer-create",
        "post",
        lambda c: f"/api/v1/hr/applications/{c.objects['application'].pk}/offers/",
        "offers.manage",
        interview_app_setup,
        success=201,
        data=_terms,
    ),
    ep("hr-offer", "get", _o, "offers.view", draft_setup),
    ep(
        "hr-offer-update",
        "patch",
        _o,
        "offers.manage",
        draft_setup,
        data=lambda c: {"lock_version": c.objects["offer"].lock_version, "salary_amount": "1600"},
    ),
    ep("hr-offer-submit", "post", lambda c: _o(c, "submit/"), "offers.manage", draft_setup),
    ep(
        "hr-offer-approve",
        "post",
        lambda c: _o(c, "approve/"),
        "offers.approve",
        pending_setup,
        data=lambda c: {"comment": "Within budget"},
    ),
    ep(
        "hr-offer-return",
        "post",
        lambda c: _o(c, "return/"),
        "offers.approve",
        pending_setup,
        data=lambda c: {"comment": "Start date too early"},
    ),
    ep(
        "hr-offer-issue",
        "post",
        lambda c: _o(c, "issue/"),
        "offers.manage",
        approved_setup,
        idempotent=True,
        needs_s3=True,
    ),
    ep(
        "hr-offer-withdraw",
        "post",
        lambda c: _o(c, "withdraw/"),
        "offers.approve",
        issued_setup,
        data=lambda c: {"reason": "Budget frozen for this quarter"},
    ),
    ep(
        "hr-offer-letter",
        "get",
        lambda c: _o(c, "letter/"),
        "offers.view",
        issued_setup,
        success=302,
    ),
    ep(
        "hr-offer-hire",
        "post",
        lambda c: _o(c, "hire/"),
        "hires.record",
        accepted_setup,
        success=201,
        data=lambda c: {"note": "Contract signed"},
    ),
    ep("hr-job-closeout-preview", "get", _closeout, "applications.decide", closeout_setup),
    ep(
        "hr-job-closeout-confirm",
        "post",
        _closeout,
        "applications.decide",
        closeout_setup,
        idempotent=True,
        data=_fingerprint,
    ),
]
