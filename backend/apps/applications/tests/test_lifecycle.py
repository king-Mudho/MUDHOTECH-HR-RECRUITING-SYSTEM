"""Withdrawal and drafts around vacancy events (P04-T09; EC-APP-12/13, EC-JOB-08/09/10)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications import lifecycle
from apps.applications.models import Application, Status
from apps.applications.services import start_or_resume_draft, transition
from apps.applications.tests.factories import make_application, published_job
from apps.core import crypto
from apps.core.email import EVENT as EMAIL_EVENT
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.jobs import services as jobs
from apps.jobs.models import Job, JobAssignment, JobStatus
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def emails_to(address: str) -> list[str]:
    return [
        crypto.decrypt(e.payload["text_enc"])
        for e in OutboxEvent.objects.filter(event_type=EMAIL_EVENT)
        if address in e.payload["to"]
    ]


@pytest.fixture
def commit(django_capture_on_commit_callbacks: Any) -> Any:
    """Outbox consumers run when the publishing transaction commits."""
    return django_capture_on_commit_callbacks


@pytest.fixture
def world() -> Any:
    team = make_org_with_team()
    team.org.verified_at = now()
    team.org.save(update_fields=["verified_at"])
    job = published_job(organisation=team.org)
    JobAssignment.objects.create(
        organisation=team.org,
        job=job,
        membership=Membership.objects.for_org(team.org).get(user=team.recruiter),
        role_on_job="recruiter",
    )
    return team, job


def client_for(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def test_withdraw_after_shortlist_notifies_recruiter(world: Any) -> None:
    """EC-APP-13."""
    team, job = world
    app = make_application(job, status=Status.SHORTLISTED)
    res = client_for(app.candidate_user).post(
        f"/api/v1/applications/{app.pk}/withdraw/",
        {"reason": "Accepted another offer"},
        format="json",
    )
    assert res.status_code == 200, res.content
    app.refresh_from_db()
    assert app.status == Status.WITHDRAWN and app.withdraw_reason == "Accepted another offer"
    [body] = emails_to(team.recruiter.email)
    assert app.reference in body and "Accepted another offer" in body
    again = client_for(app.candidate_user).post(
        f"/api/v1/applications/{app.pk}/withdraw/", {}, format="json"
    )
    assert again.status_code == 409


def test_withdraw_draft_discards_it(world: Any) -> None:
    _, job = world
    app, _ = start_or_resume_draft(job, UserFactory())
    res = client_for(app.candidate_user).post(
        f"/api/v1/applications/{app.pk}/withdraw/", {}, format="json"
    )
    assert res.status_code == 200 and res.json()["status"] == "abandoned"


def test_withdraw_is_owner_only(world: Any) -> None:
    _, job = world
    app = make_application(job, status=Status.SUBMITTED)
    res = client_for(UserFactory()).post(
        f"/api/v1/applications/{app.pk}/withdraw/", {}, format="json"
    )
    assert res.status_code == 404


def test_processing_stops_after_withdrawal(world: Any) -> None:
    """EC-APP-12: tasks call is_processable() first."""
    _, job = world
    app = make_application(job, status=Status.PROCESSING)
    assert lifecycle.is_processable(app)
    transition(app, Status.WITHDRAWN, actor=app.candidate_user)
    assert not lifecycle.is_processable(app)


def test_closing_abandons_drafts_but_not_submitted(world: Any, commit: Any) -> None:
    """EC-JOB-10."""
    team, job = world
    draft, _ = start_or_resume_draft(job, UserFactory())
    submitted = make_application(job, status=Status.SUBMITTED)
    with commit(execute=True):
        jobs.close(job, actor=team.hr_manager, reason="Position filled")
    draft.refresh_from_db()
    submitted.refresh_from_db()
    assert draft.status == Status.ABANDONED and submitted.status == Status.SUBMITTED
    [body] = emails_to(draft.candidate_user.email)
    assert "have closed" in body


def test_pausing_keeps_drafts(world: Any) -> None:
    """EC-JOB-08."""
    team, job = world
    draft, _ = start_or_resume_draft(job, UserFactory())
    jobs.pause(job, actor=team.hr_manager)
    draft.refresh_from_db()
    assert draft.status == Status.DRAFT


def test_extending_deadline_reactivates_abandoned_drafts(world: Any, commit: Any) -> None:
    """EC-JOB-09: drafts come back, unless the candidate already started a newer one."""
    team, job = world
    keep, _ = start_or_resume_draft(job, UserFactory())
    moved_on, _ = start_or_resume_draft(job, UserFactory())
    with commit(execute=True):
        jobs.close(job, actor=team.hr_manager, reason="Position filled")
    # The second candidate somehow has a new active application (e.g. reopened by HR).
    make_application(job, moved_on.candidate_user, status=Status.SUBMITTED)
    with commit(execute=True):
        jobs.extend_deadline(
            Job.objects.unscoped().get(pk=job.pk),
            actor=team.hr_manager,
            closes_at=now() + timedelta(days=60),
            reason="Too few applicants",
        )
    keep.refresh_from_db()
    moved_on.refresh_from_db()
    assert keep.status == Status.DRAFT and moved_on.status == Status.ABANDONED
    assert any("extended" in b for b in emails_to(keep.candidate_user.email))


def test_hourly_sweep_catches_missed_closures(world: Any) -> None:
    _, job = world
    draft, _ = start_or_resume_draft(job, UserFactory())
    Job.objects.unscoped().filter(pk=job.pk).update(status=JobStatus.ARCHIVED)
    assert lifecycle.sweep_stale_drafts() == 1
    assert Application.objects.unscoped().get(pk=draft.pk).status == Status.ABANDONED
    assert lifecycle.sweep_stale_drafts() == 0
