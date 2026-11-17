"""Audit trail and decision reconstruction endpoints (P08-T11). Org context via ``X-Org-Id``."""

from __future__ import annotations

import csv
import io
from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import generics, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.audit.csv_safe import cell
from apps.audit.models import AuditEvent
from apps.audit.selectors import events_for
from apps.core.pagination import StandardCursorPagination
from apps.organisations.permissions import HasOrgAction

FILTERS = [
    OpenApiParameter("target_type", str),
    OpenApiParameter("target_id", str),
    OpenApiParameter("actor", str),
    OpenApiParameter("action", str, description="Prefix, e.g. application."),
    OpenApiParameter("from", str, description="YYYY-MM-DD"),
    OpenApiParameter("to", str, description="YYYY-MM-DD"),
]
EXPORT_LIMIT = 10_000


class AuditEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    seq = serializers.IntegerField()
    actor = serializers.SerializerMethodField()
    actor_type = serializers.CharField()
    action = serializers.CharField()
    target_type = serializers.CharField()
    target_id = serializers.CharField()
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)
    request_id = serializers.CharField(allow_blank=True)
    hash = serializers.CharField()

    def get_actor(self, obj: AuditEvent) -> str | None:
        user = obj.actor
        return None if user is None else str(user.full_name or user.email)


class AuditCursorPagination(StandardCursorPagination):
    ordering = ("-created_at", "-seq")  # type: ignore[assignment]  # DRF accepts tuples


class HRAuditEventsView(generics.ListAPIView[AuditEvent]):
    permission_classes = [HasOrgAction("audit.view")]
    serializer_class = AuditEventSerializer
    pagination_class = AuditCursorPagination

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        return events_for(self.request.membership, dict(self.request.query_params.items()))  # type: ignore[attr-defined]

    @extend_schema(operation_id="hr_audit_events", parameters=FILTERS)
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


class HRAuditExportView(APIView):
    """CSV for auditors (formula injection neutralised; capped; the export itself is audited)."""

    permission_classes = [HasOrgAction("audit.view")]

    @extend_schema(
        operation_id="hr_audit_events_export",
        parameters=FILTERS,
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request: Request) -> HttpResponse:
        params = dict(request.query_params.items())
        rows = events_for(request.membership, params).order_by("created_at", "seq")[:EXPORT_LIMIT]  # type: ignore[attr-defined]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["time", "seq", "actor", "actor_type", "action", "target_type", "target_id", "reason"]
        )
        count = 0
        for e in rows:
            writer.writerow(
                [
                    cell(e.created_at.isoformat()),
                    cell(e.seq),
                    cell(e.actor.email if e.actor else ""),
                    cell(e.actor_type),
                    cell(e.action),
                    cell(e.target_type),
                    cell(e.target_id),
                    cell(e.reason),
                ]
            )
            count += 1
        audit.record(
            actor=request.user,
            action="audit.exported",
            target=("organisation", str(request.membership.organisation_id)),  # type: ignore[attr-defined]
            organisation=request.membership.organisation_id,  # type: ignore[attr-defined]
            after={"rows": count, "filters": {k: str(v)[:100] for k, v in params.items()}},
        )
        response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="audit-events.csv"'
        return response


class HRReconstructView(APIView):
    """Everything needed to explain one application's assessment and decisions."""

    permission_classes = [HasOrgAction("applications.reconstruct")]

    @extend_schema(
        operation_id="hr_application_reconstruct",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request, application_id: str) -> Response:
        from apps.applications.reconstruct import bundle

        body = bundle(request.membership, application_id)  # type: ignore[attr-defined]
        audit.log_view(request.membership, ("application", application_id), action="reconstruct")  # type: ignore[attr-defined]
        audit.record(
            actor=request.user,
            action="application.reconstructed",
            target=("application", str(application_id)),
            organisation=request.membership.organisation_id,  # type: ignore[attr-defined]
            after={"identity_hidden": body["identity_hidden"]},
        )
        return Response(body)


class HRReconstructPdfView(APIView):
    permission_classes = [HasOrgAction("applications.reconstruct")]

    @extend_schema(
        operation_id="hr_application_reconstruct_pdf",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, application_id: str) -> HttpResponse:
        from apps.applications.reconstruct import bundle
        from apps.applications.reconstruct_pdf import render

        body = bundle(request.membership, application_id)  # type: ignore[attr-defined]
        audit.log_view(request.membership, ("application", application_id), action="reconstruct")  # type: ignore[attr-defined]
        audit.record(
            actor=request.user,
            action="application.reconstructed",
            target=("application", str(application_id)),
            organisation=request.membership.organisation_id,  # type: ignore[attr-defined]
            after={"identity_hidden": body["identity_hidden"], "format": "pdf"},
        )
        response = HttpResponse(render(body), content_type="application/pdf")
        ref = body["application"]["reference"] or "application"
        response["Content-Disposition"] = f'attachment; filename="reconstruction-{ref}.pdf"'
        return response
