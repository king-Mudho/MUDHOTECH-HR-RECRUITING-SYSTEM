"""User model (email login) - docs/03 accounts.

* Email is normalised (trim + lower-case) and unique case-insensitively (EC-ACC-01).
* Roles are per organisation membership; only platform roles live on the user (SRS §2).
* Session metadata (IP, user agent, last seen, revoke) is stored by ``allauth.usersessions``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core import time
from apps.core.models import BaseModel

MFA_GRACE_PERIOD = timedelta(days=7)


def normalize_email_address(email: str) -> str:
    return email.strip().lower()


class PlatformRole(models.TextChoices):
    NONE = "none", "None"
    PLATFORM_ADMIN = "platform_admin", "Platform admin"
    PLATFORM_SUPPORT = "platform_support", "Platform support"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=normalize_email_address(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None) -> User:
        return self.get(email__iexact=normalize_email_address(username or ""))


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    preferred_name = models.CharField(max_length=150, blank=True, default="")
    phone_e164 = models.CharField(max_length=20, blank=True, default="")
    platform_role = models.CharField(
        max_length=32, choices=PlatformRole.choices, default=PlatformRole.NONE
    )
    locale = models.CharField(max_length=10, default="en")
    timezone = models.CharField(max_length=64, default="Africa/Harare")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Django admin access only.")
    date_joined = models.DateTimeField(auto_now_add=True)
    # Start of the 7-day MFA grace period once a privileged role is held (FR-M01-04).
    mfa_grace_started_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="Anonymisation marker.")

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ("email",)
        constraints = [models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci")]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email_address(self.email or "")
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        return self.preferred_name or self.full_name or self.email

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_platform_staff(self) -> bool:
        return self.platform_role in (PlatformRole.PLATFORM_ADMIN, PlatformRole.PLATFORM_SUPPORT)

    @property
    def mfa_grace_deadline(self) -> datetime | None:
        if self.mfa_grace_started_at is None:
            return None
        return self.mfa_grace_started_at + MFA_GRACE_PERIOD

    def start_mfa_grace(self) -> None:
        """Called when the user first gains a privileged role (idempotent)."""
        if self.mfa_grace_started_at is None:
            self.mfa_grace_started_at = time.now()
            self.save(update_fields=["mfa_grace_started_at", "updated_at"])
