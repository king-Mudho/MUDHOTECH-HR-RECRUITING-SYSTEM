"""Candidate profiles (SRS M06, docs/03 candidates).

A profile belongs to a user, not an organisation: candidates own their data and share a frozen
snapshot with an employer only when they submit an application. FR-M06-02 / principle 7: the core
profile never stores protected attributes (date of birth, gender, ID number, marital status,
religion, tribe, photo, health...). ``tests/test_models.py`` enforces this.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import BaseModel


class Source(models.TextChoices):
    MANUAL = "manual", "Entered by the candidate"
    CV_IMPORT = "cv_import", "Imported from a CV (confirmed by the candidate)"


class Availability(models.TextChoices):
    IMMEDIATE = "immediate", "Immediately"
    NOTICE = "notice", "After my notice period"
    NOT_LOOKING = "not_looking", "Not actively looking"


class CandidateProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate_profile"
    )
    preferred_name = models.CharField(max_length=100, blank=True, default="")
    headline = models.CharField(max_length=160, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=2, default="ZW")
    phone_e164 = models.CharField(max_length=20, blank=True, default="")
    links = models.JSONField(
        default=dict, blank=True, help_text="{linkedin, github, portfolio, other}"
    )
    availability = models.CharField(
        max_length=16, choices=Availability.choices, blank=True, default=""
    )
    notice_period_days = models.PositiveSmallIntegerField(null=True, blank=True)
    open_to_relocation = models.BooleanField(default=False)
    profile_completeness = models.PositiveSmallIntegerField(default=0)
    # default_resume (FK to documents.Document) is added with the documents app in P04-T02.
    lock_version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(profile_completeness__lte=100), name="profile_completeness_lte_100"
            )
        ]

    def __str__(self) -> str:
        return f"Profile of {self.user_id}"


class ProfileItem(BaseModel):
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ("order", "-created_at")


class Experience(ProfileItem):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="experiences"
    )
    employer = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=150, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, default="")
    source_claim_id = models.UUIDField(null=True, blank=True)

    class Meta(ProfileItem.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="experience_dates_ordered",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} at {self.employer}"


class Education(ProfileItem):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="educations"
    )
    institution = models.CharField(max_length=200)
    qualification_text = models.CharField(max_length=200)
    qualification_level = models.ForeignKey(
        "taxonomy.QualificationLevel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    field = models.CharField(max_length=150, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    grade = models.CharField(max_length=60, blank=True, default="")

    def __str__(self) -> str:
        return f"{self.qualification_text}, {self.institution}"


class Certification(ProfileItem):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=200)
    body = models.ForeignKey(
        "taxonomy.ProfessionalBody",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    issued_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    credential_id = models.CharField(max_length=100, blank=True, default="")

    def __str__(self) -> str:
        return self.name


class Proficiency(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"
    EXPERT = "expert", "Expert"


class CandidateSkill(ProfileItem):
    profile = models.ForeignKey(CandidateProfile, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(
        "taxonomy.Skill", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    raw_name = models.CharField(max_length=150)
    proficiency = models.CharField(
        max_length=16, choices=Proficiency.choices, blank=True, default=""
    )
    years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta(ProfileItem.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "skill"],
                condition=Q(skill__isnull=False),
                name="uniq_candidate_skill",
            ),
            models.UniqueConstraint(Lower("raw_name"), "profile", name="uniq_candidate_skill_name"),
        ]

    def __str__(self) -> str:
        return self.raw_name


class LanguageLevel(models.TextChoices):
    BASIC = "basic", "Basic"
    CONVERSATIONAL = "conversational", "Conversational"
    FLUENT = "fluent", "Fluent"
    NATIVE = "native", "Native"


class Language(ProfileItem):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="languages"
    )
    language = models.CharField(max_length=60)
    proficiency = models.CharField(max_length=16, choices=LanguageLevel.choices)

    class Meta(ProfileItem.Meta):
        constraints = [
            models.UniqueConstraint(Lower("language"), "profile", name="uniq_candidate_language")
        ]

    def __str__(self) -> str:
        return f"{self.language} ({self.proficiency})"
