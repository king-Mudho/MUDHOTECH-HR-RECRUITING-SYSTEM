"""Beat tasks: scheduled publish + auto-close, catch-up and idempotency (P03-T06, EC-JOB-18)."""

from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.conf import settings

from apps.core.time import now
from apps.jobs import services, tasks
from apps.jobs.models import Job, JobEvent, JobStatus
from apps.jobs.tests.test_services import approved_job, published_job, team  # noqa: F401

pytestmark = pytest.mark.django_db


def test_beat_schedule_registers_both_tasks() -> None:
    names = {e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values()}
    assert {"apps.jobs.tasks.publish_scheduled_jobs", "apps.jobs.tasks.close_expired_jobs"} <= names


def test_catch_up_publishes_overdue_scheduled_jobs_once(team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """EC-JOB-18: publish_at passed while the system was down -> published on the next run."""
    job = approved_job(team)
    services.schedule(job, actor=team.hr_manager, publish_at=now() + timedelta(hours=1))
    assert tasks.publish_scheduled_jobs() == {"published": 0, "skipped": 0, "failed": 0}
    Job.objects.for_org(team.org).filter(pk=job.pk).update(publish_at=now() - timedelta(hours=6))
    assert tasks.publish_scheduled_jobs()["published"] == 1
    assert tasks.publish_scheduled_jobs()["published"] == 0
    job.refresh_from_db()
    assert job.status == JobStatus.PUBLISHED
    assert JobEvent.objects.for_org(team.org).filter(job=job, action="published").count() == 1


def test_scheduled_job_past_its_deadline_is_not_published(team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = approved_job(team)
    services.schedule(job, actor=team.hr_manager, publish_at=now() + timedelta(hours=1))
    Job.objects.for_org(team.org).filter(pk=job.pk).update(
        publish_at=now() - timedelta(days=3), closes_at=now() - timedelta(days=1)
    )
    assert tasks.publish_scheduled_jobs()["skipped"] == 1
    job.refresh_from_db()
    assert job.status == JobStatus.APPROVED
    assert JobEvent.objects.for_org(team.org).filter(job=job, action="schedule_cancelled").exists()


def test_close_expired_jobs_respects_job_timezone(team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """EC-JOB-05: 23:59 Africa/Harare is 21:59 UTC; the job closes at that instant."""
    job = published_job(team)
    harare = zoneinfo.ZoneInfo("Africa/Harare")
    deadline = datetime(2030, 3, 31, 23, 59, tzinfo=harare)
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closes_at=deadline)
    utc = zoneinfo.ZoneInfo("UTC")
    with mock.patch("apps.jobs.tasks.now", return_value=datetime(2030, 3, 31, 21, 58, tzinfo=utc)):
        assert tasks.close_expired_jobs()["closed"] == 0
    with (
        mock.patch("apps.jobs.tasks.now", return_value=datetime(2030, 3, 31, 22, 0, tzinfo=utc)),
        mock.patch("apps.jobs.services.now", return_value=datetime(2030, 3, 31, 22, 0, tzinfo=utc)),
    ):
        assert tasks.close_expired_jobs()["closed"] == 1
        assert tasks.close_expired_jobs()["closed"] == 0
    job.refresh_from_db()
    assert job.status == JobStatus.CLOSED
    assert JobEvent.objects.for_org(team.org).filter(job=job, action="auto_closed").count() == 1


def test_paused_jobs_also_close_and_failures_are_isolated(team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    a = published_job(team)
    b = published_job(team)
    services.pause(b, actor=team.hr_manager)
    Job.objects.for_org(team.org).filter(pk__in=[a.pk, b.pk]).update(
        closes_at=now() - timedelta(minutes=1)
    )
    real = services.auto_close

    def flaky(job: Job) -> bool:
        if job.pk == a.pk:
            raise RuntimeError("boom")
        return real(job)

    with mock.patch("apps.jobs.services.auto_close", side_effect=flaky):
        assert tasks.close_expired_jobs() == {"closed": 1, "failed": 1}
    assert tasks.close_expired_jobs() == {"closed": 1, "failed": 0}
