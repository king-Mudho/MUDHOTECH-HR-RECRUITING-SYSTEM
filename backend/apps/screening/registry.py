"""Model registry seed (P07-T14, docs/05 §12).

``sync_registry()`` records the models and engines currently configured: the rules engine (engine
and threshold versions), the embedding model and the LLM provider ("none" by default, ADR-026).
It is idempotent and runs on ``post_migrate``. When a configured version changes, the previous
entry of that kind and name is closed (``active_to``) and kept, so an evaluation's
``engine_version``/``model_ids`` always resolve to what produced it.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction

from ai_engine import ENGINE_VERSION
from ai_engine.matching.config import DEFAULT_CONFIG
from apps.core.time import now

from .models import ModelRegistryEntry

Kind = ModelRegistryEntry.Kind

NO_TRAINING = (
    "Runs inside MHRS infrastructure; candidate data never leaves it and is never used for "
    "training."
)


def configured() -> list[dict[str, Any]]:
    provider = settings.LLM_PROVIDER
    entries: list[dict[str, Any]] = [
        {
            "kind": Kind.RULES,
            "name": "mhrs-screening-engine",
            "version": f"{ENGINE_VERSION}+{DEFAULT_CONFIG.version}",
            "purpose": "Evidence extraction, criterion matching, scoring, bands and template "
            "explanations (deterministic).",
            "provider": "MudhoTech Solutions",
            "data_policy": NO_TRAINING,
            "limitations": "Rules and taxonomy coverage; missing evidence is reported as unknown, "
            "never as a fail. Calibrated on the synthetic labelled set only.",
            "evaluation_report": "docs/reports/",
        },
        {
            "kind": Kind.EMBEDDING,
            "name": settings.EMBEDDING_MODEL,
            "version": "1",
            "purpose": "Semantic similarity for skills and experience relevance (assist only; "
            "every semantic match is labelled inferred).",
            "provider": "local",
            "data_policy": NO_TRAINING,
            "limitations": "English-centric; similarity scores are thresholded and capped.",
        },
    ]
    if provider in ("", "none"):
        entries.append(
            {
                "kind": Kind.LLM,
                "name": "null-llm",
                "version": "1",
                "purpose": "No language model: summaries use grounded templates only.",
                "provider": "none",
                "data_policy": "No data is sent anywhere.",
                "limitations": "",
            }
        )
    else:
        entries.append(
            {
                "kind": Kind.LLM,
                "name": settings.LLM_MODEL or "provider-default",
                "version": "1",
                "purpose": "Optional phrasing of grounded summaries and CV section assist; never "
                "scores or decides.",
                "provider": provider,
                "data_policy": "Redacted input only; provider terms: no training on data. Enabled "
                "only per organisation after the DPA addendum.",
                "limitations": "Output is discarded unless every sentence is grounded in evidence.",
            }
        )
    return entries


@transaction.atomic
def sync_registry() -> list[ModelRegistryEntry]:
    at = now()
    out = []
    active_kinds: dict[str, set[str]] = {}
    for spec in configured():
        entry, created = ModelRegistryEntry.objects.get_or_create(
            kind=spec["kind"],
            name=spec["name"],
            version=spec["version"],
            defaults={**spec, "active_from": at},
        )
        if not created and entry.active_to is not None:
            entry.active_to = None  # configured again
            entry.save(update_fields=["active_to", "updated_at"])
        active_kinds.setdefault(spec["kind"], set()).add(str(entry.pk))
        out.append(entry)
    for kind, keep in active_kinds.items():
        ModelRegistryEntry.objects.filter(kind=kind, active_to__isnull=True).exclude(
            pk__in=keep
        ).update(active_to=at)
    return out


def active_ids() -> dict[str, str]:
    """``{kind: "name@version"}`` of the active entries, recorded on each screening run."""
    return {
        e.kind: f"{e.name}@{e.version}"
        for e in ModelRegistryEntry.objects.filter(active_to__isnull=True)
    }
