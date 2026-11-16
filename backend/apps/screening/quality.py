"""AI quality metric capture hooks (P07-T14, docs/03 ai_quality_reports).

Counters are added to a per-organisation, per-vacancy, per-day ``AIQualityReport`` inside the
transaction that stores the evaluation or the verification, so they cannot drift from the data.
Rates are derived when read. No candidate data is stored. Phase 13 schedules reports and alerts
(override rate > 30%) on top of these counters.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.core.time import now

from .models import AIQualityReport, Evaluation, HumanVerification

LOW_COVERAGE = 0.6


def _report(organisation_id: Any, job_id: Any) -> AIQualityReport:
    period = now().date()
    try:
        with transaction.atomic():
            report, _ = AIQualityReport.objects.select_for_update().get_or_create(
                organisation_id=organisation_id, job_id=job_id, period=period
            )
    except IntegrityError:  # created concurrently
        report = AIQualityReport.objects.select_for_update().get(
            organisation_id=organisation_id, job_id=job_id, period=period
        )
    return report


def _add(metrics: dict[str, Any], key: str, by: float = 1) -> None:
    metrics[key] = round(metrics.get(key, 0) + by, 4)


def capture_evaluation(evaluation: Evaluation, *, sentences: int, job_id: Any) -> None:
    report = _report(evaluation.organisation_id, job_id)
    m = dict(report.metrics)
    _add(m, "evaluations")
    _add(m, f"band:{evaluation.band}")
    _add(m, f"trigger:{evaluation.trigger}")
    _add(m, "coverage_sum", float(evaluation.coverage))
    if float(evaluation.coverage) < LOW_COVERAGE:
        _add(m, "low_coverage")
    _add(m, "explanation_sentences", sentences)
    _add(m, "grounding_dropped", evaluation.grounding_dropped)
    if evaluation.llm_used:
        _add(m, "llm_used")
    report.metrics = m
    report.save(update_fields=["metrics", "updated_at"])


def capture_verification(verdict: HumanVerification, *, job_id: Any) -> None:
    report = _report(verdict.organisation_id, job_id)
    m = dict(report.metrics)
    _add(m, "verifications")
    _add(m, f"verification:{verdict.decision}")
    report.metrics = m
    report.save(update_fields=["metrics", "updated_at"])


def rates(metrics: dict[str, Any]) -> dict[str, float | None]:
    """Derived rates (grounding rate, low-coverage share, verification override rate)."""
    n = metrics.get("evaluations", 0)
    sentences = metrics.get("explanation_sentences", 0)
    dropped = metrics.get("grounding_dropped", 0)
    verified = metrics.get("verifications", 0)
    overridden = metrics.get("verification:corrected", 0) + metrics.get("verification:rejected", 0)
    return {
        "grounding_rate": (sentences / (sentences + dropped)) if sentences + dropped else None,
        "low_coverage_share": (metrics.get("low_coverage", 0) / n) if n else None,
        "mean_coverage": (metrics.get("coverage_sum", 0) / n) if n else None,
        "verification_override_rate": (overridden / verified) if verified else None,
    }
