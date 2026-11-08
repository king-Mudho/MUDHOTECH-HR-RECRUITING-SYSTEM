from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.core import time
from apps.core.exceptions import DomainError
from apps.core.idempotency import idempotent
from apps.core.models import IdempotencyKey
from tests.core_testapp.models import Widget

pytestmark = pytest.mark.django_db


class SubmitView(APIView):
    permission_classes = [AllowAny]
    calls = 0

    @idempotent(endpoint="widgets.submit")
    def post(self, request: Request) -> Response:
        SubmitView.calls += 1
        if request.data.get("fail") == "domain":
            raise DomainError("deadline_passed", "Too late.", 422)
        if request.data.get("fail") == "status":
            return Response({"error": "x"}, status=409)
        w = Widget.objects.create(organisation_id=request.data["org"], name=request.data["name"])
        return Response({"id": str(w.pk), "name": w.name}, status=201)


@pytest.fixture(autouse=True)
def _reset() -> None:
    SubmitView.calls = 0


def call(body: dict[str, Any], key: str | None, user: Any = None) -> Response:
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    req = APIRequestFactory().post("/submit/", body, format="json", **headers)
    if user is not None:
        force_authenticate(req, user=user)
    return SubmitView.as_view()(req)  # type: ignore[no-any-return]


def test_same_key_same_body_replays(org: Any, user: Any) -> None:
    key = str(uuid.uuid4())
    body = {"org": str(org.pk), "name": "a"}
    r1 = call(body, key, user)
    r2 = call(body, key, user)
    assert r1.status_code == r2.status_code == 201
    assert r1.data == r2.data
    assert r2["Idempotent-Replayed"] == "true"
    assert SubmitView.calls == 1
    assert Widget.objects.for_org(org).count() == 1


def test_same_key_different_body_is_422(org: Any, user: Any) -> None:
    key = str(uuid.uuid4())
    call({"org": str(org.pk), "name": "a"}, key, user)
    r = call({"org": str(org.pk), "name": "b"}, key, user)
    assert r.status_code == 422
    assert r.data["error"]["code"] == "idempotency_key_reuse"
    assert Widget.objects.for_org(org).count() == 1


@pytest.mark.parametrize("bad", [None, "", "not-a-uuid"])
def test_missing_or_invalid_key_is_400(org: Any, bad: str | None) -> None:
    r = call({"org": str(org.pk), "name": "a"}, bad)
    assert r.status_code == 400
    assert r.data["error"]["code"] == "validation_error"
    assert "Idempotency-Key" in r.data["error"]["details"]
    assert SubmitView.calls == 0


def test_keys_are_per_user(org: Any, user: Any) -> None:
    from apps.accounts.models import User

    other = User.objects.create_user(email="other@example.test", password="x" * 12)
    key = str(uuid.uuid4())
    body = {"org": str(org.pk), "name": "a"}
    call(body, key, user)
    r = call(body, key, other)
    assert "Idempotent-Replayed" not in r
    assert SubmitView.calls == 2


def test_anonymous_keys_work(org: Any) -> None:
    key = str(uuid.uuid4())
    body = {"org": str(org.pk), "name": "a"}
    call(body, key)
    assert call(body, key)["Idempotent-Replayed"] == "true"


def test_raised_error_is_not_stored_and_retry_allowed(org: Any, user: Any) -> None:
    key = str(uuid.uuid4())
    r = call({"org": str(org.pk), "name": "a", "fail": "domain"}, key, user)
    assert r.status_code == 422
    assert not IdempotencyKey.objects.exists()
    r2 = call({"org": str(org.pk), "name": "a", "fail": "domain"}, key, user)
    assert r2.status_code == 422 and SubmitView.calls == 2


def test_non_2xx_response_not_stored(org: Any, user: Any) -> None:
    key = str(uuid.uuid4())
    assert call({"org": str(org.pk), "name": "a", "fail": "status"}, key, user).status_code == 409
    assert not IdempotencyKey.objects.exists()


def test_expired_key_can_be_reused(org: Any, user: Any) -> None:
    key = str(uuid.uuid4())
    call({"org": str(org.pk), "name": "a"}, key, user)
    IdempotencyKey.objects.update(expires_at=time.now() - timedelta(seconds=1))
    r = call({"org": str(org.pk), "name": "different"}, key, user)
    assert r.status_code == 201 and "Idempotent-Replayed" not in r
    assert SubmitView.calls == 2


def test_purge_task_removes_expired(org: Any, user: Any) -> None:
    from apps.core.tasks import purge_expired_idempotency_keys

    call({"org": str(org.pk), "name": "a"}, str(uuid.uuid4()), user)
    call({"org": str(org.pk), "name": "b"}, str(uuid.uuid4()), user)
    IdempotencyKey.objects.filter(response_body__name="a").update(
        expires_at=time.now() - timedelta(minutes=1)
    )
    assert purge_expired_idempotency_keys.apply().get() == 1
    assert IdempotencyKey.objects.count() == 1
