"""P12-T05: hiring close-out - hire record, close prompt, confirmed final outcomes."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import time as mhrs_time
from apps.core.exceptions import ConflictError, DomainError, PermissionDeniedError
from apps.notifications.models import Notification
from apps.offers import hiring, services
from apps.offers.models import HireRecord, OfferStatus
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def member(team: Any, user: Any) -> Membership:
    return Membership.objects.for_org(team.org).get(user=user)


def terms() -> dict[str, Any]:
    return {
        "salary_amount": "1500",
        "currency": "USD",
        "period": "month",
        "start_date": (mhrs_time.now() + timedelta(days=30)).date(),
        "contract_type": "full_time",
        "expires_at": mhrs_time.now() + timedelta(days=7),
    }


@pytest.fixture
def ctx(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    app = make_application(job, status=Status.INTERVIEW)
    app.candidate_user.first_name, app.candidate_user.last_name = "Tendai", "Moyo"
    app.candidate_user.save()
    offer = services.create_draft(app, actor=team.recruiter, data=terms())
    services.submit_for_approval(offer, actor=team.recruiter)
    services.approve(offer, actor=team.hr_manager)
    offer = services.issue(offer, actor=team.recruiter)
    return {
        "team": team,
        "job": job,
        "app": app,
        "offer": offer,
        "hr": member(team, team.hr_manager),
    }


def accept(ctx: dict[str, Any]) -> None:
    services.accept(
        ctx["offer"], candidate=ctx["app"].candidate_user, typed_name="Tendai Moyo", agree=True
    )


def test_hire_needs_an_accepted_offer_and_hr(ctx: dict[str, Any]) -> None:
    with pytest.raises(DomainError) as err:
        hiring.record_hire(ctx["hr"], ctx["team"].hr_manager, ctx["offer"].pk)
    assert err.value.code == "offer_not_accepted"
    accept(ctx)
    with pytest.raises(PermissionDeniedError):
        hiring.record_hire(
            member(ctx["team"], ctx["team"].recruiter), ctx["team"].recruiter, ctx["offer"].pk
        )


def test_record_hire_and_close_prompt(ctx: dict[str, Any]) -> None:
    accept(ctx)
    result = hiring.record_hire(
        ctx["hr"], ctx["team"].hr_manager, ctx["offer"].pk, note="Contract signed"
    )
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.HIRED
    hire = HireRecord.objects.for_org(ctx["team"].org).get()
    assert hire.start_date == ctx["offer"].start_date and hire.recorded_by == ctx["team"].hr_manager
    assert result["prompt_close"] is True and result["openings"]["remaining"] == 0
    assert AuditEvent.objects.filter(action="hiring.hire_recorded").exists()
    with pytest.raises(DomainError):  # not twice
        hiring.record_hire(ctx["hr"], ctx["team"].hr_manager, ctx["offer"].pk)


def test_no_close_prompt_while_openings_remain(ctx: dict[str, Any]) -> None:
    from apps.jobs.models import Job

    Job.objects.unscoped().filter(pk=ctx["job"].pk).update(openings=2)
    accept(ctx)
    result = hiring.record_hire(ctx["hr"], ctx["team"].hr_manager, ctx["offer"].pk)
    assert result["prompt_close"] is False and result["openings"]["remaining"] == 1


def _mixed_pool(ctx: dict[str, Any]) -> dict[str, Application]:
    job = ctx["job"]
    return {
        status: make_application(job, status=status)
        for status in (
            Status.UNDER_REVIEW,
            Status.SHORTLISTED,
            Status.INTERVIEW,
            Status.ON_HOLD,
            Status.PROCESSING,
            Status.WITHDRAWN,
            Status.NOT_SELECTED,
        )
    }


def test_closeout_preview_lists_exactly_who_would_be_told(ctx: dict[str, Any]) -> None:
    pool = _mixed_pool(ctx)
    preview = hiring.closeout_preview(ctx["hr"], ctx["job"].pk)
    assert preview["to_notify"] == 4  # under_review, shortlisted, interview, on_hold
    assert preview["still_in_progress"] == [
        {"id": str(pool[Status.PROCESSING].pk), "reference": pool[Status.PROCESSING].reference}
    ]
    assert [a["id"] for a in preview["with_open_offer"]] == [str(ctx["app"].pk)]
    with pytest.raises(PermissionDeniedError):
        hiring.closeout_preview(member(ctx["team"], ctx["team"].recruiter), ctx["job"].pk)


def test_closeout_requires_confirming_the_previewed_list(ctx: dict[str, Any]) -> None:
    pool = _mixed_pool(ctx)
    preview = hiring.closeout_preview(ctx["hr"], ctx["job"].pk)
    with pytest.raises(ConflictError):
        hiring.confirm_closeout(ctx["hr"], ctx["team"].hr_manager, ctx["job"].pk, fingerprint="x")
    late = make_application(ctx["job"], status=Status.UNDER_REVIEW)  # list changed meanwhile
    with pytest.raises(ConflictError) as err:
        hiring.confirm_closeout(
            ctx["hr"], ctx["team"].hr_manager, ctx["job"].pk, fingerprint=preview["fingerprint"]
        )
    assert err.value.code == "closeout_changed"
    preview = hiring.closeout_preview(ctx["hr"], ctx["job"].pk)
    result = hiring.confirm_closeout(
        ctx["hr"], ctx["team"].hr_manager, ctx["job"].pk, fingerprint=preview["fingerprint"]
    )
    assert result == {"notified": 5, "skipped": []}
    for app in [
        *(
            pool[s]
            for s in (Status.UNDER_REVIEW, Status.SHORTLISTED, Status.INTERVIEW, Status.ON_HOLD)
        ),
        late,
    ]:
        app.refresh_from_db()
        assert app.status == Status.NOT_SELECTED
    pool[Status.PROCESSING].refresh_from_db()
    assert pool[Status.PROCESSING].status == Status.PROCESSING  # left alone
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.OFFER  # live offer untouched
    ctx["offer"].refresh_from_db()
    assert ctx["offer"].status == OfferStatus.ISSUED
    # outcome messages wait for the organisation's delay (undo window), never immediate
    pending = Notification.objects.filter(key="not_selected", channel="email")
    assert pending.count() == 5 and all(n.scheduled_for > mhrs_time.now() for n in pending)
    assert AuditEvent.objects.filter(action="hiring.closeout_confirmed").exists()
    with pytest.raises(DomainError) as err:
        hiring.confirm_closeout(
            ctx["hr"],
            ctx["team"].hr_manager,
            ctx["job"].pk,
            fingerprint=hiring.closeout_preview(ctx["hr"], ctx["job"].pk)["fingerprint"],
        )
    assert err.value.code == "nothing_to_close"
