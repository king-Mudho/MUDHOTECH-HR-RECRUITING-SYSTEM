"""Resume extraction orchestration (P06-T11).

Flow: ``application.submitted`` -> application ``processing`` -> once every CV attached to it
has passed the scan, one ``ExtractionRun`` per CV is queued -> ``extract_resume`` parses it
(sandboxed) and stores text + claims -> when all runs are usable the outbox event
``application.evidence_ready`` is emitted (screening, Phase 07, picks it up).

Failures never lose the application (principle 6): an unreadable CV puts the application in
``processing_error`` and asks the candidate to upload a readable file; a re-upload restarts the
flow. A candidate who objected to automated processing (EC-AI-12) gets no extraction at all and
the evidence event says so, so screening routes them to fully manual review.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from django.conf import settings
from django.db import transaction

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import ExtractionResult, Flag
from apps.applications.models import Application, ApplicationDocument, DocumentRole, Status
from apps.applications.services import transition
from apps.audit import services as audit
from apps.core import outbox, storage
from apps.core.time import now
from apps.documents.models import Document, ScanStatus

from . import engine
from .models import DocumentText, ExtractedClaim, ExtractionRun, RunStatus

logger = logging.getLogger(__name__)

ACCEPTED = (ScanStatus.CLEAN, ScanStatus.SKIPPED)
# extraction failures the candidate can fix by uploading another file
REUPLOAD_REASONS = {
    "corrupt": "we could not read it (the file may be damaged)",
    "encrypted_pdf": "it is password-protected",
    "too_many_pages": "it has too many pages",
    "unsupported_format": "it is not a PDF or Word (.docx) file we can read",
    "macro_document": "it contains macros (please save it as a normal .docx or PDF)",
    "zip_bomb": "it could not be opened safely",
    "too_large": "it is larger than the allowed size",
    "parser_crash": "we could not read it",
    "timeout": "it took too long to read",
    "document_rejected": "it did not pass our file checks",
    "possibly_not_cv": "it does not look like a CV",
}


def objected(app: Application) -> bool:
    event = app.status_events.filter(to_status=Status.SUBMITTED).order_by("-at").first()
    return bool(event and (event.metadata or {}).get("objects_to_automated_processing"))


def cv_links(app: Application) -> list[ApplicationDocument]:
    return list(
        ApplicationDocument.objects.for_org(app.organisation_id)
        .filter(application=app, role=DocumentRole.CV)
        .select_related("document")
    )


# --------------------------------------------------------------------------- orchestration
def start(application_id: Any) -> None:
    """``application.submitted``: move to processing and extract what is ready."""
    with transaction.atomic():
        app = Application.objects.unscoped().select_for_update().filter(pk=application_id).first()
        if app is None or app.status != Status.SUBMITTED:
            return  # withdrawn already, or a replayed event
        app = transition(app, Status.PROCESSING, actor_type="system", reason_code="extraction")
        schedule(app)


def schedule(app: Application) -> None:
    """Queue extraction for every accepted CV; finish immediately when there is nothing to do.

    Must run inside a transaction with the application row locked.
    """
    from .tasks import extract_resume

    if app.status != Status.PROCESSING:
        return
    if objected(app):
        _evidence_ready(app, [], manual=True)
        return
    links = cv_links(app)
    if any(
        link.document.scan_status in (ScanStatus.INFECTED, ScanStatus.REJECTED) for link in links
    ):
        bad = next(
            link.document
            for link in links
            if link.document.scan_status in (ScanStatus.INFECTED, ScanStatus.REJECTED)
        )
        _fail(app, bad, "document_rejected")
        return
    if any(link.document.scan_status not in ACCEPTED for link in links):
        return  # wait for document.accepted
    for link in links:
        run, _ = ExtractionRun.objects.get_or_create(
            organisation_id=app.organisation_id,
            application=app,
            document=link.document,
            engine_version=ENGINE_VERSION,
        )
        if not run.usable and run.status != RunStatus.RUNNING:
            transaction.on_commit(partial(extract_resume.delay, str(link.document_id), str(app.pk)))
    finish(app)


def on_document_accepted(document_id: Any) -> None:
    for app_id in _applications_waiting_for(document_id):
        with transaction.atomic():
            app = Application.objects.unscoped().select_for_update().get(pk=app_id)
            if app.status == Status.PROCESSING_ERROR:  # a re-upload after a failure
                app = transition(
                    app, Status.PROCESSING, actor_type="system", reason_code="reupload"
                )
            schedule(app)


def on_document_rejected(document_id: Any) -> None:
    for app_id in _applications_waiting_for(document_id):
        with transaction.atomic():
            app = Application.objects.unscoped().select_for_update().get(pk=app_id)
            if app.status == Status.PROCESSING:
                doc = Document.objects.get(pk=document_id)
                _fail(app, doc, "document_rejected", notify=False)  # the scan already told them


def _applications_waiting_for(document_id: Any) -> list[Any]:
    return list(
        ApplicationDocument.objects.unscoped()
        .filter(
            document_id=document_id,
            role=DocumentRole.CV,
            application__status__in=[Status.PROCESSING, Status.PROCESSING_ERROR],
        )
        .values_list("application_id", flat=True)
    )


# ------------------------------------------------------------------------------ extraction
def extract(document_id: Any, application_id: Any, *, final_attempt: bool = True) -> str:
    """Extract one CV for one application. Idempotent; returns the run status."""
    with transaction.atomic():
        app = Application.objects.unscoped().filter(pk=application_id).first()
        if app is None or app.status != Status.PROCESSING:
            return "skipped"  # withdrawn or no longer processing: nothing to do
        run = (
            ExtractionRun.objects.for_org(app.organisation_id)
            .select_for_update()
            .filter(application=app, document_id=document_id, engine_version=ENGINE_VERSION)
            .first()
        )
        if run is None:
            return "skipped"
        if run.usable:
            return run.status
        run.status = RunStatus.RUNNING
        run.attempts += 1
        run.started_at = now()
        run.save(update_fields=["status", "attempts", "started_at", "updated_at"])
        document = run.document

    reused = _reusable_run(document, app)
    if reused is not None:
        _copy_run(reused, run)
    else:
        try:
            data = storage.get_bytes(document.bucket, document.storage_key)
        except Exception:
            # storage outage: let the task retry; on the last attempt record a failure
            if not final_attempt:
                ExtractionRun.objects.for_org(app.organisation_id).filter(pk=run.pk).update(
                    status=RunStatus.PENDING
                )
                raise
            _store_failure(run, "storage_unavailable")
            return _after_run(app.pk)
        result, taxonomy_version = engine.run(
            data,
            document_id=str(document.pk),
            organisation_id=app.organisation_id,
            today=now().date(),
        )
        _store(run, result, taxonomy_version)
    return _after_run(app.pk)


def _reusable_run(document: Document, app: Application) -> ExtractionRun | None:
    """EC-DOC-25: the same file was already extracted for this candidate - reuse it."""
    original = document.duplicate_of_id
    candidates = ExtractionRun.objects.for_org(app.organisation_id).filter(
        engine_version=ENGINE_VERSION, status__in=[RunStatus.SUCCEEDED, RunStatus.PARTIAL]
    )
    if original is not None:
        found = candidates.filter(document_id=original).order_by("-created_at").first()
        if found is not None:
            return found
    return (
        candidates.filter(document_id=document.pk)
        .exclude(application=app)
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def _copy_run(source: ExtractionRun, run: ExtractionRun) -> None:
    for name in ("status", "error_code", "flags", "parser_used", "language", "quality_score"):
        setattr(run, name, getattr(source, name))
    run.page_count, run.claim_count, run.taxonomy_version = (
        source.page_count,
        source.claim_count,
        source.taxonomy_version,
    )
    run.reused_from = source
    run.finished_at = now()
    run.save()
    text = getattr(source, "text", None)
    if text is not None:
        DocumentText.objects.create(
            organisation_id=run.organisation_id,
            run=run,
            payload=text.payload,
            sections=text.sections,
            char_count=text.char_count,
        )
    ExtractedClaim.objects.bulk_create(
        [
            ExtractedClaim(
                organisation_id=run.organisation_id,
                run=run,
                **{
                    f.name: getattr(claim, f.name)
                    for f in ExtractedClaim._meta.concrete_fields
                    if f.name not in ("id", "run", "organisation", "created_at", "updated_at")
                },
            )
            for claim in source.claims.all()
        ]
    )


@transaction.atomic
def _store(run: ExtractionRun, result: ExtractionResult, taxonomy_version: str) -> None:
    run = ExtractionRun.objects.for_org(run.organisation_id).select_for_update().get(pk=run.pk)
    if run.usable:
        return
    run.status = result.status.value
    run.error_code = result.error_code or ""
    run.flags = sorted(flag.value for flag in result.flags)
    run.timings_ms = dict(result.timings_ms)
    run.taxonomy_version = taxonomy_version
    run.finished_at = now()
    doc = result.document
    if doc is not None:
        run.parser_used = doc.parser_used[:40]
        run.language = (doc.language or "")[:10]
        run.quality_score = doc.quality_score
        run.page_count = len(doc.pages)
        DocumentText.objects.create(
            organisation_id=run.organisation_id,
            run=run,
            payload=doc.model_dump_json(),
            sections=[s.model_dump(mode="json") for s in result.sections],
            char_count=doc.char_count,
        )
    rows = []
    for ordinal, claim in enumerate(result.claims):
        data = claim.data
        src = claim.source
        rows.append(
            ExtractedClaim(
                organisation_id=run.organisation_id,
                run=run,
                ordinal=ordinal,
                claim_type=data.type,
                section=(claim.section.value if claim.section else ""),
                method=claim.method.value,
                confidence=claim.confidence,
                evidence=claim.evidence.value,
                excluded_reason=(claim.excluded_reason.value if claim.excluded_reason else ""),
                page=src.page,
                char_start=src.char_start,
                char_end=src.char_end,
                skill_id=(getattr(data, "skill_id", None) or "")[:64],
                payload=claim.model_dump_json(),
            )
        )
    ExtractedClaim.objects.bulk_create(rows)
    run.claim_count = len(rows)
    run.save()
    audit.record(
        action="resumes.extracted",
        target=run,
        organisation=run.organisation_id,
        actor_type="system",
        after={
            "status": run.status,
            "claims": run.claim_count,
            "engine_version": run.engine_version,
            "flags": run.flags,
        },
    )


def _store_failure(run: ExtractionRun, code: str) -> None:
    ExtractionRun.objects.for_org(run.organisation_id).filter(pk=run.pk).update(
        status=RunStatus.FAILED, error_code=code, finished_at=now()
    )


def _after_run(application_id: Any) -> str:
    with transaction.atomic():
        app = Application.objects.unscoped().select_for_update().get(pk=application_id)
        return finish(app)


def finish(app: Application) -> str:
    """Decide the application's next step once its runs settle (inside a locked transaction)."""
    if app.status != Status.PROCESSING:
        return app.status
    links = cv_links(app)
    runs = {
        r.document_id: r
        for r in ExtractionRun.objects.for_org(app.organisation_id).filter(
            application=app, engine_version=ENGINE_VERSION
        )
    }
    pending = [x for x in links if x.document_id not in runs or not _settled(runs[x.document_id])]
    if pending:
        return "waiting"
    failed = [runs[x.document_id] for x in links if runs[x.document_id].status == RunStatus.FAILED]
    if failed:
        _fail(app, failed[0].document, failed[0].error_code or "corrupt")
        return "failed"
    usable = [runs[x.document_id] for x in links]
    for run in usable:
        if Flag.POSSIBLY_NOT_CV.value in run.flags:
            _ask_reupload(app, run.document, "possibly_not_cv", key=f"not_cv:{run.pk}")
    _apply_cross_checks(app, usable)
    _evidence_ready(app, usable)
    return "ready"


def _settled(run: ExtractionRun) -> bool:
    return run.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED)


def _apply_cross_checks(app: Application, runs: list[ExtractionRun]) -> None:
    """P06-T12: low-severity HR flags (EC-APP-15/16). Never changes status or scores."""
    from .crosscheck import check

    found = [f for f in check(app, runs) if f not in (app.flags or [])]
    if not found:
        return
    app.flags = sorted({*(app.flags or []), *found})
    Application.objects.unscoped().filter(pk=app.pk).update(flags=app.flags)
    audit.record(
        action="resumes.flags_raised",
        target=app,
        organisation=app.organisation_id,
        actor_type="system",
        after={"flags": found},
    )


def _evidence_ready(app: Application, runs: list[ExtractionRun], *, manual: bool = False) -> None:
    run_ids = sorted(str(r.pk) for r in runs)
    flags = sorted({f for r in runs for f in r.flags} | set(app.flags or []))
    outbox.emit(
        "application.evidence_ready",
        app,
        {
            "application_id": str(app.pk),
            "engine_version": ENGINE_VERSION,
            "extraction_run_ids": run_ids,
            "flags": flags,
            "manual_review_requested": manual,
        },
        dedupe_key=f"application.evidence_ready:{app.pk}:{ENGINE_VERSION}:{'-'.join(run_ids)}",
        organisation_id=app.organisation_id,
    )


def _fail(app: Application, document: Document, code: str, *, notify: bool = True) -> None:
    transition(
        app,
        Status.PROCESSING_ERROR,
        actor_type="system",
        reason_code=code[:40],
        metadata={"document_id": str(document.pk)},
    )
    if notify:
        _ask_reupload(app, document, code, key=f"extraction_failed:{app.pk}:{document.pk}")


def _ask_reupload(app: Application, document: Document, code: str, *, key: str) -> None:
    from apps.notifications import delivery as notifications

    why = REUPLOAD_REASONS.get(code, "we could not read it")
    notifications.notify(
        app.candidate_user,
        "document_rejected_reupload",
        {
            "document_name": document.original_filename,
            "reason": f"We could not use this file because {why}. Your application is safe - "
            "please upload a readable PDF or Word version.",
            "application_url": f"{settings.FRONTEND_URL}/candidate/applications/{app.pk}",
        },
        dedupe_key=key,
        organisation=app.organisation,
    )


# ------------------------------------------------------------------------------- retrying
def retry(app: Application, *, actor: Any) -> Application:
    """HR "Retry processing" (P06-T14): new attempt for failed runs; nothing is deleted."""
    with transaction.atomic():
        locked = Application.objects.for_org(app.organisation_id).select_for_update().get(pk=app.pk)
        if locked.status == Status.PROCESSING_ERROR:
            locked = transition(locked, Status.PROCESSING, actor=actor, reason_code="retry")
        ExtractionRun.objects.for_org(app.organisation_id).filter(
            application=locked, engine_version=ENGINE_VERSION, status=RunStatus.FAILED
        ).update(status=RunStatus.PENDING, error_code="")
        audit.record(
            actor=actor, action="resumes.retry", target=locked, organisation=app.organisation_id
        )
        schedule(locked)
    return locked
