"""P14-T02: billing models - default plans seeded (D-13, edits kept), one subscription per
organisation, unique usage counters, RLS on tenant tables."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.billing.models import Plan, Subscription, UsageCounter
from apps.billing.plans import seed_default_plans
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def test_default_plans_seeded_and_edits_kept() -> None:
    codes = set(Plan.objects.values_list("code", flat=True))
    assert {"trial", "starter", "growth", "enterprise"} <= codes
    starter = Plan.objects.get(code="starter")
    assert starter.price_usd == Decimal("49.00") and starter.limits["active_vacancies"] == 5
    assert Plan.objects.get(code="growth").price_usd == Decimal("149.00")
    assert Plan.objects.get(code="enterprise").limits == {}  # unlimited, custom price
    starter.price_usd = Decimal("55.00")
    starter.save()
    assert seed_default_plans() == 0
    assert Plan.objects.get(code="starter").price_usd == Decimal("55.00")


def test_one_subscription_and_unique_counters() -> None:
    team = make_org_with_team()
    trial = Plan.objects.get(code="trial")
    Subscription.objects.create(organisation=team.org, plan=trial)
    with pytest.raises(IntegrityError), transaction.atomic():
        Subscription.objects.create(organisation=team.org, plan=trial)
    period = date(2026, 11, 1)
    UsageCounter.objects.create(organisation=team.org, metric="seats", period=period, value=3)
    with pytest.raises(IntegrityError), transaction.atomic():
        UsageCounter.objects.create(organisation=team.org, metric="seats", period=period)


def test_row_level_security_on_billing_tables() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity "
            "AND relname LIKE 'billing_%%'"
        )
        tables = {r[0] for r in cur.fetchall()}
    assert tables == {
        "billing_subscription",
        "billing_usagecounter",
        "billing_invoice",
        "billing_payment",
    }
