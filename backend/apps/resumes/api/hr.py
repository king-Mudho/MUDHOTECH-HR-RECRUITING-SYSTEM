"""HR extraction panel endpoints (P06-T14). Org context via ``X-Org-Id``; RBAC per action."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.organisations.permissions import HasOrgAction
from apps.resumes import hr

from .serializers import ClaimViewSerializer


class HRCorrectionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    values = serializers.DictField(child=serializers.CharField(allow_blank=True))
    remove = serializers.BooleanField()
    note = serializers.CharField(allow_blank=True)


class HRClaimSerializer(ClaimViewSerializer):
    id = serializers.UUIDField()
    section = serializers.CharField(allow_blank=True)
    method = serializers.CharField()
    confidence = serializers.ChoiceField(choices=["high", "medium", "low"])
    inferred = serializers.BooleanField()
    corrections = HRCorrectionSerializer(many=True)


class HRRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    filename = serializers.CharField()
    status = serializers.CharField()
    error_code = serializers.CharField(allow_blank=True)
    flags = serializers.ListField(child=serializers.CharField())
    language = serializers.CharField(allow_blank=True)
    quality_score = serializers.FloatField(allow_null=True)
    page_count = serializers.IntegerField(allow_null=True)
    attempts = serializers.IntegerField()
    finished_at = serializers.DateTimeField(allow_null=True)
    set_aside = serializers.IntegerField()
    claims = HRClaimSerializer(many=True)


class HRExtractionSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    status = serializers.CharField()
    flags = serializers.ListField(child=serializers.CharField())
    manual_review_requested = serializers.BooleanField()
    can_retry = serializers.BooleanField()
    runs = HRRunSerializer(many=True)


class HRExtractionView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_application_extraction", responses=HRExtractionSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        view = hr.hr_view(request.membership, application_id)  # type: ignore[attr-defined]
        audit.log_view(request.membership, ("application", application_id), action="extraction")  # type: ignore[attr-defined]
        return Response(HRExtractionSerializer(view).data)


class HRRetryProcessingView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_application_retry_processing",
        request=None,
        responses=HRExtractionSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        view = hr.retry(request.membership, authed_user(request), application_id)  # type: ignore[attr-defined]
        return Response(HRExtractionSerializer(view).data)


# ------------------------------------------------------------------ evidence viewer (P08-T06)
class EvidenceHighlightSerializer(serializers.Serializer):
    claim_id = serializers.UUIDField()
    type = serializers.CharField()
    page = serializers.IntegerField()
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    criteria = serializers.ListField(child=serializers.UUIDField())


class EvidencePageSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    text = serializers.CharField(allow_blank=True)


class EvidenceDocumentSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    filename = serializers.CharField()
    mime = serializers.CharField()
    original_available = serializers.BooleanField()
    pages = EvidencePageSerializer(many=True)
    highlights = EvidenceHighlightSerializer(many=True)


class EvidenceTextSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    identity_hidden = serializers.BooleanField()
    documents = EvidenceDocumentSerializer(many=True)


class HREvidenceTextView(APIView):
    """CV text page by page with evidence spans; contact/personal details masked."""

    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_application_evidence_text", responses=EvidenceTextSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        from apps.resumes.evidence_view import evidence_text

        body = evidence_text(request.membership, application_id)  # type: ignore[attr-defined]
        audit.log_view(request.membership, ("application", application_id), action="cv_text")  # type: ignore[attr-defined]
        return Response(EvidenceTextSerializer(body).data)
