"""Platform taxonomy curation (P14-T01, SRS M24).

Platform staff edit the platform taxonomy (skills, aliases, relations, qualification aliases) in
place; the screening engine keeps using its cached indexes for the **published** version until a
new version is published (the cache is keyed by ``current_version()``), so curation never changes
evaluations half-way. Publishing records a ``TaxonomyVersion`` with a checksum of the platform
taxonomy; evaluations keep referencing the version they used. Skills are deactivated, never
deleted (evaluations reference them). New skills need ``embed_skills`` in a worker for semantic
matching; exact and alias matching work immediately after publishing.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils.text import slugify

from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.time import now

from .models import (
    QualificationAlias,
    QualificationLevel,
    Skill,
    SkillAlias,
    SkillCategory,
    SkillRelation,
    TaxonomyVersion,
)
from .services import _checksum, current_version


def _text(value: Any, field: str, max_len: int = 150) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise DomainError("validation_error", "Required.", details={field: ["Required."]})
    if len(text) > max_len:
        raise DomainError("validation_error", "Too long.", details={field: ["Too long."]})
    return text


def platform_skills(q: str = "", include_inactive: bool = False) -> QuerySet[Skill]:
    qs = Skill.objects.filter(organisation__isnull=True).prefetch_related(
        "aliases", "relations_out__to_skill"
    )
    if not include_inactive:
        qs = qs.filter(is_active=True)
    if q.strip():
        term = q.strip()
        qs = qs.filter(
            Q(canonical_name__icontains=term) | Q(aliases__alias__icontains=term)
        ).distinct()
    return qs.order_by("canonical_name")


def _skill(skill_id: Any) -> Skill:
    skill = Skill.objects.filter(pk=skill_id, organisation__isnull=True).first()
    if skill is None:
        raise NotFoundError()
    return skill


@transaction.atomic
def create_skill(actor: Any, *, name: str, category: str, aliases: list[str]) -> Skill:
    name = _text(name, "name")
    if category not in SkillCategory.values:
        raise DomainError("validation_error", "Unknown category.", details={"category": ["?"]})
    slug = slugify(name.replace("+", " plus").replace("#", " sharp"))[:170] or "skill"
    if Skill.objects.filter(slug=slug, organisation__isnull=True).exists():
        raise ConflictError(code="conflict.skill_exists", message="That skill already exists.")
    skill = Skill.objects.create(
        canonical_name=name, slug=slug, category=category, taxonomy_version="", organisation=None
    )
    for alias in aliases:
        add_alias(actor, skill.pk, alias, _audit=False)
    audit.record(actor=actor, action="taxonomy.skill_created", target=skill, after={"name": name})
    return skill


@transaction.atomic
def update_skill(actor: Any, skill_id: Any, **changes: Any) -> Skill:
    skill = _skill(skill_id)
    before = {"name": skill.canonical_name, "category": skill.category, "active": skill.is_active}
    if "canonical_name" in changes:
        skill.canonical_name = _text(changes["canonical_name"], "canonical_name")
    if "category" in changes:
        if changes["category"] not in SkillCategory.values:
            raise DomainError("validation_error", "Unknown category.", details={"category": ["?"]})
        skill.category = changes["category"]
    if "is_active" in changes:
        skill.is_active = bool(changes["is_active"])
    skill.save()
    audit.record(
        actor=actor,
        action="taxonomy.skill_updated",
        target=skill,
        before=before,
        after={"name": skill.canonical_name, "category": skill.category, "active": skill.is_active},
    )
    return skill


def add_alias(actor: Any, skill_id: Any, alias: str, *, _audit: bool = True) -> SkillAlias:
    skill = _skill(skill_id)
    text = _text(alias, "alias")
    try:
        with transaction.atomic():
            row = SkillAlias.objects.create(skill=skill, alias=text, organisation=None)
    except IntegrityError as exc:
        raise ConflictError(
            code="conflict.alias_exists", message="That alias already points to a skill."
        ) from exc
    if _audit:
        audit.record(
            actor=actor, action="taxonomy.alias_added", target=skill, after={"alias": text}
        )
    return row


def remove_alias(actor: Any, alias_id: Any) -> None:
    row = SkillAlias.objects.filter(pk=alias_id, organisation__isnull=True).first()
    if row is None:
        raise NotFoundError()
    audit.record(
        actor=actor, action="taxonomy.alias_removed", target=row.skill, before={"alias": row.alias}
    )
    skill = row.skill
    row.delete()
    skill.save(update_fields=["updated_at"])  # marks the taxonomy as changed since publishing


def add_relation(actor: Any, from_id: Any, to_id: Any, relation: str) -> SkillRelation:
    if relation not in SkillRelation.Relation.values:
        raise DomainError("validation_error", "Unknown relation.", details={"relation": ["?"]})
    a, b = _skill(from_id), _skill(to_id)
    if a.pk == b.pk:
        raise DomainError("validation_error", "A skill cannot relate to itself.")
    row, created = SkillRelation.objects.get_or_create(from_skill=a, to_skill=b, relation=relation)
    if not created:
        raise ConflictError(code="conflict.relation_exists", message="That relation exists.")
    audit.record(
        actor=actor,
        action="taxonomy.relation_added",
        target=a,
        after={"to": str(b.pk), "relation": relation},
    )
    return row


def remove_relation(actor: Any, relation_id: Any) -> None:
    row = SkillRelation.objects.filter(
        pk=relation_id, from_skill__organisation__isnull=True
    ).first()
    if row is None:
        raise NotFoundError()
    audit.record(
        actor=actor,
        action="taxonomy.relation_removed",
        target=row.from_skill,
        before={"to": str(row.to_skill_id), "relation": row.relation},
    )
    skill = row.from_skill
    row.delete()
    skill.save(update_fields=["updated_at"])


def add_qualification_alias(actor: Any, level_id: Any, alias: str) -> QualificationAlias:
    level = QualificationLevel.objects.filter(pk=level_id).first()
    if level is None:
        raise NotFoundError()
    text = _text(alias, "alias")
    if QualificationAlias.objects.filter(alias__iexact=text).exists():
        raise ConflictError(code="conflict.alias_exists", message="That alias already exists.")
    row = QualificationAlias.objects.create(level=level, alias=text)
    audit.record(
        actor=actor,
        action="taxonomy.qualification_alias_added",
        target=("qualification_level", str(level.pk)),
        after={"alias": text},
    )
    return row


def remove_qualification_alias(actor: Any, alias_id: Any) -> None:
    row = QualificationAlias.objects.filter(pk=alias_id).first()
    if row is None:
        raise NotFoundError()
    audit.record(
        actor=actor,
        action="taxonomy.qualification_alias_removed",
        target=("qualification_level", str(row.level_id)),
        before={"alias": row.alias},
    )
    level = row.level
    row.delete()
    level.save(update_fields=["updated_at"])


def changed_since(moment: Any) -> bool:
    """Any platform taxonomy row created, edited or touched (removals) after ``moment``."""
    if moment is None:
        return True
    return any(
        qs.filter(updated_at__gt=moment).exists()
        for qs in (
            Skill.objects.filter(organisation__isnull=True),
            SkillAlias.objects.filter(organisation__isnull=True),
            SkillRelation.objects.filter(from_skill__organisation__isnull=True),
            QualificationLevel.objects.all(),
            QualificationAlias.objects.all(),
        )
    )


def _snapshot() -> dict[str, Any]:
    skills = [
        [s.slug, s.canonical_name, s.category, s.is_active]
        for s in Skill.objects.filter(organisation__isnull=True).order_by("slug")
    ]
    aliases = sorted(
        [a.alias.lower(), a.skill.slug]
        for a in SkillAlias.objects.filter(organisation__isnull=True).select_related("skill")
    )
    relations = sorted(
        [r.from_skill.slug, r.to_skill.slug, r.relation]
        for r in SkillRelation.objects.filter(from_skill__organisation__isnull=True).select_related(
            "from_skill", "to_skill"
        )
    )
    quals = sorted(
        [a.alias.lower(), a.level.code] for a in QualificationAlias.objects.select_related("level")
    )
    return {"skills": skills, "aliases": aliases, "relations": relations, "quals": quals}


def _latest() -> TaxonomyVersion | None:
    """Most recently published version (unpublished rows sort first in PostgreSQL DESC)."""
    return (
        TaxonomyVersion.objects.filter(published_at__isnull=False).order_by("-published_at").first()
    )


def status() -> dict[str, Any]:
    latest = _latest()
    return {
        "current_version": current_version(),
        "published_at": latest.published_at if latest else None,
        "unpublished_changes": changed_since(latest.published_at if latest else None),
        "skills": Skill.objects.filter(organisation__isnull=True, is_active=True).count(),
        "versions": [
            {"version": v.version, "published_at": v.published_at, "notes": v.notes}
            for v in TaxonomyVersion.objects.filter(published_at__isnull=False).order_by(
                "-published_at"
            )[:10]
        ],
    }


@transaction.atomic
def publish(actor: Any, notes: str = "") -> TaxonomyVersion:
    checksum = _checksum(_snapshot())
    latest = _latest()
    if latest is not None and not changed_since(latest.published_at):
        raise ConflictError(code="conflict.nothing_to_publish", message="No changes to publish.")
    stamp = now()
    base = stamp.strftime("%Y.%m.%d")
    n = TaxonomyVersion.objects.filter(version__startswith=base).count() + 1
    version = f"{base}-{n}"
    row = TaxonomyVersion.objects.create(
        version=version, checksum=checksum, published_at=stamp, notes=notes.strip()[:2000]
    )
    Skill.objects.filter(organisation__isnull=True, taxonomy_version="").update(
        taxonomy_version=version
    )
    audit.record(
        actor=actor,
        action="taxonomy.published",
        target=("taxonomy_version", version),
        after={"checksum": checksum, "previous": latest.version if latest else None},
    )
    return row
