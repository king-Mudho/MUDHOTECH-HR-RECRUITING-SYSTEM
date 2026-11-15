"""Candidate extraction API shapes (P06-T13). Plain summaries only: no scores or confidences."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class ClaimViewSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    type = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    dates = serializers.CharField(allow_blank=True)
    detail = serializers.CharField(allow_blank=True)
    snippet = serializers.CharField(allow_blank=True)
    page = serializers.IntegerField(allow_null=True)
    excluded = serializers.BooleanField()
    excluded_reason = serializers.CharField(allow_blank=True)


class ResumeExtractionSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    status = serializers.CharField()
    error_code = serializers.CharField(allow_blank=True)
    flags = serializers.ListField(child=serializers.CharField())
    imported_at = serializers.DateTimeField(allow_null=True)
    claims = ClaimViewSerializer(many=True)


class ImportRequestSerializer(StrictSerializer):
    confirm = serializers.BooleanField()
    indexes = serializers.ListField(
        child=serializers.IntegerField(min_value=0), min_length=1, max_length=200
    )

    def validate_confirm(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError("Please confirm before we change your profile.")
        return value


class ImportResultSerializer(serializers.Serializer):
    experiences = serializers.IntegerField()
    educations = serializers.IntegerField()
    certifications = serializers.IntegerField()
    skills = serializers.IntegerField()
    languages = serializers.IntegerField()
    skipped = serializers.IntegerField()


class CorrectionViewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    values = serializers.DictField(child=serializers.CharField(allow_blank=True))
    remove = serializers.BooleanField()


class ApplicationClaimSerializer(ClaimViewSerializer):
    id = serializers.UUIDField()
    correctable = serializers.BooleanField()
    corrections = CorrectionViewSerializer(many=True)


class ApplicationRunSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    filename = serializers.CharField()
    status = serializers.CharField()
    error_code = serializers.CharField(allow_blank=True)
    flags = serializers.ListField(child=serializers.CharField())
    claims = ApplicationClaimSerializer(many=True)


class ApplicationExtractionSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    objected = serializers.BooleanField()
    runs = ApplicationRunSerializer(many=True)


class CorrectionRequestSerializer(StrictSerializer):
    values = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=300), required=False, default=dict
    )
    remove = serializers.BooleanField(default=False)
    note = serializers.CharField(allow_blank=True, max_length=1000, required=False, default="")
