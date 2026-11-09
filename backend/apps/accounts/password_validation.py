"""Offline breached-password check (FR-M01-06, docs/06 §2).

The bundled list stores SHA-1 hex digests (one per line, gzipped) so plaintext passwords are not
shipped. The default list is generated from Django's common-password corpus (~20k entries) by
``python manage.py build_breached_passwords``; operators can point ``BREACHED_PASSWORDS_FILE`` at a
larger list (e.g. top-100k) built with the same command from a vetted source.
"""

from __future__ import annotations

import functools
import gzip
import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

DEFAULT_FILE = Path(__file__).resolve().parent / "data" / "breached_passwords.sha1.gz"


def sha1_hex(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest()


@functools.cache
def _load(path: str) -> frozenset[str]:
    with gzip.open(path, "rt", encoding="ascii") as fh:
        return frozenset(line.strip() for line in fh if line.strip())


class BreachedPasswordValidator:
    """Reject passwords that appear in the breached/common password list (case-insensitive)."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path

    def _hashes(self) -> frozenset[str]:
        path = self.path or getattr(settings, "BREACHED_PASSWORDS_FILE", None) or DEFAULT_FILE
        return _load(str(path))

    def validate(self, password: str, user: Any = None) -> None:
        hashes = self._hashes()
        if sha1_hex(password) in hashes or sha1_hex(password.lower()) in hashes:
            raise ValidationError(
                _("This password has appeared in a data breach. Please choose a different one."),
                code="password_breached",
            )

    def get_help_text(self) -> str:
        return _("Your password must not be a commonly used or previously breached password.")
