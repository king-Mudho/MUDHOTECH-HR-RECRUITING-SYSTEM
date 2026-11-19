"""Interview API serializers (P12-T06). Input serializers are strict (unknown fields rejected)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.core.serializers import StrictSerializer

from ..models import InterviewMode, PanelRole, Recommendation


class PanelMemberInSerializer(StrictSerializer):
    membership_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=PanelRole.choices, default=PanelRole.MEMBER)


class InterviewCreateSerializer(StrictSerializer):
    stage = serializers.CharField(max_length=60)
    mode = serializers.ChoiceField(choices=InterviewMode.choices)
    panel = PanelMemberInSerializer(many=True, min_length=1, max_length=10)  # type: ignore[call-arg]
    starts_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    slots = serializers.ListField(
        child=serializers.DateTimeField(), required=False, default=list, max_length=12
    )
    duration_minutes = serializers.IntegerField(min_value=5, max_value=480, default=45)
    timezone = serializers.CharField(max_length=64, default="Africa/Harare")
    location = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    video_link = serializers.URLField(max_length=500, required=False, allow_blank=True, default="")
    instructions = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )
    scorecard_template_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class RescheduleSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)
    starts_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    slots = serializers.ListField(
        child=serializers.DateTimeField(), required=False, default=list, max_length=12
    )


class InterviewReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class InterviewNoteSerializer(StrictSerializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ScorecardTemplateCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    extra_competencies = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, default=list, max_length=10
    )


class ScorecardInSerializer(StrictSerializer):
    scores = serializers.DictField(child=serializers.IntegerField(), required=False)
    criterion_notes = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=2000), required=False
    )
    overall = serializers.IntegerField(required=False, allow_null=True)
    recommendation = serializers.ChoiceField(
        choices=Recommendation.choices, required=False, allow_blank=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class InterviewBookSerializer(StrictSerializer):
    slot_id = serializers.UUIDField()


# --- output ---------------------------------------------------------------------------------------
class InterviewSlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    booked = serializers.BooleanField()


class PanelistSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    submitted = serializers.BooleanField()


class InterviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    job_id = serializers.UUIDField()
    job_title = serializers.CharField()
    stage = serializers.CharField()
    mode = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    video_link = serializers.CharField(allow_blank=True)
    duration_minutes = serializers.IntegerField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    timezone = serializers.CharField()
    status = serializers.CharField()
    status_reason = serializers.CharField(allow_blank=True)
    instructions = serializers.CharField(allow_blank=True)
    scorecard_template_id = serializers.UUIDField(allow_null=True)
    sequence = serializers.IntegerField()
    slots = InterviewSlotSerializer(many=True)
    panel = PanelistSerializer(many=True)


class PanelConflictSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()
    interview_id = serializers.UUIDField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)


class ScheduledSerializer(serializers.Serializer):
    interview = InterviewSerializer()
    conflicts = PanelConflictSerializer(many=True)


class ScorecardCriterionSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    source_criterion_id = serializers.UUIDField(allow_null=True)


class ScorecardTemplateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    name = serializers.CharField()
    criteria = ScorecardCriterionSerializer(many=True)
    locked = serializers.BooleanField()


class PanelAiHintSerializer(serializers.Serializer):
    band = serializers.CharField(allow_blank=True)
    coverage = serializers.FloatField(allow_null=True)
    essentials_met = serializers.IntegerField(allow_null=True)
    essentials_unknown = serializers.IntegerField(allow_null=True)
    notice = serializers.CharField()


class PanelDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    filename = serializers.CharField()
    available = serializers.BooleanField()


class PanelViewSerializer(serializers.Serializer):
    interview = InterviewSerializer()
    documents = PanelDocumentSerializer(many=True)
    scorecard_criteria = ScorecardCriterionSerializer(many=True)
    ai = PanelAiHintSerializer(allow_null=True)
    can_manage = serializers.BooleanField()
    on_panel = serializers.BooleanField()


class ScorecardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    panelist = serializers.CharField()
    membership_id = serializers.UUIDField()
    own = serializers.BooleanField()
    scores = serializers.DictField(child=serializers.IntegerField())
    criterion_notes = serializers.DictField(child=serializers.CharField())
    overall = serializers.IntegerField(allow_null=True)
    recommendation = serializers.CharField(allow_blank=True)
    notes = serializers.CharField(allow_blank=True)
    submitted_at = serializers.DateTimeField(allow_null=True)


class FeedbackCriterionSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    count = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True)
    min = serializers.IntegerField(allow_null=True)
    max = serializers.IntegerField(allow_null=True)
    disagreement = serializers.BooleanField()


class ScorecardOutstandingSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()
    name = serializers.CharField()


class FeedbackSerializer(serializers.Serializer):
    interview_id = serializers.UUIDField()
    submitted = serializers.IntegerField()
    panel_size = serializers.IntegerField()
    outstanding = ScorecardOutstandingSerializer(many=True)
    criteria = FeedbackCriterionSerializer(many=True)
    overall_average = serializers.FloatField(allow_null=True)
    recommendations = serializers.DictField(child=serializers.IntegerField())


class CandidateInterviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    stage = serializers.CharField()
    mode = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    video_link = serializers.CharField(allow_blank=True)
    duration_minutes = serializers.IntegerField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    timezone = serializers.CharField()
    status = serializers.CharField()
    status_reason = serializers.CharField(allow_blank=True)
    instructions = serializers.CharField(allow_blank=True)
    slots = InterviewSlotSerializer(many=True)


def paginated(name: str, item: type[serializers.Serializer]) -> type[serializers.Serializer]:
    """``{count, next, previous, results}`` (StandardPagination) for the OpenAPI schema."""
    return type(
        name,
        (serializers.Serializer,),
        {
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item(many=True),
        },
    )


PaginatedInterviewSerializer = paginated("PaginatedInterviewList", InterviewSerializer)


def as_dict(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}
