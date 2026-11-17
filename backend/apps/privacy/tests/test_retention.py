"""Retention engine (P09-T05)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.core.time import now
from apps.jobs.models import Job
from apps.notifications.models import Notification
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import retention, services
from apps.privacy.models import RetentionRun

pytestmark = pytest.mark.django_db


def app(job: Any, status: str) -> Application:
    a = make_application(job, UserFactory(), status=status)
    Application.objects.unscoped().filter(pk=a.pk).update(
        candidate_profile_snapshot={"first_name": "Tendai", "last_name": "Chari"}
    )
    a.refresh_from_db()
    return a


@pytest.fixture
def world(s3: Any) -> Any:
    team = make_org_with_team()
    OrganisationPolicy.objects.filter(organisation=team.org).update(retention_months=6)
    old = published_job(organisation=team.org, title="Old vacancy")
    recent = published_job(organisation=team.org, title="Recent vacancy")
    Job.objects.unscoped().filter(pk=old.pk).update(
        status="closed", closed_at=now() - timedelta(days=250)
    )
    Job.objects.unscoped().filter(pk=recent.pk).update(
        status="closed", closed_at=now() - timedelta(days=30)
    )
    apps = {
        "old_not_selected": app(old, Status.NOT_SELECTED),
        "old_withdrawn": app(old, Status.WITHDRAWN),
        "old_hired": app(old, Status.HIRED),
        "old_held": app(old, Status.NOT_SELECTED),
        "recent": app(recent, Status.NOT_SELECTED),
    }
    services.place_hold(
        team.org.pk,
        team.admin,
        target_type="application",
        target_id=apps["old_held"].pk,
        reason="Ongoing dispute",
    )
    return team, apps


def erased(a: Application) -> bool:
    a.refresh_from_db()
    return a.candidate_profile_snapshot == {"erased": True}


def test_dry_run_reports_without_changing_anything(world: Any) -> None:
    team, apps = world
    (run,) = [r for r in retention.run_all(dry_run=True) if r.organisation_id == team.org.pk]
    assert run.dry_run and run.counts == {"due": 2, "held": 1}
    assert not any(erased(a) for a in apps.values())
    report = Notification.objects.get(
        recipient_user=team.admin, key="retention_report", channel="email"
    )
    assert report.payload["due_count"] == "2"


def test_run_anonymises_only_what_is_due_and_is_idempotent(world: Any) -> None:
    team, apps = world
    retention.run_for(team.org, dry_run=False)
    assert erased(apps["old_not_selected"]) and erased(apps["old_withdrawn"])
    assert not erased(apps["old_hired"])  # hired records are kept
    assert not erased(apps["old_held"])  # legal hold wins
    assert not erased(apps["recent"])  # inside the retention period
    second = retention.run_for(team.org, dry_run=False)
    assert second.counts == {"held": 1}  # nothing left to do
    assert RetentionRun.objects.filter(organisation=team.org, dry_run=False).count() == 2
