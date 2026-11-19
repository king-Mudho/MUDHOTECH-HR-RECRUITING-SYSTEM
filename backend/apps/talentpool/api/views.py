"""Candidate talent pool endpoints (P13-T01). The candidate only ever sees and changes their own
memberships, and only for employers they applied to."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.organisations.permissions import HasOrgAction

from .. import search, services
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


# --- HR (P13-T02) ---------------------------------------------------------------------------------
class TalentSearchView(APIView):
    permission_classes = [HasOrgAction("talentpool.search")]

    @extend_schema(
        operation_id="hr_talent_pool_search",
        parameters=[
            OpenApiParameter("q", str, description="Full-text search"),
            OpenApiParameter(
                "skill", str, many=True, description="Skill name or id (all must match)"
            ),
            OpenApiParameter("min_qualification_rank", int),
            OpenApiParameter("tag", str),
        ],
        responses=s.PaginatedTalentCandidateSerializer,
    )
    def get(self, request: Request) -> Response:
        from apps.audit import services as audit
        from apps.core.pagination import StandardPagination

        membership = request.membership  # type: ignore[attr-defined]
        p = request.query_params
        rank = p.get("min_qualification_rank")
        qs = search.search(
            membership,
            q=p.get("q", "")[:200],
            skills=p.getlist("skill")[:10],
            min_qualification_rank=int(rank) if rank and rank.isdigit() else None,
            tag=p.get("tag", "")[:40],
        )
        pager = StandardPagination()
        page = pager.paginate_queryset(qs, request, view=self)
        rows = [search.card(e) for e in page or []]
        if rows:
            audit.log_view(membership, ("talent_pool", membership.organisation_id), listing=True)
        return pager.get_paginated_response(s.TalentCandidateSerializer(rows, many=True).data)


class TalentEntryView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "talentpool.search" if self.request.method == "GET" else "talentpool.invite"
        return [HasOrgAction(action)()]

    @extend_schema(operation_id="hr_talent_pool_entry", responses=s.TalentCandidateSerializer)
    def get(self, request: Request, entry_id: str) -> Response:
        entry = search.get(request.membership, entry_id)  # type: ignore[attr-defined]
        return Response(s.TalentCandidateSerializer(search.card(entry)).data)

    @extend_schema(
        operation_id="hr_talent_pool_tags",
        request=s.TalentTagsSerializer,
        responses=s.TalentCandidateSerializer,
    )
    def patch(self, request: Request, entry_id: str) -> Response:
        data = s.TalentTagsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        entry = search.set_tags(
            request.membership,  # type: ignore[attr-defined]
            entry_id,
            data.validated_data["tags"],
        )
        return Response(s.TalentCandidateSerializer(search.card(entry)).data)


class TalentInviteView(APIView):
    permission_classes = [HasOrgAction("talentpool.invite")]

    @extend_schema(
        operation_id="hr_talent_pool_invite",
        request=s.TalentInviteSerializer,
        responses={201: s.TalentInviteResultSerializer},
    )
    def post(self, request: Request, entry_id: str) -> Response:
        data = s.TalentInviteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sent = search.invite(
            request.membership,  # type: ignore[attr-defined]
            entry_id,
            data.validated_data["job_id"],
        )
        body = {"id": sent.pk, "job_id": sent.job_id, "invited_at": sent.invited_at}
        return Response(s.TalentInviteResultSerializer(body).data, status=201)
