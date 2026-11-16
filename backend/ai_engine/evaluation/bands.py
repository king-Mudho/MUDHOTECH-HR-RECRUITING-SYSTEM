"""Bands (P07-T05, docs/05 §10). There is no "reject" band: every band is a routing hint for a
human. Thresholds are per organisation (``BandPolicy``), defaults below.

Order of precedence:
1. ``manual_review_requested`` - the candidate objected to automated processing (EC-AI-12);
2. ``eligibility_review`` - a knock-out answer differs from the expected one (EC-AI-05);
3. ``review_needed`` - low coverage or confidence, conflicts, unknown essentials, or processing
   flags (OCR, language, not-a-CV, injection);
4. ``recommended_for_review`` - total >= threshold and every essential met;
5. ``lower_match`` - otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from ai_engine.contracts import Contract, Flag
from ai_engine.evaluation.scoring import PROCESSING_FLAGS, Scores

MANUAL = "manual_review_requested"
ELIGIBILITY = "eligibility_review"
REVIEW = "review_needed"
RECOMMENDED = "recommended_for_review"
LOWER = "lower_match"
BANDS = (MANUAL, ELIGIBILITY, REVIEW, RECOMMENDED, LOWER)


class BandPolicy(Contract):
    recommended_min_score: float = Field(default=70, ge=0, le=100)
    review_min_coverage: float = Field(default=0.6, ge=0, le=1)


def band_for(
    scores: Scores,
    *,
    policy: BandPolicy | None = None,
    objected: bool = False,
    eligibility_unmet: bool = False,
    conflicts: int = 0,
    flags: Iterable[Flag] = (),
) -> tuple[str, tuple[str, ...]]:
    """(band, reasons) - reasons are codes the UI explains in plain words."""
    policy = policy or BandPolicy()
    if objected:
        return MANUAL, ("candidate_objected_to_automated_processing",)
    if eligibility_unmet:
        return ELIGIBILITY, ("knockout_answer_unmet",)
    reasons = []
    if scores.coverage < policy.review_min_coverage:
        reasons.append("low_coverage")
    if scores.confidence == "low":
        reasons.append("low_confidence")
    if conflicts:
        reasons.append("conflicts")
    if scores.essentials.unknown:
        reasons.append("essentials_unknown")
    processing = sorted(f.value for f in set(flags) & PROCESSING_FLAGS)
    reasons += [f"flag:{f}" for f in processing]
    if reasons:
        return REVIEW, tuple(reasons)
    # docs/05 §10 "all essentials met/explicit": explicit evidence (even listed-only, 50) counts;
    # weak (<= 25) or unknown essentials do not
    essentials_all_met = not (scores.essentials.not_evidenced or scores.essentials.unknown)
    if (
        scores.total is not None
        and scores.total >= policy.recommended_min_score
        and essentials_all_met
    ):
        return RECOMMENDED, ("score_and_essentials",)
    return LOWER, ("below_threshold_or_essentials_weak",)
