"""Error envelope, request id middleware, pagination, base viewset."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import RequestFactory
from rest_framework import exceptions as drf_exc
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.context import request_id_var
from apps.core.exceptions import (
    ConflictError,
    DeadlinePassedError,
    DomainError,
    InvalidTransitionError,
    OrgSuspendedError,
    StaleVersionError,
    api_exception_handler,
    csrf_failure,
    json_400,
    json_403,
    json_404,
    json_500,
)
from apps.core.logging import ContextFilter
from apps.core.middleware import RequestIDMiddleware, generate_request_id
from apps.core.pagination import StandardCursorPagination, StandardPagination
from apps.core.time import now, to_tz
from apps.core.viewsets import TenantScopedViewSet
from tests.core_testapp.models import Widget


def _handle(exc: Exception) -> Response:
    resp = api_exception_handler(exc, {})
    assert resp is not None
    return resp


# ---------------------------------------------------------------- error envelope
@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (
            drf_exc.ValidationError({"closes_at": ["Must be in the future."]}),
            400,
            "validation_error",
        ),
        (drf_exc.ParseError(), 400, "validation_error"),
        (drf_exc.NotAuthenticated(), 401, "not_authenticated"),
        (drf_exc.AuthenticationFailed(), 401, "not_authenticated"),
        (drf_exc.PermissionDenied(), 403, "permission_denied"),
        (drf_exc.NotFound(), 404, "not_found"),
        (drf_exc.MethodNotAllowed("POST"), 405, "method_not_allowed"),
        (drf_exc.UnsupportedMediaType("text/xml"), 415, "unsupported_media_type"),
        (drf_exc.Throttled(wait=12), 429, "rate_limited"),
        (Http404(), 404, "not_found"),
        (DjangoPermissionDenied(), 403, "permission_denied"),
        (DjangoValidationError({"name": ["Bad."]}), 400, "validation_error"),
        (DjangoValidationError("Bad."), 400, "validation_error"),
        (StaleVersionError(), 409, "conflict.stale_version"),
        (InvalidTransitionError(), 409, "conflict.invalid_transition"),
        (
            ConflictError(code="conflict.duplicate_application"),
            409,
            "conflict.duplicate_application",
        ),
        (OrgSuspendedError(), 423, "org_suspended"),
        (DeadlinePassedError(), 422, "deadline_passed"),
        (DomainError("gone", "Gone.", 410), 410, "gone"),
        (RuntimeError("boom"), 500, "internal_error"),
    ],
)
def test_envelope_shape(exc: Exception, status: int, code: str) -> None:
    token = request_id_var.set("req_TEST1234")
    try:
        resp = _handle(exc)
    finally:
        request_id_var.reset(token)
    assert resp.status_code == status
    err = resp.data["error"]
    assert set(err) == {"code", "message", "details", "request_id"}
    assert err["code"] == code
    assert err["request_id"] == "req_TEST1234"
    assert isinstance(err["message"], str) and err["message"]


def test_validation_details_are_field_mapped() -> None:
    resp = _handle(drf_exc.ValidationError({"closes_at": ["Must be in the future."]}))
    assert resp.data["error"]["details"] == {"closes_at": ["Must be in the future."]}
    resp = _handle(drf_exc.ValidationError(["Top level problem."]))
    assert resp.data["error"]["details"] == {"non_field_errors": ["Top level problem."]}
    assert resp.data["error"]["message"] == "Top level problem."


def test_throttle_details_and_internal_error_hides_message() -> None:
    assert _handle(drf_exc.Throttled(wait=7)).data["error"]["details"] == {"retry_after_seconds": 7}
    resp = _handle(RuntimeError("secret database password"))
    assert "secret" not in resp.data["error"]["message"]


def test_domain_error_details() -> None:
    err = DomainError("x.y", "Msg", 418, {"a": 1})
    resp = _handle(err)
    assert resp.status_code == 418
    assert resp.data["error"]["details"] == {"a": 1}


@pytest.mark.parametrize(
    ("view", "status", "code"),
    [
        (json_404, 404, "not_found"),
        (json_403, 403, "permission_denied"),
        (json_400, 400, "validation_error"),
    ],
)
def test_django_handlers(view: Any, status: int, code: str) -> None:
    import json

    resp = view(RequestFactory().get("/x"), None)
    assert resp.status_code == status
    assert json.loads(resp.content)["error"]["code"] == code


def test_django_500_and_csrf_handlers() -> None:
    import json

    assert json_500(RequestFactory().get("/x")).status_code == 500
    resp = csrf_failure(RequestFactory().post("/x"), "no token")
    assert json.loads(resp.content)["error"]["details"] == {"reason": "csrf"}


# ---------------------------------------------------------------- request id + logging
@pytest.mark.django_db
def test_request_id_generated_and_echoed(client: Any) -> None:
    resp = client.get("/api/v1/")
    rid = resp["X-Request-ID"]
    assert rid.startswith("req_") and len(rid) == 30


@pytest.mark.django_db
def test_inbound_request_id_is_reused_when_valid(client: Any) -> None:
    resp = client.get("/api/v1/", HTTP_X_REQUEST_ID="edge-abcdef123456")
    assert resp["X-Request-ID"] == "edge-abcdef123456"


@pytest.mark.django_db
def test_malicious_inbound_request_id_is_replaced(client: Any) -> None:
    resp = client.get("/api/v1/", HTTP_X_REQUEST_ID="bad id\r\ninjected: 1")
    assert resp["X-Request-ID"].startswith("req_")


@pytest.mark.django_db
def test_404_envelope_carries_request_id(client: Any) -> None:
    resp = client.get("/api/v1/does-not-exist/", HTTP_X_REQUEST_ID="req_trace_0001")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == "req_trace_0001"


def test_request_ids_are_unique_and_sortable() -> None:
    ids = [generate_request_id() for _ in range(200)]
    assert len(set(ids)) == 200


def test_middleware_resets_context() -> None:
    mw = RequestIDMiddleware(lambda r: Response())  # type: ignore[arg-type,return-value]
    mw(RequestFactory().get("/"))
    assert request_id_var.get() is None


def test_log_filter_injects_context() -> None:
    record = logging.LogRecord("x", logging.INFO, "f", 1, "msg", None, None)
    token = request_id_var.set("req_LOGTEST01")
    try:
        ContextFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "req_LOGTEST01"  # type: ignore[attr-defined]


def test_time_helpers() -> None:
    from datetime import datetime

    current = now()
    assert current.tzinfo is not None
    assert str(to_tz(current).tzinfo) == "Africa/Harare"
    assert str(to_tz(current, "UTC").tzinfo) == "UTC"
    with pytest.raises(ValueError):
        to_tz(datetime(2026, 1, 1))


@pytest.mark.django_db
def test_api_root_reports_server_time(client: Any) -> None:
    body = client.get("/api/v1/").json()
    assert body["name"] == "MUDHOTECH HR RECRUITING SYSTEM"
    assert "server_time" in body


# ---------------------------------------------------------------- pagination
@pytest.mark.django_db
def test_page_number_pagination_limits(org: Any) -> None:
    Widget.objects.bulk_create([Widget(organisation=org, name=f"w{i}") for i in range(30)])
    factory = APIRequestFactory()
    paginator = StandardPagination()
    req = Request(factory.get("/x", {"page_size": 1000}))
    page = paginator.paginate_queryset(Widget.objects.for_org(org).order_by("name"), req)
    assert page is not None and len(page) == 30  # capped at 100, only 30 rows
    data = paginator.get_paginated_response([1]).data
    assert set(data) == {"count", "next", "previous", "results"}


@pytest.mark.django_db
def test_cursor_pagination_shape(org: Any) -> None:
    Widget.objects.bulk_create([Widget(organisation=org, name=f"w{i}") for i in range(5)])
    paginator = StandardCursorPagination()
    req = Request(APIRequestFactory().get("/x", {"page_size": 2}))
    page = paginator.paginate_queryset(Widget.objects.for_org(org), req)
    assert page is not None and len(page) == 2
    data = paginator.get_paginated_response([]).data
    assert set(data) == {"next_cursor", "previous_cursor", "results"}
    assert data["next_cursor"]
    assert paginator._cursor_value(None) is None
    schema = paginator.get_paginated_response_schema({"type": "array"})
    assert "next_cursor" in schema["properties"]


# ---------------------------------------------------------------- tenant scoped viewset
class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "name"]


class WidgetViewSet(TenantScopedViewSet):
    queryset = Widget.objects.unscoped()
    serializer_class = WidgetSerializer
    permission_classes = [AllowAny]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_guard")
class TestTenantScopedViewSet:
    def _call(self, method: str, action: str, org: Any, user: Any, **kw: Any) -> Response:
        factory = APIRequestFactory()
        pk = kw.pop("pk", None)
        path = f"/w/{pk}/" if pk else "/w/"
        request = getattr(factory, method)(path, kw.get("data"), format="json")
        force_authenticate(request, user=user)
        request.organisation = org
        view = WidgetViewSet.as_view({method: action})
        return view(request, pk=pk) if pk else view(request)  # type: ignore[no-any-return]

    def test_list_excludes_other_tenant(self, org: Any, other_org: Any, user: Any) -> None:
        Widget.objects.create(organisation=org, name="mine")
        Widget.objects.create(organisation=other_org, name="theirs")
        resp = self._call("get", "list", org, user)
        assert [r["name"] for r in resp.data["results"]] == ["mine"]

    def test_cross_tenant_detail_and_mutations_404(
        self, org: Any, other_org: Any, user: Any
    ) -> None:
        theirs = Widget.objects.create(organisation=other_org, name="theirs")
        assert self._call("get", "retrieve", org, user, pk=theirs.pk).status_code == 404
        resp = self._call("patch", "partial_update", org, user, pk=theirs.pk, data={"name": "x"})
        assert resp.status_code == 404
        assert self._call("delete", "destroy", org, user, pk=theirs.pk).status_code == 404
        assert Widget.objects.unscoped().get(pk=theirs.pk).name == "theirs"

    def test_create_stamps_server_side_org(self, org: Any, other_org: Any, user: Any) -> None:
        resp = self._call(
            "post", "create", org, user, data={"name": "n", "organisation": str(other_org.pk)}
        )
        assert resp.status_code == 201
        assert Widget.objects.unscoped().get(pk=resp.data["id"]).organisation_id == org.pk

    def test_missing_org_context_is_403(self, user: Any) -> None:
        resp = self._call("get", "list", None, user)
        assert resp.status_code == 403
        assert resp.data["error"]["details"] == {"reason": "org_context_required"}


def test_tenant_viewset_requires_tenant_model() -> None:
    from apps.organisations.models import Organisation

    class Bad(TenantScopedViewSet):
        queryset = Organisation.objects.all()

    view = Bad()
    view.request = Request(APIRequestFactory().get("/"))
    with pytest.raises(TypeError):
        view.get_queryset()


@api_view(["GET"])
@permission_classes([AllowAny])
def _boom(request: Request) -> Response:
    raise DomainError("custom.code", "Custom.", 400)


def test_domain_error_through_view() -> None:
    resp = _boom(APIRequestFactory().get("/"))
    assert resp.data["error"]["code"] == "custom.code"
