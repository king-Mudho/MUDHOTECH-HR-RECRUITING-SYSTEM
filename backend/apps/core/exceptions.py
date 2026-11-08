"""Domain errors and the standard API error envelope (docs/04 §1).

Every API error is rendered as::

    {"error": {"code": str, "message": str, "details": dict, "request_id": str | None}}
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions as drf_exc
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from .context import get_request_id

logger = logging.getLogger("mhrs.errors")


class DomainError(Exception):
    """Raise from services; rendered by :func:`api_exception_handler`."""

    code: str = "domain_error"
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_message = "The request could not be completed."

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code or self.code
        self.message = message or self.default_message
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ConflictError(DomainError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    default_message = "The request conflicts with the current state of the resource."


class StaleVersionError(ConflictError):
    code = "conflict.stale_version"
    default_message = "This record was changed by someone else. Reload and try again."


class InvalidTransitionError(ConflictError):
    code = "conflict.invalid_transition"
    default_message = "This status change is not allowed from the current state."


class NotFoundError(DomainError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Not found."


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You do not have permission to perform this action."


class OrgSuspendedError(DomainError):
    code = "org_suspended"
    status_code = status.HTTP_423_LOCKED
    default_message = "This organisation is suspended."


class DeadlinePassedError(DomainError):
    code = "deadline_passed"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_message = "The deadline has passed."


# DRF exception class -> (code, default message)
_DRF_CODES: list[tuple[type[drf_exc.APIException], str, str]] = [
    (drf_exc.ValidationError, "validation_error", "Some fields are invalid."),
    (drf_exc.ParseError, "validation_error", "Malformed request body."),
    (drf_exc.NotAuthenticated, "not_authenticated", "Authentication is required."),
    (drf_exc.AuthenticationFailed, "not_authenticated", "Authentication failed."),
    (drf_exc.PermissionDenied, "permission_denied", "You do not have permission to do this."),
    (drf_exc.NotFound, "not_found", "Not found."),
    (drf_exc.MethodNotAllowed, "method_not_allowed", "Method not allowed."),
    (drf_exc.NotAcceptable, "not_acceptable", "Not acceptable."),
    (drf_exc.UnsupportedMediaType, "unsupported_media_type", "Unsupported media type."),
    (drf_exc.Throttled, "rate_limited", "Too many requests. Please slow down."),
]

_STATUS_CODES: dict[int, str] = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "unprocessable",
    423: "org_suspended",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def error_body(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


def _details_from_drf(detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        return {k: _details_from_drf(v) if isinstance(v, dict) else v for k, v in detail.items()}
    if isinstance(detail, list):
        return {"non_field_errors": detail}
    return {}


def _message_from_drf(exc: drf_exc.APIException, default: str) -> str:
    detail = exc.detail
    if isinstance(detail, str) and not isinstance(exc, drf_exc.ValidationError):
        return str(detail)
    if isinstance(detail, list) and len(detail) == 1 and isinstance(detail[0], str):
        return str(detail[0])
    return default


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF ``EXCEPTION_HANDLER``: map every error to the standard envelope."""
    if isinstance(exc, DomainError):
        return Response(error_body(exc.code, exc.message, exc.details), status=exc.status_code)

    if isinstance(exc, Http404):
        exc = drf_exc.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exc.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        detail: Any = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        exc = drf_exc.ValidationError(detail=detail)

    if isinstance(exc, drf_exc.APIException):
        response = drf_default_handler(exc, context)
        if response is None:  # pragma: no cover - defensive
            response = Response(status=exc.status_code)
        code = _STATUS_CODES.get(exc.status_code, "error")
        message = "The request could not be completed."
        for klass, klass_code, default_message in _DRF_CODES:
            if isinstance(exc, klass):
                code, message = klass_code, _message_from_drf(exc, default_message)
                break
        details: dict[str, Any] = {}
        if isinstance(exc, drf_exc.ValidationError):
            details = _details_from_drf(exc.detail)
        wait = getattr(exc, "wait", None)
        if isinstance(exc, drf_exc.Throttled) and wait is not None:
            details = {"retry_after_seconds": int(wait)}
        response.data = error_body(code, message, details)
        return response

    # Unhandled -> 500 with envelope (never leak internals).
    logger.exception("unhandled_api_exception", exc_info=exc)
    return Response(
        error_body("internal_error", "An unexpected error occurred. Please try again."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# Django-level handlers so non-DRF routes under /api also return the envelope.
def json_404(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def json_500(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        error_body("internal_error", "An unexpected error occurred. Please try again."),
        status=500,
    )


def json_403(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_body("permission_denied", "Permission denied."), status=403)


def json_400(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_body("validation_error", "Bad request."), status=400)


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    return JsonResponse(
        error_body("permission_denied", "CSRF verification failed.", {"reason": "csrf"}),
        status=403,
    )
