"""Read side of shortlisting (P08-T03): override analytics.

An *override* is a human decision that goes against the AI band (shortlisting a lower match or an
eligibility-review case; not selecting a recommended candidate). Only decisions in approved
shortlists count - drafts are work in progress. The numbers feed AI quality monitoring
(docs/05 §12, P13-T07) and the dashboard; they never change a decision.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from django.db.models import QuerySet

from .models import Shortlist, ShortlistEntry


def decided_entries(
    organisation_id: Any, *, job_id: Any = None, since: datetime | None = None
) -> QuerySet[ShortlistEntry]:
    qs = (
        ShortlistEntry.objects.for_org(organisation_id)
        .filter(shortlist__status=Shortlist.Status.APPROVED)
        .exclude(decision=ShortlistEntry.Decision.UNDECIDED)
    )
    if job_id is not None:
        qs = qs.filter(shortlist__job_id=job_id)
    if since is not None:
        qs = qs.filter(shortlist__approved_at__gte=since)
    return qs


def override_stats(
    organisation_id: Any, *, job_id: Any = None, since: datetime | None = None
) -> dict[str, Any]:
    rows = list(
        decided_entries(organisation_id, job_id=job_id, since=since).values(
            "decision", "ai_band_at_decision", "override", "reason_code"
        )
    )
    overrides = [r for r in rows if r["override"]]
    by_band: dict[str, dict[str, int]] = {}
    for r in rows:
        band = r["ai_band_at_decision"] or "not_evaluated"
        by_band.setdefault(band, Counter())[r["decision"]] += 1
    return {
        "decisions": len(rows),
        "overrides": len(overrides),
        "override_rate": round(len(overrides) / len(rows), 4) if rows else None,
        "shortlisted_against_ai": sum(1 for r in overrides if r["decision"] == "shortlist"),
        "not_selected_against_ai": sum(1 for r in overrides if r["decision"] == "not_selected"),
        "override_reasons": dict(Counter(r["reason_code"] for r in overrides)),
        "by_band": {band: dict(c) for band, c in sorted(by_band.items())},
    }
