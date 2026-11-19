"""P14-T08: change plan (invoice first, plan takes effect when paid) and platform plan management;
trial -> paid end to end with a manual payment."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.billing import entitlements
from apps.billing.models import Invoice, Plan, Subscription
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def platform() -> APIClient:
    c = APIClient()
    c.force_login(UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN))
    return c


def test_trial_to_paid_via_plan_change(s3: Any) -> None:
    team = make_org_with_team()
    assert entitlements.subscription_for(team.org.pk).status == "trialing"
    admin = staff(team.admin, team.org)
    first = admin.post("/api/v1/hr/billing/change-plan/", {"plan": "starter"}, format="json")
    assert first.status_code == 201 and first.json()["amount"] == "49.00"
    # choosing again replaces the unpaid choice
    second = admin.post("/api/v1/hr/billing/change-plan/", {"plan": "growth"}, format="json")
    assert second.status_code == 201
    statuses = dict(Invoice.objects.for_org(team.org).values_list("number", "status"))
    assert sorted(statuses.values()) == ["open", "void"]
    sub = Subscription.objects.for_org(team.org).get()
    assert sub.plan.code == "trial"  # nothing changes until paid
    paid = platform().post(
        f"/api/v1/platform/billing/invoices/{second.json()['id']}/manual-payment/",
        {"amount": second.json()["amount"], "reference": "ZB-7788"},
        format="json",
    )
    assert paid.status_code == 201
    sub.refresh_from_db()
    assert sub.plan.code == "growth" and sub.status == "active"
    assert sub.current_period_end is not None and sub.trial_ends_at <= sub.current_period_start
    again = admin.post("/api/v1/hr/billing/change-plan/", {"plan": "growth"}, format="json")
    assert again.status_code == 409
    custom = admin.post("/api/v1/hr/billing/change-plan/", {"plan": "enterprise"}, format="json")
    assert custom.status_code == 409 and custom.json()["error"]["code"] == "plan_custom_price"
    zwg = admin.post(
        "/api/v1/hr/billing/change-plan/", {"plan": "starter", "currency": "ZWG"}, format="json"
    )
    assert zwg.status_code == 409  # no ZWG price set yet
    assert (
        staff(team.hr_manager, team.org)
        .post("/api/v1/hr/billing/change-plan/", {"plan": "starter"}, format="json")
        .status_code
        == 403
    )
    assert admin.post("/api/v1/hr/billing/change-plan/", {"plan": "trial"}).status_code == 404


def test_platform_plan_management() -> None:
    c = platform()
    rows = {p["code"]: p for p in c.get("/api/v1/platform/billing/plans/").json()}
    assert {"trial", "starter", "growth", "enterprise"} <= set(rows)
    body = {
        **{k: rows["starter"][k] for k in ("code", "name", "description", "limits")},
        "price_usd": "59.00",
        "price_zwg": "1500.00",
        "is_public": True,
        "active": True,
        "order": 1,
    }
    saved = c.post("/api/v1/platform/billing/plans/", body, format="json")
    assert saved.status_code == 200 and saved.json()["price_usd"] == "59.00"
    assert Plan.objects.get(code="starter").price_zwg == Decimal("1500.00")
    bad = c.post(
        "/api/v1/platform/billing/plans/",
        {**body, "code": "x", "limits": {"widgets": 3}},
        format="json",
    )
    assert bad.status_code == 400
    support = APIClient()
    support.force_login(UserFactory(platform_role=PlatformRole.PLATFORM_SUPPORT))
    assert support.get("/api/v1/platform/billing/plans/").status_code == 200
    assert support.post("/api/v1/platform/billing/plans/", body, format="json").status_code == 403
