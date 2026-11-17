"""/platform/ai/ - model registry and the AI kill-switch for platform staff (P09-T11)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.exceptions import NotFoundError
from apps.core.serializers import StrictSerializer
from apps.organisations.models import Organisation
from apps.organisations.permissions import IsPlatformAdmin, IsPlatformStaff

from .. import killswitch
from ..models import ModelRegistryEntry


class RegistryEntrySerializer(serializers.ModelSerializer):
    active = serializers.SerializerMethodField()

    class Meta:
        model = ModelRegistryEntry
        fields = [
            "id",
            "kind",
            "name",
            "version",
            "purpose",
            "provider",
            "data_policy",
            "limitations",
            "evaluation_report",
            "active_from",
            "active_to",
            "active",
        ]
        read_only_fields = fields

    def get_active(self, obj: ModelRegistryEntry) -> bool:
        return obj.active_to is None


class DisabledOrgSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class AIGovernanceSerializer(serializers.Serializer):
    platform_enabled = serializers.BooleanField()
    disabled_organisations = DisabledOrgSerializer(many=True)
    models = RegistryEntrySerializer(many=True)


class KillSwitchSerializer(StrictSerializer):
    enabled = serializers.BooleanField()
    reason = serializers.CharField(min_length=10, max_length=500)


class OrgKillSwitchSerializer(StrictSerializer):
    # null removes the organisation override (the organisation follows the platform switch)
    enabled = serializers.BooleanField(allow_null=True)
    reason = serializers.CharField(min_length=10, max_length=500)


def _state() -> dict[str, Any]:
    ids = killswitch.disabled_organisations()
    orgs = Organisation.objects.filter(pk__in=ids).order_by("name").values("id", "name")
    return {
        "platform_enabled": killswitch.platform_enabled(),
        "disabled_organisations": list(orgs),
        "models": ModelRegistryEntry.objects.order_by("kind", "name", "-active_from"),
    }


class PlatformAIView(APIView):
    def get_permissions(self) -> list[Any]:
        return [IsPlatformStaff()] if self.request.method == "GET" else [IsPlatformAdmin()]

    @extend_schema(operation_id="platform_ai", responses=AIGovernanceSerializer)
    def get(self, request: Request) -> Response:
        return Response(AIGovernanceSerializer(_state()).data)

    @extend_schema(
        operation_id="platform_ai_switch",
        request=KillSwitchSerializer,
        responses=AIGovernanceSerializer,
    )
    def post(self, request: Request) -> Response:
        data = KillSwitchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        killswitch.set_platform(
            data.validated_data["enabled"],
            actor=authed_user(request),
            reason=data.validated_data["reason"],
        )
        return Response(AIGovernanceSerializer(_state()).data)


class PlatformOrgAIView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_ai_org_switch",
        request=OrgKillSwitchSerializer,
        responses=AIGovernanceSerializer,
    )
    def post(self, request: Request, organisation_id: str) -> Response:
        data = OrgKillSwitchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        org = Organisation.objects.filter(pk=organisation_id).first()
        if org is None:
            raise NotFoundError()
        killswitch.set_for_organisation(
            org,
            data.validated_data["enabled"],
            actor=authed_user(request),
            reason=data.validated_data["reason"],
        )
        return Response(AIGovernanceSerializer(_state()).data)
