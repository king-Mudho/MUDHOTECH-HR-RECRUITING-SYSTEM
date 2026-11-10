"""Quarantine scan pipeline (P04-T03). Runs on the ``documents`` queue, never on the request path.

Order matters: hash -> cheap signature check -> antivirus -> deep inspection (PDF/DOCX/image parse).
Infected files are never parsed (EC-DOC-06). Accepted files move to the private ``documents``
bucket; rejected files stay in quarantine until the cleanup job removes them (P04-T04).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import outbox, storage
from apps.core.time import now

from . import antivirus, inspect
from .models import Document, ScanStatus
from .services import RULES, max_bytes

logger = logging.getLogger(__name__)

# Candidate-facing explanations (generic for malware: never reveal signatures).
REASON_TEXT = {
    "malware": "it did not pass our security check",
    "type_mismatch": "its content doesn't match its file type",
    "encrypted": "it is password-protected",
    "too_many_pages": "it has too many pages",
    "archive_limits": "it could not be opened safely",
    "macros": "it contains macros (please save it as a normal .docx or PDF)",
    "corrupt": "it could not be opened",
    "size": "it is larger than the allowed size",
}


def _notify_rejection(doc: Document, reason: str) -> None:
    from django.conf import settings

    from apps.notifications import delivery as notifications

    why = REASON_TEXT.get(reason, "it could not be accepted")
    with transaction.atomic():
        notifications.notify(
            doc.owner_user,
            "document_rejected_reupload",
            {
                "document_name": doc.original_filename,
                "reason": f"It could not be accepted because {why}.",
                "application_url": f"{settings.FRONTEND_URL}/candidate/documents",
            },
            dedupe_key=f"document_rejected:{doc.pk}",
        )


def _reject(
    doc: Document, status: str, reason: str, *, signature: str = "", engine: str = ""
) -> None:
    doc.scan_status = status
    doc.rejected_reason = reason
    doc.scanned_at = now()
    doc.scan_engine_version = engine[:100]
    doc.save(
        update_fields=[
            "scan_status",
            "rejected_reason",
            "scanned_at",
            "scan_engine_version",
            "sha256",
            "mime_detected",
            "updated_at",
        ]
    )
    if status == ScanStatus.INFECTED:
        audit.record(
            action="document.malware_detected",
            target=doc,
            organisation=doc.organisation_id,
            actor_type="system",
            after={"signature": signature[:100], "purpose": doc.purpose},
        )
    outbox.emit(
        "document.rejected",
        doc,
        {"document_id": str(doc.pk), "reason": reason, "owner_user_id": str(doc.owner_user_id)},
        dedupe_key=f"document.rejected:{doc.pk}",
    )
    _notify_rejection(doc, reason)


def _find_original(doc: Document) -> Document | None:
    """EC-DOC-25: an accepted, non-alias document of the same owner, purpose and bytes."""
    return (
        Document.objects.filter(
            owner_user_id=doc.owner_user_id,
            sha256=doc.sha256,
            purpose=doc.purpose,
            scan_status__in=[ScanStatus.CLEAN, ScanStatus.SKIPPED],
            deleted_at__isnull=True,
            duplicate_of__isnull=True,
        )
        .exclude(pk=doc.pk)
        .order_by("created_at")
        .first()
    )


def _alias(doc: Document, original: Document) -> None:
    """Point a duplicate at the original's stored file and verdict (extraction is reused)."""
    doc.duplicate_of = original
    doc.bucket = original.bucket
    doc.storage_key = original.storage_key
    for name in ("mime_detected", "page_count", "size_bytes", "scan_status", "scan_engine_version"):
        setattr(doc, name, getattr(original, name))
    doc.scanned_at = now()
    doc.save()
    outbox.emit(
        "document.accepted",
        doc,
        {
            "document_id": str(doc.pk),
            "purpose": doc.purpose,
            "owner_user_id": str(doc.owner_user_id),
            "duplicate_of": str(original.pk),
        },
        dedupe_key=f"document.accepted:{doc.pk}",
    )


def scan_document(document_id: Any) -> str:
    """Scan one quarantined document. Idempotent: anything but ``pending`` is a no-op."""
    with transaction.atomic():
        doc = (
            Document.objects.select_for_update()
            .select_related("owner_user")
            .filter(pk=document_id)
            .first()
        )
        if doc is None or doc.scan_status != ScanStatus.PENDING:
            return "noop"
        quarantine_key = doc.storage_key
        limit = max_bytes(doc.purpose, doc.organisation_id)
        data = storage.get_bytes("quarantine", quarantine_key, max_bytes=limit + 1)
        doc.sha256 = hashlib.sha256(data).hexdigest()
        doc.mime_detected = inspect.sniff(data)
        if len(data) > limit:
            _reject(doc, ScanStatus.REJECTED, "size")
            return "rejected"

        original = _find_original(doc)
        if original is not None:
            _alias(doc, original)
            outcome = "duplicate"
        else:
            outcome = _scan_and_promote(doc, data, quarantine_key)
            if outcome != "accepted":
                return outcome
    storage.delete_object("quarantine", quarantine_key)
    return outcome


def _scan_and_promote(doc: Document, data: bytes, quarantine_key: str) -> str:
    extension = PurePosixPath(quarantine_key).suffix
    expected = inspect.EXTENSION_MIME.get(extension)
    sniffed_ok = doc.mime_detected == expected or (
        expected == inspect.DOCX_MIME and doc.mime_detected == "application/zip"
    )
    if not sniffed_ok:  # EC-DOC-05: refuse before handing bytes to any parser
        _reject(doc, ScanStatus.REJECTED, "type_mismatch")
        return "rejected"

    verdict = antivirus.scan(data)  # ScannerUnavailableError -> retry; document stays pending
    if not verdict.clean:
        _reject(
            doc, ScanStatus.INFECTED, "malware", signature=verdict.signature, engine=verdict.engine
        )
        return "infected"

    try:
        result = inspect.inspect(data, extension, RULES[doc.purpose].max_pages)
    except inspect.RejectedFileError as exc:
        _reject(doc, ScanStatus.REJECTED, exc.reason, engine=verdict.engine)
        return "rejected"

    body = result.replacement if result.replacement is not None else data
    storage.put_bytes("documents", doc.storage_key, body, result.mime)
    doc.bucket = "documents"
    doc.mime_detected = result.mime
    doc.page_count = result.page_count
    doc.size_bytes = len(body)
    doc.scan_status = ScanStatus.SKIPPED if verdict.skipped else ScanStatus.CLEAN
    doc.scan_engine_version = verdict.engine[:100]
    doc.scanned_at = now()
    doc.save()
    outbox.emit(
        "document.accepted",
        doc,
        {
            "document_id": str(doc.pk),
            "purpose": doc.purpose,
            "owner_user_id": str(doc.owner_user_id),
        },
        dedupe_key=f"document.accepted:{doc.pk}",
    )
    return "accepted"
