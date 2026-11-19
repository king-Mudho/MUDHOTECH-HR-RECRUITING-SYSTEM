"""P12-T06: offer API behaviour beyond the role matrix - candidate view/accept/decline, idempotent
accept, acceptance metadata from the request, draft offers invisible to candidates.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.core import time as mhrs_time
from apps.offers import services
from apps.offers.models import Offer, OfferStatus
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    app = make_application(published_job(organisation=team.org), status=Status.INTERVIEW)
    user = app.candidate_user
    user.first_name, user.last_name = "Tendai", "Moyo"
    user.save()
    offer = services.create_draft(
        app,
        actor=team.recruiter,
        data={
            "salary_amount": "1500",
            "currency": "USD",
            "period": "month",
            "start_date": (mhrs_time.now() + timedelta(days=30)).date(),
            "contract_type": "full_time",
            "expires_at": mhrs_time.now() + timedelta(days=7),
        },
    )
    return {"team": team, "app": app, "offer": offer, "user": user}


def candidate(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def test_candidate_never_sees_unissued_offers(ctx: dict[str, Any]) -> None:
    me = candidate(ctx["user"])
    assert me.get(f"/api/v1/applications/{ctx['app'].pk}/offers/").json() == []
    resp = me.post(
        f"/api/v1/offers/{ctx['offer'].pk}/accept/",
        {"typed_name": "Tendai Moyo", "agree": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 404


def test_accept_via_api_records_request_metadata_and_is_idempotent(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    services.submit_for_approval(ctx["offer"], actor=team.recruiter)
    services.approve(ctx["offer"], actor=team.hr_manager)
    services.issue(ctx["offer"], actor=team.recruiter)
    me = candidate(ctx["user"])
    listing = me.get(f"/api/v1/applications/{ctx['app'].pk}/offers/").json()
    assert listing[0]["status"] == "issued" and listing[0]["letter_document_id"]
    assert "I accept this offer" in listing[0]["acceptance_statement"]
    stranger = candidate(UserFactory())
    key = str(uuid.uuid4())
    body = {"typed_name": "Tendai Moyo", "agree": True}
    assert (
        stranger.post(
            f"/api/v1/offers/{ctx['offer'].pk}/accept/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ).status_code
        == 404
    )
    first = me.post(
        f"/api/v1/offers/{ctx['offer'].pk}/accept/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="196.4.81.77",
        HTTP_USER_AGENT="Mozilla/5.0",
    )
    again = me.post(
        f"/api/v1/offers/{ctx['offer'].pk}/accept/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="196.4.81.77",
    )
    assert first.status_code == 200 and again.status_code == 200
    assert first.json() == again.json()  # double click: same answer, accepted once
    offer = Offer.objects.get(pk=ctx["offer"].pk)
    assert (
        offer.status == OfferStatus.ACCEPTED
        and offer.acceptance_meta["ip_prefix"] == "196.4.81.0/24"
    )
    # the letter is downloadable by its owner through the documents API
    letter = me.get(f"/api/v1/documents/{offer.letter_document_id}/download/")
    assert letter.status_code == 302


def test_decline_via_api(ctx: dict[str, Any]) -> None:
    team = ctx["team"]
    services.submit_for_approval(ctx["offer"], actor=team.recruiter)
    services.approve(ctx["offer"], actor=team.hr_manager)
    services.issue(ctx["offer"], actor=team.recruiter)
    resp = candidate(ctx["user"]).post(
        f"/api/v1/offers/{ctx['offer'].pk}/decline/",
        {"reason": "Accepted another role"},
        format="json",
    )
    assert resp.status_code == 200 and resp.json()["status"] == "declined"
