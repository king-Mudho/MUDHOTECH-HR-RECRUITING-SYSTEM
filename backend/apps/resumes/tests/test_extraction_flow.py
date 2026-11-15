"""CV extraction orchestration (P06-T11): EC-DOC-01..28, EC-AI-10/11/12, principle 6."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.db import connection

from ai_engine import ENGINE_VERSION
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationStatusEvent,
    DocumentRole,
    Status,
)
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import storage
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.documents.models import Document, Purpose, ScanStatus
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.resumes import services
from apps.resumes.models import ExtractedClaim, ExtractionRun, RunStatus
from apps.taxonomy.models import Skill

pytestmark = pytest.mark.django_db
CORPUS = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_cvs"
GOOD_CV = "cv_001_software_developer_strong.docx"  # Takudzwa Chari, Granite Labs, Python, Django


def submitted_app(*, objection: bool = False, org: Any = None, user: Any = None) -> Application:
    job = published_job(organisation=org) if org else published_job()
    app = make_application(job, user or UserFactory(), status=Status.SUBMITTED)
    ApplicationStatusEvent.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        from_status="draft",
        to_status="submitted",
        actor_type="human",
        metadata={"objects_to_automated_processing": objection},
        at=now(),
    )
    return app


def attach(
    app: Application,
    data: bytes | None = None,
    *,
    filename: str = GOOD_CV,
    scan: str = ScanStatus.CLEAN,
    duplicate_of: Document | None = None,
) -> Document:
    data = data if data is not None else (CORPUS / filename).read_bytes()
    doc = Document.objects.create(
        owner_user=app.candidate_user,
        purpose=Purpose.CV,
        original_filename=filename,
        size_bytes=len(data),
        storage_key=f"cv/{app.pk}/{filename}",
        bucket="documents",
        scan_status=scan,
        duplicate_of=duplicate_of,
    )
    storage.put_bytes("documents", doc.storage_key, data, "application/octet-stream")
    ApplicationDocument.objects.create(
        organisation_id=app.organisation_id, application=app, document=doc, role=DocumentRole.CV
    )
    return doc


def events(name: str) -> list[OutboxEvent]:
    return list(OutboxEvent.objects.filter(event_type=name))


def test_happy_path_extracts_encrypts_and_reports_evidence(act: Any) -> None:
    app = submitted_app()
    attach(app)
    act(services.start, app.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING  # screening (Phase 07) moves it on
    run = ExtractionRun.objects.for_org(app.organisation_id).get(application=app)
    assert run.status == RunStatus.SUCCEEDED and run.attempts == 1
    assert run.engine_version == ENGINE_VERSION and run.claim_count > 10
    assert run.parser_used == "python-docx" and run.quality_score and run.language == "en"
    claims = ExtractedClaim.objects.for_org(app.organisation_id).filter(run=run)
    types = set(claims.values_list("claim_type", flat=True))
    assert {"experience", "education", "skill", "language", "contact"} <= types
    skill = claims.filter(claim_type="skill", skill_id=str(Skill.objects.get(slug="python").pk))
    assert skill.exists()
    # CV content is encrypted at rest
    with connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM resumes_extractedclaim LIMIT 50")
        raw = " ".join(row[0] for row in cursor.fetchall())
        cursor.execute("SELECT payload FROM resumes_documenttext")
        raw_text = cursor.fetchone()[0]
    assert "Granite Labs" not in raw and "Granite Labs" not in raw_text
    assert "Granite Labs" in run.text.payload  # decrypted through the field
    (ready,) = events("application.evidence_ready")
    assert ready.payload["extraction_run_ids"] == [str(run.pk)]
    assert ready.payload["manual_review_requested"] is False
    assert AuditEvent.objects.filter(action="resumes.extracted").exists()


def test_waits_for_scan_then_extracts_on_document_accepted(act: Any) -> None:
    app = submitted_app()
    doc = attach(app, scan=ScanStatus.PENDING)
    act(services.start, app.pk)
    assert not ExtractionRun.objects.for_org(app.organisation_id).exists()
    assert not events("application.evidence_ready")
    Document.objects.filter(pk=doc.pk).update(scan_status=ScanStatus.CLEAN)
    act(services.on_document_accepted, doc.pk)
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert run.status == RunStatus.SUCCEEDED and len(events("application.evidence_ready")) == 1


def test_unreadable_cv_moves_to_processing_error_and_asks_for_reupload(act: Any) -> None:
    app = submitted_app()
    attach(app, b"%PDF-1.7\nthis is not really a pdf", filename="broken.pdf")
    act(services.start, app.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR  # kept, never lost (principle 6)
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert run.status == RunStatus.FAILED and run.error_code == "corrupt"
    keys = set(
        Notification.objects.filter(recipient_user=app.candidate_user).values_list("key", flat=True)
    )
    assert keys == {"document_rejected_reupload"}  # email + in-app
    assert not events("application.evidence_ready")
    # a fixed upload restarts processing
    fixed = attach(app)
    act(services.on_document_accepted, fixed.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR  # the broken CV is still attached and failed
    ApplicationDocument.objects.for_org(app.organisation_id).filter(
        document__original_filename="broken.pdf"
    ).delete()
    act(services.on_document_accepted, fixed.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING and len(events("application.evidence_ready")) == 1


def test_objection_to_automated_processing_skips_extraction(act: Any) -> None:
    app = submitted_app(objection=True)
    attach(app)
    act(services.start, app.pk)
    assert not ExtractionRun.objects.for_org(app.organisation_id).exists()
    (ready,) = events("application.evidence_ready")
    assert ready.payload["manual_review_requested"] is True


def test_idempotent_and_skips_withdrawn_applications(act: Any) -> None:
    app = submitted_app()
    doc = attach(app)
    act(services.start, app.pk)
    act(services.start, app.pk)  # replayed event
    assert services.extract(doc.pk, app.pk) == RunStatus.SUCCEEDED
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert run.attempts == 1
    assert ExtractedClaim.objects.for_org(app.organisation_id).count() == run.claim_count
    assert len(events("application.evidence_ready")) == 1

    other = submitted_app()
    other_doc = attach(other)
    transition(other, Status.WITHDRAWN, actor=other.candidate_user, reason="Found a job")
    assert services.extract(other_doc.pk, other.pk) == "skipped"


def test_duplicate_file_reuses_extraction(act: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    first = submitted_app()
    original = attach(first)
    act(services.start, first.pk)
    source = ExtractionRun.objects.for_org(first.organisation_id).get()

    def no_storage(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("must not re-read a duplicate")

    second = submitted_app(org=first.organisation, user=first.candidate_user)
    attach(second, duplicate_of=original)
    monkeypatch.setattr(storage, "get_bytes", no_storage)
    act(services.start, second.pk)
    run = ExtractionRun.objects.for_org(second.organisation_id).get(application=second)
    assert run.reused_from_id == source.pk and run.status == source.status
    assert run.claim_count == source.claim_count == run.claims.count()


def test_storage_outage_retries_then_fails_safely(
    act: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = submitted_app()
    doc = attach(app, scan=ScanStatus.PENDING)
    act(services.start, app.pk)
    Document.objects.filter(pk=doc.pk).update(scan_status=ScanStatus.CLEAN)

    def outage(*args: Any, **kwargs: Any) -> bytes:
        raise ConnectionError("s3 down")

    monkeypatch.setattr(storage, "get_bytes", outage)
    with pytest.raises(ConnectionError):  # not the last attempt: the task retries
        with_runs = ExtractionRun.objects.for_org(app.organisation_id)
        ExtractionRun.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            document=doc,
            engine_version=ENGINE_VERSION,
        )
        services.extract(doc.pk, app.pk, final_attempt=False)
    assert with_runs.get().status == RunStatus.PENDING
    assert services.extract(doc.pk, app.pk, final_attempt=True) == "failed"
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR
    assert with_runs.get().error_code == "storage_unavailable"


def test_hr_retry_and_document_rejected_after_submit(
    act: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    team = make_org_with_team()
    app = submitted_app(org=team.org)
    doc = attach(app, scan=ScanStatus.PENDING)
    act(services.start, app.pk)
    Document.objects.filter(pk=doc.pk).update(scan_status=ScanStatus.CLEAN)
    ExtractionRun.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        document=doc,
        engine_version=ENGINE_VERSION,
    )
    real = storage.get_bytes
    monkeypatch.setattr(storage, "get_bytes", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    services.extract(doc.pk, app.pk, final_attempt=True)  # the task's last attempt
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR
    monkeypatch.setattr(storage, "get_bytes", real)
    act(services.retry, app, actor=team.hr_manager)
    app.refresh_from_db()
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert app.status == Status.PROCESSING and run.status == RunStatus.SUCCEEDED
    assert run.attempts == 2 and AuditEvent.objects.filter(action="resumes.retry").exists()

    late = submitted_app()
    bad = attach(late, scan=ScanStatus.PENDING)
    act(services.start, late.pk)
    Document.objects.filter(pk=bad.pk).update(scan_status=ScanStatus.INFECTED)
    act(services.on_document_rejected, bad.pk)
    late.refresh_from_db()
    assert late.status == Status.PROCESSING_ERROR
    assert not Notification.objects.filter(recipient_user=late.candidate_user).exists()
    assert doc.pk != bad.pk


def test_not_a_cv_still_reaches_review_and_asks_candidate(act: Any) -> None:
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_textbox(
        pymupdf.Rect(50, 50, 545, 800),
        "CERTIFICATE OF COMPLETION\n\nThis is to certify that Rudo Moyo has successfully "
        "completed the course in First Aid at the Red Cross training centre. " * 3,
        fontsize=12,
    )
    app = submitted_app()
    attach(app, pdf.tobytes(), filename="certificate.pdf")
    act(services.start, app.pk)
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert "possibly_not_cv" in run.flags
    (ready,) = events("application.evidence_ready")
    assert "possibly_not_cv" in ready.payload["flags"]
    assert Notification.objects.filter(
        recipient_user=app.candidate_user, key="document_rejected_reupload"
    ).exists()


def test_claims_are_tenant_scoped(act: Any) -> None:
    app = submitted_app()
    attach(app)
    act(services.start, app.pk)
    other = make_org_with_team().org
    assert ExtractedClaim.objects.for_org(other.pk).count() == 0
    assert ExtractionRun.objects.for_org(other.pk).count() == 0
    assert ExtractedClaim.objects.for_org(app.organisation_id).count() > 0


def test_no_cv_attached_is_ready_immediately(act: Any) -> None:
    app = submitted_app()
    act(services.start, app.pk)
    (ready,) = events("application.evidence_ready")
    assert ready.payload["extraction_run_ids"] == []


def test_outbox_consumers_drive_the_flow(act: Any, settings: Any) -> None:
    from django.db import transaction

    from apps.core import outbox

    app = submitted_app()
    attach(app)

    def submit_event() -> None:
        with transaction.atomic():
            outbox.emit(
                "application.submitted",
                app,
                {"application_id": str(app.pk)},
                dedupe_key=f"application.submitted:{app.pk}",
                organisation_id=app.organisation_id,
            )

    settings.RESUMES_AUTOSTART = False
    act(submit_event)
    app.refresh_from_db()
    assert app.status == Status.SUBMITTED  # switched off: consumers do nothing

    settings.RESUMES_AUTOSTART = True
    OutboxEvent.objects.all().delete()
    from apps.core.models import ProcessedEvent

    ProcessedEvent.objects.all().delete()
    act(submit_event)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert run.status == RunStatus.SUCCEEDED
    assert len(events("application.evidence_ready")) == 1


def test_redelivered_task_after_worker_loss_finishes_the_run(act: Any) -> None:
    """EC-OPS-04: a deploy/crash mid-extraction leaves the run 'running'; acks_late redelivers the
    task, which finishes the run without duplicating claims or events."""
    from apps.resumes.tasks import extract_resume, parse_resume_preview

    assert extract_resume.acks_late and extract_resume.reject_on_worker_lost
    assert parse_resume_preview.acks_late
    app = submitted_app()
    doc = attach(app, scan=ScanStatus.PENDING)
    act(services.start, app.pk)
    Document.objects.filter(pk=doc.pk).update(scan_status=ScanStatus.CLEAN)
    run = ExtractionRun.objects.create(
        organisation_id=app.organisation_id,
        application=app,
        document=doc,
        engine_version=ENGINE_VERSION,
        status=RunStatus.RUNNING,  # the worker died here
        attempts=1,
    )
    assert act(extract_resume.apply, args=(str(doc.pk), str(app.pk))).get() == "ready"
    run.refresh_from_db()
    assert run.status == RunStatus.SUCCEEDED and run.attempts == 2
    assert run.claims.count() == run.claim_count > 0
    assert len(events("application.evidence_ready")) == 1
    assert extract_resume.apply(args=(str(doc.pk), str(app.pk))).get() == RunStatus.SUCCEEDED
    assert run.claims.count() == run.claim_count  # a second redelivery is a no-op
