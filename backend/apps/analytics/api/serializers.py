"""Response shapes of the recruitment report (OpenAPI + generated frontend types)."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class DurationStatsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    median_hours = serializers.FloatField(allow_null=True)
    mean_hours = serializers.FloatField(allow_null=True)
    p90_hours = serializers.FloatField(allow_null=True)


class TimingSerializer(serializers.Serializer):
    time_to_review = DurationStatsSerializer()
    time_to_shortlist = DurationStatsSerializer()
    time_to_hire = DurationStatsSerializer()


class ReportFunnelStageSerializer(serializers.Serializer):
    stage = serializers.CharField()
    count = serializers.IntegerField()
    conversion = serializers.FloatField(allow_null=True)


class ReportFunnelSerializer(serializers.Serializer):
    stages = ReportFunnelStageSerializer(many=True)
    withdrawn = serializers.IntegerField()


class SourceRowSerializer(serializers.Serializer):
    source = serializers.CharField()  # type: ignore[assignment]
    applications = serializers.IntegerField()
    shortlisted = serializers.IntegerField()


class StepRowSerializer(serializers.Serializer):
    step = serializers.CharField()
    unfinished = serializers.IntegerField()


class QuestionRowSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    key = serializers.CharField()
    prompt = serializers.CharField()
    required = serializers.BooleanField()  # type: ignore[assignment]
    answered = serializers.IntegerField()
    started = serializers.IntegerField()
    drop_off = serializers.FloatField(allow_null=True)


class QuestionnaireStatsSerializer(serializers.Serializer):
    started = serializers.IntegerField()
    submitted = serializers.IntegerField()
    unfinished = serializers.IntegerField()
    unfinished_by_step = StepRowSerializer(many=True)
    questions = QuestionRowSerializer(many=True)


class ProcessingStatsSerializer(serializers.Serializer):
    extraction_runs = serializers.IntegerField()
    parse_failure_rate = serializers.FloatField(allow_null=True)
    partial_rate = serializers.FloatField(allow_null=True)
    ocr_rate = serializers.FloatField(allow_null=True)
    mean_extraction_seconds = serializers.FloatField(allow_null=True)
    submission_to_evaluation = DurationStatsSerializer()


class OverrideRowSerializer(serializers.Serializer):
    decisions = serializers.IntegerField()
    overrides = serializers.IntegerField()
    override_rate = serializers.FloatField(allow_null=True)


class BandOverrideSerializer(OverrideRowSerializer):
    band = serializers.CharField()


class JobOverrideSerializer(OverrideRowSerializer):
    job_id = serializers.UUIDField()


class AIAgreementSerializer(serializers.Serializer):
    decisions = serializers.IntegerField()
    overrides = serializers.IntegerField()
    override_rate = serializers.FloatField(allow_null=True)
    agreement_rate = serializers.FloatField(allow_null=True)
    by_band = BandOverrideSerializer(many=True)
    by_job = JobOverrideSerializer(many=True)
    claim_verification_override_rate = serializers.FloatField(allow_null=True)
    evaluations = serializers.IntegerField()


class ClarificationStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    answered = serializers.IntegerField()
    expired = serializers.IntegerField()
    open = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    response_rate = serializers.FloatField(allow_null=True)
    time_to_answer = DurationStatsSerializer()


class ReportScopeSerializer(serializers.Serializer):
    from_ = serializers.DateField()
    to = serializers.DateField()
    department = serializers.UUIDField(allow_null=True)
    job = serializers.UUIDField(allow_null=True)

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["from"] = fields.pop("from_")
        return fields


class RecruitmentReportSerializer(serializers.Serializer):
    scope = ReportScopeSerializer()
    computed_at = serializers.DateTimeField()
    origin = serializers.ChoiceField(choices=["snapshot", "live"])
    applications = serializers.IntegerField()
    timing = TimingSerializer()
    funnel = ReportFunnelSerializer()
    sources = SourceRowSerializer(many=True)
    questionnaire = QuestionnaireStatsSerializer()
    processing = ProcessingStatsSerializer()
    ai_agreement = AIAgreementSerializer()
    clarifications = ClarificationStatsSerializer()


class ExportRequestSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=["applicants", "report"])
    format = serializers.ChoiceField(choices=["csv", "xlsx", "pdf"])
    blind = serializers.BooleanField(required=False, default=False)
    job = serializers.UUIDField(required=False, allow_null=True, default=None)
    department = serializers.UUIDField(required=False, allow_null=True, default=None)
    date_from = serializers.DateField(required=False, allow_null=True, default=None)
    date_to = serializers.DateField(required=False, allow_null=True, default=None)


class ExportJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    format = serializers.CharField()
    blind = serializers.BooleanField()
    params = serializers.DictField(child=serializers.CharField())
    status = serializers.CharField()
    row_count = serializers.IntegerField()
    error = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)


class ExportDownloadSerializer(serializers.Serializer):
    url = serializers.URLField()
    filename = serializers.CharField()
    expires_in = serializers.IntegerField()
