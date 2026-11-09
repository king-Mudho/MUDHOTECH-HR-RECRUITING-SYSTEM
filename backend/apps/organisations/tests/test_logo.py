"""Organisation logo direct upload - P02-T13 (docs/06 §3 image re-encoding)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from moto import mock_aws
from PIL import Image
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.core import storage
from apps.organisations.logo import InvalidLogoError, process_logo
from apps.organisations.models import Organisation
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def s3(settings: Any) -> Iterator[Any]:
    settings.S3_ENDPOINT_URL = None
    settings.S3_PUBLIC_ENDPOINT_URL = None
    with mock_aws():
        storage.reset_clients()
        raw = boto3.client("s3", region_name="us-east-1")
        for bucket in settings.S3_BUCKETS.values():
            raw.create_bucket(Bucket=bucket)
        yield raw
    storage.reset_clients()


def image_bytes(
    fmt: str = "JPEG", size: tuple[int, int] = (1200, 800), exif: bool = False
) -> bytes:
    img = Image.new("RGB", size, (31, 78, 148))
    out = io.BytesIO()
    kwargs: dict[str, Any] = {}
    if exif:
        ex = Image.Exif()
        ex[0x010E] = "secret GPS-ish metadata"  # ImageDescription
        kwargs["exif"] = ex.tobytes()
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


def test_process_logo_reencodes_resizes_and_strips_metadata() -> None:
    png = process_logo(image_bytes(exif=True))
    with Image.open(io.BytesIO(png)) as img:
        assert img.format == "PNG"
        assert max(img.size) == 512
        assert not img.getexif()
    assert b"secret GPS-ish" not in png


@pytest.mark.parametrize(
    "raw",
    [b"not an image at all", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"%PDF-1.7"],
)
def test_process_logo_rejects_non_images(raw: bytes) -> None:
    with pytest.raises(InvalidLogoError):
        process_logo(raw)


def test_process_logo_rejects_disallowed_format_and_size() -> None:
    with pytest.raises(InvalidLogoError):
        process_logo(image_bytes("GIF", (10, 10)))
    with pytest.raises(InvalidLogoError):
        process_logo(b"x" * (2 * 1024 * 1024 + 1))


def test_upload_endpoint_stores_png_and_returns_url(s3: Any) -> None:
    team = make_org_with_team()
    client = APIClient()
    client.force_login(team.admin)
    upload = SimpleUploadedFile("logo.jpg", image_bytes(), content_type="image/jpeg")
    resp = client.post(
        f"/api/v1/organisations/{team.org.pk}/logo/", {"logo": upload}, format="multipart"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["logo_url"] and "X-Amz-Signature" in body["logo_url"]
    org = Organisation.objects.get(pk=team.org.pk)
    assert org.logo_key.startswith(f"logos/{org.pk}/") and org.logo_key.endswith(".png")
    assert storage.head_object("public", org.logo_key).content_type == "image/png"  # type: ignore[union-attr]
    assert AuditEvent.objects.filter(action="organisation.logo_updated").exists()
    public = APIClient().get(f"/api/v1/companies/{org.slug}/").json()
    assert public["logo_url"]


def test_upload_permissions_and_validation(s3: Any) -> None:
    team, other = make_org_with_team(), make_org_with_team()
    url = f"/api/v1/organisations/{team.org.pk}/logo/"
    hr = APIClient()
    hr.force_login(team.hr_manager)
    assert (
        hr.post(
            url, {"logo": SimpleUploadedFile("l.png", image_bytes("PNG"))}, format="multipart"
        ).status_code
        == 403
    )
    outsider = APIClient()
    outsider.force_login(other.admin)
    assert (
        outsider.post(
            url, {"logo": SimpleUploadedFile("l.png", image_bytes("PNG"))}, format="multipart"
        ).status_code
        == 404
    )
    admin = APIClient()
    admin.force_login(team.admin)
    bad = admin.post(url, {"logo": SimpleUploadedFile("l.png", b"nope")}, format="multipart")
    assert bad.status_code == 400 and "logo" in bad.json()["error"]["details"]
    assert admin.post(url, {}, format="multipart").status_code == 400
