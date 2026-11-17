"""Row-level security (P09-T07, ADR-012): second line of tenant defence + overhead record."""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


APP_ROLE = "mhrs_rls_probe"


def _ensure_app_role() -> None:
    """A non-superuser role like the production application role (superusers bypass RLS)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mhrs_rls_probe') "
            "THEN CREATE ROLE mhrs_rls_probe NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")


@contextmanager
def app_role() -> Iterator[None]:
    _ensure_app_role()
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {APP_ROLE}")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@contextmanager
def org_context(org_id: Any) -> Iterator[None]:
    with app_role(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_org', %s, false)", [str(org_id)])
        try:
            yield
        finally:
            cursor.execute("SELECT set_config('app.current_org', '', false)")


def test_policy_hides_other_tenants_rows_even_without_a_filter() -> None:
    a, b = make_org_with_team(), make_org_with_team()
    mine = make_application(
        published_job(organisation=a.org), UserFactory(), status=Status.UNDER_REVIEW
    )
    theirs = make_application(
        published_job(organisation=b.org), UserFactory(), status=Status.UNDER_REVIEW
    )
    with org_context(a.org.pk):
        # a forgotten tenant filter (unscoped) still cannot reach the other organisation
        ids = set(Application.objects.unscoped().values_list("pk", flat=True))
    assert mine.pk in ids and theirs.pk not in ids
    # without a context (system code, candidates, platform) nothing is restricted
    both = set(Application.objects.unscoped().values_list("pk", flat=True))
    assert {mine.pk, theirs.pk} <= both


def test_writes_into_another_tenant_are_refused() -> None:
    from django.db import DatabaseError, transaction

    a, b = make_org_with_team(), make_org_with_team()
    theirs = make_application(
        published_job(organisation=b.org), UserFactory(), status=Status.UNDER_REVIEW
    )
    with org_context(a.org.pk):
        changed = Application.objects.unscoped().filter(pk=theirs.pk).update(tags=["x"])
        assert changed == 0  # invisible rows cannot be updated
        with pytest.raises(DatabaseError), transaction.atomic():
            Application.objects.unscoped().filter(pk=theirs.pk).update(organisation_id=a.org.pk)
            Application.objects.unscoped().create(
                organisation_id=b.org.pk,
                job=theirs.job,
                job_version=theirs.job_version,
                candidate_user=UserFactory(),
                status="draft",
            )


def test_hr_requests_set_and_clear_the_context() -> None:
    a = make_org_with_team()
    job = published_job(organisation=a.org)
    make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    c = APIClient()
    c.force_login(a.hr_manager)
    c.credentials(HTTP_X_ORG_ID=str(a.org.pk))
    assert c.get(f"/api/v1/hr/jobs/{job.pk}/applications/").json()["count"] == 1
    with connection.cursor() as cursor:
        cursor.execute("SELECT coalesce(current_setting('app.current_org', true), '')")
        assert cursor.fetchone()[0] == ""  # reset after the request (pooled connections)


@pytest.mark.slow
def test_rls_overhead_on_the_applicants_query_is_small() -> None:
    """Exit record for ADR-012: the applicants list query with and without an org context."""
    orgs = [make_org_with_team(), make_org_with_team()]
    jobs = [published_job(organisation=o.org) for o in orgs]
    users = [UserFactory() for _ in range(40)]
    for job in jobs:
        for i in range(600):
            app = make_application(
                job, users[i % 40] if i < 40 else UserFactory(), status=Status.UNDER_REVIEW
            )
            Application.objects.unscoped().filter(pk=app.pk).update(score=Decimal(i % 100))
    job = jobs[0]

    def run() -> float:
        start = time.perf_counter()
        list(
            Application.objects.for_org(job.organisation_id)
            .filter(job=job, status="under_review")
            .order_by("-score", "-submitted_at")[:50]
            .values_list("pk", flat=True)
        )
        return time.perf_counter() - start

    with app_role():
        for _ in range(20):
            run()
        plain = statistics.median(run() for _ in range(200))
    with org_context(job.organisation_id):
        for _ in range(20):
            run()
        scoped = statistics.median(run() for _ in range(200))
    overhead = (scoped - plain) / plain
    summary = f"{plain * 1000:.2f} ms -> {scoped * 1000:.2f} ms ({overhead:+.1%})"
    print(f"\n[ADR-012] applicants query median {summary}")  # noqa: T201
    assert overhead < 0.10
