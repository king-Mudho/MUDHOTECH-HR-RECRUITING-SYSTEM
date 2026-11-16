"""Vacancy-level screening analytics (P07-T12, EC-AI-14/15).

Counts only each application's current (non-superseded) evaluation, for applications the member
can see. The numbers inform HR; nothing here cuts anyone off (no automatic shortlist size).
"""

from __future__ import annotations

from typing import Any

from ai_engine.evaluation.bands import BANDS

from .models import Evaluation
from .runs import _job

LOW_COVERAGE = 0.6
LOW_COVERAGE_SHARE = 0.5  # EC-AI-15: at least half the evaluations have low coverage
HIGH_SCORE = 85.0
SATURATION_SHARE = 0.4  # EC-AI-14: many candidates score very high
MIN_SAMPLE = 5


def vacancy_analytics(membership: Any, job_id: Any) -> dict[str, Any]:
    from apps.applications.hr import applications_visible_to

    job = _job(membership, job_id)
    visible = applications_visible_to(membership).filter(job=job).values("pk")
    rows = list(
        Evaluation.objects.for_org(job.organisation_id)
        .filter(application__in=visible)
        .exclude(status=Evaluation.Status.SUPERSEDED)
        .values("band", "total_score", "coverage")
    )
    bands = dict.fromkeys(BANDS, 0)
    buckets = [0] * 10  # 0-9, 10-19, ..., 90-100
    scores: list[float] = []
    low = 0
    for r in rows:
        bands[r["band"]] = bands.get(r["band"], 0) + 1
        if float(r["coverage"]) < LOW_COVERAGE:
            low += 1
        if r["total_score"] is not None:
            value = float(r["total_score"])
            scores.append(value)
            buckets[min(int(value // 10), 9)] += 1
    n = len(rows)
    high = sum(1 for s in scores if s >= HIGH_SCORE)
    warnings = []
    if n >= MIN_SAMPLE and low / n >= LOW_COVERAGE_SHARE:
        warnings.append(
            {
                "code": "low_coverage",
                "message": "Low evidence coverage — review the rubric or request information.",
                "count": low,
            }
        )
    if scores and len(scores) >= MIN_SAMPLE and high / len(scores) >= SATURATION_SHARE:
        warnings.append(
            {
                "code": "high_score_saturation",
                "message": (
                    "Many candidates score very high. Consider how many you want to shortlist and "
                    "review the rubric; there is no automatic cut-off."
                ),
                "count": high,
            }
        )
    ordered = sorted(scores)
    median = None
    if ordered:
        mid = len(ordered) // 2
        median = (
            ordered[mid] if len(ordered) % 2 else round((ordered[mid - 1] + ordered[mid]) / 2, 2)
        )
    return {
        "job_id": job.pk,
        "evaluated": n,
        "bands": [{"band": b, "count": c} for b, c in bands.items()],
        "score_buckets": [
            {"start": i * 10, "end": 100 if i == 9 else i * 10 + 9, "count": c}
            for i, c in enumerate(buckets)
        ],
        "median_score": median,
        "low_coverage": low,
        "high_scores": high,
        "warnings": warnings,
        "ai_notice": "AI-assisted suggestion — requires human review",
    }
