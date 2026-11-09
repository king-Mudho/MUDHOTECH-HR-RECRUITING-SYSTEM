"""Block privileged users without MFA from staff APIs once their grace period ends (FR-M01-04)."""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.exceptions import error_body

DEFAULT_STAFF_PREFIXES = (
    "/api/v1/hr/",
    "/api/v1/organisations/",
    "/api/v1/platform/",
)


class MfaEnforcementMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.prefixes: tuple[str, ...] = tuple(
            getattr(settings, "MFA_ENFORCED_PATH_PREFIXES", DEFAULT_STAFF_PREFIXES)
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and request.path.startswith(self.prefixes)
            and not self._exempt(request)
        ):
            from .mfa import mfa_status

            if mfa_status(user).enforced:
                return JsonResponse(
                    error_body(
                        "mfa_required",
                        "Two-factor authentication is required for your role. "
                        "Set it up in account settings to continue.",
                        {"setup_url": f"{settings.FRONTEND_URL}/account/security"},
                    ),
                    status=401,
                )
        return self.get_response(request)

    @staticmethod
    def _exempt(request: HttpRequest) -> bool:
        # Creating a first organisation must not be blocked (the creator becomes org_admin).
        return request.method == "POST" and request.path.rstrip("/") == "/api/v1/organisations"
