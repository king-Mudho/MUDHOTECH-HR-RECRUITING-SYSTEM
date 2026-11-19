"""P14-T07: dunning and lifecycle - reminder before due, overdue -> 7-day grace -> read-only for
staff (billing still usable), public vacancies and candidates unaffected (EC-BIL-04), trial end,
reactivation on payment."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.tests.factories import published_job
from apps.applications.tests.test_submit import ready_draft, submit
from apps.billing import entitlements, invoicing, lifecycle
from apps.billing.models import Invoice, Plan, Subscription, SubscriptionStatus
from apps.core.time import now
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enforce(settings: Any) -> None:
    settings.BILLING_ENFORCE = True


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def keys(user: Any) -> set[str]:
    return set(Notification.objects.filter(recipient_user=user).values_list("key", flat=True))


@pytest.fixture
def world(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    sub = entitlements.subscription_for(team.org.pk)
    Subscription.objects.for_org(team.org).filter(pk=sub.pk).update(
        plan=Plan.objects.get(code="starter"), status=SubscriptionStatus.ACTIVE
    )
    sub.refresh_from_db()
    invoice = invoicing.issue_invoice(sub, period_start=now(), period_end=now() + timedelta(30))
    return {"team": team, "sub": sub, "invoice": invoice}


def status(world: dict[str, Any]) -> str:
    return Subscription.objects.for_org(world["team"].org).get().status


def test_reminder_overdue_grace_then_read_only_and_reactivation(world: dict[str, Any]) -> None:
    team, invoice = world["team"], world["invoice"]
    Invoice.objects.for_org(team.org).filter(pk=invoice.pk).update(due_at=now() + timedelta(days=2))
    assert lifecycle.sweep()["due_soon"] == 1
    assert "invoice_due_soon" in keys(team.admin)
    Invoice.objects.for_org(team.org).filter(pk=invoice.pk).update(due_at=now() - timedelta(1))
    assert lifecycle.sweep()["overdue"] == 1
    assert status(world) == SubscriptionStatus.PAST_DUE and "invoice_overdue" in keys(team.admin)
    # during grace everything still works for staff
    hr = staff(team.hr_manager, team.org)
    paused = published_job(organisation=team.org)
    assert hr.post(f"/api/v1/hr/jobs/{paused.pk}/pause/", {}, format="json").status_code == 200
    job = published_job(organisation=team.org)
    Subscription.objects.for_org(team.org).update(grace_until=now() - timedelta(minutes=1))
    assert lifecycle.sweep()["read_only"] == 1
    assert status(world) == SubscriptionStatus.READ_ONLY
    assert "subscription_read_only" in keys(team.admin)
    # read-only: staff writes refused, reads fine, billing still usable to pay
    blocked = hr.post(f"/api/v1/hr/jobs/{job.pk}/pause/", {"reason": "Hold"}, format="json")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "billing_read_only"
    assert hr.get("/api/v1/hr/jobs/").status_code == 200
    admin = staff(team.admin, team.org)
    pay = admin.post(f"/api/v1/hr/billing/invoices/{invoice.pk}/pay/", {"method": "card"})
    assert pay.status_code == 503  # not blocked by read-only (Paynow not configured in tests)
    # EC-BIL-04: the public vacancy stays open and candidates still apply
    user = UserFactory()
    candidate = APIClient()
    candidate.force_login(user)
    assert APIClient().get(f"/api/v1/jobs/{job.slug}/").status_code == 200
    assert submit(candidate, ready_draft(job, user)).status_code == 201
    # a bank payment recorded by the platform reactivates immediately
    platform = APIClient()
    platform.force_login(UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN))
    paid = platform.post(
        f"/api/v1/platform/billing/invoices/{invoice.pk}/manual-payment/",
        {"amount": str(invoice.amount), "reference": "ZB-123"},
        format="json",
    )
    assert paid.status_code == 201
    assert status(world) == SubscriptionStatus.ACTIVE
    unblocked = hr.post(f"/api/v1/hr/jobs/{job.pk}/pause/", {"reason": "Hold"}, format="json")
    assert unblocked.status_code == 200


def test_trial_reminder_end_and_grace() -> None:
    team = make_org_with_team()
    sub = entitlements.subscription_for(team.org.pk)
    Subscription.objects.for_org(team.org).filter(pk=sub.pk).update(
        trial_ends_at=now() + timedelta(days=3)
    )
    assert lifecycle.sweep()["trial_ending"] == 1 and "trial_ending" in keys(team.admin)
    Subscription.objects.for_org(team.org).filter(pk=sub.pk).update(trial_ends_at=now())
    assert lifecycle.sweep()["trial_ended"] == 1
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.PAST_DUE and sub.grace_until > now()
    assert "trial_ended" in keys(team.admin)


def test_sweep_is_idempotent(world: dict[str, Any]) -> None:
    Invoice.objects.for_org(world["team"].org).update(due_at=now() - timedelta(1))
    lifecycle.sweep()
    sent = Notification.objects.filter(key="invoice_overdue").count()
    again = lifecycle.sweep()
    assert again["overdue"] == 0 and again["read_only"] == 0
    assert Notification.objects.filter(key="invoice_overdue").count() == sent
