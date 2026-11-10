"""Application data model and duplicate policy (P04-T05, EC-APP-02/03)."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.db import IntegrityError, InternalError, ProgrammingError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import (
    AppendOnlyError,
    Application,
    ApplicationStatusEvent,
    Status,
)
from apps.applications.services import (
    DuplicateApplicationError,
    next_reference,
    org_code,
    start_or_resume_draft,
)
from apps.applications.tests.factories import make_application, published_job
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.jobs.models import Job, JobStatus
from apps.organisations.models import OrganisationPolicy

pytestmark = pytest.mark.django_db


def test_reference_format_and_sequence() -> None:
    job = published_job()
    org = job.organisation
    first, second = next_reference(org, 2026), next_reference(org, 2026)
    code = org_code(org)
    assert re.fullmatch(rf"MHRS-{code}-2026-\d{{6}}", first)
    assert first.endswith("000001") and second.endswith("000002")
    assert next_reference(org, 2027).endswith("000001")  # new year restarts
    other = published_job().organisation
    assert next_reference(other, 2026).endswith("000001")  # per organisation


def test_submitted_application_requires_reference() -> None:
    job = published_job()
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.create(
            organisation=job.organisation,
            job=job,
            job_version=job.published_version,
            candidate_user=UserFactory(),
            status=Status.SUBMITTED,
        )


def test_resume_existing_draft_and_block_second_active() -> None:
    """EC-APP-02 (one_active, the default policy)."""
    job, user = published_job(), UserFactory()
    draft, created = start_or_resume_draft(job, user)
    assert created and draft.status == Status.DRAFT and draft.job_version == job.published_version
    again, created_again = start_or_resume_draft(job, user)
    assert again.pk == draft.pk and not created_again
    Application.objects.for_org(job.organisation).filter(pk=draft.pk).update(
        status=Status.SUBMITTED, reference=next_reference(job.organisation), submitted_at=now()
    )
    with pytest.raises(DuplicateApplicationError) as exc:
        start_or_resume_draft(job, user)
    assert exc.value.status_code == 409 and exc.value.details["application_id"] == str(draft.pk)


def test_database_refuses_two_active_applications() -> None:
    job, user = published_job(), UserFactory()
    make_application(job, user)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_application(job, user)


def test_reapply_after_withdrawal() -> None:
    """EC-APP-03."""
    job, user = published_job(), UserFactory()
    first = make_application(job, user, status=Status.SUBMITTED)
    Application.objects.for_org(job.organisation).filter(pk=first.pk).update(
        status=Status.WITHDRAWN, active_key=None
    )
    draft, created = start_or_resume_draft(job, user)
    assert created and draft.pk != first.pk


def test_allow_multiple_policy() -> None:
    job, user = published_job(), UserFactory()
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(
        duplicate_policy="allow_multiple"
    )
    make_application(job, user, status=Status.SUBMITTED)
    draft, created = start_or_resume_draft(job, user)
    assert created and draft.active_key is None


def test_resubmit_replace_policy_allows_new_draft() -> None:
    job, user = published_job(), UserFactory()
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(
        duplicate_policy="allow_resubmit_replace"
    )
    submitted = make_application(job, user, status=Status.SUBMITTED)
    draft, created = start_or_resume_draft(job, user)
    assert created and draft.pk != submitted.pk and draft.active_key is None


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"status": JobStatus.CLOSED}, "job_not_accepting"),
        ({"status": JobStatus.PAUSED}, "job_not_accepting"),
        ({"closes_at": "past"}, "deadline_passed"),
    ],
)
def test_cannot_start_on_closed_paused_or_expired_jobs(change: dict, code: str) -> None:  # type: ignore[type-arg]
    job = published_job()
    if change.get("closes_at") == "past":
        change = {"closes_at": now() - timedelta(minutes=1)}
    Job.objects.unscoped().filter(pk=job.pk).update(**change)
    job.refresh_from_db()
    with pytest.raises(DomainError) as exc:
        start_or_resume_draft(job, UserFactory())
    assert exc.value.code == code


def test_status_events_are_append_only() -> None:
    app = make_application()
    event = ApplicationStatusEvent.objects.create(
        organisation=app.organisation,
        application=app,
        from_status="draft",
        to_status="submitted",
        actor_type="human",
        at=now(),
    )
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()
    with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
        ApplicationStatusEvent.objects.for_org(app.organisation).filter(pk=event.pk).update(
            reason_text="tampered"
        )
    with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
        ApplicationStatusEvent.objects.for_org(app.organisation).filter(pk=event.pk).delete()
