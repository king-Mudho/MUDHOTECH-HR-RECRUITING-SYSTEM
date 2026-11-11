"""HR notification template API (docs/04 Notifications: /hr/notification-templates).

Organisation context comes from ``X-Org-Id``. Platform defaults are readable by every
organisation; an organisation's own versions are invisible to others (404).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.services import authed_user
from apps.core.serializers import StrictSerializer
from apps.notifications import registry, services
from apps.notifications.models import Channel, NotificationTemplate
from apps.organisations.api.views import RbacActionMixin


class TemplateSerializer(serializers.ModelSerializer):
    is_default = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    allowed_variables = serializers.SerializerMethodField()

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "key",
            "channel",
            "locale",
            "subject",
            "body_md",
            "variables",
            "version",
            "active",
            "is_default",
            "description",
            "allowed_variables",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_default(self, obj: NotificationTemplate) -> bool:
        return obj.organisation_id is None

    def get_description(self, obj: NotificationTemplate) -> str:
        kind = registry.KINDS.get(obj.key)
        return kind.description if kind else ""

    def get_allowed_variables(self, obj: NotificationTemplate) -> list[str]:
        kind = registry.KINDS.get(obj.key)
        return sorted(kind.allowed) if kind else []


class TemplateWriteSerializer(StrictSerializer):
    key = serializers.ChoiceField(choices=sorted(registry.KINDS))
    channel = serializers.ChoiceField(choices=Channel.choices, default=Channel.EMAIL)
    locale = serializers.CharField(max_length=10, default="en")
    subject = serializers.CharField(max_length=300, allow_blank=True, default="")
    body_md = serializers.CharField(max_length=25_000)


class PreviewSerializer(StrictSerializer):
    context = serializers.DictField(  # type: ignore[assignment]
        child=serializers.CharField(max_length=500), required=False
    )
    subject = serializers.CharField(max_length=300, allow_blank=True, required=False)
    body_md = serializers.CharField(max_length=25_000, required=False)


class RevertSerializer(StrictSerializer):
    key = serializers.ChoiceField(choices=sorted(registry.KINDS))
    channel = serializers.ChoiceField(choices=Channel.choices, default=Channel.EMAIL)
    locale = serializers.CharField(max_length=10, default="en")


class RenderedSerializer(serializers.Serializer):
    subject = serializers.CharField()
    text = serializers.CharField()
    html = serializers.CharField()


@extend_schema_view(
    list=extend_schema(
        operation_id="hr_notification_templates_list",
        parameters=[OpenApiParameter("channel", str, enum=["email", "inapp"])],
    ),
    retrieve=extend_schema(operation_id="hr_notification_templates_retrieve"),
    create=extend_schema(
        operation_id="hr_notification_templates_create",
        request=TemplateWriteSerializer,
        responses={201: TemplateSerializer},
    ),
)
class NotificationTemplateViewSet(RbacActionMixin, viewsets.GenericViewSet):
    serializer_class = TemplateSerializer
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "notifications.manage",
        "retrieve": "notifications.manage",
        "create": "notifications.manage",
        "preview": "notifications.manage",
        "history": "notifications.manage",
        "revert": "notifications.manage",
    }

    def get_queryset(self) -> QuerySet[NotificationTemplate]:
        if getattr(self, "swagger_fake_view", False):
            return NotificationTemplate.objects.none()
        return services.visible_templates(self.request.organisation)  # type: ignore[attr-defined]

    def list(self, request: Request) -> Response:
        """The template in force for every notification (override if any, else default)."""
        org = request.organisation  # type: ignore[attr-defined]
        channel = request.query_params.get("channel") or Channel.EMAIL
        if channel not in Channel.values:
            channel = Channel.EMAIL
        rows = []
        for key in sorted(registry.KINDS):
            template = services.effective_template(org, key, channel)
            if template is not None:
                rows.append(template)
        return Response(TemplateSerializer(rows, many=True).data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(TemplateSerializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        ser = TemplateWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        template = services.save_template(
            request.organisation,  # type: ignore[attr-defined]
            actor=authed_user(request),
            **ser.validated_data,
        )
        return Response(TemplateSerializer(template).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="hr_notification_templates_preview",
        request=PreviewSerializer,
        responses=RenderedSerializer,
    )
    @action(detail=True, methods=["post"])
    def preview(self, request: Request, pk: str | None = None) -> Response:
        ser = PreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        rendered = services.preview(
            self.get_object(),
            data.get("context"),
            subject=data.get("subject"),
            body_md=data.get("body_md"),
        )
        return Response(RenderedSerializer(rendered).data)

    @extend_schema(
        operation_id="hr_notification_templates_history",
        responses=TemplateSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def history(self, request: Request, pk: str | None = None) -> Response:
        """Every version of this template visible to the organisation (default + own)."""
        template = self.get_object()
        rows = self.get_queryset().filter(
            key=template.key, channel=template.channel, locale=template.locale
        )
        return Response(
            TemplateSerializer(rows.order_by("organisation", "-version"), many=True).data
        )

    @extend_schema(
        operation_id="hr_notification_templates_revert",
        request=RevertSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def revert(self, request: Request) -> Response:
        ser = RevertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.revert_to_default(
            request.organisation,  # type: ignore[attr-defined]
            actor=authed_user(request),
            **ser.validated_data,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_context(self) -> dict[str, Any]:
        return super().get_serializer_context()
