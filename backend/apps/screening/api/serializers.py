"""Screening API serializers (P07-T10..T12). Every AI output carries the human-review label."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer

from ..models import HumanVerification, ScreeningRun


class StartRunSerializer(StrictSerializer):
    scope = serializers.ChoiceField(choices=ScreeningRun.Scope.choices, default="pending")
    application_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=500
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    use_current_version = serializers.BooleanField(required=False, default=False)


class ScreeningFailureSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    status = serializers.CharField()


class ScreeningRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    job_version_id = serializers.UUIDField()
    trigger = serializers.CharField()
    scope = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    total = serializers.IntegerField()
    done = serializers.IntegerField()
    failed = serializers.IntegerField()
    progress = serializers.FloatField()
    engine_version = serializers.CharField()
    config_version = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class ScreeningRunDetailSerializer(ScreeningRunSerializer):
    failures = ScreeningFailureSerializer(many=True)


class EvaluationEvidenceSerializer(serializers.Serializer):
    claim_id = serializers.UUIDField(allow_null=True)
    question_response_id = serializers.UUIDField(allow_null=True)
    document_id = serializers.UUIDField(allow_null=True)
    page = serializers.IntegerField(allow_null=True)
    snippet = serializers.CharField(allow_blank=True)


class CriterionResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    criterion_id = serializers.UUIDField()
    title = serializers.CharField()
    type = serializers.CharField()
    importance = serializers.CharField()
    category = serializers.CharField()
    score = serializers.FloatField(allow_null=True)
    assessable = serializers.BooleanField()
    evidence_status = serializers.CharField()
    match_method = serializers.CharField()
    confidence = serializers.FloatField()
    rationale = serializers.CharField(allow_blank=True)
    flags = serializers.ListField(child=serializers.CharField())
    evidence = EvaluationEvidenceSerializer(many=True)


class EvaluationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    status = serializers.CharField()
    trigger = serializers.CharField()
    band = serializers.CharField()
    total_score = serializers.FloatField(allow_null=True)
    created_at = serializers.DateTimeField()


class EvaluationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    status = serializers.CharField()
    trigger = serializers.CharField()
    band = serializers.CharField()
    band_reasons = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()
    engine_version = serializers.CharField()
    config_version = serializers.CharField(allow_blank=True)
    llm_used = serializers.BooleanField()
    ai_notice = serializers.CharField()
    total_score = serializers.FloatField(allow_null=True)
    coverage = serializers.FloatField(allow_null=True)
    confidence = serializers.CharField(allow_null=True)
    flags = serializers.ListField(child=serializers.CharField())
    categories = serializers.ListField(child=serializers.DictField())
    essentials = serializers.DictField()
    conflicts = serializers.ListField(child=serializers.DictField())
    criteria = CriterionResultSerializer(many=True)
    explanation = serializers.ListField(child=serializers.DictField())
    summary = serializers.ListField(child=serializers.DictField())
    clarification_suggestions = serializers.ListField(child=serializers.DictField())


class VerifySerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=HumanVerification.Decision.choices)
    values = serializers.DictField(required=False, default=dict)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    reevaluate = serializers.BooleanField(required=False, default=False)
    criterion_result_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class VerificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    claim_id = serializers.UUIDField(allow_null=True)
    decision = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    at = serializers.DateTimeField()
    verifier = serializers.CharField()


class BandCountSerializer(serializers.Serializer):
    band = serializers.CharField()
    count = serializers.IntegerField()


class BucketSerializer(serializers.Serializer):
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    count = serializers.IntegerField()


class ScreeningWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    count = serializers.IntegerField()


class ScreeningAnalyticsSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    evaluated = serializers.IntegerField()
    bands = BandCountSerializer(many=True)
    score_buckets = BucketSerializer(many=True)
    median_score = serializers.FloatField(allow_null=True)
    low_coverage = serializers.IntegerField()
    high_scores = serializers.IntegerField()
    warnings = ScreeningWarningSerializer(many=True)
    ai_notice = serializers.CharField()
