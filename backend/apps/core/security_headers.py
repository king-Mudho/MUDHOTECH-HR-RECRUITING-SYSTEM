"""Security headers on every Django response (P09-T08, docs/06 §1).

The API serves JSON (and a few files): nothing on it should ever be rendered as a page, framed
or allowed to load resources, so the CSP is ``default-src 'none'``. Django's own middleware
already sets nosniff, X-Frame-Options, Referrer-Policy and (in production) HSTS.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=()"
ADMIN_PREFIX = "/django-admin/"


class SecurityHeadersMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not request.path.startswith(ADMIN_PREFIX):  # the admin needs its own scripts/styles
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # personal data must never be stored by browsers or shared caches (ASVS 8.1.1)
            response.headers["Cache-Control"] = "no-store"
        return response
