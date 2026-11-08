"""Request-scoped middleware."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import request_id_var, tenant_guard_var

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


def generate_request_id() -> str:
    """Time-sortable id `req_<10 time chars><16 random chars>` (ULID-like)."""
    ms = int(time.time() * 1000)
    ts = ""
    for _ in range(10):
        ts = _ALPHABET[ms % 32] + ts
        ms //= 32
    rand = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return f"req_{ts}{rand}"


class RequestIDMiddleware:
    """Accept a well-formed inbound `X-Request-ID` (from Nginx/Next.js) or generate one.

    The id is stored in a contextvar (picked up by logging and the error envelope), set on the
    request object and echoed back in the response header. It also switches on the strict tenant
    guard for the duration of the request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if _VALID_ID.match(inbound) else generate_request_id()
        request.request_id = request_id  # type: ignore[attr-defined]
        rid_token = request_id_var.set(request_id)
        guard_token = tenant_guard_var.set(True)
        try:
            response = self.get_response(request)
        finally:
            tenant_guard_var.reset(guard_token)
            request_id_var.reset(rid_token)
        response[REQUEST_ID_HEADER] = request_id
        return response
