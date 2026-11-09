"""Organisation context resolution (docs/02 §5.4, FR-M02-05, EC-ORG-06, EC-ORG-07)."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.exceptions import error_body

from .selectors import active_membership

ORG_HEADER = "X-Org-Id"
SESSION_KEY = "active_org_id"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Staff APIs whose organisation comes from this middleware (path-scoped org APIs validate the
# path id themselves via HasOrgRole).
CONTEXT_WRITE_GUARDED_PREFIXES = ("/api/v1/hr/",)


class OrganisationContextMiddleware:
    """Sets ``request.organisation`` and ``request.membership``.

    Resolution: ``X-Org-Id`` header (must match an active membership) -> session active org.
    Never from the request body. A header naming an organisation the user does not belong to is
    answered with 404 (no existence leak) and audited as ``tenant_violation_attempt``.
    Suspended/closed organisations are read-only for staff: unsafe requests on context-scoped staff
    APIs get 423 ``org_suspended``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.organisation = None  # type: ignore[attr-defined]
        request.membership = None  # type: ignore[attr-defined]
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            header = request.headers.get(ORG_HEADER)
            if header:
                membership = active_membership(user, header)
                if membership is None:
                    return self._violation(request, header)
            else:
                membership = self._from_session(request)
            if membership is not None:
                request.organisation = membership.organisation  # type: ignore[attr-defined]
                request.membership = membership  # type: ignore[attr-defined]
                if (
                    membership.organisation.is_read_only
                    and request.method not in SAFE_METHODS
                    and request.path.startswith(CONTEXT_WRITE_GUARDED_PREFIXES)
                ):
                    return JsonResponse(
                        error_body(
                            "org_suspended",
                            "This organisation is suspended. Recruitment data is read-only.",
                        ),
                        status=423,
                    )
        return self.get_response(request)

    @staticmethod
    def _from_session(request: HttpRequest):  # type: ignore[no-untyped-def]
        session = getattr(request, "session", None)
        if session is None or SESSION_KEY not in session:
            return None
        membership = active_membership(request.user, session.get(SESSION_KEY))  # type: ignore[arg-type]
        if membership is None:
            session.pop(SESSION_KEY, None)  # stale (left org / deactivated)
        return membership

    @staticmethod
    def _violation(request: HttpRequest, header: str) -> JsonResponse:
        from apps.audit import services as audit

        audit.record(
            actor=request.user,
            action="tenant_violation_attempt",
            target=("organisations.organisation", header[:64]),
            organisation=None,
            after={"path": request.path, "method": request.method},
            request=request,
        )
        return JsonResponse(error_body("not_found", "Not found."), status=404)
