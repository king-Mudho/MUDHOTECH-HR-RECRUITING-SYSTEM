"""P14-T04: usage metering - consumers count each event once, daily roll-up keeps the month's peak,
usage page for organisation admins only."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.billing import metering
from apps.billing.models import UsageCounter
from apps.billing.tasks import meter_application, meter_evaluation
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def counter(org: Any, metric: str) -> int:
    row = UsageCounter.objects.for_org(org).filter(
        metric=metric, period=now().date().replace(day=1)
    )
    return row.first().value if row.exists() else 0


def test_consumers_count_each_event_once() -> None:
    team = make_org_with_team()
    event = OutboxEvent.objects.create(
        event_type="screening.completed",
        aggregate_type="application",
        aggregate_id="x",
        payload={"application_id": "x"},
        organisation_id=team.org.pk,
        dedupe_key="screening.completed:test-1",
        available_at=now(),
    )
    meter_evaluation(str(event.pk))
    meter_evaluation(str(event.pk))  # redelivered: idempotent
    assert counter(team.org, "ai_evaluations_month") == 1
    submitted = OutboxEvent.objects.create(
        event_type="application.submitted",
        aggregate_type="application",
        aggregate_id="y",
        payload={"application_id": "y"},
        organisation_id=team.org.pk,
        dedupe_key="application.submitted:test-1",
        available_at=now(),
    )
    meter_application(str(submitted.pk))
    assert counter(team.org, "applications_month") == 1
    metering.increment(team.org.pk, "applications_month", day=date(2026, 1, 15))
    assert UsageCounter.objects.for_org(team.org).filter(period=date(2026, 1, 1)).count() == 1


def test_rollup_keeps_the_monthly_peak() -> None:
    team = make_org_with_team()
    jobs = [published_job(organisation=team.org) for _ in range(3)]
    assert metering.rollup(team.org.pk)["active_vacancies"] == 3
    Job.objects.for_org(team.org).filter(pk=jobs[0].pk).update(status=JobStatus.CLOSED)
    assert metering.rollup(team.org.pk)["active_vacancies"] == 3  # peak stays
    assert counter(team.org, "active_vacancies") == 3
    assert counter(team.org, "seats") == 6


def test_usage_page_for_org_admins() -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    body = staff(team.admin, team.org).get("/api/v1/hr/billing/").json()
    assert body["plan"]["code"] == "trial" and body["subscription"]["status"] == "trialing"
    used = {u["metric"]: u for u in body["usage"]}
    assert used["active_vacancies"]["used"] == 1 and used["active_vacancies"]["limit"] == 2
    assert used["applications_month"]["used"] == 1 and used["applications_month"]["limit"] is None
    assert {p["code"] for p in body["plans"]} >= {"starter", "growth", "enterprise"}
    assert staff(team.hr_manager, team.org).get("/api/v1/hr/billing/").status_code == 403
