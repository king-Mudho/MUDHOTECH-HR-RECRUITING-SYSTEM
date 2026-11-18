"""P11-T08: field-encryption key rotation (rotate_field_keys) - docs/runbooks/rotate-keys.md."""

from __future__ import annotations

import io
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.core.management import CommandError, call_command
from django.db import connection

from apps.core import crypto
from apps.core.keyrotation import encrypted_fields, rotate_field
from tests.core_testapp.models import SecretNote

pytestmark = pytest.mark.django_db
K1 = f"k1:{Fernet.generate_key().decode()}"
K2 = f"k2:{Fernet.generate_key().decode()}"


def raw_body(note: SecretNote) -> str:
    with connection.cursor() as cur:
        cur.execute("SELECT body FROM core_testapp_secretnote WHERE id = %s", [note.pk])
        return str(cur.fetchone()[0])


def test_discovers_every_encrypted_column() -> None:
    labels = {f"{m._meta.label}.{f.name}" for m, f in encrypted_fields()}
    assert {"core_testapp.SecretNote.body", "resumes.ExtractedClaim.payload"} <= labels
    assert "screening.EvaluationEvidence.snippet" in labels


def test_rotation_moves_values_to_the_new_primary_key(settings: Any) -> None:
    settings.FIELD_ENCRYPTION_KEYS = K1
    notes = [SecretNote.objects.create(body=f"secret {i}") for i in range(7)]
    empty = SecretNote.objects.create(body=None)
    assert {crypto.key_id_of(raw_body(n)) for n in notes} == {"k1"}

    settings.FIELD_ENCRYPTION_KEYS = f"{K2},{K1}"  # new primary first, old still readable
    fresh = SecretNote.objects.create(body="written after the deploy")
    out = io.StringIO()
    call_command("rotate_field_keys", "--batch-size", "3", stdout=out)
    assert "core_testapp.SecretNote.body: scanned 8, on other keys 7, rotated 7" in out.getvalue()
    assert {crypto.key_id_of(raw_body(n)) for n in [*notes, fresh]} == {"k2"}

    settings.FIELD_ENCRYPTION_KEYS = K2  # the old key can now be removed
    assert [SecretNote.objects.get(pk=n.pk).body for n in notes] == [
        f"secret {i}" for i in range(7)
    ]
    assert SecretNote.objects.get(pk=empty.pk).body is None
    out = io.StringIO()
    call_command("rotate_field_keys", stdout=out)
    assert "done: 0 value(s) still on an old key" in out.getvalue()


def test_dry_run_changes_nothing(settings: Any) -> None:
    settings.FIELD_ENCRYPTION_KEYS = K1
    note = SecretNote.objects.create(body="x")
    before = raw_body(note)
    settings.FIELD_ENCRYPTION_KEYS = f"{K2},{K1}"
    out = io.StringIO()
    call_command("rotate_field_keys", "--dry-run", stdout=out)
    assert raw_body(note) == before
    assert "value(s) still on an old key" in out.getvalue() and "(dry run)" in out.getvalue()


def test_a_value_rewritten_meanwhile_is_not_overwritten(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.FIELD_ENCRYPTION_KEYS = K1
    note = SecretNote.objects.create(body="old text")
    settings.FIELD_ENCRYPTION_KEYS = f"{K2},{K1}"
    real_rotate = crypto.rotate

    def rotate_while_the_app_writes(ciphertext: str) -> str:
        SecretNote.objects.filter(pk=note.pk).update(body="new text from the app")
        return real_rotate(ciphertext)

    monkeypatch.setattr(crypto, "rotate", rotate_while_the_app_writes)
    report = rotate_field(SecretNote, SecretNote._meta.get_field("body"))  # type: ignore[arg-type]
    assert (report.stale, report.rotated, report.raced) == (1, 0, 1)
    assert SecretNote.objects.get(pk=note.pk).body == "new text from the app"


def test_fails_clearly_when_the_old_key_was_removed_too_early(settings: Any) -> None:
    settings.FIELD_ENCRYPTION_KEYS = K1
    SecretNote.objects.create(body="x")
    settings.FIELD_ENCRYPTION_KEYS = K2
    with pytest.raises(CommandError, match="old key still in FIELD_ENCRYPTION_KEYS"):
        call_command("rotate_field_keys", stdout=io.StringIO())
