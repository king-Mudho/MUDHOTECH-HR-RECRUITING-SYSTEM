"""Scan pipeline (P04-T03): signatures, archive guards, PDF checks, antivirus, promotion."""

from __future__ import annotations

import io
import socket
import struct
import threading
import zipfile
from typing import Any

import pytest
from PIL import Image

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.core.models import OutboxEvent
from apps.documents import antivirus, inspect
from apps.documents.models import Document, ScanStatus
from apps.documents.services import complete_session, create_session

pytestmark = pytest.mark.django_db

DOCX_MIME = inspect.DOCX_MIME


def make_pdf(pages: int = 1, password: str | None = None) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Synthetic CV page {i + 1}")
    out = io.BytesIO()
    if password:
        doc.save(out, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password)
    else:
        doc.save(out)
    return out.getvalue()


def make_docx(extra: dict[str, bytes] | None = None, content_types: bytes | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types or b"<Types/>")
        z.writestr("word/document.xml", b"<w:document>Synthetic CV</w:document>")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def upload(s3: Any, django_capture_on_commit_callbacks: Any) -> Any:
    """Real flow: session -> PUT to quarantine -> complete -> scan (on commit, eager in tests)."""

    def run(user: Any, data: bytes, filename: str, mime: str, purpose: str = "cv") -> Document:
        session, _ = create_session(
            user, purpose=purpose, filename=filename, mime=mime, size=len(data)
        )
        s3.put_object(Bucket="mhrs-uploads-quarantine", Key=session.object_key, Body=data)
        with django_capture_on_commit_callbacks(execute=True):
            doc = complete_session(user, session.pk)
        doc.refresh_from_db()
        return doc

    return run


def rejection_emails(user: Any) -> list[str]:
    """Rendered bodies of the re-upload requests queued for ``user``."""
    from apps.notifications.testing import emails_for

    return emails_for(user, "document_rejected_reupload")


def quarantine_keys(s3: Any) -> list[str]:
    return [
        o["Key"] for o in s3.list_objects_v2(Bucket="mhrs-uploads-quarantine").get("Contents", [])
    ]


# ------------------------------------------------------------------------------- inspect unit
def test_sniff_signatures() -> None:
    assert inspect.sniff(b"%PDF-1.7 ...") == inspect.PDF_MIME
    assert inspect.sniff(b"\x89PNG\r\n\x1a\n....") == inspect.PNG_MIME
    assert inspect.sniff(b"\xff\xd8\xff\xe0") == inspect.JPEG_MIME
    assert inspect.sniff(b"PK\x03\x04") == "application/zip"
    assert inspect.sniff(b"MZ\x90\x00") == "application/x-executable"
    assert inspect.sniff(b"\xd0\xcf\x11\xe0\xa1\xb1") == "application/x-ole-storage"


def test_docx_guards() -> None:
    inspect.check_docx(make_docx())
    with pytest.raises(inspect.RejectedFileError) as macro:
        inspect.check_docx(make_docx({"word/vbaProject.bin": b"x"}))
    assert macro.value.reason == "macros"
    bomb = make_docx({"word/media/zeros.bin": b"\0" * (120 * 1024 * 1024)})  # EC-DOC-07
    with pytest.raises(inspect.RejectedFileError) as exc:
        inspect.check_docx(bomb)
    assert exc.value.reason == "archive_limits"
    not_word = io.BytesIO()
    with zipfile.ZipFile(not_word, "w") as z:
        z.writestr("readme.txt", b"hi")
    with pytest.raises(inspect.RejectedFileError) as exc2:
        inspect.check_docx(not_word.getvalue())
    assert exc2.value.reason == "type_mismatch"


def test_pdf_checks() -> None:
    assert inspect.check_pdf(make_pdf(3), 30) == 3
    with pytest.raises(inspect.RejectedFileError) as many:
        inspect.check_pdf(make_pdf(31), 30)  # EC-DOC-08
    assert many.value.reason == "too_many_pages"
    with pytest.raises(inspect.RejectedFileError) as enc:
        inspect.check_pdf(make_pdf(1, password="secret"), 30)
    assert enc.value.reason == "encrypted"
    with pytest.raises(inspect.RejectedFileError):
        inspect.check_pdf(b"%PDF-1.4 garbage", 30)


def test_image_reencode_strips_metadata_and_appended_payload() -> None:
    img = Image.new("RGB", (20, 20), "red")
    raw = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "GPS secret"  # ImageDescription
    img.save(raw, format="JPEG", exif=exif)
    polyglot = raw.getvalue() + b"<?php echo 'x'; ?>"
    out = inspect.reencode_image(polyglot, inspect.JPEG_MIME)
    assert b"GPS secret" not in out and b"<?php" not in out
    with Image.open(io.BytesIO(out)) as again:
        assert again.size == (20, 20)


# ----------------------------------------------------------------------------- full pipeline
@pytest.fixture
def user() -> Any:
    return UserFactory()


def test_clean_pdf_is_promoted(s3: Any, user: Any, upload: Any) -> None:
    doc = upload(user, make_pdf(2), "cv.pdf", "application/pdf")
    assert doc.scan_status == ScanStatus.CLEAN and doc.bucket == "documents"
    assert doc.page_count == 2 and len(doc.sha256) == 64 and doc.scan_engine_version == "fake"
    assert quarantine_keys(s3) == []
    s3.head_object(Bucket="mhrs-documents", Key=doc.storage_key)
    assert OutboxEvent.objects.filter(
        event_type="document.accepted", aggregate_id=str(doc.pk)
    ).exists()


def test_clean_docx_is_promoted(s3: Any, user: Any, upload: Any) -> None:
    doc = upload(user, make_docx(), "cv.docx", DOCX_MIME)
    assert doc.scan_status == ScanStatus.CLEAN and doc.mime_detected == DOCX_MIME


def test_eicar_is_quarantined_audited_and_candidate_notified(
    s3: Any, user: Any, upload: Any
) -> None:
    """EC-DOC-06: malware never leaves quarantine and is never parsed."""
    infected = make_pdf(1) + b"\n" + antivirus.EICAR
    doc = upload(user, infected, "cv.pdf", "application/pdf")
    assert doc.scan_status == ScanStatus.INFECTED and doc.rejected_reason == "malware"
    assert doc.bucket == "quarantine" and doc.page_count is None
    assert quarantine_keys(s3) == [doc.storage_key]
    assert AuditEvent.objects.filter(
        action="document.malware_detected", target_id=str(doc.pk)
    ).exists()
    assert OutboxEvent.objects.filter(
        event_type="document.rejected", aggregate_id=str(doc.pk)
    ).exists()
    emails = rejection_emails(user)
    assert len(emails) == 1
    body = emails[0]
    assert "security check" in body and "Eicar" not in body  # generic message


def test_spoofed_executable_is_rejected_before_scanning(
    s3: Any, user: Any, monkeypatch: Any, upload: Any
) -> None:
    """EC-DOC-05: an .exe renamed .pdf fails the signature check; no parser/AV sees it."""
    called = []
    monkeypatch.setattr(antivirus, "scan", lambda data: called.append(1))
    doc = upload(user, b"MZ\x90\x00" + b"\0" * 200, "cv.pdf", "application/pdf")
    assert doc.scan_status == ScanStatus.REJECTED and doc.rejected_reason == "type_mismatch"
    assert doc.mime_detected == "application/x-executable" and called == []


@pytest.mark.parametrize(
    ("data", "name", "mime", "reason"),
    [
        (make_pdf(31), "cv.pdf", "application/pdf", "too_many_pages"),
        (make_pdf(1, password="pw"), "cv.pdf", "application/pdf", "encrypted"),
        (make_docx({"word/vbaProject.bin": b"x"}), "cv.docx", DOCX_MIME, "macros"),
        (b"%PDF-1.4 not really", "cv.pdf", "application/pdf", "corrupt"),
    ],
)
def test_content_rejections(
    s3: Any, user: Any, data: bytes, name: str, mime: str, reason: str, upload: Any
) -> None:
    doc = upload(user, data, name, mime)
    assert doc.scan_status == ScanStatus.REJECTED and doc.rejected_reason == reason
    assert len(rejection_emails(user)) == 1


def test_supporting_png_is_reencoded(s3: Any, user: Any, upload: Any) -> None:
    raw = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(raw, format="PNG")
    data = raw.getvalue() + b"TRAILING-PAYLOAD"
    doc = upload(user, data, "certificate.png", "image/png", purpose="supporting")
    assert doc.scan_status == ScanStatus.CLEAN
    stored = s3.get_object(Bucket="mhrs-documents", Key=doc.storage_key)["Body"].read()
    assert b"TRAILING-PAYLOAD" not in stored and doc.size_bytes == len(stored)


def test_scanner_outage_leaves_document_pending_for_retry(
    s3: Any, user: Any, monkeypatch: Any
) -> None:
    from apps.documents import pipeline, tasks

    def down(data: bytes) -> Any:
        raise antivirus.ScannerUnavailableError("connection refused")

    session, _ = create_session(
        user, purpose="cv", filename="cv.pdf", mime="application/pdf", size=10
    )
    s3.put_object(Bucket="mhrs-uploads-quarantine", Key=session.object_key, Body=make_pdf(1))
    doc = complete_session(user, session.pk)  # scan is deferred to on_commit (not run here)
    monkeypatch.setattr(antivirus, "scan", down)
    with pytest.raises(antivirus.ScannerUnavailableError):
        pipeline.scan_document(doc.pk)
    doc.refresh_from_db()
    assert doc.scan_status == ScanStatus.PENDING and doc.sha256 == ""  # rolled back, retryable
    assert antivirus.ScannerUnavailableError in tasks.scan_document.autoretry_for
    monkeypatch.undo()
    assert pipeline.scan_document(doc.pk) == "accepted"
    assert pipeline.scan_document(doc.pk) == "noop"  # idempotent


def test_skip_mode_refused_without_debug(settings: Any) -> None:
    settings.DOCUMENT_SCANNER = "skip"
    settings.DEBUG = False
    with pytest.raises(antivirus.ScannerUnavailableError):
        antivirus.scan(b"x")
    settings.DEBUG = True
    assert antivirus.scan(b"x").skipped


# ----------------------------------------------------------------------------- clamd protocol
class FakeClamd:
    """Minimal clamd speaking the z-command / INSTREAM protocol."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                buf = b""
                while b"\0" not in buf:
                    buf += conn.recv(1024)
                command, _, rest = buf.partition(b"\0")
                if command == b"zVERSION":
                    conn.sendall(b"ClamAV 1.4.0/27000\0")
                    continue
                data = rest
                payload = b""
                while True:
                    while len(data) < 4:
                        data += conn.recv(65536)
                    (size,) = struct.unpack("!L", data[:4])
                    data = data[4:]
                    if size == 0:
                        break
                    while len(data) < size:
                        data += conn.recv(65536)
                    payload, data = payload + data[:size], data[size:]
                found = antivirus.EICAR in payload
                conn.sendall(b"stream: Eicar-Test-Signature FOUND\0" if found else b"stream: OK\0")


def test_clamd_instream_protocol(settings: Any) -> None:
    server = FakeClamd()
    settings.CLAMAV_HOST, settings.CLAMAV_PORT, settings.CLAMAV_TIMEOUT = (
        "127.0.0.1",
        server.port,
        5,
    )
    settings.DOCUMENT_SCANNER = "clamd"
    ok = antivirus.scan(b"%PDF-1.4" + b"a" * 200_000)  # several INSTREAM chunks
    assert ok.clean and ok.engine.startswith("ClamAV 1.4.0")
    bad = antivirus.scan(b"prefix " + antivirus.EICAR)
    assert not bad.clean and bad.signature == "Eicar-Test-Signature"
    server.sock.close()


def test_clamd_unreachable_raises(settings: Any) -> None:
    settings.CLAMAV_HOST, settings.CLAMAV_PORT, settings.CLAMAV_TIMEOUT = "127.0.0.1", 1, 1
    settings.DOCUMENT_SCANNER = "clamd"
    with pytest.raises(antivirus.ScannerUnavailableError):
        antivirus.scan(b"x")


@pytest.mark.skipif(
    not __import__("os").environ.get("CLAMD_INTEGRATION"),
    reason="needs a real clamd (nightly: CLAMD_INTEGRATION=1, CLAMAV_HOST/PORT)",
)
def test_real_clamd_detects_eicar(settings: Any) -> None:
    import os

    settings.DOCUMENT_SCANNER = "clamd"
    settings.CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "localhost")
    settings.CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", "3310"))
    settings.CLAMAV_TIMEOUT = 60
    assert antivirus.scan(b"%PDF-1.4 clean synthetic file").clean
    verdict = antivirus.scan(antivirus.EICAR)
    # ClamAV names it e.g. "Win.Test.EICAR_HDB-1" (older releases: "Eicar-Signature")
    assert not verdict.clean and "eicar" in verdict.signature.lower()
