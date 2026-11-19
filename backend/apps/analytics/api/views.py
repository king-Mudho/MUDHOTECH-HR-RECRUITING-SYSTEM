"""GET /hr/reports/recruitment (docs/04) and the on-demand refresh. HR managers and admins."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError
from apps.organisations.permissions import HasOrgAction

from .. import exports, selectors, services
from . import serializers as s

FILTERS = ("from", "to", "department", "job")


def _check_refs(organisation_id: Any, params: dict[str, Any]) -> None:
    """A department or vacancy of another organisation is simply not found."""
    from apps.jobs.models import Job
    from apps.organisations.models import Department

    try:
        if (
            params.get("job")
            and not Job.objects.for_org(organisation_id).filter(pk=params["job"]).exists()
        ):
            raise NotFoundError()
        if (
            params.get("department")
            and not Department.objects.for_org(organisation_id)
            .filter(pk=params["department"])
            .exists()
        ):
            raise NotFoundError()
    except (ValueError, TypeError) as exc:  # malformed UUID
        raise NotFoundError() from exc


class RecruitmentReportView(APIView):
    permission_classes = [HasOrgAction("reports.view")]

    @extend_schema(
        operation_id="hr_reports_recruitment",
        parameters=[
            OpenApiParameter("from", str, description="Local date, inclusive (default: 90 days)"),
            OpenApiParameter("to", str, description="Local date, inclusive (default: today)"),
            OpenApiParameter("department", str),
            OpenApiParameter("job", str),
        ],
        responses=s.RecruitmentReportSerializer,
    )
    def get(self, request: Request) -> Response:
        from django.core.exceptions import ValidationError

        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        params = {k: request.query_params.get(k) for k in FILTERS if request.query_params.get(k)}
        try:
            _check_refs(org_id, params)
        except ValidationError as exc:
            raise NotFoundError() from exc
        if params:
            data = services._jsonable(selectors.report(selectors.scope_from(org_id, params)))
            origin = "live"
        else:
            data, origin = services.default_report(org_id)
        return Response(s.RecruitmentReportSerializer({**data, "origin": origin}).data)


class RecruitmentReportRefreshView(APIView):
    permission_classes = [HasOrgAction("reports.view")]

    @extend_schema(
        operation_id="hr_reports_recruitment_refresh",
        request=None,
        responses=s.RecruitmentReportSerializer,
    )
    def post(self, request: Request) -> Response:
        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        data = services.refresh(org_id)
        return Response(s.RecruitmentReportSerializer({**data, "origin": "live"}).data)


# --- exports (P13-T06) --------------------------------------------------------------------------
class ExportListView(APIView):
    permission_classes = [HasOrgAction("reports.export")]

    @extend_schema(operation_id="hr_exports", responses=s.ExportJobSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = exports.visible(request.membership).order_by("-created_at")[:20]  # type: ignore[attr-defined]
        return Response(s.ExportJobSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="hr_exports_create",
        request=s.ExportRequestSerializer,
        responses={202: s.ExportJobSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.ExportRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        job = exports.request_export(
            request.membership,  # type: ignore[attr-defined]
            kind=v["kind"],
            fmt=v["format"],
            blind=v["blind"],
            params={
                "job": v["job"],
                "department": v["department"],
                "from": v["date_from"],
                "to": v["date_to"],
            },
        )
        return Response(s.ExportJobSerializer(job).data, status=202)


class ExportDetailView(APIView):
    permission_classes = [HasOrgAction("reports.export")]

    @extend_schema(operation_id="hr_export", responses=s.ExportJobSerializer)
    def get(self, request: Request, export_id: str) -> Response:
        job = exports.visible(request.membership).filter(pk=export_id).first()  # type: ignore[attr-defined]
        if job is None:
            raise NotFoundError()
        return Response(s.ExportJobSerializer(job).data)


class ExportDownloadView(APIView):
    permission_classes = [HasOrgAction("reports.export")]

    @extend_schema(
        operation_id="hr_export_download", request=None, responses=s.ExportDownloadSerializer
    )
    def post(self, request: Request, export_id: str) -> Response:
        job, url = exports.download_url(request.membership, export_id)  # type: ignore[attr-defined]
        body = {"url": url, "filename": job.filename, "expires_in": exports.LINK_TTL}
        return Response(s.ExportDownloadSerializer(body).data)
