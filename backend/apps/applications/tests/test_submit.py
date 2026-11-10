"""Submit (P04-T08): checks, exactly-once (Idempotency-Key), receipts, concurrency (EC-APP-01)."""

from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationStatusEvent,
    Status,
)
from apps.applications.services import start_or_resume_draft
from apps.applications.tests.factories import published_job
from apps.candidates.services import update_profile
from apps.core import crypto
from apps.core.email import EVENT as EMAIL_EVENT
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.documents.models import Document, ScanStatus
from apps.jobs.models import Job, JobStatus
from apps.organisations.models import Organisation, OrganisationPolicy

pytestmark = pytest.mark.django_db


def ready_draft(job: Any, user: Any = None, scan: str = ScanStatus.CLEAN) -> Application:
    user = user or UserFactory()
    app, _ = start_or_resume_draft(job, user)
    doc = Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=100,
        storage_key=f"cv/{uuid.uuid4().hex}.pdf",
        scan_status=scan,
    )
    ApplicationDocument.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        document=doc,
        role="cv",
        required_doc_key="cv",
    )
    return app


def submit(client: APIClient, app: Application, key: str | None = None, **body: Any) -> Any:
    headers = {"HTTP_IDEMPOTENCY_KEY": key or str(uuid.uuid4())} if key != "" else {}
    return client.post(
        f"/api/v1/applications/{app.pk}/submit/",
        {"accept_privacy": True, **body},
        format="json",
        **headers,
    )


def login(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


@pytest.fixture
def job() -> Any:
    return published_job()


def test_submit_freezes_snapshot_assigns_reference_and_queues_receipt(job: Any) -> None:
    app = ready_draft(job)
    user = app.candidate_user
    update_profile(user, {"headline": "Python developer", "city": "Harare"})
    res = submit(login(user), app)
    assert res.status_code == 201, res.content
    body = res.json()
    assert re.fullmatch(r"MHRS-[A-Z0-9]{1,8}-\d{4}-\d{6}", body["reference"])
    app.refresh_from_db()
    assert app.status == Status.SUBMITTED and app.submitted_at is not None
    assert app.candidate_profile_snapshot["headline"] == "Python developer"
    assert app.candidate_profile_snapshot["email"] == user.email
    assert app.job_version_id == job.published_version_id
    event = ApplicationStatusEvent.objects.for_org(job.organisation).get(application=app)
    assert (event.from_status, event.to_status, event.actor_id) == ("draft", "submitted", user.pk)
    assert OutboxEvent.objects.filter(
        event_type="application.submitted", aggregate_id=str(app.pk)
    ).exists()
    receipt = [
        e
        for e in OutboxEvent.objects.filter(event_type=EMAIL_EVENT)
        if e.payload["to"] == [user.email]
    ]
    assert len(receipt) == 1 and body["reference"] in crypto.decrypt(receipt[0].payload["text_enc"])


def test_scan_pending_documents_are_allowed(job: Any) -> None:
    app = ready_draft(job, scan=ScanStatus.PENDING)
    assert submit(login(app.candidate_user), app).status_code == 201


def test_same_key_replays_single_application(job: Any) -> None:
    """EC-APP-04: double click / retry."""
    app = ready_draft(job)
    client, key = login(app.candidate_user), str(uuid.uuid4())
    first, second = submit(client, app, key), submit(client, app, key)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() and second["Idempotent-Replayed"] == "true"
    assert Application.objects.unscoped().filter(reference__isnull=False).count() == 1
    other_key = submit(client, app)
    assert (
        other_key.status_code == 409 and other_key.json()["error"]["code"] == "conflict.not_draft"
    )


def test_idempotency_key_required(job: Any) -> None:
    app = ready_draft(job)
    res = submit(login(app.candidate_user), app, key="")
    assert res.status_code == 400


def test_incomplete_application_lists_missing(job: Any) -> None:
    app, _ = start_or_resume_draft(job, UserFactory())
    res = submit(login(app.candidate_user), app)
    assert res.status_code == 422 and res.json()["error"]["code"] == "submit_blocked"
    assert {"step": "documents", "code": "document_required", "key": "cv"} in res.json()["error"][
        "details"
    ]["missing"]


def test_unverified_email_blocks_submit(job: Any) -> None:
    """EC-ACC-03."""
    app = ready_draft(job, UserFactory(verified=False))
    res = submit(login(app.candidate_user), app)
    assert res.status_code == 422 and res.json()["error"]["code"] == "email_unverified"


def test_privacy_acceptance_required(job: Any) -> None:
    app = ready_draft(job)
    res = submit(login(app.candidate_user), app, accept_privacy=False)
    assert res.status_code == 400


def test_deadline_is_server_time_and_inclusive(job: Any) -> None:
    """EC-APP-05: <= closes_at is accepted; one second later is refused."""
    closes = now() + timedelta(hours=1)
    Job.objects.unscoped().filter(pk=job.pk).update(closes_at=closes)
    on_time, late = ready_draft(job), ready_draft(job)
    with mock.patch("apps.applications.services.now", return_value=closes):
        assert submit(login(on_time.candidate_user), on_time).status_code == 201
    with mock.patch("apps.applications.services.now", return_value=closes + timedelta(seconds=1)):
        res = submit(login(late.candidate_user), late)
    assert res.status_code == 422 and res.json()["error"]["code"] == "deadline_passed"
    late.refresh_from_db()
    assert late.status == Status.DRAFT  # nothing lost


def test_paused_job_keeps_draft(job: Any) -> None:
    """EC-JOB-08."""
    app = ready_draft(job)
    Job.objects.unscoped().filter(pk=job.pk).update(status=JobStatus.PAUSED)
    res = submit(login(app.candidate_user), app)
    assert res.status_code == 422 and res.json()["error"]["code"] == "job_paused"


def test_suspended_org_is_423(job: Any) -> None:
    """EC-APP-19."""
    app = ready_draft(job)
    Organisation.objects.filter(pk=job.organisation_id).update(status=Organisation.Status.SUSPENDED)
    res = submit(login(app.candidate_user), app)
    assert res.status_code == 423


def test_resubmit_replace_withdraws_previous(job: Any) -> None:
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(
        duplicate_policy="allow_resubmit_replace"
    )
    user = UserFactory()
    first = ready_draft(job, user)
    client = login(user)
    assert submit(client, first).status_code == 201
    second = ready_draft(job, user)
    assert second.pk != first.pk
    assert submit(client, second).status_code == 201
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == Status.WITHDRAWN and first.active_key is None
    assert second.status == Status.SUBMITTED and second.duplicate_of_id == first.pk


@pytest.mark.django_db(transaction=True)
def test_one_hundred_concurrent_submissions() -> None:
    """EC-APP-01 / exit criterion: 100 concurrent submits (each double-clicked) -> 100 applications,
    unique references, no duplicates, 100 receipts queued."""
    job = published_job()
    drafts = [ready_draft(job) for _ in range(100)]

    def run(app: Application) -> tuple[int, int]:
        try:
            client, key = login(app.candidate_user), str(uuid.uuid4())
            return submit(client, app, key).status_code, submit(client, app, key).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(run, drafts))
    assert results == [(201, 201)] * 100
    submitted = Application.objects.unscoped().filter(job=job, status=Status.SUBMITTED)
    refs = list(submitted.values_list("reference", flat=True))
    assert len(refs) == 100 and len(set(refs)) == 100
    numbers = sorted(int(r.rsplit("-", 1)[1]) for r in refs)
    assert numbers == list(range(1, 101))  # gap-free under contention
    receipts = OutboxEvent.objects.filter(
        event_type=EMAIL_EVENT, dedupe_key__startswith="email.application_receipt:"
    )
    assert receipts.count() == 100
    assert OutboxEvent.objects.filter(event_type="application.submitted").count() == 100
