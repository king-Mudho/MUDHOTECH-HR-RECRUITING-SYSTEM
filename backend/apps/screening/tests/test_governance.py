"""Model registry seed and AI quality capture hooks (P07-T14)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_engine import ENGINE_VERSION
from apps.applications.models import Application
from apps.organisations.models import Membership
from apps.screening import quality, registry, runs, services, verification
from apps.screening.models import AIQualityReport, EvaluationEvidence, ModelRegistryEntry

pytestmark = pytest.mark.django_db


def member(vacancy: Any) -> Membership:
    return Membership.objects.get(user=vacancy.team.hr_manager, organisation=vacancy.team.org)


def test_registry_is_seeded_on_migrate_and_idempotent() -> None:
    active = registry.active_ids()
    assert set(active) == {"rules", "embedding", "llm"}
    assert active["llm"] == "null-llm@1"  # LLM off by default (ADR-026)
    assert active["rules"].startswith(f"mhrs-screening-engine@{ENGINE_VERSION}+")
    before = ModelRegistryEntry.objects.count()
    registry.sync_registry()
    assert ModelRegistryEntry.objects.count() == before


def test_changed_configuration_closes_the_old_entry(settings: Any) -> None:
    settings.LLM_PROVIDER = "anthropic"
    settings.LLM_MODEL = "claude-opus-5-5"
    registry.sync_registry()
    old = ModelRegistryEntry.objects.get(name="null-llm")
    assert old.active_to is not None  # kept for history, no longer active
    assert registry.active_ids()["llm"] == "claude-opus-5-5@1"
    settings.LLM_PROVIDER = "none"
    registry.sync_registry()
    old.refresh_from_db()
    assert old.active_to is None and registry.active_ids()["llm"] == "null-llm@1"


def test_runs_record_the_active_models(vacancy: Any) -> None:
    run = runs.start_run(
        member(vacancy),
        vacancy.team.hr_manager,
        vacancy.job.pk,
        scope="all",
    )
    assert run.model_ids == registry.active_ids()


def test_evaluations_and_verifications_update_quality_counters(
    read_app: Application, vacancy: Any
) -> None:
    evaluation = services.evaluate_application(read_app.pk)
    assert evaluation is not None
    report = AIQualityReport.objects.get(
        organisation_id=read_app.organisation_id, job_id=vacancy.job.pk
    )
    m = report.metrics
    assert m["evaluations"] == 1 and m[f"band:{evaluation.band}"] == 1
    assert m["trigger:auto"] == 1 and m["explanation_sentences"] > 0
    assert m["grounding_dropped"] == 0
    r = quality.rates(m)
    assert r["grounding_rate"] == 1.0 and r["verification_override_rate"] is None

    claim_id = (
        EvaluationEvidence.objects.for_org(read_app.organisation_id)
        .filter(criterion_result__evaluation=evaluation, claim__isnull=False)
        .values_list("claim_id", flat=True)
        .first()
    )
    membership = member(vacancy)
    verification.verify(
        membership, vacancy.team.hr_manager, claim_id, decision="rejected", note="Not shown"
    )
    report.refresh_from_db()
    assert report.metrics["verifications"] == 1
    assert quality.rates(report.metrics)["verification_override_rate"] == 1.0
    assert not any("python" in str(k).lower() for k in report.metrics)  # counters only


# EC-AI-17: skills taxonomy updated -> new taxonomy_version; earlier runs keep the old one
def test_runs_keep_the_taxonomy_version_they_used(vacancy: Any) -> None:
    from apps.core.time import now
    from apps.taxonomy.models import TaxonomyVersion

    first = runs.start_run(member(vacancy), vacancy.team.hr_manager, vacancy.job.pk, scope="all")
    TaxonomyVersion.objects.create(version="2099.01.1", published_at=now())
    second = runs.start_run(member(vacancy), vacancy.team.hr_manager, vacancy.job.pk, scope="all")
    first.refresh_from_db()
    assert second.taxonomy_version == "2099.01.1"
    assert first.taxonomy_version != "2099.01.1"
