"""Idempotency keys for unsafe, consequential endpoints (docs/04 §1).

Usage on a DRF view / viewset action::

    @idempotent(endpoint="applications.submit")
    def post(self, request, *args, **kwargs): ...

Semantics:
* ``Idempotency-Key`` header (UUID) is required -> 400 ``validation_error`` when missing/invalid.
* Same key + same body -> the stored response is replayed (``Idempotent-Replayed: true``).
* Same key + different body -> 422 ``idempotency_key_reuse``.
* The view runs in the same transaction as the key row: if the view raises, nothing is stored and
  the client may retry; concurrent duplicates serialise on the unique index and then replay.
* Only successful (2xx) responses are stored; keys live 24 h.
"""

from __future__ import annotations

import functools
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.request import Request
from rest_framework.response import Response

from . import time
from .exceptions import DomainError
from .models import IdempotencyKey

HEADER = "Idempotency-Key"
TTL = timedelta(hours=24)


class IdempotencyKeyReuseError(DomainError):
    code = "idempotency_key_reuse"
    status_code = 422
    default_message = "This Idempotency-Key was already used with a different request body."


class IdempotencyKeyMissingError(DomainError):
    code = "validation_error"
    status_code = 400
    default_message = "A valid Idempotency-Key header (UUID) is required for this request."


def request_fingerprint(request: Request) -> str:
    try:
        body: Any = request.data
    except Exception:  # pragma: no cover - unparsable body is rejected by DRF earlier
        body = None
    if hasattr(body, "dict"):
        body = body.dict()
    canonical = json.dumps(
        {"method": request.method, "path": request.path, "body": body},
        sort_keys=True,
        cls=DjangoJSONEncoder,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _parse_key(request: Request) -> str:
    raw = request.headers.get(HEADER, "").strip()
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise IdempotencyKeyMissingError(details={HEADER: ["Must be a UUID."]}) from exc


def _replay(record: IdempotencyKey) -> Response:
    response = Response(record.response_body, status=record.response_status)
    response["Idempotent-Replayed"] = "true"
    return response


def idempotent(endpoint: str) -> Callable[[Callable[..., Response]], Callable[..., Response]]:
    def decorator(view_method: Callable[..., Response]) -> Callable[..., Response]:
        @functools.wraps(view_method)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
            key = _parse_key(request)
            fingerprint = request_fingerprint(request)
            user = request.user if request.user and request.user.is_authenticated else None
            now = time.now()

            with transaction.atomic():
                # Drop an expired record so the key can be reused after the TTL.
                IdempotencyKey.objects.filter(
                    user=user, key=key, endpoint=endpoint, expires_at__lte=now
                ).delete()
                record, created = IdempotencyKey.objects.select_for_update().get_or_create(
                    user=user,
                    key=key,
                    endpoint=endpoint,
                    defaults={"request_hash": fingerprint, "expires_at": now + TTL},
                )
                if not created:
                    if record.request_hash != fingerprint:
                        raise IdempotencyKeyReuseError()
                    if record.response_status is not None:
                        return _replay(record)

                response = view_method(self, request, *args, **kwargs)
                if 200 <= response.status_code < 300:
                    record.response_status = response.status_code
                    record.response_body = json.loads(
                        json.dumps(response.data, cls=DjangoJSONEncoder)
                    )
                    record.save(update_fields=["response_status", "response_body", "updated_at"])
                else:
                    record.delete()
                return response

        return wrapper

    return decorator
