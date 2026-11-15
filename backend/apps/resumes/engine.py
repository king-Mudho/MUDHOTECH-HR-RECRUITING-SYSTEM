"""Django adapter around the pure ``ai_engine`` extraction pipeline.

Taxonomy indexes (skills + aliases, qualification levels + professional bodies) are built from the
database once per process and rebuilt when the taxonomy version or an organisation's custom
skills change. Untrusted files are parsed in the sandbox subprocess unless
``EXTRACTION_SANDBOX`` is off (tests).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.conf import settings
from django.db.models import Max, Q

from ai_engine.contracts import ExtractionResult
from ai_engine.extraction.extract import extract_document
from ai_engine.extraction.guards import Limits
from ai_engine.extraction.parser import extract_claims
from ai_engine.extraction.pii import protect
from ai_engine.extraction.sandbox import run_extraction
from ai_engine.extraction.skills import SkillIndex
from ai_engine.normalisation.qualifications import QualificationIndex, normalise_education
from ai_engine.normalisation.titles import normalise_experience
from apps.taxonomy.models import ProfessionalBody, QualificationLevel, Skill, SkillAlias
from apps.taxonomy.services import current_version


@dataclass(frozen=True)
class Indexes:
    skills: SkillIndex
    qualifications: QualificationIndex
    taxonomy_version: str


_cache: dict[tuple[Any, ...], Indexes] = {}
_lock = threading.Lock()


def _skill_scope(organisation_id: Any) -> Q:
    scope = Q(organisation__isnull=True)
    if organisation_id is not None:
        scope |= Q(organisation_id=organisation_id)
    return scope


def indexes(organisation_id: Any = None) -> Indexes:
    version = current_version()
    skills = Skill.objects.filter(_skill_scope(organisation_id), is_active=True)
    marker = skills.aggregate(m=Max("updated_at"))["m"]
    key = (version, organisation_id, marker, skills.count())
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    aliases: dict[Any, list[str]] = {}
    alias_scope = Q(organisation__isnull=True)
    if organisation_id is not None:
        alias_scope |= Q(organisation_id=organisation_id)
    for skill_id, alias in SkillAlias.objects.filter(alias_scope, skill__in=skills).values_list(
        "skill_id", "alias"
    ):
        aliases.setdefault(skill_id, []).append(alias)
    skill_index = SkillIndex.from_taxonomy(
        {"id": str(pk), "name": name, "aliases": aliases.get(pk, [])}
        for pk, name in skills.values_list("id", "canonical_name")
    )
    levels = [
        {
            "code": level.code,
            "name": level.name,
            "rank": level.rank,
            "framework": level.framework,
            "aliases": [a.alias for a in level.aliases.all()],
        }
        for level in QualificationLevel.objects.prefetch_related("aliases")
    ]
    bodies = [
        {"code": b.code, "name": b.name, "designations": list(b.designations or [])}
        for b in ProfessionalBody.objects.all()
    ]
    built = Indexes(skill_index, QualificationIndex.from_taxonomy(levels, bodies), version)
    with _lock:
        _cache.clear() if len(_cache) > 64 else None
        _cache[key] = built
    return built


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def run(
    data: bytes, *, document_id: str, organisation_id: Any, today: date
) -> tuple[ExtractionResult, str]:
    """Bytes -> fully processed result (text, sections, claims, levels, protection)."""
    limits = Limits(max_pages=getattr(settings, "EXTRACTION_MAX_PAGES", 30))
    if getattr(settings, "EXTRACTION_SANDBOX", True):
        result = run_extraction(data, document_id=document_id, limits=limits)
    else:
        result = extract_document(data, document_id=document_id, limits=limits)
    idx = indexes(organisation_id)
    if result.document is None:
        return result, idx.taxonomy_version
    semantic = None
    if getattr(settings, "SEMANTIC_SKILL_MATCHING", True):
        from apps.taxonomy.embeddings import semantic_matcher

        semantic = semantic_matcher(organisation_id)
    result = extract_claims(
        result, today=(today.year, today.month), skills=idx.skills, semantic=semantic
    )
    result = normalise_experience(normalise_education(result, idx.qualifications))
    return protect(result), idx.taxonomy_version
