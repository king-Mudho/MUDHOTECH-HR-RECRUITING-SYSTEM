"""Clarification and message endpoints (docs/04 Applications + Notifications & messaging).

Candidate endpoints act on the caller's own application (anything else is 404). HR endpoints take
the organisation from ``X-Org-Id`` and only reach applications the caller may see.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.serializers import StrictSerializer
from apps.messaging import services
from apps.messaging.models import ClarificationRequest, Message
from apps.organisations.permissions import HasOrgAction


# --------------------------------------------------------------------------- serializers
class ClarificationQuestionSerializer(serializers.Serializer):
    id = serializers.CharField()
    prompt = serializers.CharField()
    allow_upload = serializers.BooleanField()


class ClarificationAnswerItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    document_id = serializers.UUIDField(allow_null=True)


class ClarificationSerializer(serializers.ModelSerializer):
    questions = ClarificationQuestionSerializer(many=True)
    answers = ClarificationAnswerItemSerializer(many=True)

    class Meta:
        model = ClarificationRequest
        fields = [
            "id",
            "status",
            "message",
            "questions",
            "answers",
            "due_at",
            "answered_at",
            "created_at",
        ]
        read_only_fields = fields


class ClarificationQuestionInputSerializer(StrictSerializer):
    prompt = serializers.CharField(max_length=1000)
    allow_upload = serializers.BooleanField(default=False)


class ClarificationCreateSerializer(StrictSerializer):
    questions = ClarificationQuestionInputSerializer(many=True)
    due_at = serializers.DateTimeField()
    message = serializers.CharField(max_length=2000, allow_blank=True, default="")
    criterion_id = serializers.UUIDField(required=False, allow_null=True)


class ClarificationAnswerInputSerializer(StrictSerializer):
    id = serializers.CharField(max_length=20)
    text = serializers.CharField(max_length=5000, allow_blank=True, default="")
    document_id = serializers.UUIDField(required=False, allow_null=True)


class ClarificationAnswerSerializer(StrictSerializer):
    answers = ClarificationAnswerInputSerializer(many=True)


class QuestionTemplateSerializer(serializers.Serializer):
    key = serializers.CharField()
    prompt = serializers.CharField()
    allow_upload = serializers.BooleanField()


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()
    attachment_document_ids = serializers.ListField(child=serializers.UUIDField())

    class Meta:
        model = Message
        fields = [
            "id",
            "sender_role",
            "sender_name",
            "mine",
            "body",
            "attachment_document_ids",
            "created_at",
            "read_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_sender_name(self, obj: Message) -> str:
        # Candidates see the organisation, not individual staff names.
        if obj.sender_role == "staff" and self.context.get("viewer") == "candidate":
            return str(self.context.get("organisation_name") or "")
        return obj.sender_user.display_name if obj.sender_user else ""

    @extend_schema_field(serializers.BooleanField())
    def get_mine(self, obj: Message) -> bool:
        return obj.sender_role == self.context.get("viewer")


class MessageCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=5000)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=3
    )


def _messages(rows: list[Message], viewer: str, organisation_name: str = "") -> Any:
    context = {"viewer": viewer, "organisation_name": organisation_name}
    return MessageSerializer(rows, many=True, context=context).data


# ----------------------------------------------------------------------------- candidate
class CandidateClarificationsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_clarifications_list",
        responses=ClarificationSerializer(many=True),
    )
    def get(self, request: Request, application_id: str) -> Response:
        rows = services.own_clarifications(authed_user(request), application_id)
        return Response(ClarificationSerializer(rows, many=True).data)


class CandidateClarificationAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_clarifications_answer",
        request=ClarificationAnswerSerializer,
        responses=ClarificationSerializer,
    )
    def post(self, request: Request, application_id: str, clarification_id: str) -> Response:
        ser = ClarificationAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        req = services.answer_clarification(
            authed_user(request), application_id, clarification_id, ser.validated_data["answers"]
        )
        return Response(ClarificationSerializer(req).data)


class CandidateMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_messages_list", responses=MessageSerializer(many=True)
    )
    def get(self, request: Request, application_id: str) -> Response:
        from apps.applications.services import get_own

        user = authed_user(request)
        org = get_own(user, application_id).organisation.name
        return Response(
            _messages(services.candidate_messages(user, application_id), "candidate", org)
        )

    @extend_schema(
        operation_id="applications_messages_create",
        request=MessageCreateSerializer,
        responses={201: MessageSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = MessageCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        message = services.candidate_post(
            authed_user(request),
            application_id,
            ser.validated_data["body"],
            ser.validated_data["attachment_ids"],
        )
        return Response(
            MessageSerializer(message, context={"viewer": "candidate"}).data,
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------------------------ HR
class _HRView(APIView):
    """GET needs ``applications.view``; writes need the action named by ``write_action``."""

    write_action = "applications.view"

    def get_permissions(self) -> list[Any]:
        action = "applications.view" if self.request.method == "GET" else self.write_action
        return [HasOrgAction(action)()]


class HRQuestionTemplatesView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_clarification_templates_list",
        responses=QuestionTemplateSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        return Response(services.QUESTION_TEMPLATES)


class HRClarificationsView(_HRView):
    write_action = "applications.transition"

    @extend_schema(
        operation_id="hr_applications_clarifications_list",
        responses=ClarificationSerializer(many=True),
    )
    def get(self, request: Request, application_id: str) -> Response:
        rows = services.staff_clarifications(request.membership, application_id)  # type: ignore[attr-defined]
        return Response(ClarificationSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="hr_applications_clarifications_create",
        request=ClarificationCreateSerializer,
        responses={201: ClarificationSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = ClarificationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        req = services.request_clarification(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            **ser.validated_data,
        )
        return Response(ClarificationSerializer(req).data, status=status.HTTP_201_CREATED)


class HRClarificationCancelView(_HRView):
    write_action = "applications.transition"

    @extend_schema(
        operation_id="hr_applications_clarifications_cancel",
        request=None,
        responses=ClarificationSerializer,
    )
    def post(self, request: Request, application_id: str, clarification_id: str) -> Response:
        req = services.cancel_clarification(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            clarification_id,
        )
        return Response(ClarificationSerializer(req).data)


class HRMessagesView(_HRView):
    write_action = "applications.view"

    @extend_schema(
        operation_id="hr_applications_messages_list", responses=MessageSerializer(many=True)
    )
    def get(self, request: Request, application_id: str) -> Response:
        rows = services.staff_messages(request.membership, application_id)  # type: ignore[attr-defined]
        return Response(_messages(rows, "staff"))

    @extend_schema(
        operation_id="hr_applications_messages_create",
        request=MessageCreateSerializer,
        responses={201: MessageSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = MessageCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        message = services.staff_post(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            ser.validated_data["body"],
            ser.validated_data["attachment_ids"],
        )
        return Response(
            MessageSerializer(message, context={"viewer": "staff"}).data,
            status=status.HTTP_201_CREATED,
        )


class CandidateActionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["clarification", "reupload", "message"])
    application_id = serializers.UUIDField()
    job_title = serializers.CharField()
    organisation_name = serializers.CharField()
    due_at = serializers.DateTimeField(required=False)
    document_name = serializers.CharField(required=False)
    count = serializers.IntegerField(required=False)


class CandidateActionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_actions_list", responses=CandidateActionSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = services.candidate_actions(authed_user(request))
        return Response(CandidateActionSerializer(rows, many=True).data)
