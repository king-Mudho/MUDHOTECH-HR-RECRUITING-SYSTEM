"""AI quality monitoring (P13-T07, docs/05 §13).

* ``check_override_alerts`` (daily): for each vacancy, the share of approved shortlist decisions
  that went against the AI band over the last 30 days. Above 30 % (with at least
  ``MIN_DECISIONS`` decisions) the organisation's HR managers and admins get one alert per vacancy
  per week suggesting a rubric review. The alert is advice to people; nothing changes
  automatically.
* ``drift_indicators`` (weekly, stored as the platform ``AIQualityReport`` row with no
  organisation): CV parse failure rate per week and, per engine version, the score distribution
  and band shares, flagging a shift between the two most recent versions. Aggregates only.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models.functions import TruncWeek

from apps.audit import services as audit
from apps.core.time import now

from .models import AIQualityReport, Evaluation

OVERRIDE_THRESHOLD = 0.30
MIN_DECISIONS = 10
WINDOW = timedelta(days=30)
MEAN_SHIFT_POINTS = 10.0
BAND_SHIFT_SHARE = 0.15
MIN_VERSION_SAMPLE = 20


def check_override_alerts() -> int:
    from apps.jobs.models import Job
    from apps.notifications import delivery as notifications
    from apps.organisations.models import Membership, Role
    from apps.shortlisting.models import ShortlistEntry
    from apps.shortlisting.selectors import override_stats

    since = now() - WINDOW
    pairs = set(
        ShortlistEntry.objects.unscoped()  # system sweep across organisations
        .filter(shortlist__status="approved", shortlist__approved_at__gte=since)
        .exclude(decision="undecided")
        .values_list("organisation_id", "shortlist__job_id")
    )
    week = now().strftime("%G-W%V")
    sent = 0
    for org_id, job_id in sorted(pairs, key=str):
        stats = override_stats(org_id, job_id=job_id, since=since)
        rate = stats["override_rate"]
        if stats["decisions"] < MIN_DECISIONS or rate is None or rate <= OVERRIDE_THRESHOLD:
            continue
        job = Job.objects.for_org(org_id).select_related("organisation").get(pk=job_id)
        recipients = (
            Membership.objects.for_org(org_id)
            .filter(status=Membership.Status.ACTIVE, role__in=[Role.HR_MANAGER, Role.ORG_ADMIN])
            .select_related("user")
        )
        with transaction.atomic():
            for m in recipients:
                notifications.notify(
                    m.user,
                    "ai_override_alert",
                    {
                        "organisation_name": job.organisation.name,
                        "job_title": job.title,
                        "override_rate": f"{round(rate * 100)}%",
                        "decisions": str(stats["decisions"]),
                        "report_url": f"{settings.FRONTEND_URL}/hr/reports",
                    },
                    dedupe_key=f"ai_override_alert:{job.pk}:{week}:{m.user_id}",
                    organisation=job.organisation,
                )
            audit.record(
                actor=None,
                actor_type="system",
                action="ai_quality.override_alert",
                target=job,
                organisation=org_id,
                after={"override_rate": rate, "decisions": stats["decisions"], "week": week},
            )
        sent += 1
    return sent


def _versions(since: Any) -> dict[str, dict[str, Any]]:
    rows = (
        Evaluation.objects.unscoped()  # platform aggregate, no candidate data leaves
        .filter(created_at__gte=since)
        .exclude(status=Evaluation.Status.SUPERSEDED)
        .values("engine_version", "band", "total_score", "created_at")
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[r["engine_version"] or "unknown"].append(r)
    out: dict[str, dict[str, Any]] = {}
    for version, items in grouped.items():
        scores = [float(i["total_score"]) for i in items if i["total_score"] is not None]
        bands: dict[str, int] = defaultdict(int)
        for i in items:
            bands[i["band"]] += 1
        out[version] = {
            "evaluations": len(items),
            "mean_score": round(statistics.fmean(scores), 2) if scores else None,
            "median_score": round(statistics.median(scores), 2) if scores else None,
            "band_shares": {b: round(n / len(items), 4) for b, n in sorted(bands.items())},
            "first_seen": min(i["created_at"] for i in items).isoformat(),
        }
    return out


def _shift(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if min(old["evaluations"], new["evaluations"]) < MIN_VERSION_SAMPLE:
        return reasons
    if (
        old["mean_score"] is not None
        and new["mean_score"] is not None
        and abs(new["mean_score"] - old["mean_score"]) >= MEAN_SHIFT_POINTS
    ):
        reasons.append("mean_score")
    for band in set(old["band_shares"]) | set(new["band_shares"]):
        diff = new["band_shares"].get(band, 0) - old["band_shares"].get(band, 0)
        if abs(diff) >= BAND_SHIFT_SHARE:
            reasons.append(f"band:{band}")
    return sorted(reasons)


def drift_indicators(days: int = 90) -> dict[str, Any]:
    from apps.resumes.models import ExtractionRun, RunStatus

    since = now() - timedelta(days=days)
    weekly: dict[str, dict[str, int]] = {}
    runs = (
        ExtractionRun.objects.unscoped()
        .filter(finished_at__gte=since)
        .exclude(status__in=[RunStatus.PENDING, RunStatus.RUNNING])
        .annotate(week=TruncWeek("finished_at"))
        .values_list("week", "status")
    )
    for week, status in runs:
        slot = weekly.setdefault(week.date().isoformat(), {"runs": 0, "failed": 0})
        slot["runs"] += 1
        slot["failed"] += 1 if status == RunStatus.FAILED else 0
    parse_trend = [
        {"week": w, **v, "failure_rate": round(v["failed"] / v["runs"], 4) if v["runs"] else None}
        for w, v in sorted(weekly.items())
    ]
    versions = _versions(since)
    ordered = sorted(versions.items(), key=lambda kv: kv[1]["first_seen"])
    shift: dict[str, Any] | None = None
    if len(ordered) >= 2:
        (old_v, old), (new_v, new) = ordered[-2], ordered[-1]
        shift = {"from": old_v, "to": new_v, "flags": _shift(old, new)}
    return {
        "window_days": days,
        "computed_at": now().isoformat(),
        "parse_failure_trend": parse_trend,
        "engine_versions": [{"engine_version": v, **d} for v, d in ordered],
        "latest_shift": shift,
    }


def store_platform_report() -> AIQualityReport:
    """The weekly platform row (organisation and vacancy empty) holding the drift indicators."""
    data = drift_indicators()
    report, _ = AIQualityReport.objects.update_or_create(
        organisation=None, job=None, period=now().date(), defaults={"metrics": {"drift": data}}
    )
    if data["latest_shift"] and data["latest_shift"]["flags"]:
        audit.record(
            actor=None,
            actor_type="system",
            action="ai_quality.drift_flagged",
            target=("ai_quality_report", str(report.pk)),
            after=data["latest_shift"],
        )
    return report


def latest_platform_report() -> dict[str, Any]:
    row = (
        AIQualityReport.objects.filter(organisation__isnull=True, job__isnull=True)
        .order_by("-period")
        .first()
    )
    if row is not None and "drift" in (row.metrics or {}):
        return dict(row.metrics["drift"])
    return drift_indicators()
