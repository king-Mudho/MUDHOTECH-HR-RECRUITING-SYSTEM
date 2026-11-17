"""HR dashboard (P08-T10): cards, AI vs human split, funnel - reconciled with direct queries."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.core.time import now
from apps.jobs.models import JobAssignment
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team
from apps.shortlisting.models import Shortlist

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def app(job: Any, status: str, band: str = "", days_ago: int = 0) -> Application:
    a = make_application(job, UserFactory(), status=status)
    Application.objects.unscoped().filter(pk=a.pk).update(
        ai_band=band, submitted_at=now() - timedelta(days=days_ago)
    )
    a.refresh_from_db()
    return a


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    dev = published_job(organisation=team.org, title="Software Developer")
    analyst = published_job(organisation=team.org, title="Analyst")
    apps = [
        app(dev, Status.UNDER_REVIEW, "recommended_for_review"),
        app(dev, Status.UNDER_REVIEW, "review_needed", days_ago=3),
        app(dev, Status.PROCESSING, days_ago=10),
        app(dev, Status.PROCESSING_ERROR, days_ago=1),
        app(analyst, Status.UNDER_REVIEW, "lower_match"),
        app(analyst, Status.WITHDRAWN, days_ago=2),
    ]
    transition(apps[0], Status.SHORTLISTED, actor=team.hr_manager, reason="Strong evidence")
    Shortlist.objects.create(
        organisation=team.org,
        job=dev,
        job_version=dev.published_version,
        proposed_by=team.recruiter,
        status="pending_approval",
        submitted_at=now(),
    )
    return team, dev, analyst, apps


def test_cards_reconcile_with_direct_queries(world: Any) -> None:
    team, _dev, _, _ = world
    body = staff(team.hr_manager, team.org).get("/api/v1/hr/dashboard/summary/").json()
    org_apps = Application.objects.for_org(team.org).exclude(status__in=["draft", "abandoned"])
    cards = body["cards"]
    assert cards["pending_reviews"] == org_apps.filter(status="under_review").count() == 2
    assert cards["processing_errors"] == org_apps.filter(status="processing_error").count() == 1
    assert (
        cards["processing_queue"] == org_apps.filter(status__in=["submitted", "processing"]).count()
    )
    assert (
        cards["applications_7d"]
        == org_apps.filter(submitted_at__gte=now() - timedelta(days=7)).count()
        == 5
    )
    assert cards["shortlist_approvals_pending"] == 1
    assert cards["open_vacancies"] == 2
    # AI suggestions and human decisions are separate
    assert body["ai_suggestions"]["bands"] == {"review_needed": 1, "lower_match": 1}
    assert body["ai_suggestions"]["ai_notice"].startswith("AI-assisted")
    human = ApplicationStatusEvent.objects.for_org(team.org).filter(
        actor_type="human", to_status="shortlisted"
    )
    assert body["human_decisions"]["shortlisted"] == human.count() == 1
    assert [r["status"] for r in body["queues"]["failed_processing"]] == ["processing_error"]
    assert body["queues"]["approvals"][0]["job_title"] == "Software Developer"


def test_filters_by_vacancy_and_date(world: Any) -> None:
    team, _dev, analyst, _ = world
    c = staff(team.hr_manager, team.org)
    only_analyst = c.get("/api/v1/hr/dashboard/summary/", {"job": str(analyst.pk)}).json()
    assert only_analyst["cards"]["pending_reviews"] == 1
    assert only_analyst["cards"]["shortlist_approvals_pending"] == 0
    today = now().date().isoformat()
    recent = c.get("/api/v1/hr/dashboard/summary/", {"from": today, "to": today}).json()
    assert recent["cards"]["pending_reviews"] == 1  # the one submitted today


def test_funnel(world: Any) -> None:
    team, dev, _, _ = world
    body = staff(team.hr_manager, team.org).get(f"/api/v1/hr/jobs/{dev.pk}/funnel/").json()
    stages = {s["stage"]: s["count"] for s in body["stages"]}
    direct = (
        Application.objects.for_org(team.org)
        .filter(job=dev)
        .exclude(status__in=["draft", "abandoned"])
    )
    assert stages["submitted"] == direct.count() == 4
    assert stages["shortlisted"] == direct.filter(status="shortlisted").count() == 1
    assert stages["reviewed"] == 1 and stages["processed"] == 2


def test_recruiter_sees_only_assigned_vacancies(world: Any) -> None:
    team, dev, _, _ = world
    JobAssignment.objects.create(
        organisation=team.org,
        job=dev,
        membership=Membership.objects.get(user=team.recruiter, organisation=team.org),
        role_on_job="recruiter",
    )
    body = staff(team.recruiter, team.org).get("/api/v1/hr/dashboard/summary/").json()
    assert body["cards"]["pending_reviews"] == 1  # the Analyst vacancy is not theirs
    other = make_org_with_team()
    foreign = staff(other.hr_manager, other.org).get("/api/v1/hr/dashboard/summary/").json()
    assert foreign["cards"]["pending_reviews"] == 0
