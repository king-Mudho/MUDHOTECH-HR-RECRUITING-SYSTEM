"""Taxonomy loading (idempotent, versioned) and organisation custom skills."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from apps.audit import services as audit
from apps.core import time
from apps.core.exceptions import ConflictError

from .models import (
    ProfessionalBody,
    QualificationAlias,
    QualificationLevel,
    Skill,
    SkillAlias,
    SkillRelation,
    TaxonomyVersion,
)

FIXTURE_DIR = Path(settings.BASE_DIR) / "fixtures" / "taxonomy"


@dataclass
class LoadResult:
    version: str
    skipped: bool = False
    counts: dict[str, int] = field(default_factory=dict)


def _checksum(*payloads: Any) -> str:
    raw = json.dumps(payloads, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


@transaction.atomic
def load_taxonomy(directory: Path | None = None, *, force: bool = False) -> LoadResult:
    """Upsert the platform taxonomy from fixtures. Re-running the same version is a no-op.

    Skills removed from the fixture are deactivated (never deleted: evaluations reference them).
    """
    directory = directory or FIXTURE_DIR
    skills_doc = json.loads((directory / "skills.json").read_text(encoding="utf-8"))
    quals_doc = json.loads((directory / "qualifications.json").read_text(encoding="utf-8"))
    version = skills_doc["version"]
    checksum = _checksum(skills_doc, quals_doc)
    existing = TaxonomyVersion.objects.filter(version=version).first()
    if existing and existing.checksum == checksum and not force:
        return LoadResult(version=version, skipped=True)
    if existing and existing.checksum != checksum and not force:
        raise ConflictError(
            code="conflict.taxonomy_version",
            message=f"Taxonomy {version} was already loaded with different content; bump VERSION.",
        )

    counts = {"skills": 0, "aliases": 0, "relations": 0, "levels": 0, "bodies": 0}
    by_name: dict[str, Skill] = {}
    seen_slugs: set[str] = set()
    for item in skills_doc["skills"]:
        slug = slugify(item["name"].replace("+", " plus").replace("#", " sharp"))[:170] or "skill"
        if item["name"] == ".NET":
            slug = "dotnet"
        seen_slugs.add(slug)
        skill, _ = Skill.objects.update_or_create(
            slug=slug,
            organisation=None,
            defaults={
                "canonical_name": item["name"],
                "category": item["category"],
                "taxonomy_version": version,
                "is_active": True,
            },
        )
        by_name[item["name"]] = skill
        counts["skills"] += 1
        for alias in item.get("aliases", []):
            SkillAlias.objects.update_or_create(
                alias__iexact=alias, organisation=None, defaults={"alias": alias, "skill": skill}
            )
            counts["aliases"] += 1
    Skill.objects.filter(organisation=None).exclude(slug__in=seen_slugs).update(is_active=False)

    for rel in skills_doc.get("relations", []):
        SkillRelation.objects.get_or_create(
            from_skill=by_name[rel["from"]],
            to_skill=by_name[rel["to"]],
            relation=rel["relation"],
        )
        counts["relations"] += 1

    for lvl in quals_doc["levels"]:
        level, _ = QualificationLevel.objects.update_or_create(
            code=lvl["code"],
            defaults={"name": lvl["name"], "rank": lvl["rank"], "framework": lvl["framework"]},
        )
        counts["levels"] += 1
        for alias in lvl.get("aliases", []):
            QualificationAlias.objects.update_or_create(
                alias__iexact=alias, defaults={"alias": alias, "level": level}
            )
    for body in quals_doc["professional_bodies"]:
        ProfessionalBody.objects.update_or_create(
            code=body["code"],
            defaults={
                "name": body["name"],
                "country": body["country"],
                "designations": body["designations"],
            },
        )
        counts["bodies"] += 1

    TaxonomyVersion.objects.update_or_create(
        version=version,
        defaults={"checksum": checksum, "published_at": time.now(), "notes": json.dumps(counts)},
    )
    return LoadResult(version=version, counts=counts)


def current_version() -> str:
    latest = TaxonomyVersion.objects.order_by("-published_at").first()
    return latest.version if latest else ""


@transaction.atomic
def create_custom_skill(
    *,
    org: Any,
    actor: Any,
    name: str,
    category: str,
    aliases: list[str] | None = None,
    request: Any = None,
) -> Skill:
    """Organisation-specific skill (e.g. an in-house system); visible only to that org."""
    slug = slugify(name)[:170] or "skill"
    if Skill.objects.filter(organisation=org, slug=slug).exists():
        raise ConflictError(
            code="conflict.duplicate_skill", message="Your organisation already has this skill."
        )
    skill = Skill.objects.create(
        organisation=org,
        canonical_name=name.strip(),
        slug=slug,
        category=category,
        taxonomy_version="org",
    )
    for alias in aliases or []:
        if alias.strip():
            SkillAlias.objects.get_or_create(
                alias__iexact=alias.strip(),
                organisation=org,
                defaults={"alias": alias.strip(), "skill": skill},
            )
    audit.record(
        actor=actor,
        action="taxonomy.custom_skill_created",
        target=skill,
        organisation=org,
        after={"name": skill.canonical_name},
        request=request,
    )
    return skill
