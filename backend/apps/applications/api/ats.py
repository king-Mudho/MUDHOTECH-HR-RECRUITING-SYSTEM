"""HR applicant-tracking endpoints (docs/04: transition, notes, assign; tags; decision reasons)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.applications import ats
from apps.applications.models import ApplicationNote, DecisionReason, Status
from apps.core.serializers import StrictSerializer
from apps.organisations.permissions import HasOrgAction

from .hr import HRApplicationDetailSerializer


class TransitionSerializer(StrictSerializer):
    to_status = serializers.ChoiceField(choices=Status.choices)
    reason_code = serializers.CharField(max_length=40, allow_blank=True, default="")
    reason_text = serializers.CharField(max_length=2000, allow_blank=True, default="")
    lock_version = serializers.IntegerField(required=False, allow_null=True)


class NoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationNote
        fields = ["id", "body", "visibility", "mentions", "author_name", "mine", "created_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_author_name(self, obj: ApplicationNote) -> str:
        return obj.author.display_name if obj.author else ""

    @extend_schema_field(serializers.BooleanField())
    def get_mine(self, obj: ApplicationNote) -> bool:
        return obj.author_id == self.context.get("user_id")


class NoteCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=5000)
    mentions = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    visibility = serializers.ChoiceField(
        choices=ApplicationNote.Visibility.choices, default=ApplicationNote.Visibility.TEAM
    )


class TagsSerializer(StrictSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=60, allow_blank=True, trim_whitespace=False),
        max_length=20,
    )


class AssignSerializer(StrictSerializer):
    user_id = serializers.UUIDField(allow_null=True)


class DecisionReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionReason
        fields = ["code", "label", "applies_to"]
        read_only_fields = fields


def _detail(request: Request, app: Any) -> Response:
    from apps.applications import hr

    data = hr.application_detail(authed_user(request), request.membership, app.pk)  # type: ignore[attr-defined]
    context = {"extra": data, "membership": request.membership}  # type: ignore[attr-defined]
    return Response(HRApplicationDetailSerializer(data["application"], context=context).data)


class HRTransitionView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_applications_transition",
        request=TransitionSerializer,
        responses=HRApplicationDetailSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = TransitionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        app = ats.hr_transition(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            **ser.validated_data,
        )
        return _detail(request, app)


class HRNotesView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_applications_notes_list", responses=NoteSerializer(many=True))
    def get(self, request: Request, application_id: str) -> Response:
        user = authed_user(request)
        rows = ats.visible_notes(request.membership, user, application_id)  # type: ignore[attr-defined]
        return Response(NoteSerializer(rows, many=True, context={"user_id": user.pk}).data)

    @extend_schema(
        operation_id="hr_applications_notes_create",
        request=NoteCreateSerializer,
        responses={201: NoteSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = NoteCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authed_user(request)
        note = ats.add_note(
            request.membership,  # type: ignore[attr-defined]
            user,
            application_id,
            **ser.validated_data,
        )
        return Response(
            NoteSerializer(note, context={"user_id": user.pk}).data, status=status.HTTP_201_CREATED
        )


class HRTagsView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_applications_tags_update",
        request=TagsSerializer,
        responses=HRApplicationDetailSerializer,
    )
    def put(self, request: Request, application_id: str) -> Response:
        ser = TagsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        app = ats.set_tags(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            ser.validated_data["tags"],
        )
        return _detail(request, app)


class HRAssignView(APIView):
    permission_classes = [HasOrgAction("applications.assign")]

    @extend_schema(
        operation_id="hr_applications_assign",
        request=AssignSerializer,
        responses=HRApplicationDetailSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        ser = AssignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        app = ats.assign(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            ser.validated_data["user_id"],
        )
        return _detail(request, app)


class HRDecisionReasonsView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_decision_reasons_list",
        parameters=[
            OpenApiParameter(
                "applies_to", str, enum=[c for c, _ in DecisionReason.AppliesTo.choices]
            )
        ],
        responses=DecisionReasonSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        applies_to = request.query_params.get("applies_to") or None
        rows = ats.decision_reasons(request.organisation, applies_to)  # type: ignore[attr-defined]
        return Response(DecisionReasonSerializer(rows, many=True).data)
