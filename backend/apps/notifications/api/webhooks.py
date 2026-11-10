"""Provider webhooks. No session, no CSRF: each message is verified cryptographically."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications import bounces


class SesFeedbackWebhook(APIView):
    """Amazon SNS -> SES bounce and complaint notifications (signature-verified)."""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        result = bounces.handle_sns(request._request.body)
        return Response({"result": result})
