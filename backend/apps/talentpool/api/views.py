"""Candidate talent pool endpoints (P13-T01). The candidate only ever sees and changes their own
memberships, and only for employers they applied to."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user

from .. import services
from . import serializers as s


def _client_ip(request: Request) -> str | None:
    forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


class CandidateTalentPoolsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_talent_pools",
        responses=s.TalentPoolMembershipSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = services.status_for(authed_user(request))
        return Response(s.TalentPoolMembershipSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="candidate_talent_pool_join",
        request=s.TalentPoolJoinSerializer,
        responses=s.TalentPoolMembershipSerializer,
    )
    def post(self, request: Request) -> Response:
        user = authed_user(request)
        data = s.TalentPoolJoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        org_id = data.validated_data["organisation_id"]
        services.join(user, org_id, ip=_client_ip(request))
        return Response(s.TalentPoolMembershipSerializer(services.entry_row(user, org_id)).data)


class CandidateTalentPoolLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_talent_pool_leave",
        request=s.TalentPoolLeaveSerializer,
        responses=s.TalentPoolMembershipSerializer,
    )
    def post(self, request: Request, organisation_id: str) -> Response:
        user = authed_user(request)
        data = s.TalentPoolLeaveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.leave(user, organisation_id, delete=data.validated_data["delete"])
        return Response(
            s.TalentPoolMembershipSerializer(services.entry_row(user, organisation_id)).data
        )
