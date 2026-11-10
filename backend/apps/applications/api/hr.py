"""Minimal HR application views (P04-T15, docs/04 Applications HR). Read-only until Phase 08.

Organisation context comes from ``X-Org-Id``; the selectors decide what the caller may see
(foreign, unassigned or still-draft applications are 404).
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import generics, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.applications import hr
from apps.applications.models import Application
from apps.core.pagination import StandardPagination
from apps.organisations.permissions import HasOrgAction


class HRApplicationListSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    candidate_email = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "reference",
            "status",
            "submitted_at",
            "candidate_name",
            "candidate_email",
            "channel",
            "is_assisted",
            "objects_to_automated_processing",
        ]
        read_only_fields = fields

    def get_candidate_name(self, obj: Application) -> str:
        snap = obj.candidate_profile_snapshot or {}
        name = " ".join(p for p in (snap.get("first_name"), snap.get("last_name")) if p)
        return name or str(snap.get("email") or "")

    def get_candidate_email(self, obj: Application) -> str:
        return str((obj.candidate_profile_snapshot or {}).get("email") or "")


class HRDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    required_doc_key = serializers.CharField()
    filename = serializers.CharField()
    scan_status = serializers.CharField()
    size_bytes = serializers.IntegerField()
    available = serializers.BooleanField()


class HRAnswerSerializer(serializers.Serializer):
    key = serializers.CharField()
    prompt = serializers.CharField()
    type = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    document_id = serializers.UUIDField(allow_null=True)


class HRStatusEventSerializer(serializers.Serializer):
    from_status = serializers.CharField()
    to_status = serializers.CharField()
    actor_type = serializers.CharField()
    reason_code = serializers.CharField()
    reason_text = serializers.CharField()
    at = serializers.DateTimeField()


class HRJobRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    version = serializers.IntegerField()


class HRApplicationDetailSerializer(HRApplicationListSerializer):
    job = serializers.SerializerMethodField()
    candidate = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta(HRApplicationListSerializer.Meta):
        fields = [
            *HRApplicationListSerializer.Meta.fields,
            "withdrawn_at",
            "withdraw_reason",
            "job",
            "candidate",
            "documents",
            "answers",
            "timeline",
        ]
        read_only_fields = fields

    @extend_schema_field(HRJobRefSerializer)
    def get_job(self, obj: Application) -> dict[str, Any]:
        return {"id": obj.job_id, "title": obj.job.title, "version": obj.job_version.number}

    @extend_schema_field(serializers.DictField())
    def get_candidate(self, obj: Application) -> dict[str, Any]:
        return dict(obj.candidate_profile_snapshot or {})

    @extend_schema_field(HRDocumentSerializer(many=True))
    def get_documents(self, obj: Application) -> list[dict[str, Any]]:
        return list(self.context["extra"]["documents"])

    @extend_schema_field(HRAnswerSerializer(many=True))
    def get_answers(self, obj: Application) -> list[dict[str, Any]]:
        return list(self.context["extra"]["answers"])

    @extend_schema_field(HRStatusEventSerializer(many=True))
    def get_timeline(self, obj: Application) -> list[dict[str, Any]]:
        return list(HRStatusEventSerializer(self.context["extra"]["timeline"], many=True).data)


class HRJobApplicationsView(generics.ListAPIView[Application]):
    permission_classes = [HasOrgAction("applications.view")]
    serializer_class = HRApplicationListSerializer
    pagination_class = StandardPagination

    def get_queryset(self) -> QuerySet[Application]:
        if getattr(self, "swagger_fake_view", False):
            return Application.objects.none()
        return hr.job_applications(
            self.request.membership,  # type: ignore[attr-defined]
            self.kwargs["job_id"],
            dict(self.request.query_params.items()),
        )

    @extend_schema(
        operation_id="hr_job_applications_list",
        parameters=[
            OpenApiParameter("status", str, description="Comma-separated statuses"),
            OpenApiParameter("search", str, description="Name, email or reference contains"),
            OpenApiParameter("ordering", str, enum=["-submitted_at", "submitted_at"]),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


class HRApplicationDetailView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_applications_retrieve", responses=HRApplicationDetailSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        data = hr.application_detail(
            authed_user(request),
            request.membership,  # type: ignore[attr-defined]
            application_id,
        )
        return Response(
            HRApplicationDetailSerializer(data["application"], context={"extra": data}).data
        )
