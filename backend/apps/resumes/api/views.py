"""Candidate extraction endpoints (P06-T13). Owner-only: other people's documents are 404."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.resumes import candidate
from apps.resumes.models import RunStatus

from . import serializers as s


class ResumeExtractionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_resume_extraction",
        responses={200: s.ResumeExtractionSerializer, 202: s.ResumeExtractionSerializer},
    )
    def get(self, request: Request, document_id: str) -> Response:
        """What we read from one of your CVs. 202 while it is still being read (poll again)."""
        parse = candidate.preview(authed_user(request), document_id)
        body = s.ResumeExtractionSerializer(candidate.preview_view(parse)).data
        pending = parse.status in (RunStatus.PENDING, RunStatus.RUNNING)
        return Response(body, status=202 if pending else 200)


class ResumeImportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_resume_import",
        request=s.ImportRequestSerializer,
        responses=s.ImportResultSerializer,
    )
    def post(self, request: Request, document_id: str) -> Response:
        data = s.ImportRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = candidate.import_to_profile(
            authed_user(request), document_id, data.validated_data["indexes"]
        )
        return Response(s.ImportResultSerializer(result).data)


class ApplicationExtractionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_application_extraction",
        responses=s.ApplicationExtractionSerializer,
    )
    def get(self, request: Request, application_id: str) -> Response:
        view = candidate.application_view(authed_user(request), application_id)
        return Response(s.ApplicationExtractionSerializer(view).data)


class ClaimCorrectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_claim_correction",
        request=s.CorrectionRequestSerializer,
        responses={201: s.CorrectionViewSerializer},
    )
    def post(self, request: Request, claim_id: str) -> Response:
        data = s.CorrectionRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        correction = candidate.correct(
            authed_user(request), claim_id, fields=v["values"], remove=v["remove"], note=v["note"]
        )
        return Response(
            s.CorrectionViewSerializer(
                {
                    "id": correction.pk,
                    "status": correction.status,
                    "created_at": correction.created_at,
                    "values": {k: str(x) for k, x in v["values"].items()},
                    "remove": v["remove"],
                }
            ).data,
            status=201,
        )
