"""Document upload services (P04-T02; FR-M07-02, docs/06 §3, EC-DOC-04/05).

Validation at session creation is *declared* (name, MIME, size) and cheap; the authoritative checks
(magic bytes, archive guards, page counts, antivirus) run in the scan pipeline (P04-T03) before a
file ever leaves quarantine.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.audit import services as audit
from apps.core import outbox, storage
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now

from .models import Document, Purpose, ScanStatus, UploadSession

MB = 1024 * 1024


@dataclass(frozen=True)
class FileRule:
    extensions: dict[str, set[str]]  # extension -> accepted declared MIME types
    max_bytes: int
    max_pages: int | None


PDF = {".pdf": {"application/pdf"}}
DOCX = {".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}
IMAGES = {".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"}}

RULES: dict[str, FileRule] = {
    Purpose.CV: FileRule({**PDF, **DOCX}, 10 * MB, 30),
    Purpose.SUPPORTING: FileRule({**PDF, **DOCX, **IMAGES}, 10 * MB, 50),
    Purpose.MESSAGE_ATTACHMENT: FileRule({**PDF, **DOCX, **IMAGES}, 10 * MB, 50),
    Purpose.OFFER_LETTER: FileRule({**PDF}, 10 * MB, 50),
}
# EC-DOC-04: legacy/unsupported formats get specific guidance instead of a generic error.
CONVERT_GUIDANCE = {".doc", ".docm", ".odt", ".pages", ".rtf", ".wps", ".txt", ".xls", ".xlsx"}
APPLICATION_TOTAL_BYTES = 25 * MB


def max_bytes(purpose: str, organisation: Any = None) -> int:
    """Per-purpose limit (settings override) narrowed by the organisation's policy if any."""
    overrides: dict[str, int] = getattr(settings, "DOCUMENT_MAX_BYTES", {})
    limit = int(overrides.get(purpose, RULES[purpose].max_bytes))
    if organisation is not None:
        from apps.organisations.models import OrganisationPolicy

        policy = OrganisationPolicy.objects.filter(organisation=organisation).first()
        org_mb = (getattr(policy, "upload_limits_mb", None) or {}).get(purpose)
        if org_mb:
            limit = min(limit, int(org_mb) * MB)
    return limit


def sanitise_filename(name: str) -> str:
    """Keep a readable, safe display name (storage keys are UUIDs, never this value)."""
    base = PureWindowsPath(PurePosixPath(name or "").name).name  # drop any directory part
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")  # control chars
    base = re.sub(r"[^\w .()\-]", "_", base).strip(" .")
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    stem = re.sub(r"\s+", " ", stem)[:120] or "document"
    return f"{stem}.{ext.lower()[:10]}" if ext else stem


def _extension(name: str) -> str:
    suffix = PurePosixPath(name.lower()).suffix
    return suffix


def validate_declared(
    purpose: str, filename: str, mime: str, size: int, organisation: Any = None
) -> str:
    if purpose not in RULES:
        raise DomainError(
            "validation_error", "Unknown upload purpose.", details={"purpose": ["Invalid."]}
        )
    rule = RULES[purpose]
    clean = sanitise_filename(filename)
    ext = _extension(clean)
    if ext in CONVERT_GUIDANCE:
        raise DomainError(
            "unsupported_media_type",
            "This file type isn't accepted. Save it as PDF or Word (.docx) and upload again.",
            status_code=415,
            details={"filename": [f"{ext} files are not accepted."]},
        )
    if ext not in rule.extensions:
        allowed = ", ".join(sorted(e.lstrip(".").upper() for e in rule.extensions))
        raise DomainError(
            "unsupported_media_type",
            f"Please upload one of: {allowed}.",
            status_code=415,
            details={"filename": [f"Allowed: {allowed}."]},
        )
    if (mime or "").lower() not in rule.extensions[ext]:
        raise DomainError(
            "unsupported_media_type",
            "The file type doesn't match its name.",
            status_code=415,
            details={"mime": ["Does not match the file extension."]},
        )
    limit = max_bytes(purpose, organisation)
    if size <= 0:
        raise DomainError(
            "validation_error", "The file is empty.", details={"size": ["Empty file."]}
        )
    if size > limit:
        raise DomainError(
            "payload_too_large",
            f"The file is too large. The limit is {limit // MB} MB.",
            status_code=413,
            details={"size": [f"Maximum {limit // MB} MB."]},
        )
    return clean


def _object_key(user: Any, purpose: str, filename: str) -> str:
    return f"{purpose}/{user.pk}/{uuid.uuid4().hex}{_extension(filename)}"


@transaction.atomic
def create_session(
    user: Any, *, purpose: str, filename: str, mime: str, size: int, organisation: Any = None
) -> tuple[UploadSession, dict[str, Any]]:
    clean = validate_declared(purpose, filename, mime, size, organisation)
    session = UploadSession.objects.create(
        owner_user=user,
        organisation=organisation,
        purpose=purpose,
        declared_name=clean,
        declared_mime=mime.lower(),
        declared_size=size,
        object_key=_object_key(user, purpose, clean),
        expires_at=now() + timedelta(seconds=storage.PUT_TTL_SECONDS),
    )
    presigned = storage.presign_put("quarantine", session.object_key, session.declared_mime)
    return session, presigned


def _create_document(session: UploadSession, size: int) -> Document:
    doc = Document.objects.create(
        owner_user=session.owner_user,
        organisation=session.organisation,
        purpose=session.purpose,
        original_filename=session.declared_name,
        declared_mime=session.declared_mime,
        size_bytes=size,
        storage_key=session.object_key,
        bucket="quarantine",
        scan_status=ScanStatus.PENDING,
    )
    session.status = UploadSession.Status.UPLOADED
    session.document = doc
    session.save(update_fields=["status", "document", "updated_at"])
    # The scan pipeline (documents queue) consumes this; nothing heavy on the request path.
    outbox.emit(
        "document.uploaded",
        doc,
        {"document_id": str(doc.pk), "purpose": doc.purpose},
        dedupe_key=f"document.uploaded:{doc.pk}:1",
    )
    return doc


def complete_session(user: Any, session_id: Any) -> Document:
    """Confirm a presigned upload. Idempotent; a rejection is committed before the error."""
    with transaction.atomic():
        session = (
            UploadSession.objects.select_for_update().filter(pk=session_id, owner_user=user).first()
        )
        if session is None:
            raise NotFoundError()
        if session.status == UploadSession.Status.UPLOADED and session.document is not None:
            return session.document  # retry after a lost response
        if session.status != UploadSession.Status.PENDING:
            raise DomainError(
                "conflict.upload_closed",
                "This upload can no longer be completed. Please upload the file again.",
                status_code=409,
            )
        info = storage.head_object("quarantine", session.object_key)
        if info is None:
            raise DomainError(
                "upload_missing",
                "We didn't receive the file. Please try the upload again.",
                status_code=409,
            )
        limit = max_bytes(session.purpose, session.organisation)
        if 0 < info.size <= limit:
            return _create_document(session, info.size)
        session.status = UploadSession.Status.REJECTED
        session.rejected_reason = "size"
        session.save(update_fields=["status", "rejected_reason", "updated_at"])
        key = session.object_key
    storage.delete_object("quarantine", key)
    raise DomainError(
        "payload_too_large",
        f"The file is too large. The limit is {limit // MB} MB.",
        status_code=413,
    )


@transaction.atomic
def direct_upload(user: Any, *, purpose: str, uploaded: Any, organisation: Any = None) -> Document:
    """Multipart fallback for networks/browsers where presigned PUT fails (same validation)."""
    mime = getattr(uploaded, "content_type", "") or ""
    clean = validate_declared(purpose, uploaded.name, mime, uploaded.size, organisation)
    session = UploadSession.objects.create(
        owner_user=user,
        organisation=organisation,
        purpose=purpose,
        declared_name=clean,
        declared_mime=mime.lower(),
        declared_size=uploaded.size,
        object_key=_object_key(user, purpose, clean),
        expires_at=now() + timedelta(seconds=storage.PUT_TTL_SECONDS),
    )
    storage.put_bytes("quarantine", session.object_key, uploaded.read(), session.declared_mime)
    return _create_document(session, uploaded.size)


def can_access(user: Any, document: Document) -> bool:
    """Owner always; staff access through applications is added by the applications app."""
    if document.owner_user_id == user.pk:
        return True
    return any(check(user, document) for check in _ACCESS_CHECKERS)


_ACCESS_CHECKERS: list[Any] = []


def register_access_checker(fn: Any) -> Any:
    """Applications (P04-T15) register 'staff assigned to an application that links this doc'."""
    if fn not in _ACCESS_CHECKERS:
        _ACCESS_CHECKERS.append(fn)
    return fn


def get_document(user: Any, document_id: Any) -> Document:
    doc = Document.objects.filter(pk=document_id, deleted_at__isnull=True).first()
    if doc is None or not can_access(user, doc):
        raise NotFoundError()
    return doc


def download_url(user: Any, document_id: Any) -> str:
    doc = get_document(user, document_id)
    if not doc.is_available:
        raise DomainError(
            "document_unavailable",
            "This file isn't available for download yet.",
            status_code=409,
            details={"scan_status": doc.scan_status},
        )
    audit.log_access(user=user, target=doc, organisation=doc.organisation_id, action="download")
    return storage.presign_get(
        "documents", doc.storage_key, ttl=storage.GET_TTL_SECONDS, filename=doc.original_filename
    )
