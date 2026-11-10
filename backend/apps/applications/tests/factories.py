"""Synthetic application factories."""

from __future__ import annotations

from typing import Any

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.services import active_key_for, next_reference
from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.jobs.tests.factories import JobFactory


def published_job(**kwargs: Any) -> Job:
    """A factory job flipped to published (no approval workflow; for application tests)."""
    job = JobFactory(**kwargs)
    Job.objects.unscoped().filter(pk=job.pk).update(
        status=JobStatus.PUBLISHED, published_version=job.current_version, published_at=now()
    )
    job.refresh_from_db()
    return job


def make_application(
    job: Job | None = None, user: Any = None, status: str = Status.DRAFT
) -> Application:
    job = job or published_job()
    app = Application(
        organisation_id=job.organisation_id,
        job=job,
        job_version_id=job.published_version_id or job.current_version_id,
        candidate_user=user or UserFactory(),
        status=status,
    )
    if status != Status.DRAFT:
        app.reference = next_reference(job.organisation)
        app.submitted_at = now()
    app.active_key = active_key_for(app)
    app.save()
    return app
