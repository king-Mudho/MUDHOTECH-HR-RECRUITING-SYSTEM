"""HR screening endpoints (P07-T10..T12). Org context via ``X-Org-Id``; RBAC per action.

AI results are suggestions for a person to review: reading needs ``applications.view``,
starting runs and verifying claims need ``applications.transition``.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.core.exceptions import NotFoundError
from apps.organisations.permissions import HasOrgAction

from .. import analytics, runs, selectors, verification
from ..models import ScreeningRun
from . import serializers as s


def _run(run: ScreeningRun, *, failures: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": run.pk,
        "job_id": run.job_id,
        "job_version_id": run.job_version_id,
        "trigger": run.trigger,
        "scope": run.scope,
        "reason": run.reason,
        "status": run.status,
        "total": run.total,
        "done": run.done,
        "failed": run.failed,
        "progress": round(run.done / run.total, 3) if run.total else 1.0,
        "engine_version": run.engine_version,
        "config_version": run.config_version,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }
    if failures:
        body["failures"] = [
            {"application_id": a.pk, "status": a.status} for a in runs.failures(run)
        ]
    return body


class JobScreeningRunsView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "applications.view" if self.request.method == "GET" else "applications.transition"
        return [HasOrgAction(action)()]

    @extend_schema(
        operation_id="hr_screening_runs_list", responses=s.ScreeningRunSerializer(many=True)
    )
    def get(self, request: Request, job_id: str) -> Response:
        items = runs.runs_for(request.membership, job_id)  # type: ignore[attr-defined]
        return Response(s.ScreeningRunSerializer([_run(r) for r in items], many=True).data)

    @extend_schema(
        operation_id="hr_screening_runs_start",
        request=s.StartRunSerializer,
        responses={201: s.ScreeningRunDetailSerializer},
    )
    def post(self, request: Request, job_id: str) -> Response:
        data = s.StartRunSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        run = runs.start_run(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            job_id,
            scope=v["scope"],
            application_ids=v["application_ids"],
            reason=v["reason"],
            use_current_version=v["use_current_version"],
        )
        return Response(s.ScreeningRunDetailSerializer(_run(run, failures=True)).data, status=201)


class ScreeningRunView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_screening_run", responses=s.ScreeningRunDetailSerializer)
    def get(self, request: Request, run_id: str) -> Response:
        run = runs.run_detail(request.membership, run_id)  # type: ignore[attr-defined]
        return Response(s.ScreeningRunDetailSerializer(_run(run, failures=True)).data)


class JobScreeningAnalyticsView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_screening_analytics", responses=s.ScreeningAnalyticsSerializer)
    def get(self, request: Request, job_id: str) -> Response:
        body = analytics.vacancy_analytics(request.membership, job_id)  # type: ignore[attr-defined]
        return Response(s.ScreeningAnalyticsSerializer(body).data)


class ApplicationEvaluationView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_application_evaluation", responses=s.EvaluationSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        """The current evaluation (404 until the application has been evaluated)."""
        body = selectors.current_evaluation(request.membership, application_id)  # type: ignore[attr-defined]
        if body is None:
            raise NotFoundError()
        audit.log_view(request.membership, ("application", application_id), action="evaluation")  # type: ignore[attr-defined]
        return Response(s.EvaluationSerializer(body).data)


class ApplicationEvaluationsView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_application_evaluations",
        responses=s.EvaluationSummarySerializer(many=True),
    )
    def get(self, request: Request, application_id: str) -> Response:
        items = selectors.versions(request.membership, application_id)  # type: ignore[attr-defined]
        body = [
            {
                "id": e.pk,
                "version": e.version,
                "status": e.status,
                "trigger": e.trigger,
                "band": e.band,
                "total_score": (
                    float(e.total_score)
                    if e.total_score is not None and e.band != selectors.MANUAL
                    else None
                ),
                "created_at": e.created_at,
            }
            for e in items
        ]
        return Response(s.EvaluationSummarySerializer(body, many=True).data)


class ApplicationEvaluationVersionView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_application_evaluation_version", responses=s.EvaluationSerializer
    )
    def get(self, request: Request, application_id: str, version: int) -> Response:
        body = selectors.evaluation_version(request.membership, application_id, version)  # type: ignore[attr-defined]
        audit.log_view(request.membership, ("application", application_id), action="evaluation")  # type: ignore[attr-defined]
        return Response(s.EvaluationSerializer(body).data)


class ClaimVerifyView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_claim_verify",
        request=s.VerifySerializer,
        responses={201: s.VerificationSerializer},
    )
    def post(self, request: Request, claim_id: str) -> Response:
        data = s.VerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        verdict = verification.verify(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            claim_id,
            decision=v["decision"],
            values=v["values"],
            note=v["note"],
            reevaluate=v["reevaluate"],
            criterion_result_id=v["criterion_result_id"],
        )
        return Response(s.VerificationSerializer(_verdict(verdict)).data, status=201)


class ApplicationVerificationsView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(
        operation_id="hr_application_verifications",
        responses=s.VerificationSerializer(many=True),
    )
    def get(self, request: Request, application_id: str) -> Response:
        items = verification.verifications_for(request.membership, application_id)  # type: ignore[attr-defined]
        return Response(s.VerificationSerializer([_verdict(v) for v in items], many=True).data)


def _verdict(v: Any) -> dict[str, Any]:
    return {
        "id": v.pk,
        "claim_id": v.claim_id,
        "decision": v.decision,
        "note": v.note,
        "at": v.at,
        "verifier": v.verifier.full_name or v.verifier.email,
    }
