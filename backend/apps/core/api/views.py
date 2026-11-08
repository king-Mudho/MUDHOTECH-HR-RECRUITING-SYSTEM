from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core import time


@extend_schema(
    operation_id="api_root",
    summary="API metadata",
    responses=inline_serializer(
        name="ApiRoot",
        fields={
            "name": serializers.CharField(),
            "version": serializers.CharField(),
            "server_time": serializers.DateTimeField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request: Request) -> Response:
    """Public API metadata including the authoritative server time (EC-OPS-06)."""
    return Response(
        {
            "name": settings.APP_NAME,
            "version": settings.SPECTACULAR_SETTINGS["VERSION"],
            "server_time": time.now(),
        }
    )
