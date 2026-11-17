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


# ------------------------------------------------------------------------- blind review (P08-T04)
class RevealIdentitySerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000)


class IdentityRevealSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    revealed_at = serializers.DateTimeField()


class HRRevealIdentityView(APIView):
    """Show this reviewer who a blind-reviewed applicant is (reason required, audited)."""

    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_application_reveal_identity",
        request=RevealIdentitySerializer,
        responses={201: IdentityRevealSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        from apps.applications.blind import reveal

        data = RevealIdentitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = reveal(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            reason=data.validated_data["reason"],
        )
        return Response(
            IdentityRevealSerializer(
                {"application_id": row.application_id, "revealed_at": row.at}
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------ applicants table (P08-T05)
class SavedViewSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=60)
    scope = serializers.CharField(max_length=20, default="applications")
    params = serializers.DictField(child=serializers.CharField(allow_blank=True))


class HRSavedViewsView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_saved_views",
        parameters=[OpenApiParameter("scope", str, enum=["applications"])],
        responses=SavedViewSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        from apps.applications import saved_views

        rows = saved_views.views_for(
            request.membership,  # type: ignore[attr-defined]
            request.query_params.get("scope", "applications"),
        )
        return Response(SavedViewSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="hr_saved_view_create",
        request=SavedViewSerializer,
        responses={201: SavedViewSerializer},
    )
    def post(self, request: Request) -> Response:
        from apps.applications import saved_views

        data = SavedViewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = saved_views.create(request.membership, **data.validated_data)  # type: ignore[attr-defined]
        return Response(SavedViewSerializer(row).data, status=status.HTTP_201_CREATED)


class HRSavedViewDetailView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_saved_view_delete", responses={204: None})
    def delete(self, request: Request, view_id: str) -> Response:
        from apps.applications import saved_views

        saved_views.delete(request.membership, view_id)  # type: ignore[attr-defined]
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkQuestionSerializer(StrictSerializer):
    prompt = serializers.CharField(max_length=1000)


class BulkActionSerializer(StrictSerializer):
    action = serializers.ChoiceField(
        choices=["assign_me", "unassign", "tag", "untag", "clarification", "propose_shortlist"]
    )
    application_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=500
    )
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list, max_length=10
    )
    questions = BulkQuestionSerializer(many=True, required=False, default=list)
    message = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    due_days = serializers.IntegerField(required=False, default=5, min_value=1, max_value=30)


class BulkSkipSerializer(serializers.Serializer):
    application_id = serializers.CharField()
    reason = serializers.CharField()


class BulkActionResultSerializer(serializers.Serializer):
    action = serializers.CharField()
    done = serializers.IntegerField()
    skipped = BulkSkipSerializer(many=True)
    shortlist_id = serializers.UUIDField(allow_null=True)


class HRBulkApplicationsView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_job_applications_bulk",
        request=BulkActionSerializer,
        responses=BulkActionResultSerializer,
    )
    def post(self, request: Request, job_id: str) -> Response:
        from apps.applications import bulk

        data = BulkActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = bulk.run(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            job_id,
            action=v["action"],
            application_ids=v["application_ids"],
            tags=v["tags"],
            questions=[dict(q) for q in v["questions"]],
            message=v["message"],
            due_days=v["due_days"],
        )
        return Response(BulkActionResultSerializer(result).data)


# ------------------------------------------------------------------ conflicts (P08-T09)
class DeclareConflictSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000)


class ConflictDeclaredSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    declared_at = serializers.DateTimeField()


class HRDeclareConflictView(APIView):
    """Step back from an application you have a conflict of interest with (EC-REV-11)."""

    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_application_declare_conflict",
        request=DeclareConflictSerializer,
        responses={201: ConflictDeclaredSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        from apps.applications.conflicts import declare

        data = DeclareConflictSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = declare(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            application_id,
            reason=data.validated_data["reason"],
        )
        return Response(
            ConflictDeclaredSerializer(
                {"application_id": row.application_id, "declared_at": row.declared_at}
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------ dashboard (P08-T10)
class DashboardCardsSerializer(serializers.Serializer):
    open_vacancies = serializers.IntegerField()
    applications_today = serializers.IntegerField()
    applications_7d = serializers.IntegerField()
    processing_queue = serializers.IntegerField()
    processing_errors = serializers.IntegerField()
    pending_reviews = serializers.IntegerField()
    clarifications_outstanding = serializers.IntegerField()
    shortlist_approvals_pending = serializers.IntegerField()


class DashboardAISerializer(serializers.Serializer):
    ai_notice = serializers.CharField()
    bands = serializers.DictField(child=serializers.IntegerField())


class DashboardHumanSerializer(serializers.Serializer):
    shortlisted = serializers.IntegerField()
    not_selected = serializers.IntegerField()
    on_hold = serializers.IntegerField()


class DashboardAppRowSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    job_title = serializers.CharField()
    status = serializers.CharField()
    at = serializers.DateTimeField(allow_null=True)


class DashboardClarificationSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    job_title = serializers.CharField()
    due_at = serializers.DateTimeField()


class DashboardApprovalSerializer(serializers.Serializer):
    shortlist_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    job_title = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)


class DashboardQueuesSerializer(serializers.Serializer):
    failed_processing = DashboardAppRowSerializer(many=True)
    pending_reviews = DashboardAppRowSerializer(many=True)
    clarifications_due = DashboardClarificationSerializer(many=True)
    approvals = DashboardApprovalSerializer(many=True)


class DashboardSummarySerializer(serializers.Serializer):
    cards = DashboardCardsSerializer()
    ai_suggestions = DashboardAISerializer()
    human_decisions = DashboardHumanSerializer()
    queues = DashboardQueuesSerializer()


class FunnelStageSerializer(serializers.Serializer):
    stage = serializers.CharField()
    count = serializers.IntegerField()


class FunnelSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    stages = FunnelStageSerializer(many=True)
    withdrawn = serializers.IntegerField()


class HRDashboardSummaryView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_dashboard_summary",
        parameters=[
            OpenApiParameter("department", str),
            OpenApiParameter("job", str),
            OpenApiParameter("recruiter", str),
            OpenApiParameter("from", str, description="YYYY-MM-DD"),
            OpenApiParameter("to", str, description="YYYY-MM-DD"),
        ],
        responses=DashboardSummarySerializer,
    )
    def get(self, request: Request) -> Response:
        from apps.applications import dashboard

        body = dashboard.summary(request.membership, dict(request.query_params.items()))  # type: ignore[attr-defined]
        return Response(DashboardSummarySerializer(body).data)


class HRJobFunnelView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_job_funnel", responses=FunnelSerializer)
    def get(self, request: Request, job_id: str) -> Response:
        from apps.applications import dashboard

        return Response(FunnelSerializer(dashboard.funnel(request.membership, job_id)).data)  # type: ignore[attr-defined]
