"""P12-T04: offers - approval chain, issue with letter, accept/decline, expiry, withdrawal, openings
(EC-OFF-01..04)."""

from __future__ import annotations

import unicodedata
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pymupdf
import pytest

from apps.applications.models import Application, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import storage
from apps.core import time as mhrs_time
from apps.core.exceptions import ConflictError, DomainError, PermissionDeniedError
from apps.jobs.models import Job
from apps.notifications.models import Notification
from apps.offers import services
from apps.offers.models import HireRecord, Offer, OfferStatus
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    app = make_application(job, status=Status.INTERVIEW)
    user = app.candidate_user
    user.first_name, user.last_name = "Tendai", "Moyo"
    user.save()
    return {"team": team, "job": job, "app": app, "candidate": user}


def terms(**kw: Any) -> dict[str, Any]:
    data = {
        "salary_amount": "1850.00",
        "currency": "USD",
        "period": "month",
        "start_date": (mhrs_time.now() + timedelta(days=30)).date(),
        "contract_type": "full_time",
        "conditions": "Probation: 3 months.\nMedical aid & pension.",
        "expires_at": mhrs_time.now() + timedelta(days=7),
    }
    data.update(kw)
    return data


def approved_offer(ctx: dict[str, Any], app: Application | None = None) -> Offer:
    team = ctx["team"]
    offer = services.create_draft(app or ctx["app"], actor=team.recruiter, data=terms())
    services.submit_for_approval(offer, actor=team.recruiter)
    return services.approve(offer, actor=team.hr_manager, comment="Within budget")


def keys(user: Any) -> set[str]:
    return set(Notification.objects.filter(recipient_user=user).values_list("key", flat=True))


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"salary_amount": "0"}, "salary_amount"),
        ({"salary_amount": "12.345"}, "salary_amount"),
        ({"currency": "EUR"}, "currency"),
        ({"period": "week"}, "period"),
        ({"contract_type": "gig"}, "contract_type"),
        ({"start_date": (mhrs_time.now() - timedelta(days=1)).date()}, "start_date"),
        ({"expires_at": mhrs_time.now() - timedelta(hours=1)}, "expires_at"),
    ],
)
def test_draft_validation(ctx: dict[str, Any], override: dict[str, Any], field: str) -> None:
    with pytest.raises(DomainError) as err:
        services.create_draft(ctx["app"], actor=ctx["team"].recruiter, data=terms(**override))
    assert field in err.value.details


def test_only_after_interview_one_live_offer_and_permissions(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    early = make_application(ctx["job"], status=Status.SHORTLISTED)
    with pytest.raises(DomainError):
        services.create_draft(early, actor=team.recruiter, data=terms())
    with pytest.raises(PermissionDeniedError):
        services.create_draft(ctx["app"], actor=team.panelist, data=terms())
    offer = services.create_draft(ctx["app"], actor=team.recruiter, data=terms())
    assert offer.salary_amount == Decimal("1850.00") and offer.required_approvals == 1
    with pytest.raises(ConflictError):
        services.create_draft(ctx["app"], actor=team.recruiter, data=terms())


def test_issue_blocked_without_approval(ctx: dict[str, Any]) -> None:
    """EC-OFF-01."""
    team = ctx["team"]
    offer = services.create_draft(ctx["app"], actor=team.recruiter, data=terms())
    for o in (offer, services.submit_for_approval(offer, actor=team.recruiter)):
        with pytest.raises(DomainError) as err:
            services.issue(o, actor=team.recruiter)
        assert err.value.code == "offer_not_approved"


def test_approval_chain_separation_and_rounds(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    OrganisationPolicy.objects.filter(organisation=team.org).update(offer_approvals_required=2)
    offer = services.create_draft(ctx["app"], actor=team.hr_manager, data=terms())
    services.submit_for_approval(offer, actor=team.hr_manager)
    with pytest.raises(PermissionDeniedError):  # drafter can't approve
        services.approve(offer, actor=team.hr_manager)
    with pytest.raises(PermissionDeniedError):  # recruiters can't approve
        services.approve(offer, actor=team.recruiter)
    one = services.approve(offer, actor=team.admin)
    assert one.status == OfferStatus.PENDING_APPROVAL  # 1 of 2
    with pytest.raises(ConflictError):
        services.approve(offer, actor=team.admin)
    back = services.return_for_changes(offer, actor=team.admin, comment="Start date too early")
    assert back.status == OfferStatus.DRAFT and back.approval_round == 2
    updated = services.update_draft(
        back, actor=team.hr_manager, data={"salary_amount": "1900"}, lock_version=back.lock_version
    )
    with pytest.raises(ConflictError):  # stale version
        services.update_draft(back, actor=team.hr_manager, data={}, lock_version=back.lock_version)
    services.submit_for_approval(updated, actor=team.hr_manager)
    services.approve(updated, actor=team.admin)
    assert (
        Offer.objects.get(pk=offer.pk).status == OfferStatus.PENDING_APPROVAL
    )  # round 2: 1 of 2 again


def test_issue_creates_letter_moves_application_and_notifies(ctx: dict[str, Any]) -> None:
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    assert offer.status == OfferStatus.ISSUED and offer.issued_at
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.OFFER
    doc = offer.letter_document
    assert doc.purpose == "offer_letter" and doc.owner_user == ctx["candidate"] and doc.is_available
    pdf = storage.get_bytes("documents", doc.storage_key)
    # NFKC: PDF text extraction returns typographic ligatures ("ﬀ" for "ff")
    text = unicodedata.normalize("NFKC", pymupdf.open(stream=pdf, filetype="pdf")[0].get_text())
    assert "Offer of employment" in text and "Tendai Moyo" in text and "USD 1,850.00" in text
    assert "score" not in text.lower() and "AI" not in text.split()
    assert "offer_issued" in keys(ctx["candidate"])
    assert AuditEvent.objects.filter(action="offers.issued").exists()


def test_accept_records_electronic_acceptance(ctx: dict[str, Any]) -> None:
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    cand = ctx["candidate"]
    with pytest.raises(PermissionDeniedError):
        services.accept(
            offer,
            candidate=make_application(ctx["job"]).candidate_user,
            typed_name="Tendai Moyo",
            agree=True,
        )
    with pytest.raises(DomainError) as err:
        services.accept(offer, candidate=cand, typed_name="T Moyo", agree=False)
    assert set(err.value.details) == {"typed_name", "agree"}
    done, counter = services.accept(
        offer,
        candidate=cand,
        typed_name="  tendai   MOYO ",
        agree=True,
        ip="196.4.81.77",
        user_agent="Mozilla/5.0",
        counter_offer_note="Could the start be a week later?",
    )
    meta = done.acceptance_meta
    assert done.status == OfferStatus.ACCEPTED and meta["ip_prefix"] == "196.4.81.0/24"
    assert meta["typed_name"] == "tendai   MOYO" and len(meta["user_agent_sha256"]) == 64
    assert meta["letter_sha256"] == done.letter_document.sha256
    assert counter == {"openings": 1, "accepted": 1, "hired": 0, "remaining": 0, "over": False}
    assert "offer_accepted" in keys(ctx["team"].recruiter)
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.OFFER  # the hire is recorded by HR (P12-T05)


def test_two_acceptances_for_one_opening_warn(ctx: dict[str, Any]) -> None:
    """EC-OFF-03: never blocked, HR is warned."""
    first = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    services.accept(first, candidate=ctx["candidate"], typed_name="Tendai Moyo", agree=True)
    other = make_application(ctx["job"], status=Status.INTERVIEW)
    other.candidate_user.first_name, other.candidate_user.last_name = "Rudo", "Chari"
    other.candidate_user.save()
    second = services.issue(approved_offer(ctx, other), actor=ctx["team"].recruiter)
    _, counter = services.accept(
        second, candidate=other.candidate_user, typed_name="Rudo Chari", agree=True
    )
    assert counter["over"] is True and counter["accepted"] == 2
    note = Notification.objects.filter(key="offer_accepted").order_by("-created_at").first()
    assert note is not None and "more than the openings" in note.payload["openings_note"]
    Job.objects.unscoped().filter(pk=ctx["job"].pk).update(openings=2)
    assert services.openings(Job.objects.unscoped().get(pk=ctx["job"].pk))["over"] is False


def test_decline(ctx: dict[str, Any]) -> None:
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    done = services.decline(offer, candidate=ctx["candidate"], reason="Accepted another role")
    assert done.status == OfferStatus.DECLINED
    ctx["app"].refresh_from_db()
    assert ctx["app"].status == Status.OFFER_DECLINED
    assert "offer_declined" in keys(ctx["team"].recruiter)
    with pytest.raises(DomainError):
        services.accept(done, candidate=ctx["candidate"], typed_name="Tendai Moyo", agree=True)


def test_expiry_and_reminder(ctx: dict[str, Any]) -> None:
    """EC-OFF-02."""
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)  # expires in 7 days
    now = mhrs_time.now()
    assert services.expire_due(now) == {"expired": 0, "reminded": 0}
    assert services.expire_due(now + timedelta(days=6)) == {"expired": 0, "reminded": 1}
    assert services.expire_due(now + timedelta(days=6, hours=1)) == {"expired": 0, "reminded": 0}
    assert "offer_expiring" in keys(ctx["candidate"])
    assert services.expire_due(now + timedelta(days=8)) == {"expired": 1, "reminded": 0}
    offer.refresh_from_db()
    assert offer.status == OfferStatus.EXPIRED and "offer_expired" in keys(ctx["team"].recruiter)
    with pytest.raises(DomainError):
        services.accept(offer, candidate=ctx["candidate"], typed_name="Tendai Moyo", agree=True)
    # a new offer can follow (application still at offer)
    renewed = services.create_draft(ctx["app"], actor=ctx["team"].recruiter, data=terms())
    assert renewed.status == OfferStatus.DRAFT


def test_employer_withdrawal(ctx: dict[str, Any]) -> None:
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    with pytest.raises(PermissionDeniedError):
        services.withdraw(offer, actor=ctx["team"].recruiter, reason="Budget frozen for Q1")
    done = services.withdraw(offer, actor=ctx["team"].hr_manager, reason="Budget frozen for Q1")
    assert done.status == OfferStatus.WITHDRAWN and "offer_withdrawn" in keys(ctx["candidate"])


def test_candidate_withdraws_after_accepting(ctx: dict[str, Any]) -> None:
    """EC-OFF-04: offer withdrawn, hire record cancelled."""
    offer = services.issue(approved_offer(ctx), actor=ctx["team"].recruiter)
    services.accept(offer, candidate=ctx["candidate"], typed_name="Tendai Moyo", agree=True)
    HireRecord.objects.create(
        organisation=ctx["team"].org,
        application=ctx["app"],
        offer=offer,
        start_date=offer.start_date,
        recorded_at=mhrs_time.now(),
    )
    transition(ctx["app"], Status.WITHDRAWN, actor=ctx["candidate"], reason="Personal reasons")
    assert services.on_application_withdrawn(ctx["app"].pk) == 1
    offer.refresh_from_db()
    assert offer.status == OfferStatus.WITHDRAWN
    assert HireRecord.objects.for_org(ctx["team"].org).get().cancelled_at is not None
    assert services.on_application_withdrawn(ctx["app"].pk) == 0  # idempotent


def test_letter_escapes_user_text(ctx: dict[str, Any]) -> None:
    from apps.offers import letter

    offer = services.create_draft(
        ctx["app"],
        actor=ctx["team"].recruiter,
        data=terms(conditions='<script>alert(1)</script>\nBonus "up to 10%" & allowances'),
    )
    html = letter.html(offer)
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp; allowances" in html


def test_policy_approvals_range(ctx: dict[str, Any]) -> None:
    from django.core.exceptions import ValidationError

    policy = OrganisationPolicy.objects.get(organisation=ctx["team"].org)
    for bad in (0, 6):
        policy.offer_approvals_required = bad
        with pytest.raises(ValidationError):
            policy.full_clean()
