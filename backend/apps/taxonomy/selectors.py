"""Taxonomy reads: autocomplete (pg_trgm similarity) and alias resolution."""

from __future__ import annotations

from typing import Any

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Max, Q, QuerySet
from django.db.models.functions import Coalesce, Greatest

from .models import QualificationLevel, Skill, SkillAlias

MIN_SIMILARITY = 0.2


def visible_skills(org: Any = None) -> QuerySet[Skill]:
    """Platform skills plus (when given) the organisation's custom skills."""
    scope = Q(organisation__isnull=True)
    if org is not None:
        scope |= Q(organisation=org)
    return Skill.objects.filter(scope, is_active=True)


def search_skills(query: str, *, org: Any = None, limit: int = 20) -> list[Skill]:
    """Autocomplete: prefix/exact matches first, then trigram similarity on names and aliases."""
    q = query.strip()
    if not q:
        return list(visible_skills(org).order_by("canonical_name")[:limit])
    qs = (
        visible_skills(org)
        .annotate(
            name_sim=TrigramSimilarity("canonical_name", q),
            alias_sim=Coalesce(Max(TrigramSimilarity("aliases__alias", q)), 0.0),
        )
        .annotate(score=Greatest("name_sim", "alias_sim"))
        .filter(
            Q(canonical_name__icontains=q)
            | Q(aliases__alias__iexact=q)
            | Q(score__gte=MIN_SIMILARITY)
        )
    )
    results = list(qs.order_by("-score", "canonical_name")[: limit * 3])
    ql = q.lower()

    def rank(s: Skill) -> tuple[int, float, str]:
        name = s.canonical_name.lower()
        tier = 0 if name == ql else 1 if name.startswith(ql) else 2
        return (tier, -float(getattr(s, "score", 0) or 0), name)

    ranked: list[Skill] = sorted(results, key=rank)
    return ranked[:limit]


def resolve_skill(text: str, *, org: Any = None) -> Skill | None:
    """Exact canonical-name or alias match (case-insensitive); org aliases win over platform."""
    t = text.strip()
    if not t:
        return None
    by_name = visible_skills(org).filter(canonical_name__iexact=t).order_by("organisation").first()
    if by_name:
        return by_name
    alias_scope = Q(organisation__isnull=True) | (Q(organisation=org) if org else Q(pk__in=[]))
    alias = (
        SkillAlias.objects.filter(alias_scope, alias__iexact=t, skill__is_active=True)
        .select_related("skill")
        .order_by("organisation")
        .first()
    )
    return alias.skill if alias else None


def qualification_levels() -> QuerySet[QualificationLevel]:
    return QualificationLevel.objects.prefetch_related("aliases").order_by("rank", "code")
