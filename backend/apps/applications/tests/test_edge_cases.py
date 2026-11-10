"""Phase 04 edge cases that span documents and applications (docs/07 EC-APP / EC-OPS)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from botocore.exceptions import EndpointConnectionError

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationDocument, Status
from apps.applications.services import start_or_resume_draft
from apps.applications.tests.factories import published_job
from apps.applications.tests.test_submit import login, ready_draft, submit
from apps.core import storage
from apps.core.models import OutboxEvent
from apps.documents import antivirus, pipeline
from apps.documents.models import Document, ScanStatus, UploadSession
from apps.documents.services import complete_session, create_session
from apps.documents.tests.test_scan_pipeline import make_pdf, rejection_emails

pytestmark = pytest.mark.django_db


@pytest.fixture
def job() -> Any:
    return published_job()


def uploaded(s3: Any, user: Any, data: bytes) -> Document:
    """Upload through the real session flow but leave the scan for later (on-commit not run)."""
    session, _ = create_session(
        user, purpose="cv", filename="cv.pdf", mime="application/pdf", size=len(data)
    )
    s3.put_object(Bucket="mhrs-uploads-quarantine", Key=session.object_key, Body=data)
    return complete_session(user, session.pk)


def attach(app: Application, doc: Document) -> None:
    ApplicationDocument.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        document=doc,
        role="cv",
        required_doc_key="cv",
    )


def test_ec_app_09_infected_after_submit_keeps_application_and_asks_for_reupload(
    s3: Any, job: Any
) -> None:
    """EC-APP-09: submit is allowed while the CV is still being checked; when the scan later
    finds malware the application is kept and the candidate is asked (generically) to re-upload."""
    user = UserFactory()
    app, _ = start_or_resume_draft(job, user)
    doc = uploaded(s3, user, make_pdf(1) + b"\n" + antivirus.EICAR)
    assert doc.scan_status == ScanStatus.PENDING
    attach(app, doc)
    assert submit(login(user), app).status_code == 201
    pipeline.scan_document(doc.pk)
    doc.refresh_from_db()
    app.refresh_from_db()
    assert doc.scan_status == ScanStatus.INFECTED
    assert app.status == Status.SUBMITTED and app.reference  # never lost (principle 6)
    assert any("security check" in body for body in rejection_emails(user))


def test_ec_app_07_unfinished_upload_is_never_attached(s3: Any, job: Any) -> None:
    """EC-APP-07: a session whose object never arrived creates no document, so nothing partial
    can be attached; the client simply starts a new session (fresh presigned URL) to retry."""
    user = UserFactory()
    app, _ = start_or_resume_draft(job, user)
    client = login(user)
    first = client.post(
        "/api/v1/documents/upload-sessions/",
        {"purpose": "cv", "filename": "cv.pdf", "mime": "application/pdf", "size": 10},
        format="json",
    ).json()
    assert (
        client.post(f"/api/v1/documents/upload-sessions/{first['id']}/complete/").status_code == 409
    )
    assert not Document.objects.filter(owner_user=user).exists()
    res = client.put(
        f"/api/v1/applications/{app.pk}/documents/",
        {"documents": [{"document_id": first["id"], "role": "cv", "required_doc_key": "cv"}]},
        format="json",
    )
    assert (
        res.status_code in (400, 404)
        and not ApplicationDocument.objects.filter(application=app).exists()
    )
    retry = client.post(
        "/api/v1/documents/upload-sessions/",
        {"purpose": "cv", "filename": "cv.pdf", "mime": "application/pdf", "size": 10},
        format="json",
    ).json()
    assert retry["id"] != first["id"] and retry["url"] != first["url"]


def test_ec_app_15_same_cv_on_two_accounts_takes_no_automatic_action(s3: Any, job: Any) -> None:
    """EC-APP-15: identical file bytes from two accounts are two separate documents; both
    applications go through unchanged (the HR flag is computed in Phase 06; no auto action)."""
    data = make_pdf(1)
    apps = []
    for _ in range(2):
        user = UserFactory()
        app, _ = start_or_resume_draft(job, user)
        doc = uploaded(s3, user, data)
        pipeline.scan_document(doc.pk)
        attach(app, doc)
        assert submit(login(user), app).status_code == 201
        apps.append(app)
    docs = Document.objects.filter(sha256__isnull=False).values_list("owner_user_id", flat=True)
    assert len(set(docs)) == 2
    for app in apps:
        app.refresh_from_db()
        assert app.status == Status.SUBMITTED and app.flags == []


def test_ec_app_16_contact_name_different_from_account_is_not_penalised(job: Any) -> None:
    """EC-APP-16: the wizard name may differ from the account name; nothing is blocked or scored."""
    user = UserFactory(first_name="Tendai", last_name="Moyo")
    app = ready_draft(job, user)
    client = login(user)
    client.patch(
        f"/api/v1/applications/{app.pk}/",
        {"lock_version": app.lock_version, "contact": {"first_name": "T.", "last_name": "Chari"}},
        format="json",
    )
    assert submit(client, app).status_code == 201
    app.refresh_from_db()
    assert app.status == Status.SUBMITTED and app.flags == []
    assert app.candidate_profile_snapshot["last_name"] == "Chari"


def test_ec_app_22_under_age_answer_is_never_auto_rejected(job: Any) -> None:
    """EC-APP-22: an approved eligibility (age) question never auto-rejects; the application is
    submitted normally and left for human review."""
    from apps.questionnaires.models import Question, Questionnaire

    version = job.published_version
    questionnaire = Questionnaire.objects.create(
        organisation_id=job.organisation_id, job_version=version, status="approved"
    )
    Question.objects.create(
        organisation_id=job.organisation_id,
        questionnaire=questionnaire,
        key="min_age",
        type="number",
        prompt="Are you at least 18? Enter your age.",
        protected_topic_flag=["age"],
        protected_exception_reason="Statutory minimum working age for night shifts.",
    )
    user = UserFactory()
    app = ready_draft(job, user)
    client = login(user)
    res = client.put(
        f"/api/v1/applications/{app.pk}/answers/",
        {"answers": [{"key": "min_age", "value": 15}]},
        format="json",
    )
    assert res.status_code == 200, res.content
    assert submit(client, app).status_code == 201
    app.refresh_from_db()
    assert app.status == Status.SUBMITTED  # never not_selected without a human decision


def test_ec_app_23_missing_source_is_direct(job: Any) -> None:
    """EC-APP-23: no referral/utm data -> source ``direct``; utm kept, unknown keys dropped."""
    a, _ = start_or_resume_draft(job, UserFactory())
    assert a.source == {"source": "direct"}
    b, _ = start_or_resume_draft(
        job, UserFactory(), source={"utm_source": "whatsapp", "evil": "x" * 10}
    )
    assert b.source == {"utm_source": "whatsapp", "source": "whatsapp"}


class _DownClient:
    """Stands in for ``storage.client`` (keeps ``cache_clear`` for fixture teardown)."""

    def __call__(self) -> Any:
        return _DownS3()

    def cache_clear(self) -> None:
        return None


class _DownS3:
    def __getattr__(self, name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            raise EndpointConnectionError(endpoint_url="http://s3:9000")

        return fail


def test_ec_ops_02_storage_outage_fails_uploads_gracefully(
    s3: Any, job: Any, monkeypatch: Any
) -> None:
    """EC-OPS-02: with S3 down, uploads answer 503 ``storage_unavailable`` (retry message), the
    session stays retryable and already-submitted applications are unaffected."""
    user = UserFactory()
    done = ready_draft(job, user)
    client = login(user)
    assert submit(client, done).status_code == 201
    session = client.post(
        "/api/v1/documents/upload-sessions/",
        {"purpose": "cv", "filename": "cv.pdf", "mime": "application/pdf", "size": 10},
        format="json",
    ).json()  # presigning is offline, so it still works
    monkeypatch.setattr(storage, "client", _DownClient())
    res = client.post(f"/api/v1/documents/upload-sessions/{session['id']}/complete/")
    assert res.status_code == 503 and res.json()["error"]["code"] == "storage_unavailable"
    assert "try again" in res.json()["error"]["message"]
    assert UploadSession.objects.get(pk=session["id"]).status == UploadSession.Status.PENDING
    from django.core.files.uploadedfile import SimpleUploadedFile

    direct = client.post(
        "/api/v1/documents/direct-upload/",
        {"purpose": "cv", "file": SimpleUploadedFile("cv.pdf", make_pdf(1), "application/pdf")},
        format="multipart",
    )
    assert direct.status_code == 503
    assert client.get(f"/api/v1/applications/{done.pk}/").json()["status"] == "submitted"
    assert not OutboxEvent.objects.filter(event_type="document.uploaded").exists()
    assert uuid.UUID(session["id"])
