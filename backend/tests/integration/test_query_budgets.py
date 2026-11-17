"""Query budgets for the hot endpoints (P10-T05, NFR-PERF-01): no N+1.

Each endpoint is called with a small and a larger data set; the number of SQL queries must not
grow with the number of rows (the larger call may use at most the small call's count).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit import services as audit
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def queries(call: Callable[[], Any]) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = call()
    assert response.status_code == 200, getattr(response, "content", b"")[:300]
    return len(ctx.captured_queries)


def add_applications(job: Any, n: int) -> None:
    for i in range(n):
        app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
        Application.objects.unscoped().filter(pk=app.pk).update(
            score=Decimal(50 + i % 50), ai_band="review_needed", tags=["python"]
        )


def assert_constant(small: int, large: int, what: str) -> None:
    assert large <= small, f"{what}: {small} queries for few rows, {large} for many (N+1)"


def test_hr_applicants_list_does_not_grow_with_rows() -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    c = staff(team.hr_manager, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/?page_size=50"
    add_applications(job, 3)
    small = queries(lambda: c.get(url))
    add_applications(job, 30)
    large = queries(lambda: c.get(url))
    assert_constant(small, large, "applicants list")
    assert small <= 25  # absolute budget: auth, org context, page, count, audit view log


def test_hr_dashboard_does_not_grow_with_rows() -> None:
    team = make_org_with_team()
    jobs = [published_job(organisation=team.org) for _ in range(2)]
    c = staff(team.hr_manager, team.org)
    add_applications(jobs[0], 3)
    small = queries(lambda: c.get("/api/v1/hr/dashboard/summary/"))
    for job in jobs:
        add_applications(job, 15)
    jobs.append(published_job(organisation=team.org))
    large = queries(lambda: c.get("/api/v1/hr/dashboard/summary/"))
    assert_constant(small, large, "HR dashboard")


def test_candidate_applications_list_does_not_grow_with_rows() -> None:
    team = make_org_with_team()
    candidate = UserFactory(verified=True)
    c = APIClient()
    c.force_login(candidate)
    make_application(published_job(organisation=team.org), candidate, status=Status.UNDER_REVIEW)
    small = queries(lambda: c.get("/api/v1/applications/"))
    for _ in range(8):
        make_application(
            published_job(organisation=team.org), candidate, status=Status.UNDER_REVIEW
        )
    large = queries(lambda: c.get("/api/v1/applications/"))
    assert_constant(small, large, "candidate applications")


def test_audit_events_list_does_not_grow_with_rows() -> None:
    team = make_org_with_team()
    c = staff(team.admin, team.org)
    job = published_job(organisation=team.org)

    def events(n: int) -> None:
        for i in range(n):
            audit.record(actor=team.admin, action="test.event", target=job, after={"i": i})

    events(3)
    small = queries(lambda: c.get("/api/v1/hr/audit-events/"))
    events(40)
    large = queries(lambda: c.get("/api/v1/hr/audit-events/"))
    assert_constant(small, large, "audit events")
