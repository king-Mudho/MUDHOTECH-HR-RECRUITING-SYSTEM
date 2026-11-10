"""In-app notifications for the signed-in user (docs/04: /notifications, P05-T05).

Strictly per user: another person's notification is 404. Texts are rendered from the in-app
templates; links are site-relative paths only (never an external URL from a payload).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.exceptions import NotFoundError
from apps.core.pagination import StandardPagination
from apps.core.time import now
from apps.notifications import delivery
from apps.notifications.models import Channel, Notification

LINK_KEYS = (
    "clarification_url",
    "application_url",
    "apply_url",
    "note_url",
    "dashboard_url",
    "invitation_url",
)


def own_inbox(user: Any) -> QuerySet[Notification]:
    return Notification.objects.filter(recipient_user=user, channel=Channel.INAPP)


def relative_link(payload: dict[str, Any]) -> str:
    """First known link variable, reduced to a path on our own site (else empty)."""
    site = urlparse(settings.FRONTEND_URL)
    for key in LINK_KEYS:
        value = str(payload.get(key) or "")
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.netloc and parsed.netloc != site.netloc:
            continue
        path = parsed.path or "/"
        if not path.startswith("/") or path.startswith("//"):
            continue
        return path + (f"#{parsed.fragment}" if parsed.fragment else "")
    return ""


class InboxItemSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "key", "text", "link", "organisation", "created_at", "read_at"]
        read_only_fields = fields

    def get_text(self, obj: Notification) -> str:
        return delivery.render_inapp(obj)

    def get_link(self, obj: Notification) -> str:
        return relative_link(obj.payload)


class UnreadCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class InboxListView(generics.ListAPIView[Notification]):
    permission_classes = [IsAuthenticated]
    serializer_class = InboxItemSerializer
    pagination_class = StandardPagination

    def get_queryset(self) -> QuerySet[Notification]:
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        qs = own_inbox(self.request.user).select_related("recipient_user")
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        return qs.order_by("-created_at")

    @extend_schema(
        operation_id="notifications_list",
        parameters=[OpenApiParameter("unread", bool, description="Only unread")],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="notifications_unread_count", responses=UnreadCountSerializer)
    def get(self, request: Request) -> Response:
        count = own_inbox(authed_user(request)).filter(read_at__isnull=True).count()
        return Response({"count": count})


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="notifications_read", request=None, responses=InboxItemSerializer)
    def post(self, request: Request, notification_id: str) -> Response:
        n = own_inbox(authed_user(request)).filter(pk=notification_id).first()
        if n is None:
            raise NotFoundError()
        if n.read_at is None:
            n.read_at = now()
            n.save(update_fields=["read_at", "updated_at"])
        return Response(InboxItemSerializer(n).data)


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_read_all", request=None, responses=UnreadCountSerializer
    )
    def post(self, request: Request) -> Response:
        own_inbox(authed_user(request)).filter(read_at__isnull=True).update(read_at=now())
        return Response({"count": 0})
