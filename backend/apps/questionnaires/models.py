"""Screening questionnaires (SRS M08, docs/03 questionnaires).

A questionnaire belongs to a job version (frozen with it) or is an organisation template in the
question bank (``is_template``). Questions are addressed by a stable ``key`` so branching rules
(``{"show_if": {"question": "<key>", "op": "eq", "value": "yes"}}``) survive re-ordering.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import TenantModel


class QuestionType(models.TextChoices):
    YES_NO = "yes_no", "Yes / no"
    SINGLE_CHOICE = "single_choice", "Single choice"
    MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
    NUMBER = "number", "Number"
    SHORT_TEXT = "short_text", "Short text"
    LONG_TEXT = "long_text", "Long text"
    DATE = "date", "Date"
    FILE_UPLOAD = "file_upload", "File upload"
    SCALE = "scale", "Scale (1-5)"
    AVAILABILITY = "availability", "Availability / notice period"
    SALARY_EXPECTATION = "salary_expectation", "Salary expectation"


class ScoringMode(models.TextChoices):
    NONE = "none", "Not scored"
    EXACT = "exact", "Expected answer"
    OPTIONS = "options", "Points per option"
    RANGE = "range", "Numeric range"
    RUBRIC_TEXT = "rubric_text", "Text rubric (keywords/criteria)"
    HUMAN = "human", "Scored by a person"


class Questionnaire(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    job_version = models.OneToOneField(
        "jobs.JobVersion",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="questionnaire",
    )
    name = models.CharField(max_length=200, default="Screening questions")
    is_template = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.name


class Question(TenantModel):
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.CASCADE, related_name="questions"
    )
    key = models.SlugField(max_length=60)
    section = models.CharField(max_length=120, blank=True, default="")
    order = models.PositiveSmallIntegerField(default=0)
    type = models.CharField(max_length=24, choices=QuestionType.choices)
    prompt = models.TextField()
    help_text = models.TextField(blank=True, default="")
    required = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    branching = models.JSONField(default=dict, blank=True)
    scoring = models.JSONField(default=dict, blank=True)
    # FR-M08-04: knock-out questions never auto-reject; they flag eligibility for human review.
    is_knockout = models.BooleanField(default=False)
    criterion = models.ForeignKey(
        "jobs.JobCriterion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    protected_topic_flag = models.JSONField(default=list, blank=True)
    protected_exception_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("questionnaire", "order")
        constraints = [
            models.UniqueConstraint(fields=["questionnaire", "key"], name="uniq_question_key")
        ]

    def __str__(self) -> str:
        return f"{self.key}: {self.prompt[:40]}"

    @property
    def blocks_publishing(self) -> bool:
        return bool(self.protected_topic_flag) and not self.protected_exception_reason.strip()


class QuestionOption(TenantModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    order = models.PositiveSmallIntegerField(default=0)
    label = models.CharField(max_length=200)
    value = models.CharField(max_length=100)
    points = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("question", "order")
        constraints = [
            models.UniqueConstraint(fields=["question", "value"], name="uniq_option_value")
        ]

    def __str__(self) -> str:
        return self.label


class QuestionResponse(TenantModel):
    """Candidate answers (used from Phase 04). ``application_id`` becomes a FK in Phase 04."""

    application_id = models.UUIDField(db_index=True)
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="responses")
    value = models.JSONField(null=True, blank=True)
    document_id = models.UUIDField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application_id", "question"], name="uniq_response_per_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.application_id}:{self.question_id}"
