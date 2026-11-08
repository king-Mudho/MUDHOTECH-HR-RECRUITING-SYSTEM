from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from moto import mock_aws

from apps.core import crypto, storage
from tests.core_testapp.models import SecretNote


# ---------------------------------------------------------------- storage
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


def test_bucket_for_unknown_purpose() -> None:
    with pytest.raises(ValueError):
        storage.bucket_for("nope")  # type: ignore[arg-type]


def test_presign_put_and_get(s3: Any) -> None:
    put = storage.presign_put("quarantine", "u/1/cv.pdf", "application/pdf")
    assert put["method"] == "PUT" and put["expires_in"] == 600
    assert put["headers"] == {"Content-Type": "application/pdf"}
    assert "mhrs-uploads-quarantine" in put["url"]
    url = storage.presign_get("documents", "d/1.pdf", filename='my "cv".pdf')
    qs = parse_qs(urlparse(url).query)
    assert qs["X-Amz-Expires"] == ["60"]
    assert qs["response-content-disposition"] == ['attachment; filename="my cv.pdf"']
    inline = storage.presign_get("documents", "d/1.pdf", filename="cv.pdf", inline=True)
    assert "inline" in parse_qs(urlparse(inline).query)["response-content-disposition"][0]


def test_head_put_get_move_delete(s3: Any) -> None:
    assert storage.head_object("quarantine", "k1") is None
    storage.put_bytes("quarantine", "k1", b"%PDF-1.7 hello", "application/pdf")
    info = storage.head_object("quarantine", "k1")
    assert info is not None and info.size == 14 and info.content_type == "application/pdf"
    assert storage.get_bytes("quarantine", "k1", max_bytes=4) == b"%PDF"
    dst = storage.move_object("quarantine", "k1", "documents", "clean/k1")
    assert dst == "clean/k1"
    assert storage.head_object("quarantine", "k1") is None
    assert storage.get_bytes("documents", "clean/k1") == b"%PDF-1.7 hello"
    storage.delete_object("documents", "clean/k1")
    assert storage.head_object("documents", "clean/k1") is None
    storage.check_bucket("documents")


def test_head_object_reraises_other_errors(s3: Any) -> None:
    from botocore.exceptions import ClientError

    s3.delete_bucket(Bucket="mhrs-exports")
    with pytest.raises(ClientError):
        storage.head_object("exports", "x")


def test_presign_uses_public_endpoint(settings: Any, s3: Any) -> None:
    settings.S3_PUBLIC_ENDPOINT_URL = "http://localhost:9000"
    storage.reset_clients()
    assert storage.presign_get("documents", "a").startswith("http://localhost:9000/")


# ---------------------------------------------------------------- encryption
def test_encrypt_decrypt_roundtrip_with_key_id() -> None:
    token = crypto.encrypt("Tendai's CV text ✓")
    assert token.startswith("k2$")
    assert crypto.decrypt(token) == "Tendai's CV text ✓"
    assert not crypto.needs_rotation(token)


def test_old_key_still_decrypts_and_rotates(settings: Any) -> None:
    old = settings.FIELD_ENCRYPTION_KEYS.split(",")[1]  # k1
    settings.FIELD_ENCRYPTION_KEYS = old
    legacy = crypto.encrypt("legacy secret")
    assert legacy.startswith("k1$")

    new_key = f"k3:{Fernet.generate_key().decode()}"
    settings.FIELD_ENCRYPTION_KEYS = f"{new_key},{old}"
    assert crypto.decrypt(legacy) == "legacy secret"
    assert crypto.needs_rotation(legacy)
    rotated = crypto.rotate(legacy)
    assert rotated.startswith("k3$") and crypto.decrypt(rotated) == "legacy secret"
    assert crypto.rotate(rotated) == rotated


def test_unknown_key_id_falls_back_to_multifernet(settings: Any) -> None:
    token = crypto.encrypt("x")
    renamed = "kX$" + token.split("$", 1)[1]
    assert crypto.decrypt(renamed) == "x"


def test_tampered_or_malformed_ciphertext_raises() -> None:
    token = crypto.encrypt("x")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token[:-4] + "AAAA")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt("no-separator")


def test_removed_key_cannot_decrypt(settings: Any) -> None:
    token = crypto.encrypt("x")
    settings.FIELD_ENCRYPTION_KEYS = f"k9:{Fernet.generate_key().decode()}"
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "nokeyid",
        "k1:not-a-key",
        "k1:" + Fernet.generate_key().decode() + ",k1:" + Fernet.generate_key().decode(),
    ],
)
def test_bad_key_config(raw: str) -> None:
    with pytest.raises(ImproperlyConfigured):
        crypto.parse_keys(raw)


def test_generate_key_format() -> None:
    k = crypto.generate_key("k7")
    assert crypto.parse_keys(k).primary_id == "k7"


@pytest.mark.django_db
def test_encrypted_field_stores_ciphertext() -> None:
    note = SecretNote.objects.create(body="Candidate phone +263 77 123 4567")
    with connection.cursor() as cur:
        cur.execute("SELECT body FROM core_testapp_secretnote WHERE id = %s", [note.pk])
        raw = cur.fetchone()[0]
    assert raw.startswith("k2$") and "263" not in raw
    assert SecretNote.objects.get(pk=note.pk).body == "Candidate phone +263 77 123 4567"
    empty = SecretNote.objects.create(body=None)
    assert SecretNote.objects.get(pk=empty.pk).body is None
    assert SecretNote.objects.filter(body__isnull=True).count() == 1


@pytest.mark.django_db
def test_encrypted_field_rejects_content_lookups() -> None:
    with pytest.raises(TypeError):
        SecretNote.objects.filter(body="x").count()
