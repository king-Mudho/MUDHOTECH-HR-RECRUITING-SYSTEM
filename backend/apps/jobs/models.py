"""Vacancies (SRS M04, docs/03 jobs).

* ``Job`` holds the vacancy header and lifecycle status (draft -> in_review -> approved ->
  scheduled|published -> paused <-> published -> closed -> archived).
* ``JobVersion`` holds the advert content, criteria, rubric and questionnaire. A version is
  editable while ``draft``, frozen once approved (principle 5). Editing a published vacancy creates
  a new version; applications stay bound to the version they applied under (EC-JOB-06).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel, TenantModel


class JobStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    IN_REVIEW = "in_review", "In review"
    APPROVED = "approved", "Approved"
    SCHEDULED = "scheduled", "Scheduled"
    PUBLISHED = "published", "Published"
    PAUSED = "paused", "Paused"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public (listed)"
    UNLISTED = "unlisted", "Unlisted (link only)"  # EC-JOB-20 MVP subset


class WorkplaceType(models.TextChoices):
    ON_SITE = "on_site", "On-site"
    HYBRID = "hybrid", "Hybrid"
    REMOTE = "remote", "Remote"


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full-time"
    PART_TIME = "part_time", "Part-time"
    CONTRACT = "contract", "Contract"
    INTERNSHIP = "internship", "Internship"
    ATTACHMENT = "attachment", "Attachment / industrial attachment"
    TEMPORARY = "temporary", "Temporary"
    GRADUATE_TRAINEE = "graduate_trainee", "Graduate trainee"


class Seniority(models.TextChoices):
    ENTRY = "entry", "Entry level"
    JUNIOR = "junior", "Junior"
    MID = "mid", "Mid level"
    SENIOR = "senior", "Senior"
    LEAD = "lead", "Lead / principal"
    MANAGER = "manager", "Manager"
    EXECUTIVE = "executive", "Executive"


class Currency(models.TextChoices):
    USD = "USD", "US dollar"
    ZWG = "ZWG", "Zimbabwe Gold"


class SalaryPeriod(models.TextChoices):
    HOUR = "hour", "per hour"
    DAY = "day", "per day"
    MONTH = "month", "per month"
    YEAR = "year", "per year"


class Job(TenantModel):
    department = models.ForeignKey(
        "organisations.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    locations = models.ManyToManyField("organisations.Location", blank=True, related_name="+")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    reference_code = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=16, choices=JobStatus.choices, default=JobStatus.DRAFT)
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    current_version = models.ForeignKey(
        "jobs.JobVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_version = models.ForeignKey(
        "jobs.JobVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    workplace_type = models.CharField(
        max_length=16, choices=WorkplaceType.choices, default=WorkplaceType.ON_SITE
    )
    employment_type = models.CharField(
        max_length=24, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    seniority = models.CharField(max_length=16, choices=Seniority.choices, blank=True, default="")
    openings = models.PositiveSmallIntegerField(default=1)
    closes_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Harare")
    publish_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=255, blank=True, default="")
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    salary_period = models.CharField(
        max_length=8, choices=SalaryPeriod.choices, default=SalaryPeriod.MONTH
    )
    salary_disclosed = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    lock_version = models.PositiveIntegerField(default=1)
    search_vector = SearchVectorField(null=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organisation", "status"], name="job_org_status_idx"),
            models.Index(fields=["status", "closes_at"], name="job_status_closes_idx"),
            models.Index(fields=["status", "publish_at"], name="job_status_publish_idx"),
            GinIndex(fields=["search_vector"], name="job_search_gin"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(openings__gte=1), name="job_openings_gte_1"),
            models.CheckConstraint(
                condition=Q(salary_min__isnull=True)
                | Q(salary_max__isnull=True)
                | Q(salary_min__lte=F("salary_max")),
                name="job_salary_min_lte_max",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def accepts_applications(self) -> bool:
        return self.status == JobStatus.PUBLISHED


class JobSlugRedirect(BaseModel):
    """EC-JOB-13: old public slugs keep working (301 to the current slug)."""

    old_slug = models.SlugField(max_length=120, unique=True)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="slug_redirects")

    def __str__(self) -> str:
        return f"{self.old_slug} -> {self.job_id}"


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    IN_REVIEW = "in_review", "In review"
    APPROVED = "approved", "Approved"
    SUPERSEDED = "superseded", "Superseded"


class JobVersion(TenantModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16, choices=VersionStatus.choices, default=VersionStatus.DRAFT
    )
    summary = models.TextField(blank=True, default="")
    responsibilities_html = models.TextField(blank=True, default="")
    requirements_html = models.TextField(blank=True, default="")
    benefits_html = models.TextField(blank=True, default="")
    required_documents = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField(default=dict, blank=True, help_text="Frozen advert at approval.")
    change_note = models.CharField(max_length=500, blank=True, default="")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("job", "-number")
        constraints = [
            models.UniqueConstraint(fields=["job", "number"], name="uniq_job_version_number")
        ]

    def __str__(self) -> str:
        return f"{self.job_id} v{self.number} ({self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status == VersionStatus.DRAFT


class CriterionType(models.TextChoices):
    SKILL = "skill", "Skill"
    EXPERIENCE = "experience", "Experience"
    QUALIFICATION = "qualification", "Qualification"
    CERTIFICATION = "certification", "Certification"
    COMPETENCY = "competency", "Competency"
    LANGUAGE = "language", "Language"
    LICENCE = "licence", "Licence"
    ELIGIBILITY = "eligibility", "Eligibility"


class Importance(models.TextChoices):
    ESSENTIAL = "essential", "Essential"
    PREFERRED = "preferred", "Preferred"


class RubricCategory(models.TextChoices):
    TECHNICAL = "technical", "Technical skills"
    EXPERIENCE = "experience", "Relevant experience"
    COMPETENCY = "competency", "Job competencies"
    QUALIFICATION = "qualification", "Qualifications"
    ANSWERS = "answers", "Screening answers"


class JobCriterion(TenantModel):
    job_version = models.ForeignKey(JobVersion, on_delete=models.CASCADE, related_name="criteria")
    order = models.PositiveSmallIntegerField(default=0)
    type = models.CharField(max_length=16, choices=CriterionType.choices)
    importance = models.CharField(max_length=16, choices=Importance.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    evidence_guidance = models.TextField(blank=True, default="")
    justification = models.TextField(blank=True, default="", help_text="Required when essential.")
    skill = models.ForeignKey(
        "taxonomy.Skill", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qualification_level = models.ForeignKey(
        "taxonomy.QualificationLevel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    min_months = models.PositiveIntegerField(null=True, blank=True)
    equivalents = models.JSONField(default=list, blank=True)
    rubric_category = models.CharField(max_length=16, choices=RubricCategory.choices)
    weight_within_category = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ("job_version", "order")

    def __str__(self) -> str:
        return f"{self.title} ({self.importance})"


class RubricStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    LOCKED = "locked", "Locked"


class Rubric(TenantModel):
    """Weighted scoring categories (FR-M04-04). ``categories`` = [{key, label, weight, bands}]."""

    job_version = models.OneToOneField(JobVersion, on_delete=models.CASCADE, related_name="rubric")
    version = models.PositiveIntegerField(default=1)
    categories = models.JSONField(default=list)
    total_weight = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=16, choices=RubricStatus.choices, default=RubricStatus.DRAFT
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # EC-JOB-02: an approved/locked rubric always totals exactly 100.
            models.CheckConstraint(
                condition=Q(status=RubricStatus.DRAFT) | Q(total_weight=100),
                name="rubric_weights_total_100",
            )
        ]

    def __str__(self) -> str:
        return f"Rubric v{self.version} for {self.job_version_id}"


class JobApproval(TenantModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"

    job_version = models.ForeignKey(JobVersion, on_delete=models.CASCADE, related_name="approvals")
    step = models.PositiveSmallIntegerField(default=1)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decision = models.CharField(max_length=24, choices=Decision.choices)
    comment = models.TextField(blank=True, default="")
    decided_at = models.DateTimeField()

    class Meta:
        ordering = ("job_version", "decided_at")

    def __str__(self) -> str:
        return f"{self.decision} by {self.approver_id}"


class JobAssignment(TenantModel):
    class RoleOnJob(models.TextChoices):
        RECRUITER = "recruiter", "Recruiter"
        HIRING_MANAGER = "hiring_manager", "Hiring manager"
        APPROVER = "approver", "Approver"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="assignments")
    membership = models.ForeignKey(
        "organisations.Membership", on_delete=models.CASCADE, related_name="job_assignments"
    )
    role_on_job = models.CharField(max_length=16, choices=RoleOnJob.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "membership", "role_on_job"], name="uniq_job_assignment"
            )
        ]

    def __str__(self) -> str:
        return f"{self.membership_id} {self.role_on_job} on {self.job_id}"


class JobEvent(TenantModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=16, blank=True, default="")
    to_status = models.CharField(max_length=16)
    action = models.CharField(max_length=40)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reason = models.TextField(blank=True, default="")
    version_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("job", "created_at")

    def __str__(self) -> str:
        return f"{self.job_id}: {self.from_status} -> {self.to_status} ({self.action})"
