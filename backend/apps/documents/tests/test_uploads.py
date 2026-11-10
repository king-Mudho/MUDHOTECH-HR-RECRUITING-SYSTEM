"""Document uploads (P04-T02): declared validation, presign flow, direct upload, access."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AccessLog
from apps.core.models import OutboxEvent
from apps.documents import services
from apps.documents.models import Document, ScanStatus, UploadSession

pytestmark = pytest.mark.django_db

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def candidate() -> Any:
    return UserFactory()


@pytest.fixture
def client(candidate: Any) -> APIClient:
    c = APIClient()
    c.force_login(candidate)
    return c


def start(client: APIClient, **over: Any) -> Any:
    body = {
        "purpose": "cv",
        "filename": "My CV.pdf",
        "mime": PDF_MIME,
        "size": len(PDF_BYTES),
        **over,
    }
    return client.post("/api/v1/documents/upload-sessions/", body, format="json")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\CV final.PDF", "CV final.pdf"),
        ("cv\x00<script>.pdf", "cv_script_.pdf"),
        ("  .pdf", "pdf"),
        ("résumé (2).docx", "résumé (2).docx"),
    ],
)
def test_filename_sanitisation(name: str, expected: str) -> None:
    assert services.sanitise_filename(name) == expected


def test_presign_flow_creates_pending_document(client: APIClient, candidate: Any, s3: Any) -> None:
    res = start(client)
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["method"] == "PUT" and "mhrs-uploads-quarantine" in body["url"]
    assert parse_qs(urlparse(body["url"]).query)["X-Amz-Expires"] == ["600"]
    session = UploadSession.objects.get(pk=body["id"])
    assert session.object_key.startswith(f"cv/{candidate.pk}/") and session.object_key.endswith(
        ".pdf"
    )
    assert "My CV" not in session.object_key  # storage keys never carry user-supplied names
    s3.put_object(Bucket="mhrs-uploads-quarantine", Key=session.object_key, Body=PDF_BYTES)
    done = client.post(f"/api/v1/documents/upload-sessions/{body['id']}/complete/")
    assert done.status_code == 201, done.content
    doc = Document.objects.get(pk=done.json()["id"])
    assert doc.scan_status == ScanStatus.PENDING and doc.bucket == "quarantine"
    assert doc.original_filename == "My CV.pdf" and doc.size_bytes == len(PDF_BYTES)
    assert OutboxEvent.objects.filter(
        event_type="document.uploaded", aggregate_id=str(doc.pk)
    ).exists()
    # Completing twice is idempotent.
    again = client.post(f"/api/v1/documents/upload-sessions/{body['id']}/complete/")
    assert again.json()["id"] == str(doc.pk)


def test_complete_without_object_is_409(client: APIClient, s3: Any) -> None:
    sid = start(client).json()["id"]
    res = client.post(f"/api/v1/documents/upload-sessions/{sid}/complete/")
    assert res.status_code == 409 and res.json()["error"]["code"] == "upload_missing"


def test_complete_rejects_oversized_actual_object(
    client: APIClient, s3: Any, settings: Any
) -> None:
    settings.DOCUMENT_MAX_BYTES = {"cv": 100}
    sid = start(client, size=50).json()["id"]
    key = UploadSession.objects.get(pk=sid).object_key
    s3.put_object(Bucket="mhrs-uploads-quarantine", Key=key, Body=b"x" * 500)
    res = client.post(f"/api/v1/documents/upload-sessions/{sid}/complete/")
    assert res.status_code == 413
    assert UploadSession.objects.get(pk=sid).status == "rejected"
    assert s3.list_objects_v2(Bucket="mhrs-uploads-quarantine").get("KeyCount") == 0


@pytest.mark.parametrize(
    ("over", "status", "code"),
    [
        (
            {"filename": "cv.doc", "mime": "application/msword"},
            415,
            "unsupported_media_type",
        ),  # EC-DOC-04
        (
            {"filename": "cv.odt", "mime": "application/vnd.oasis.opendocument.text"},
            415,
            "unsupported_media_type",
        ),
        ({"filename": "cv.exe", "mime": "application/octet-stream"}, 415, "unsupported_media_type"),
        (
            {"filename": "photo.png", "mime": "image/png"},
            415,
            "unsupported_media_type",
        ),  # not for CVs
        (
            {"filename": "cv.pdf", "mime": "image/png"},
            415,
            "unsupported_media_type",
        ),  # EC-DOC-05 declared
        ({"size": 11 * 1024 * 1024}, 413, "payload_too_large"),
        ({"size": 0}, 400, "validation_error"),
        ({"purpose": "logo"}, 400, "validation_error"),
    ],
)
def test_declared_validation(
    client: APIClient, s3: Any, over: dict[str, Any], status: int, code: str
) -> None:
    res = start(client, **over)
    assert res.status_code == status, res.content
    assert res.json()["error"]["code"] == code


def test_supporting_documents_accept_images(client: APIClient, s3: Any) -> None:
    assert (
        start(client, purpose="supporting", filename="cert.png", mime="image/png").status_code
        == 201
    )


def test_org_policy_narrows_limit(candidate: Any, org: Any, s3: Any) -> None:
    from apps.organisations.models import OrganisationPolicy

    OrganisationPolicy.objects.create(organisation=org, upload_limits_mb={"cv": 1})
    assert services.max_bytes("cv", org) == 1024 * 1024
    with pytest.raises(Exception) as exc:
        services.create_session(
            candidate,
            purpose="cv",
            filename="cv.pdf",
            mime=PDF_MIME,
            size=2 * 1024 * 1024,
            organisation=org,
        )
    assert getattr(exc.value, "status_code", None) == 413


def test_direct_upload_fallback(client: APIClient, s3: Any) -> None:
    upload = SimpleUploadedFile("Final CV.docx", b"PK\x03\x04docx", content_type=DOCX_MIME)
    res = client.post(
        "/api/v1/documents/direct-upload/", {"purpose": "cv", "file": upload}, format="multipart"
    )
    assert res.status_code == 201, res.content
    doc = Document.objects.get(pk=res.json()["id"])
    assert doc.scan_status == ScanStatus.PENDING
    stored = s3.get_object(Bucket="mhrs-uploads-quarantine", Key=doc.storage_key)["Body"].read()
    assert stored == b"PK\x03\x04docx"


def test_documents_are_private_to_owner(client: APIClient, candidate: Any, s3: Any) -> None:
    doc = Document.objects.create(
        owner_user=candidate,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key="cv/x.pdf",
        bucket="documents",
        scan_status=ScanStatus.CLEAN,
    )
    other = APIClient()
    other.force_login(UserFactory())
    assert other.get(f"/api/v1/documents/{doc.pk}/").status_code == 404
    assert other.get(f"/api/v1/documents/{doc.pk}/download/").status_code == 404
    assert client.get(f"/api/v1/documents/{doc.pk}/").json()["scan_status"] == "clean"
    res = client.get(f"/api/v1/documents/{doc.pk}/download/")
    assert res.status_code == 302 and res["Cache-Control"] == "no-store"
    qs = parse_qs(urlparse(res["Location"]).query)
    assert qs["X-Amz-Expires"] == ["60"]
    assert qs["response-content-disposition"] == ['attachment; filename="cv.pdf"']
    assert AccessLog.objects.filter(
        target_id=str(doc.pk), action="download", user=candidate
    ).exists()


def test_unscanned_documents_cannot_be_downloaded(
    client: APIClient, candidate: Any, s3: Any
) -> None:
    doc = Document.objects.create(
        owner_user=candidate,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key="k",
    )
    res = client.get(f"/api/v1/documents/{doc.pk}/download/")
    assert res.status_code == 409 and res.json()["error"]["code"] == "document_unavailable"


def test_anonymous_cannot_upload() -> None:
    assert APIClient().post(
        "/api/v1/documents/upload-sessions/", {}, format="json"
    ).status_code in (401, 403)
