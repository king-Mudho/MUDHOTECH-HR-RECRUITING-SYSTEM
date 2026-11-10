"""Candidate application APIs (docs/04 Applications, candidate side). Owner-only by construction."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.applications import services
from apps.core.exceptions import NotFoundError
from apps.core.idempotency import idempotent
from apps.jobs.models import Job

from . import serializers as s


class ApplicationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="applications_list", responses=s.ApplicationSerializer(many=True))
    def get(self, request: Request) -> Response:
        apps = services.own_applications(authed_user(request)).select_related("job", "organisation")
        return Response(s.ApplicationSerializer(apps.order_by("-updated_at")[:200], many=True).data)

    @extend_schema(
        operation_id="applications_start",
        request=s.StartSerializer,
        responses={201: s.ApplicationSerializer, 200: s.ApplicationSerializer},
    )
    def post(self, request: Request) -> Response:
        ser = s.StartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        job = Job.objects.unscoped().filter(pk=ser.validated_data["job_id"]).first()
        if job is None:
            raise NotFoundError()
        app, created = services.start_or_resume_draft(
            job, authed_user(request), source=ser.validated_data.get("source")
        )
        app = services.get_own(authed_user(request), app.pk)
        return Response(
            s.ApplicationSerializer(app).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ApplicationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="applications_retrieve", responses=s.ApplicationSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        return Response(
            s.ApplicationSerializer(services.get_own(authed_user(request), application_id)).data
        )

    @extend_schema(
        operation_id="applications_partial_update",
        request=s.DraftPatchSerializer,
        responses=s.ApplicationSerializer,
    )
    def patch(self, request: Request, application_id: str) -> Response:
        ser = s.DraftPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data: dict[str, Any] = dict(ser.validated_data)
        lock = data.pop("lock_version")
        if "contact" in data:
            data["contact"] = dict(data["contact"])
        app = services.update_draft(authed_user(request), application_id, data, lock_version=lock)
        return Response(
            s.ApplicationSerializer(services.get_own(authed_user(request), app.pk)).data
        )


def _review_response(request: Request, application_id: str) -> Response:
    return Response(s.ReviewSerializer(services.review(authed_user(request), application_id)).data)


class ApplicationDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_documents_set",
        request=s.AttachSerializer,
        responses=s.ReviewSerializer,
    )
    def put(self, request: Request, application_id: str) -> Response:
        ser = s.AttachSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = [dict(i) for i in ser.validated_data["documents"]]
        services.set_documents(authed_user(request), application_id, items)
        return _review_response(request, application_id)


class ApplicationAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_answers_upsert",
        request=s.AnswersSerializer,
        responses=s.ReviewSerializer,
    )
    def put(self, request: Request, application_id: str) -> Response:
        ser = s.AnswersSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = [dict(i) for i in ser.validated_data["answers"]]
        services.upsert_answers(authed_user(request), application_id, items)
        return _review_response(request, application_id)


class ApplicationReviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="applications_review", responses=s.ReviewSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        return _review_response(request, application_id)


class ApplicationSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_submit",
        request=s.SubmitSerializer,
        responses={201: s.SubmitResultSerializer},
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description="UUID per user attempt (EC-APP-04)",
            )
        ],
    )
    @idempotent(endpoint="applications.submit")
    def post(self, request: Request, application_id: str) -> Response:
        ser = s.SubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        app = services.submit(
            authed_user(request),
            application_id,
            accept_privacy=ser.validated_data["accept_privacy"],
            objects_to_automated_processing=ser.validated_data["objects_to_automated_processing"],
            ip=request.META.get("REMOTE_ADDR"),
        )
        body = {
            "id": app.pk,
            "reference": app.reference,
            "submitted_at": app.submitted_at,
            "status": app.status,
        }
        return Response(s.SubmitResultSerializer(body).data, status=status.HTTP_201_CREATED)


class ApplicationWithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="applications_withdraw",
        request=s.WithdrawSerializer,
        responses=s.ApplicationSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        from apps.applications import lifecycle

        ser = s.WithdrawSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authed_user(request)
        app = lifecycle.withdraw(user, application_id, ser.validated_data.get("reason", ""))
        return Response(s.ApplicationSerializer(services.get_own(user, app.pk)).data)
