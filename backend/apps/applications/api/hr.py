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
from apps.applications.applicants import ApplicantPagination
from apps.applications.applicants import applicants as applicants_query
from apps.applications.blind import BlindView
from apps.applications.models import Application
from apps.organisations.permissions import HasOrgAction


class HRApplicationListSerializer(serializers.ModelSerializer):
    """Identity fields are redacted server-side in blind review (P08-T04): the view passes a
    ``BlindView`` in the context; without one nothing is shown."""

    candidate_name = serializers.SerializerMethodField()
    candidate_email = serializers.SerializerMethodField()
    identity_hidden = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "reference",
            "status",
            "submitted_at",
            "candidate_name",
            "candidate_email",
            "identity_hidden",
            "channel",
            "is_assisted",
            "objects_to_automated_processing",
            "tags",
            "assigned_recruiter",
            "lock_version",
        ]
        read_only_fields = fields

    def _blind(self, obj: Application) -> BlindView:
        view = self.context.get("blind")
        if view is None:  # fail closed
            view = BlindView(None, obj.organisation_id, [])
            view.enabled = True
        return view

    def get_candidate_name(self, obj: Application) -> str:
        return self._blind(obj).name(obj)

    def get_candidate_email(self, obj: Application) -> str:
        return self._blind(obj).email(obj)

    def get_identity_hidden(self, obj: Application) -> bool:
        return self._blind(obj).hidden(obj.pk)


class EssentialsCountSerializer(serializers.Serializer):
    met = serializers.IntegerField()
    unknown = serializers.IntegerField()
    not_evidenced = serializers.IntegerField()


class HRApplicantRowSerializer(HRApplicationListSerializer):
    """A row of the applicants table: AI fields are suggestions shown next to human data."""

    essentials = serializers.SerializerMethodField()
    assigned_name = serializers.SerializerMethodField()
    score = serializers.FloatField(read_only=True, allow_null=True)
    coverage = serializers.FloatField(read_only=True, allow_null=True)

    class Meta(HRApplicationListSerializer.Meta):
        fields = [
            *HRApplicationListSerializer.Meta.fields,
            "ai_band",
            "score",
            "coverage",
            "flags",
            "essentials",
            "assigned_name",
        ]
        read_only_fields = fields

    @extend_schema_field(EssentialsCountSerializer(allow_null=True))
    def get_essentials(self, obj: Application) -> dict[str, int] | None:
        if obj.essentials_met is None:
            return None
        return {
            "met": obj.essentials_met,
            "unknown": obj.essentials_unknown or 0,
            "not_evidenced": obj.essentials_not_evidenced or 0,
        }

    def get_assigned_name(self, obj: Application) -> str:
        user = obj.assigned_recruiter
        return str(user.full_name or user.email) if user is not None else ""


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
    allowed_transitions = serializers.SerializerMethodField()

    class Meta(HRApplicationListSerializer.Meta):
        fields = [
            *HRApplicationListSerializer.Meta.fields,
            "withdrawn_at",
            "withdraw_reason",
            "flags",
            "ai_band",
            "job",
            "candidate",
            "documents",
            "answers",
            "timeline",
            "allowed_transitions",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_allowed_transitions(self, obj: Application) -> list[str]:
        from apps.applications.ats import allowed_targets

        membership = self.context.get("membership")
        return allowed_targets(membership, obj) if membership is not None else []

    @extend_schema_field(HRJobRefSerializer)
    def get_job(self, obj: Application) -> dict[str, Any]:
        return {"id": obj.job_id, "title": obj.job.title, "version": obj.job_version.number}

    @extend_schema_field(serializers.DictField())
    def get_candidate(self, obj: Application) -> dict[str, Any]:
        return self._blind(obj).candidate(obj)

    @extend_schema_field(HRDocumentSerializer(many=True))
    def get_documents(self, obj: Application) -> list[dict[str, Any]]:
        return self._blind(obj).documents(obj, list(self.context["extra"]["documents"]))

    @extend_schema_field(HRAnswerSerializer(many=True))
    def get_answers(self, obj: Application) -> list[dict[str, Any]]:
        return list(self.context["extra"]["answers"])

    @extend_schema_field(HRStatusEventSerializer(many=True))
    def get_timeline(self, obj: Application) -> list[dict[str, Any]]:
        return list(HRStatusEventSerializer(self.context["extra"]["timeline"], many=True).data)


class HRJobApplicationsView(generics.ListAPIView[Application]):
    """Applicants table (P08-T05): filters, cursor pagination with a total, blind redaction."""

    permission_classes = [HasOrgAction("applications.view")]
    serializer_class = HRApplicantRowSerializer
    pagination_class = ApplicantPagination

    def get_queryset(self) -> QuerySet[Application]:
        if getattr(self, "swagger_fake_view", False):
            return Application.objects.none()
        from apps.applications.blind import policy_flags

        membership = self.request.membership  # type: ignore[attr-defined]
        blind, _ = policy_flags(membership.organisation_id)
        return applicants_query(
            membership,
            self.kwargs["job_id"],
            dict(self.request.query_params.items()),
            blind=blind,
        )

    @extend_schema(
        operation_id="hr_job_applications_list",
        parameters=[
            OpenApiParameter("status", str, description="Comma-separated statuses"),
            OpenApiParameter("band", str, description="Comma-separated AI bands"),
            OpenApiParameter("min_score", float),
            OpenApiParameter("max_score", float),
            OpenApiParameter("coverage_lt", float, description="Coverage below (0-1)"),
            OpenApiParameter("flags", str, description="Comma-separated; any of"),
            OpenApiParameter("essentials", str, enum=["all_met", "unknown", "not_evidenced"]),
            OpenApiParameter("tag", str),
            OpenApiParameter("assigned", str, enum=["me", "none"]),
            OpenApiParameter(
                "search", str, description="Reference; name/email too unless blind review"
            ),
            OpenApiParameter(
                "ordering",
                str,
                enum=["-score", "score", "-submitted_at", "submitted_at", "coverage"],
            ),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from apps.audit import services as audit

        response = super().get(request, *args, **kwargs)
        audit.log_view(
            request.membership,  # type: ignore[attr-defined]
            ("job", kwargs.get("job_id")),
            action="list_applicants",
            listing=True,
        )
        return response

    def get_serializer(self, *args: Any, **kwargs: Any) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return super().get_serializer(*args, **kwargs)
        rows = args[0] if args else []
        ids = [a.pk for a in rows] if isinstance(rows, list) else []
        kwargs.setdefault("context", self.get_serializer_context())
        kwargs["context"]["blind"] = BlindView(
            self.request.user,
            self.request.membership.organisation_id,  # type: ignore[attr-defined]
            ids,
        )
        return super().get_serializer(*args, **kwargs)


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
            HRApplicationDetailSerializer(
                data["application"],
                context={
                    "extra": data,
                    "membership": request.membership,  # type: ignore[attr-defined]
                    "blind": BlindView(
                        request.user, data["application"].organisation_id, [data["application"].pk]
                    ),
                },
            ).data
        )
