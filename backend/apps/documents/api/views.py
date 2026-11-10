"""Document upload/download APIs (docs/04 Candidate profile & documents)."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponseRedirect
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.serializers import StrictSerializer
from apps.documents import services
from apps.documents.models import Document, Purpose


class UploadSessionCreateSerializer(StrictSerializer):
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    filename = serializers.CharField(max_length=255)
    mime = serializers.CharField(max_length=120)
    size = serializers.IntegerField(min_value=1)


class UploadSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.CharField()
    method = serializers.CharField()
    headers = serializers.DictField(child=serializers.CharField())
    expires_at = serializers.DateTimeField()
    filename = serializers.CharField()


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "purpose",
            "original_filename",
            "mime_detected",
            "size_bytes",
            "page_count",
            "scan_status",
            "rejected_reason",
            "scanned_at",
            "created_at",
        ]
        read_only_fields = fields


class DirectUploadSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    file = serializers.FileField()


class _UploadThrottle(ScopedRateThrottle):
    scope = "uploads"


class UploadSessionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [_UploadThrottle]

    @extend_schema(
        operation_id="documents_upload_session_create",
        request=UploadSessionCreateSerializer,
        responses={201: UploadSessionSerializer},
    )
    def post(self, request: Request) -> Response:
        ser = UploadSessionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        session, presigned = services.create_session(
            authed_user(request),
            purpose=d["purpose"],
            filename=d["filename"],
            mime=d["mime"],
            size=d["size"],
        )
        body = {
            "id": session.pk,
            "url": presigned["url"],
            "method": presigned["method"],
            "headers": presigned["headers"],
            "expires_at": session.expires_at,
            "filename": session.declared_name,
        }
        return Response(UploadSessionSerializer(body).data, status=status.HTTP_201_CREATED)


class UploadCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="documents_upload_session_complete",
        request=None,
        responses={201: DocumentSerializer},
    )
    def post(self, request: Request, session_id: str) -> Response:
        doc = services.complete_session(authed_user(request), session_id)
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DirectUploadView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [_UploadThrottle]
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="documents_direct_upload",
        request={"multipart/form-data": DirectUploadSerializer},
        responses={201: DocumentSerializer},
    )
    def post(self, request: Request) -> Response:
        ser = DirectUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc = services.direct_upload(
            authed_user(request),
            purpose=ser.validated_data["purpose"],
            uploaded=ser.validated_data["file"],
        )
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="documents_retrieve", responses=DocumentSerializer)
    def get(self, request: Request, document_id: str) -> Response:
        return Response(
            DocumentSerializer(services.get_document(authed_user(request), document_id)).data
        )


class DocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="documents_download",
        responses={302: OpenApiResponse(description="Redirect to a 60-second presigned URL")},
    )
    def get(self, request: Request, document_id: str) -> Any:
        url = services.download_url(authed_user(request), document_id)
        response = HttpResponseRedirect(url)
        response["Cache-Control"] = "no-store"
        return response
