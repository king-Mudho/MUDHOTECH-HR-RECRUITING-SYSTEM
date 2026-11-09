"""/platform/organisations - tenant lifecycle for platform staff (docs/04 'Platform admin')."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, IntegerField, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.services import authed_user
from apps.core.serializers import StrictSerializer
from apps.organisations.models import Membership, Organisation
from apps.organisations.permissions import IsPlatformAdmin, IsPlatformStaff
from apps.platform import services


class PlatformOrganisationSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    verified_by_email = serializers.EmailField(
        source="verified_by.email", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = Organisation
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "industry",
            "city",
            "country",
            "website",
            "registration_number",
            "created_at",
            "verified_at",
            "verified_by_email",
            "member_count",
        ]
        read_only_fields = fields


class PlatformReasonSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class PlatformSuspendReasonSerializer(StrictSerializer):
    reason = serializers.CharField(min_length=5, max_length=1000)


@extend_schema_view(
    list=extend_schema(operation_id="platform_organisations_list"),
    retrieve=extend_schema(operation_id="platform_organisations_retrieve"),
)
class PlatformOrganisationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PlatformOrganisationSerializer
    lookup_url_kwarg = "organisation_id"
    queryset = Organisation.objects.none()
    search_fields = ["name", "slug", "registration_number"]
    ordering_fields = ["created_at", "name", "status"]
    ordering = ["-created_at"]
    filterset_fields = ["status"]

    def get_permissions(self) -> list[BasePermission]:
        # Support staff may read tenant metadata; only platform admins change lifecycle state.
        if self.action in ("list", "retrieve"):
            return [IsPlatformStaff()]
        return [IsPlatformAdmin()]

    def get_queryset(self) -> QuerySet[Organisation]:
        active_members = (
            Membership.objects.unscoped()  # platform view is cross-tenant by design
            .filter(organisation=OuterRef("pk"), status=Membership.Status.ACTIVE)
            .values("organisation")
            .annotate(c=Count("id"))
            .values("c")
        )
        return Organisation.objects.select_related("verified_by").annotate(
            member_count=Coalesce(Subquery(active_members, output_field=IntegerField()), 0)
        )

    def _act(self, request: Request, fn: Any, serializer_cls: type[StrictSerializer]) -> Response:
        ser = serializer_cls(data=request.data)
        ser.is_valid(raise_exception=True)
        org = fn(
            self.get_object(),
            actor=authed_user(request),
            reason=ser.validated_data.get("reason", ""),
            request=request,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=org.pk)).data)

    @extend_schema(operation_id="platform_organisations_verify", request=PlatformReasonSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._act(request, services.verify_organisation, PlatformReasonSerializer)

    @extend_schema(
        operation_id="platform_organisations_suspend", request=PlatformSuspendReasonSerializer
    )
    @action(detail=True, methods=["post"])
    def suspend(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._act(request, services.suspend_organisation, PlatformSuspendReasonSerializer)

    @extend_schema(
        operation_id="platform_organisations_reactivate", request=PlatformReasonSerializer
    )
    @action(detail=True, methods=["post"])
    def reactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._act(request, services.reactivate_organisation, PlatformReasonSerializer)
