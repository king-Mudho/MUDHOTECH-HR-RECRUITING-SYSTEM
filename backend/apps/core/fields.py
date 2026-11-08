"""Custom model fields."""

from __future__ import annotations

from typing import Any

from django.db import models

from . import crypto


class EncryptedTextField(models.TextField):
    """Text column encrypted at rest with Fernet (MultiFernet, key-id prefixed).

    Not searchable or orderable in SQL by design. Lookups other than ``isnull`` are rejected.
    """

    description = "Encrypted text"

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if value is None:
            return None
        return crypto.encrypt(str(value))

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None:
            return None
        return crypto.decrypt(value)

    def get_lookup(self, lookup_name: str) -> Any:
        if lookup_name != "isnull":
            raise TypeError(f"EncryptedTextField does not support the '{lookup_name}' lookup.")
        return super().get_lookup(lookup_name)
