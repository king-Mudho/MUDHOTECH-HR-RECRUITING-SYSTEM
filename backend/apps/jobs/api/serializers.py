"""HR job API serializers (P03-T11). Inputs are strict; organisation/status never writable."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.jobs.models import (
    Currency,
    EmploymentType,
    Job,
    JobAssignment,
    JobCriterion,
    JobEvent,
    JobVersion,
    SalaryPeriod,
    Seniority,
    Visibility,
    WorkplaceType,
)


# ---------------------------------------------------------------------------------- inputs
class JobWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200)
    reference_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    visibility = serializers.ChoiceField(choices=Visibility.choices, required=False)
    workplace_type = serializers.ChoiceField(choices=WorkplaceType.choices, required=False)
    employment_type = serializers.ChoiceField(choices=EmploymentType.choices, required=False)
    seniority = serializers.ChoiceField(choices=Seniority.choices, required=False, allow_blank=True)
    openings = serializers.IntegerField(min_value=1, max_value=1000, required=False)
    closes_at = serializers.DateTimeField(required=False, allow_null=True)
    timezone = serializers.CharField(max_length=64, required=False)
    salary_min = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    salary_max = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    salary_currency = serializers.ChoiceField(choices=Currency.choices, required=False)
    salary_period = serializers.ChoiceField(choices=SalaryPeriod.choices, required=False)
    salary_disclosed = serializers.BooleanField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    location_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=20
    )
    summary = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    responsibilities_html = serializers.CharField(
        max_length=20000, required=False, allow_blank=True
    )
    requirements_html = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    benefits_html = serializers.CharField(max_length=20000, required=False, allow_blank=True)
    required_documents = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=10
    )
    change_note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class JobPatchSerializer(JobWriteSerializer):
    title = serializers.CharField(max_length=200, required=False)
    lock_version = serializers.IntegerField(min_value=1)


class LockedListSerializer(StrictSerializer):
    lock_version = serializers.IntegerField(min_value=1, required=False)


class CriterionInputSerializer(StrictSerializer):
    type = serializers.CharField(max_length=16)
    importance = serializers.CharField(max_length=16)
    title = serializers.CharField(max_length=200, allow_blank=True)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    evidence_guidance = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    justification = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    skill_id = serializers.UUIDField(required=False, allow_null=True)
    qualification_level_id = serializers.UUIDField(required=False, allow_null=True)
    min_months = serializers.IntegerField(required=False, allow_null=True)
    equivalents = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, max_length=20
    )
    rubric_category = serializers.CharField(max_length=16, required=False, allow_blank=True)
    weight_within_category = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False
    )


class CriteriaInputSerializer(LockedListSerializer):
    criteria = CriterionInputSerializer(many=True)


class RubricBandSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    descriptor = serializers.CharField(max_length=300)


class RubricCategorySerializer(serializers.Serializer):
    key = serializers.CharField(max_length=16)
    label = serializers.CharField(max_length=100, required=False)  # type: ignore[assignment]
    weight = serializers.IntegerField()
    bands = RubricBandSerializer(many=True)


class RubricInputSerializer(LockedListSerializer):
    categories = RubricCategorySerializer(many=True)


class RubricOutSerializer(serializers.Serializer):
    categories = RubricCategorySerializer(many=True)
    total_weight = serializers.IntegerField()
    status = serializers.CharField()


class QuestionOptionInputSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)  # type: ignore[assignment]
    value = serializers.CharField(max_length=100)
    points = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True
    )


class QuestionInputSerializer(StrictSerializer):
    key = serializers.CharField(max_length=60)
    section = serializers.CharField(max_length=120, required=False, allow_blank=True)
    type = serializers.CharField(max_length=24)
    prompt = serializers.CharField(max_length=1000, allow_blank=True)
    help_text = serializers.CharField(max_length=1000, required=False, allow_blank=True)  # type: ignore[assignment]
    required = serializers.BooleanField(required=False, default=True)  # type: ignore[assignment]
    config = serializers.DictField(required=False)
    branching = serializers.DictField(required=False)
    scoring = serializers.DictField(required=False)
    is_knockout = serializers.BooleanField(required=False, default=False)
    knockout_expected = serializers.JSONField(required=False, allow_null=True)
    criterion_id = serializers.UUIDField(required=False, allow_null=True)
    options = QuestionOptionInputSerializer(many=True, required=False)


class QuestionnaireInputSerializer(LockedListSerializer):
    questions = QuestionInputSerializer(many=True, max_length=60)  # type: ignore[call-arg]


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class CommentSerializer(StrictSerializer):
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ScheduleSerializer(StrictSerializer):
    publish_at = serializers.DateTimeField()


class ExtendSerializer(StrictSerializer):
    closes_at = serializers.DateTimeField()
    reason = serializers.CharField(max_length=1000)


class DuplicateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200, required=False)


class AssignmentInputSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()
    role_on_job = serializers.ChoiceField(choices=JobAssignment.RoleOnJob.choices)


class AssignmentsInputSerializer(StrictSerializer):
    assignments = AssignmentInputSerializer(many=True, max_length=50)  # type: ignore[call-arg]


class ProtectedExceptionSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000)


# --------------------------------------------------------------------------------- outputs
class CriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCriterion
        fields = [
            "id",
            "order",
            "type",
            "importance",
            "title",
            "description",
            "evidence_guidance",
            "justification",
            "skill",
            "qualification_level",
            "min_months",
            "equivalents",
            "rubric_category",
            "weight_within_category",
        ]
        read_only_fields = fields


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobVersion
        fields = [
            "id",
            "number",
            "status",
            "summary",
            "responsibilities_html",
            "requirements_html",
            "benefits_html",
            "required_documents",
            "change_note",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "created_at",
        ]
        read_only_fields = fields


class VersionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = JobVersion
        fields = [
            "id",
            "number",
            "status",
            "change_note",
            "submitted_at",
            "approved_at",
            "created_at",
        ]
        read_only_fields = fields


class QuestionOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    section = serializers.CharField()
    order = serializers.IntegerField()
    type = serializers.CharField()
    prompt = serializers.CharField()
    help_text = serializers.CharField()  # type: ignore[assignment]
    required = serializers.BooleanField()  # type: ignore[assignment]
    config = serializers.DictField()
    branching = serializers.DictField()
    scoring = serializers.DictField()
    is_knockout = serializers.BooleanField()
    knockout_expected = serializers.JSONField(allow_null=True)
    criterion_id = serializers.UUIDField(allow_null=True)
    protected_topic_flag = serializers.ListField(child=serializers.DictField())
    protected_exception_reason = serializers.CharField()
    options = QuestionOptionInputSerializer(many=True)


def question_out(q: Any) -> dict[str, Any]:
    return {
        "id": q.pk,
        "key": q.key,
        "section": q.section,
        "order": q.order,
        "type": q.type,
        "prompt": q.prompt,
        "help_text": q.help_text,
        "required": q.required,
        "config": {k: v for k, v in q.config.items() if k != "knockout_expected"},
        "branching": q.branching,
        "scoring": q.scoring,
        "is_knockout": q.is_knockout,
        "knockout_expected": q.config.get("knockout_expected"),
        "criterion_id": q.criterion_id,
        "protected_topic_flag": q.protected_topic_flag,
        "protected_exception_reason": q.protected_exception_reason,
        "options": [
            {"label": o.label, "value": o.value, "points": o.points} for o in q.options.all()
        ],
    }


class HRJobListSerializer(serializers.ModelSerializer):
    current_version = serializers.SerializerMethodField()
    department = serializers.UUIDField(source="department_id", allow_null=True, read_only=True)
    locations = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "slug",
            "title",
            "reference_code",
            "status",
            "visibility",
            "department",
            "locations",
            "workplace_type",
            "employment_type",
            "seniority",
            "openings",
            "closes_at",
            "timezone",
            "publish_at",
            "published_at",
            "closed_at",
            "current_version",
            "lock_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(VersionSummarySerializer(allow_null=True))
    def get_current_version(self, obj: Job) -> dict[str, Any] | None:
        v = obj.current_version
        return VersionSummarySerializer(v).data if v else None

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_locations(self, obj: Job) -> list[str]:
        return [str(loc.pk) for loc in obj.locations.all()]


class HRJobDetailSerializer(HRJobListSerializer):
    version = serializers.SerializerMethodField()
    published_version_number = serializers.SerializerMethodField()
    salary_min = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    salary_max = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    criteria = serializers.SerializerMethodField()
    rubric = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta(HRJobListSerializer.Meta):
        fields = [
            *HRJobListSerializer.Meta.fields,
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "salary_disclosed",
            "start_date",
            "close_reason",
            "published_version_number",
            "version",
            "criteria",
            "rubric",
            "questions",
        ]
        read_only_fields = fields

    @extend_schema_field(VersionSerializer(allow_null=True))
    def get_version(self, obj: Job) -> dict[str, Any] | None:
        v = obj.current_version
        return VersionSerializer(v).data if v else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_published_version_number(self, obj: Job) -> int | None:
        return obj.published_version.number if obj.published_version else None

    @extend_schema_field(CriterionSerializer(many=True))
    def get_criteria(self, obj: Job) -> list[dict[str, Any]]:
        v = obj.current_version
        if v is None:
            return []
        qs = JobCriterion.objects.for_org(obj.organisation_id).filter(job_version=v)
        return list(CriterionSerializer(qs.order_by("order"), many=True).data)

    @extend_schema_field(RubricOutSerializer(allow_null=True))
    def get_rubric(self, obj: Job) -> dict[str, Any] | None:
        from apps.jobs.models import Rubric

        v = obj.current_version
        r = Rubric.objects.for_org(obj.organisation_id).filter(job_version=v).first() if v else None
        if r is None:
            return None
        return {"categories": r.categories, "total_weight": r.total_weight, "status": r.status}

    @extend_schema_field(QuestionOutSerializer(many=True))
    def get_questions(self, obj: Job) -> list[dict[str, Any]]:
        from apps.questionnaires.models import Question

        v = obj.current_version
        if v is None:
            return []
        qs = (
            Question.objects.for_org(obj.organisation_id)
            .filter(questionnaire__job_version=v)
            .order_by("order")
            .prefetch_related("options")
        )
        return [question_out(q) for q in qs]


class JobEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobEvent
        fields = [
            "id",
            "action",
            "from_status",
            "to_status",
            "actor",
            "reason",
            "version_number",
            "created_at",
        ]
        read_only_fields = fields


class AssignmentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    org_role = serializers.CharField(source="membership.role", read_only=True)

    class Meta:
        model = JobAssignment
        fields = ["id", "membership", "role_on_job", "user_name", "org_role", "created_at"]
        read_only_fields = fields

    def get_user_name(self, obj: JobAssignment) -> str:
        u = obj.membership.user
        return (u.full_name or u.email).strip()


class ReadinessCheckSerializer(serializers.Serializer):
    id = serializers.CharField()
    ok = serializers.BooleanField()
    message = serializers.CharField()
    blocking = serializers.BooleanField()
    details = serializers.DictField()


class ReadinessSerializer(serializers.Serializer):
    ready = serializers.BooleanField()
    stage = serializers.CharField()
    checks = ReadinessCheckSerializer(many=True)
    warnings = serializers.ListField(child=serializers.DictField())


class SuggestionsSerializer(serializers.Serializer):
    engine = serializers.CharField()
    requires_acceptance = serializers.BooleanField()
    criteria = serializers.ListField(child=serializers.DictField())
    questions = serializers.ListField(child=serializers.DictField())
