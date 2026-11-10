from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.models import Application, ApplicationDocument, DocumentRole
from apps.core.serializers import StrictSerializer


class JobBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    organisation_name = serializers.CharField()
    closes_at = serializers.DateTimeField(allow_null=True)
    timezone = serializers.CharField()


class NoticesSerializer(serializers.Serializer):
    privacy_notice = serializers.CharField()
    privacy_notice_version = serializers.CharField()
    ai_notice_version = serializers.CharField()
    ai_notice_url = serializers.CharField()


class ApplicationSerializer(serializers.ModelSerializer):
    job = serializers.SerializerMethodField()
    notices = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "reference",
            "status",
            "job",
            "contact",
            "last_step",
            "submitted_at",
            "withdrawn_at",
            "objects_to_automated_processing",
            "notices",
            "lock_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(NoticesSerializer)
    def get_notices(self, obj: Application) -> dict[str, str]:
        from apps.privacy import services as privacy

        version, text = privacy.privacy_notice_version(obj.organisation_id)
        return {
            "privacy_notice": text,
            "privacy_notice_version": version,
            "ai_notice_version": privacy.ai_notice_version(),
            "ai_notice_url": "/how-we-use-ai",
        }

    @extend_schema_field(JobBriefSerializer)
    def get_job(self, obj: Application) -> dict[str, Any]:
        return {
            "id": obj.job_id,
            "slug": obj.job.slug,
            "title": obj.job.title,
            "organisation_name": obj.organisation.name,
            "closes_at": obj.job.closes_at,
            "timezone": obj.job.timezone,
        }


class StartSerializer(StrictSerializer):
    job_id = serializers.UUIDField()
    source = serializers.DictField(  # type: ignore[assignment]
        child=serializers.CharField(max_length=200), required=False
    )


class ContactSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    preferred_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)


class DraftPatchSerializer(StrictSerializer):
    lock_version = serializers.IntegerField(min_value=1)
    contact = ContactSerializer(required=False)
    last_step = serializers.IntegerField(min_value=1, max_value=6, required=False)


class AttachItemSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=DocumentRole.choices)
    required_doc_key = serializers.CharField(max_length=40, required=False, allow_blank=True)


class AttachSerializer(StrictSerializer):
    documents = AttachItemSerializer(many=True, max_length=20)  # type: ignore[call-arg]


class AnswerItemSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=60)
    value = serializers.JSONField(allow_null=True)


class AnswersSerializer(StrictSerializer):
    answers = AnswerItemSerializer(many=True, max_length=60)  # type: ignore[call-arg]


class AttachedDocumentSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="document.original_filename", read_only=True)
    scan_status = serializers.CharField(source="document.scan_status", read_only=True)
    size_bytes = serializers.IntegerField(source="document.size_bytes", read_only=True)

    class Meta:
        model = ApplicationDocument
        fields = ["document", "role", "required_doc_key", "filename", "scan_status", "size_bytes"]
        read_only_fields = fields


class MissingItemSerializer(serializers.Serializer):
    step = serializers.CharField()
    code = serializers.CharField()
    key = serializers.CharField()


class ReviewSerializer(serializers.Serializer):
    application = ApplicationSerializer()
    ready = serializers.BooleanField()
    missing = MissingItemSerializer(many=True)
    visible_questions = serializers.ListField(child=serializers.CharField())
    documents = AttachedDocumentSerializer(many=True)
    answers = serializers.DictField(child=serializers.JSONField(allow_null=True))


class SubmitSerializer(StrictSerializer):
    accept_privacy = serializers.BooleanField()
    objects_to_automated_processing = serializers.BooleanField(required=False, default=False)


class SubmitResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField()
    submitted_at = serializers.DateTimeField()
    status = serializers.CharField()


class WithdrawSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class TimelineEntrySerializer(serializers.Serializer):
    status = serializers.CharField()
    at = serializers.DateTimeField()
    note = serializers.CharField(allow_blank=True)


# Internal steps candidates don't need to see separately (they stay "submitted / under review").
CANDIDATE_STATUS = {
    "processing": "submitted",
    "processing_error": "submitted",
    "on_hold": "under_review",
}


def candidate_timeline(app: Any) -> list[dict[str, Any]]:
    """Status history as the candidate sees it: no staff names, no internal reasons."""
    from apps.applications.models import ApplicationStatusEvent

    out: list[dict[str, Any]] = []
    for e in ApplicationStatusEvent.objects.for_org(app.organisation_id).filter(application=app):
        shown = CANDIDATE_STATUS.get(e.to_status, e.to_status)
        if out and out[-1]["status"] == shown:
            continue
        note = e.reason_text if e.to_status == "withdrawn" else ""
        out.append({"status": shown, "at": e.at, "note": note})
    return out
