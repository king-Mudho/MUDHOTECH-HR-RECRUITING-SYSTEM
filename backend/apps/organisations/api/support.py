"""Break-glass support access endpoints (P09-T06)."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.exceptions import PermissionDeniedError
from apps.core.serializers import StrictSerializer
from apps.core.time import now
from apps.organisations import support_access
from apps.organisations.models import SupportAccessGrant
from apps.organisations.permissions import HasOrgAction, IsPlatformAdmin


class GrantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organisation_id = serializers.UUIDField()
    organisation_name = serializers.CharField()
    platform_user = serializers.CharField()
    reason = serializers.CharField()
    requested_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField()
    approved_by = serializers.CharField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    active = serializers.BooleanField()
    accesses = serializers.IntegerField()


class RequestAccessSerializer(StrictSerializer):
    organisation_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=2000)
    minutes = serializers.IntegerField(min_value=5, max_value=support_access.MAX_MINUTES)


class ActiveSupportSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    until = serializers.DateTimeField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)


def _shape(grants: list[SupportAccessGrant]) -> list[dict[str, Any]]:
    from apps.audit.models import AccessLog

    counts = dict(
        AccessLog.objects.filter(action="support_read", target_type="support_grant")
        .filter(target_id__in=[str(g.pk) for g in grants])
        .values_list("target_id")
        .annotate(n=Count("pk"))
        .values_list("target_id", "n")
    )
    moment = now()
    return [
        {
            "id": g.pk,
            "organisation_id": g.organisation_id,
            "organisation_name": g.organisation.name,
            "platform_user": g.platform_user.email,
            "reason": g.reason,
            "requested_at": g.requested_at,
            "duration_minutes": g.duration_minutes,
            "approved_by": g.approved_by.email if g.approved_by else None,
            "approved_at": g.approved_at,
            "expires_at": g.expires_at,
            "revoked_at": g.revoked_at,
            "active": bool(
                g.approved_at and not g.revoked_at and g.expires_at and g.expires_at > moment
            ),
            "accesses": counts.get(str(g.pk), 0),
        }
        for g in grants
    ]


# ------------------------------------------------------------------ platform
class PlatformSupportAccessView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="platform_support_access", responses=GrantSerializer(many=True))
    def get(self, request: Request) -> Response:
        user = authed_user(request)
        if user.platform_role not in support_access.SUPPORT_ROLES:
            raise PermissionDeniedError()
        qs = SupportAccessGrant.objects.select_related(
            "organisation", "platform_user", "approved_by"
        )
        if user.platform_role != "platform_admin":
            qs = qs.filter(platform_user=user)
        return Response(GrantSerializer(_shape(list(qs[:200])), many=True).data)

    @extend_schema(
        operation_id="platform_support_access_request",
        request=RequestAccessSerializer,
        responses={201: GrantSerializer},
    )
    def post(self, request: Request) -> Response:
        data = RequestAccessSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        grant = support_access.request_access(
            authed_user(request), v["organisation_id"], reason=v["reason"], minutes=v["minutes"]
        )
        return Response(GrantSerializer(_shape([grant])[0]).data, status=status.HTTP_201_CREATED)


class PlatformSupportApproveView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_support_access_approve", request=None, responses=GrantSerializer
    )
    def post(self, request: Request, grant_id: str) -> Response:
        grant = support_access.approve(authed_user(request), grant_id)
        return Response(GrantSerializer(_shape([grant])[0]).data)


class PlatformSupportRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="platform_support_access_revoke", request=None, responses=GrantSerializer
    )
    def post(self, request: Request, grant_id: str) -> Response:
        user = authed_user(request)
        if user.platform_role not in support_access.SUPPORT_ROLES:
            raise PermissionDeniedError()
        grant = support_access.revoke(user, grant_id)
        return Response(GrantSerializer(_shape([grant])[0]).data)


# ------------------------------------------------------------------ organisation (tenant-visible)
class HRSupportAccessView(APIView):
    permission_classes = [HasOrgAction("members.manage")]

    @extend_schema(operation_id="hr_support_access", responses=GrantSerializer(many=True))
    def get(self, request: Request) -> Response:
        grants = list(support_access.grants_for(request.membership.organisation_id)[:200])  # type: ignore[attr-defined]
        return Response(GrantSerializer(_shape(grants), many=True).data)


class HRSupportRevokeView(APIView):
    permission_classes = [HasOrgAction("members.manage")]

    @extend_schema(operation_id="hr_support_access_revoke", request=None, responses=GrantSerializer)
    def post(self, request: Request, grant_id: str) -> Response:
        grant = support_access.revoke(
            authed_user(request),
            grant_id,
            organisation_id=request.membership.organisation_id,  # type: ignore[attr-defined]
        )
        return Response(GrantSerializer(_shape([grant])[0]).data)


class HRSupportActiveView(APIView):
    """For the banner every staff member of the organisation sees while support has access."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="hr_support_access_active", responses=ActiveSupportSerializer)
    def get(self, request: Request) -> Response:
        membership = getattr(request, "membership", None)
        if membership is None:
            return Response({"active": False, "until": None, "reason": ""})
        moment = now()
        grant = (
            SupportAccessGrant.objects.filter(
                organisation_id=membership.organisation_id,
                approved_at__isnull=False,
                revoked_at__isnull=True,
                expires_at__gt=moment,
            )
            .filter(~Q(platform_user_id=None))
            .order_by("-expires_at")
            .first()
        )
        if grant is None:
            return Response({"active": False, "until": None, "reason": ""})
        return Response({"active": True, "until": grant.expires_at, "reason": grant.reason})
