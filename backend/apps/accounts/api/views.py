from __future__ import annotations

from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@extend_schema(
    operation_id="auth_csrf",
    summary="Set the CSRF cookie for the browser client",
    responses=inline_serializer(name="CsrfToken", fields={"csrf_token": serializers.CharField()}),
)
@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request: Request) -> Response:
    """Sets `csrftoken` (readable by JS) so the SPA can send `X-CSRFToken` on unsafe requests."""
    return Response({"csrf_token": get_token(request)})
