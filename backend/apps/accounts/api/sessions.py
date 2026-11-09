"""/me/sessions - list and revoke the caller's sessions (FR-M01-03)."""

from __future__ import annotations

from typing import Any

from allauth.usersessions.models import UserSession
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import sessions as session_service
from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.audit.services import truncate_ip
from apps.core.exceptions import NotFoundError


class UserSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    last_seen_at = serializers.DateTimeField(read_only=True)
    ip = serializers.SerializerMethodField()
    user_agent = serializers.CharField(read_only=True)
    is_current = serializers.SerializerMethodField()

    def get_ip(self, obj: UserSession) -> str:
        return truncate_ip(obj.ip)  # never expose full addresses

    def get_is_current(self, obj: UserSession) -> bool:
        request = self.context["request"]
        return bool(obj.session_key == request.session.session_key)


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="me_sessions_list", responses=UserSessionSerializer(many=True))
    def get(self, request: Request) -> Response:
        data = UserSessionSerializer(
            session_service.list_sessions(authed_user(request)),
            many=True,
            context={"request": request},
        ).data
        return Response(data)


class SessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="me_sessions_revoke", responses={204: None})
    def delete(self, request: Request, session_id: int) -> Response:
        if not session_service.revoke_session(authed_user(request), session_id):
            raise NotFoundError()
        audit.record(
            actor=request.user,
            action="user.session_revoked",
            target=authed_user(request),
            after={"session_id": session_id},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeOtherSessionsView(APIView):
    """'Log out all other devices'."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="me_sessions_revoke_others",
        request=None,
        responses=inline_serializer(
            name="RevokedSessions", fields={"revoked": serializers.IntegerField()}
        ),
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        revoked = session_service.revoke_other_sessions(
            authed_user(request), request.session.session_key
        )
        audit.record(
            actor=request.user,
            action="user.sessions_revoked_others",
            target=authed_user(request),
            after={"revoked": revoked},
            request=request,
        )
        return Response({"revoked": revoked})
