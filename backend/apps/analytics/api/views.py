"""GET /hr/reports/recruitment (docs/04) and the on-demand refresh. HR managers and admins."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError
from apps.organisations.permissions import HasOrgAction

from .. import selectors, services
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
