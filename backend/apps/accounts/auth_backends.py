from __future__ import annotations

from typing import Any

from allauth.account.auth_backends import AuthenticationBackend
from django.http import HttpRequest

from . import lockout


class LockoutAwareAuthenticationBackend(AuthenticationBackend):
    """allauth backend that also refuses locked accounts for non-allauth logins (Django admin)."""

    def authenticate(self, request: HttpRequest | None, **credentials: Any) -> Any:
        identifier = credentials.get("email") or credentials.get("username") or ""
        if identifier and lockout.is_locked(identifier):
            return None
        return super().authenticate(request, **credentials)
