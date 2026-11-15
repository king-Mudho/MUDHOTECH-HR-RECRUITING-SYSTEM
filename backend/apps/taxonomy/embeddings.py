"""Skill embeddings: precompute into ``Skill.embedding`` (pgvector) and build semantic matchers.

The model runs only in workers (the ``ml`` extra); ``settings.EMBEDDING_MODEL`` picks it and
tests use the deterministic ``hashing-384`` encoder. When the model cannot be loaded the
matcher is ``None`` and extraction continues on the rule/taxonomy path (EC-AI-06).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from django.conf import settings
from django.core.cache import caches
from django.db.models import Q

from ai_engine.matching.semantic import (
    EmbeddingService,
    SemanticSkillMatcher,
    SkillVector,
    get_encoder,
)
from apps.taxonomy.models import Skill

logger = logging.getLogger(__name__)
BATCH = 64

_matchers: dict[tuple[Any, ...], SemanticSkillMatcher] = {}
_lock = threading.Lock()


def service() -> EmbeddingService:
    return EmbeddingService(get_encoder(settings.EMBEDDING_MODEL), caches["default"])


def skill_text(skill: Skill) -> str:
    """What we embed for a skill: its name plus aliases, e.g. 'Python (py, python3)'."""
    aliases = sorted({a.alias for a in skill.aliases.all() if a.organisation_id is None})[:8]
    return f"{skill.canonical_name} ({', '.join(aliases)})" if aliases else skill.canonical_name


def embed_skills(*, force: bool = False, model: str | None = None) -> int:
    """Embed active skills whose vector is missing or came from another model. Returns count."""
    model = model or settings.EMBEDDING_MODEL
    svc = EmbeddingService(get_encoder(model), caches["default"])
    todo = Skill.objects.filter(is_active=True).prefetch_related("aliases")
    if not force:
        todo = todo.filter(Q(embedding__isnull=True) | ~Q(embedding_model=model))
    skills = list(todo.order_by("id"))
    for i in range(0, len(skills), BATCH):
        batch = skills[i : i + BATCH]
        vectors = svc.embed([skill_text(s) for s in batch])
        for skill, vector in zip(batch, vectors, strict=True):
            skill.embedding = vector
            skill.embedding_model = model
        Skill.objects.bulk_update(batch, ["embedding", "embedding_model", "updated_at"])
    clear_matchers()
    return len(skills)


def clear_matchers() -> None:
    with _lock:
        _matchers.clear()


def semantic_matcher(organisation_id: Any = None) -> SemanticSkillMatcher | None:
    """Matcher over platform skills (+ the organisation's custom skills), cached per process."""
    model = settings.EMBEDDING_MODEL
    scope = Q(organisation__isnull=True)
    if organisation_id is not None:
        scope |= Q(organisation_id=organisation_id)
    rows = Skill.objects.filter(scope, is_active=True, embedding_model=model).exclude(
        embedding__isnull=True
    )
    marker = rows.order_by("-updated_at").values_list("updated_at", flat=True).first()
    key = (model, organisation_id, marker, rows.count())
    with _lock:
        cached = _matchers.get(key)
    if cached is not None:
        return cached
    if key[3] == 0:
        return None
    try:
        svc = service()
        svc.encoder.encode(["warm-up"])  # loads the model once per worker; fails fast if missing
    except (ImportError, OSError, RuntimeError) as exc:
        logger.warning("semantic matching unavailable", extra={"error": type(exc).__name__})
        return None
    matcher = SemanticSkillMatcher(
        svc,
        [
            SkillVector(str(s.id), s.canonical_name, [float(x) for x in s.embedding])
            for s in rows.only("id", "canonical_name", "embedding")
        ],
        threshold=getattr(settings, "SEMANTIC_SKILL_THRESHOLD", 0.75),
    )
    with _lock:
        _matchers[key] = matcher
    return matcher
