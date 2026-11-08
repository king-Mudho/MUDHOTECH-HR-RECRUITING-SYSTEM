"""Test-only models used to exercise core abstractions (installed only in test settings)."""

from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, TenantModel


class Widget(TenantModel):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class SecretNote(BaseModel):
    body = EncryptedTextField(null=True, blank=True)

    def __str__(self) -> str:
        return str(self.id)
