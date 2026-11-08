"""Application-level field encryption (ADR-011).

``FIELD_ENCRYPTION_KEYS="k2:<fernet>,k1:<fernet>"`` - the first key encrypts; every listed key can
decrypt. Ciphertext is stored as ``"<key_id>$<fernet token>"`` so rotation is observable and a
re-encrypt job (``rotate``) can find rows still on an old key.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SEPARATOR = "$"


class DecryptionError(ValueError):
    pass


@dataclass(frozen=True)
class Keyring:
    primary_id: str
    keys: dict[str, Fernet]
    multi: MultiFernet


def parse_keys(raw: str) -> Keyring:
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    if not entries:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is empty.")
    keys: dict[str, Fernet] = {}
    order: list[str] = []
    for entry in entries:
        key_id, sep, key = entry.partition(":")
        if not sep or not key_id or not key:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS entries must look like 'k1:<key>'.")
        if key_id in keys:
            raise ImproperlyConfigured(f"Duplicate field encryption key id: {key_id}")
        try:
            keys[key_id] = Fernet(key.encode())
        except ValueError as exc:
            raise ImproperlyConfigured(f"Invalid Fernet key for id {key_id}.") from exc
        order.append(key_id)
    return Keyring(primary_id=order[0], keys=keys, multi=MultiFernet([keys[k] for k in order]))


@functools.cache
def _keyring_for(raw: str) -> Keyring:
    return parse_keys(raw)


def keyring() -> Keyring:
    return _keyring_for(settings.FIELD_ENCRYPTION_KEYS)


def encrypt(plaintext: str) -> str:
    ring = keyring()
    token = ring.keys[ring.primary_id].encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{ring.primary_id}{SEPARATOR}{token}"


def key_id_of(ciphertext: str) -> str | None:
    key_id, sep, _ = ciphertext.partition(SEPARATOR)
    return key_id if sep else None


def decrypt(ciphertext: str) -> str:
    ring = keyring()
    key_id, sep, token = ciphertext.partition(SEPARATOR)
    if not sep:
        raise DecryptionError("Value is not in '<key_id>$<token>' format.")
    try:
        if key_id in ring.keys:
            return ring.keys[key_id].decrypt(token.encode()).decode("utf-8")
        return ring.multi.decrypt(token.encode()).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(f"Unable to decrypt value encrypted with key '{key_id}'.") from exc


def needs_rotation(ciphertext: str) -> bool:
    return key_id_of(ciphertext) != keyring().primary_id


def rotate(ciphertext: str) -> str:
    """Re-encrypt with the current primary key (no-op if already on it)."""
    if not needs_rotation(ciphertext):
        return ciphertext
    return encrypt(decrypt(ciphertext))


def generate_key(key_id: str) -> str:
    """Helper for ops: ``python -c 'from apps.core.crypto import generate_key; ...'``."""
    return f"{key_id}:{Fernet.generate_key().decode()}"
