"""Organisation logo upload (FR-M02-01) - simple direct upload until the Phase 04 uploader.

Images are verified and re-encoded with Pillow (strips EXIF/metadata, defeats polyglots - docs/06
§3), resized to fit 512x512 and stored as PNG under a random key in the private ``public`` bucket.
Browsers get short-lived presigned URLs only.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from apps.audit import services as audit
from apps.core import storage
from apps.core.exceptions import DomainError

from .models import Organisation

logger = logging.getLogger("mhrs.organisations.logo")

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 25_000_000  # decompression-bomb guard
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_SIDE = 512
URL_TTL_SECONDS = 3600


class InvalidLogoError(DomainError):
    code = "validation_error"
    status_code = 400
    default_message = "Upload a PNG, JPEG or WebP image up to 2 MB."


def process_logo(raw: bytes) -> bytes:
    if len(raw) > MAX_BYTES:
        raise InvalidLogoError(details={"logo": ["The image must be 2 MB or smaller."]})
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise InvalidLogoError(details={"logo": ["Only PNG, JPEG or WebP images are allowed."]})
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise InvalidLogoError(details={"logo": ["The image dimensions are too large."]})
            canvas = source.convert("RGBA")
            canvas.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            canvas.save(out, format="PNG", optimize=True)  # fresh file: no metadata carried over
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise InvalidLogoError(details={"logo": ["This file is not a valid image."]}) from exc
    return out.getvalue()


@transaction.atomic
def set_logo(*, org: Organisation, actor: Any, upload: UploadedFile, request: Any = None) -> str:
    png = process_logo(upload.read(MAX_BYTES + 1))
    key = f"logos/{org.pk}/{uuid.uuid4()}.png"
    storage.put_bytes("public", key, png, "image/png")
    previous = org.logo_key
    org = Organisation.objects.select_for_update().get(pk=org.pk)
    org.logo_key = key
    org.save(update_fields=["logo_key", "updated_at"])
    audit.record(
        actor=actor,
        action="organisation.logo_updated",
        target=org,
        before={"logo_key": previous},
        after={"logo_key": key},
        request=request,
    )
    if previous:
        transaction.on_commit(lambda: _delete_quietly(previous))
    return key


def _delete_quietly(key: str) -> None:
    try:
        storage.delete_object("public", key)
    except Exception:  # pragma: no cover - the orphan cleanup job (Phase 04) retries later
        logger.warning("logo_cleanup_failed", extra={"key": key})


def logo_url(org: Organisation) -> str | None:
    if not org.logo_key:
        return None
    try:
        return storage.presign_get(
            "public", org.logo_key, ttl=URL_TTL_SECONDS, inline=True, filename="logo.png"
        )
    except Exception:  # storage misconfigured/unavailable: degrade gracefully
        return None
