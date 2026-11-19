"""Phase 14 exit: trial -> paid through Paynow (test double) end to end; entitlements enforced;
candidate flows never blocked by billing."""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.tests.factories import published_job
from apps.applications.tests.test_submit import ready_draft, submit
from apps.billing import lifecycle, paynow
from apps.billing.models import Subscription
from apps.billing.tests.test_payments import KEY, POLL, FakePaynow
from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.jobs.tests.test_services import approved_job
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake(settings: Any) -> Any:
    settings.BILLING_ENFORCE = True
    settings.PAYNOW_INTEGRATIONS = {"USD": {"id": "1201", "key": KEY}}
    f = FakePaynow()
    paynow.set_transport(f)
    yield f
    paynow.set_transport(None)


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def test_trial_to_paid_with_paynow_and_candidates_never_blocked(fake: FakePaynow, s3: Any) -> None:
    team = make_org_with_team()
    team.org.verified_at = now()
    team.org.save(update_fields=["verified_at"])
    OrganisationPolicy.objects.filter(organisation=team.org).update(
        privacy_notice="We process your application data to assess suitability for the role."
    )
    admin, hr = staff(team.admin, team.org), staff(team.hr_manager, team.org)

    # trial: 2 published vacancies allowed
    assert admin.get("/api/v1/hr/billing/").json()["subscription"]["status"] == "trialing"
    live = [published_job(organisation=team.org) for _ in range(2)]
    third = approved_job(team)
    blocked = hr.post(f"/api/v1/hr/jobs/{third.pk}/publish/", {}, format="json")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "plan_limit_reached"

    # the trial ends and the grace period runs out: staff read-only, candidates unaffected
    Subscription.objects.for_org(team.org).update(trial_ends_at=now() - timedelta(minutes=1))
    lifecycle.sweep()
    Subscription.objects.for_org(team.org).update(grace_until=now() - timedelta(minutes=1))
    lifecycle.sweep()
    assert admin.get("/api/v1/hr/billing/").json()["subscription"]["status"] == "read_only"
    pause = hr.post(f"/api/v1/hr/jobs/{live[0].pk}/pause/", {}, format="json")
    assert pause.json()["error"]["code"] == "billing_read_only"
    user = UserFactory()
    candidate = APIClient()
    candidate.force_login(user)
    assert submit(candidate, ready_draft(live[0], user)).status_code == 201

    # choose Growth and pay with EcoCash through Paynow
    invoice = admin.post("/api/v1/hr/billing/change-plan/", {"plan": "growth"}, format="json")
    assert invoice.status_code == 201
    started = admin.post(
        f"/api/v1/hr/billing/invoices/{invoice.json()['id']}/pay/",
        {"method": "ecocash", "phone": "0771234567"},
        format="json",
    )
    assert started.status_code == 201, started.content
    payment = started.json()["payment"]
    guid = next(iter(fake.state))
    fake.state[guid]["status"] = "Paid"
    fields = [
        ("reference", payment["reference"]),
        ("paynowreference", "PN-1"),
        ("amount", payment["amount"]),
        ("status", "Paid"),
        ("pollurl", POLL + guid),
    ]
    body = urllib.parse.urlencode([*fields, ("hash", paynow.make_hash(fields, KEY))])
    result = APIClient().post(
        "/api/v1/billing/paynow/result/", body, content_type="application/x-www-form-urlencoded"
    )
    assert result.status_code == 200
    assert admin.get(f"/api/v1/hr/billing/payments/{payment['id']}/").json()["status"] == "paid"

    # active on Growth: writes work again and the higher limit applies
    overview = admin.get("/api/v1/hr/billing/").json()
    assert overview["subscription"]["status"] == "active" and overview["plan"]["code"] == "growth"
    published = hr.post(f"/api/v1/hr/jobs/{third.pk}/publish/", {}, format="json")
    assert published.status_code == 200, published.content
    assert Job.objects.for_org(team.org).filter(status=JobStatus.PUBLISHED).count() == 3
    invoices = admin.get("/api/v1/hr/billing/invoices/").json()
    assert invoices[0]["status"] == "paid"
