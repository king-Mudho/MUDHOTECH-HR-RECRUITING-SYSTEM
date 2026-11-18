"""Re-encrypt every ``EncryptedTextField`` value with the current primary key (ADR-011, P11-T08).

Rotation procedure (docs/runbooks/rotate-keys.md): prepend a new key to ``FIELD_ENCRYPTION_KEYS``
(``k2:<new>,k1:<old>``) and deploy - new writes use ``k2`` at once and old values stay readable -
then run ``manage.py rotate_field_keys`` until it reports nothing left; only then remove ``k1``.

Values are read as raw ciphertext (no decryption on the way out), only rows still on another key are
touched, and each update is conditional on the ciphertext being unchanged since it was read, so a
value the application rewrote meanwhile (already on the new key) is never overwritten.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from django.apps import apps
from django.db import models, transaction
from django.db.models.functions import Cast

from . import crypto
from .fields import EncryptedTextField


@dataclass
class FieldReport:
    label: str
    scanned: int = 0
    stale: int = 0
    rotated: int = 0
    raced: int = 0  # changed by the application between read and write (already re-encrypted)
    key_ids: dict[str, int] = field(default_factory=dict)


def encrypted_fields() -> Iterator[tuple[type[models.Model], EncryptedTextField]]:
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        for f in model._meta.concrete_fields:
            if isinstance(f, EncryptedTextField):
                yield model, f


def rotate_field(
    model: type[models.Model],
    f: EncryptedTextField,
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> FieldReport:
    report = FieldReport(label=f"{model._meta.label}.{f.name}")
    primary = crypto.keyring().primary_id
    raw = Cast(f.attname, output_field=models.TextField())  # ciphertext, not decrypted
    base = model._base_manager.exclude(**{f"{f.attname}__isnull": True}).annotate(mhrs_raw=raw)
    last_pk = None
    while True:
        page = base.order_by("pk")
        if last_pk is not None:
            page = page.filter(pk__gt=last_pk)
        rows = list(page.values_list("pk", "mhrs_raw")[:batch_size])
        if not rows:
            return report
        last_pk = rows[-1][0]
        for pk, ciphertext in rows:
            report.scanned += 1
            key_id = crypto.key_id_of(ciphertext) or "?"
            report.key_ids[key_id] = report.key_ids.get(key_id, 0) + 1
            if key_id == primary:
                continue
            report.stale += 1
            new = crypto.rotate(ciphertext)  # DecryptionError if no configured key can read it
            if dry_run:
                continue
            with transaction.atomic():
                updated = (
                    model._base_manager.annotate(mhrs_raw=raw)
                    .filter(pk=pk, mhrs_raw=ciphertext)
                    .update(**{f.attname: models.Value(new, output_field=models.TextField())})
                )
            if updated:
                report.rotated += 1
            else:
                report.raced += 1


def rotate_all(*, dry_run: bool = False, batch_size: int = 500) -> list[FieldReport]:
    return [
        rotate_field(m, f, dry_run=dry_run, batch_size=batch_size) for m, f in encrypted_fields()
    ]
