"""MFA policy (FR-M01-04, docs/06 §2).

TOTP + recovery codes are provided by ``allauth.mfa``. This module decides *who must* use MFA:
platform roles always; organisation roles ``org_admin`` / ``hr_manager`` (registered by the
organisations app as a privilege provider). Privileged users get a 7-day grace period (with a banner
driven by ``/me``) and are then blocked from staff APIs with ``mfa_required`` until they enrol.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from allauth.mfa.models import Authenticator
from django.db import transaction

from apps.core import time

from .models import User

PrivilegeProvider = Callable[[User], bool]
_PROVIDERS: list[PrivilegeProvider] = []


def register_privilege_provider(fn: PrivilegeProvider) -> PrivilegeProvider:
    """Other apps declare 'this user holds a role that requires MFA'."""
    if fn not in _PROVIDERS:
        _PROVIDERS.append(fn)
    return fn


@register_privilege_provider
def _platform_role(user: User) -> bool:
    return user.is_platform_staff


def is_privileged(user: User) -> bool:
    return any(provider(user) for provider in _PROVIDERS)


def has_mfa(user: User) -> bool:
    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


@dataclass(frozen=True)
class MfaStatus:
    required: bool
    enabled: bool
    grace_deadline: datetime | None

    @property
    def enforced(self) -> bool:
        """True when the user must be blocked from staff APIs right now."""
        if not self.required or self.enabled:
            return False
        return self.grace_deadline is None or self.grace_deadline <= time.now()

    @property
    def in_grace(self) -> bool:
        return self.required and not self.enabled and not self.enforced

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "enabled": self.enabled,
            "grace_deadline": self.grace_deadline,
            "in_grace": self.in_grace,
            "enforced": self.enforced,
        }


def mfa_status(user: User) -> MfaStatus:
    required = is_privileged(user)
    if required and user.mfa_grace_started_at is None:
        user.start_mfa_grace()
    return MfaStatus(
        required=required,
        enabled=has_mfa(user),
        grace_deadline=user.mfa_grace_deadline if required else None,
    )


def reset_mfa(user: User, *, actor: User, reason: str) -> int:
    """EC-ACC-08 lost device: remove all authenticators after an identity check (audited).

    The caller (org_admin/platform endpoint) is responsible for the identity check and permission.
    The user restarts the grace period so they can re-enrol.
    """
    from apps.audit import services as audit

    with transaction.atomic():
        deleted, _ = Authenticator.objects.filter(user=user).delete()
        user.mfa_grace_started_at = time.now()
        user.save(update_fields=["mfa_grace_started_at", "updated_at"])
        audit.record(
            actor=actor,
            action="user.mfa_reset",
            target=user,
            reason=reason,
            after={"authenticators_removed": deleted},
        )
    return deleted
