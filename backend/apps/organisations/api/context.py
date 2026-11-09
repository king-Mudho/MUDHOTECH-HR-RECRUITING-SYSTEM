"""POST /me/active-org - switch the session's active organisation (FR-M02-05)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.exceptions import NotFoundError
from apps.organisations.middleware import SESSION_KEY
from apps.organisations.selectors import active_membership


class ActiveOrgSerializer(serializers.Serializer):
    organisation_id = serializers.UUIDField()


class ActiveOrgView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="me_active_org_set",
        request=ActiveOrgSerializer,
        responses=inline_serializer(
            name="ActiveOrg",
            fields={
                "organisation_id": serializers.UUIDField(),
                "role": serializers.CharField(),
            },
        ),
    )
    def post(self, request: Request) -> Response:
        ser = ActiveOrgSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org_id = ser.validated_data["organisation_id"]
        membership = active_membership(authed_user(request), org_id)
        if membership is None:
            raise NotFoundError()  # same answer whether the org exists or not
        request.session[SESSION_KEY] = str(org_id)
        return Response({"organisation_id": str(org_id), "role": membership.role})
