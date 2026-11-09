"""Skills taxonomy & qualification equivalence (SRS M24, docs/03 taxonomy).

Platform rows have ``organisation=None``; organisations may add custom skills.
Evaluations reference ``TaxonomyVersion.version`` so results stay reproducible after curation.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from pgvector.django import VectorField

from apps.core.models import BaseModel

EMBEDDING_DIMENSIONS = 384  # all-MiniLM-L6-v2 (ADR-010)


class TaxonomyVersion(BaseModel):
    version = models.CharField(max_length=32, unique=True)
    notes = models.TextField(blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.version


class SkillCategory(models.TextChoices):
    SOFTWARE_IT = "software_it", "Software & IT"
    FINANCE = "finance", "Finance & accounting"
    ENGINEERING = "engineering", "Engineering"
    HEALTH = "health", "Health"
    SALES_MARKETING = "sales_marketing", "Sales & marketing"
    LOGISTICS = "logistics", "Logistics & supply chain"
    EDUCATION = "education", "Education"
    AGRICULTURE = "agriculture", "Agriculture"
    MINING = "mining", "Mining"
    NGO = "ngo", "NGO & development"
    BUSINESS = "business", "Business, HR & administration"
    LEGAL = "legal", "Legal"
    LANGUAGE = "language", "Languages"
    GENERAL = "general", "General & soft skills"


class Skill(BaseModel):
    taxonomy_version = models.CharField(max_length=32, default="", db_index=True)
    canonical_name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170)
    category = models.CharField(max_length=32, choices=SkillCategory.choices)
    description = models.TextField(blank=True, default="")
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="custom_skills",
        help_text="Null = platform taxonomy; set = organisation custom skill.",
    )

    class Meta:
        ordering = ("canonical_name",)
        constraints = [
            models.UniqueConstraint(
                "slug", "organisation", name="uniq_skill_slug_org", nulls_distinct=False
            )
        ]
        indexes = [
            GinIndex(fields=["canonical_name"], name="skill_name_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return self.canonical_name


class SkillAlias(BaseModel):
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=150)
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        ordering = ("alias",)
        constraints = [
            models.UniqueConstraint(
                Lower("alias"), "organisation", name="uniq_alias_org_ci", nulls_distinct=False
            )
        ]
        indexes = [GinIndex(fields=["alias"], name="alias_trgm", opclasses=["gin_trgm_ops"])]

    def __str__(self) -> str:
        return f"{self.alias} -> {self.skill_id}"


class SkillRelation(BaseModel):
    class Relation(models.TextChoices):
        BROADER = "broader", "Broader"
        NARROWER = "narrower", "Narrower"
        RELATED = "related", "Related"
        IMPLIES = "implies", "Implies"

    from_skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="relations_out")
    to_skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="relations_in")
    relation = models.CharField(max_length=16, choices=Relation.choices)
    weight = models.FloatField(default=1.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_skill", "to_skill", "relation"], name="uniq_skill_relation"
            ),
            models.CheckConstraint(
                condition=~Q(from_skill=models.F("to_skill")), name="skill_relation_not_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_skill_id} {self.relation} {self.to_skill_id}"


class QualificationLevel(BaseModel):
    class Framework(models.TextChoices):
        ZW = "ZW", "Zimbabwe"
        INTL = "INTL", "International"

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    rank = models.PositiveSmallIntegerField(help_text="Higher = more advanced; used for minimums.")
    framework = models.CharField(max_length=8, choices=Framework.choices)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("rank", "code")

    def __str__(self) -> str:
        return self.name


class QualificationAlias(BaseModel):
    level = models.ForeignKey(QualificationLevel, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=150)

    class Meta:
        ordering = ("alias",)
        constraints = [models.UniqueConstraint(Lower("alias"), name="uniq_qualification_alias_ci")]

    def __str__(self) -> str:
        return self.alias


class ProfessionalBody(BaseModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, blank=True, default="")
    designations = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("code",)
        verbose_name_plural = "professional bodies"

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
