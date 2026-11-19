"""Recruitment analytics computed from the raw data (docs/01 M19, P13-T03).

Everything is counted from the organisation's own rows, filtered by submission date, department
and vacancy, so every figure can be reconciled with a direct query (the tests do). Aggregates
only: no names, contact details or protected attributes leave this module.

Sections:
* ``timing`` - hours from submission to the first human review action, to shortlisting and to
  hire (count, median, mean, 90th percentile).
* ``funnel`` - applications that *reached* each stage and the conversion from the stage before.
* ``sources`` - applicants by UTM source (``direct`` when none), with how many were shortlisted.
* ``questionnaire`` - unfinished applications by the last step reached and, for one vacancy,
  how often each question was answered by people who started the questions.
* ``processing`` - CV extraction failure and OCR rates, extraction time, submission-to-evaluation.
* ``ai_agreement`` - human decisions against the AI band (override rate by band and vacancy).
* ``clarifications`` - response rate and time to answer.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone

from apps.applications.dashboard import (
    FUNNEL_REVIEWED,
    INTERVIEW_ONWARD,
    OFFER_ONWARD,
    SHORTLIST_ONWARD,
    _reached,
)
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.core.time import now

STEPS = ("contact", "profile", "documents", "questions", "review", "done")
DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True)
class Scope:
    organisation_id: Any
    start: datetime
    end: datetime
    department_id: Any = None
    job_id: Any = None

    def as_params(self) -> dict[str, Any]:
        return {
            "from": timezone.localdate(self.start).isoformat(),
            "to": timezone.localdate(self.end).isoformat(),
            "department": str(self.department_id) if self.department_id else None,
            "job": str(self.job_id) if self.job_id else None,
        }


def scope_from(organisation_id: Any, params: dict[str, Any]) -> Scope:
    """``from``/``to`` are local dates (inclusive); default: the last 90 days."""
    tz = timezone.get_default_timezone()
    today = timezone.localdate()

    def parse(value: Any) -> date | None:
        try:
            return date.fromisoformat(str(value)) if value else None
        except ValueError:
            return None

    end_day = parse(params.get("to")) or today
    start_day = parse(params.get("from")) or end_day - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    return Scope(
        organisation_id=organisation_id,
        start=timezone.make_aware(datetime.combine(start_day, time.min), tz),
        end=timezone.make_aware(datetime.combine(end_day, time.max), tz),
        department_id=params.get("department") or None,
        job_id=params.get("job") or None,
    )


def submitted(scope: Scope) -> QuerySet[Application]:
    qs = Application.objects.for_org(scope.organisation_id).filter(
        submitted_at__isnull=False, submitted_at__gte=scope.start, submitted_at__lte=scope.end
    )
    if scope.department_id:
        qs = qs.filter(job__department_id=scope.department_id)
    if scope.job_id:
        qs = qs.filter(job_id=scope.job_id)
    return qs


def _stats(hours: list[float]) -> dict[str, Any]:
    if not hours:
        return {"count": 0, "median_hours": None, "mean_hours": None, "p90_hours": None}
    ordered = sorted(hours)
    p90 = ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]
    return {
        "count": len(ordered),
        "median_hours": round(statistics.median(ordered), 2),
        "mean_hours": round(statistics.fmean(ordered), 2),
        "p90_hours": round(p90, 2),
    }


def _first_event(org: Any, **filters: Any) -> Subquery:
    return Subquery(
        ApplicationStatusEvent.objects.for_org(org)
        .filter(application=OuterRef("pk"), **filters)
        .order_by("at")
        .values("at")[:1]
    )


def timing(scope: Scope) -> dict[str, Any]:
    org = scope.organisation_id
    rows = submitted(scope).annotate(
        reviewed_at=_first_event(org, actor_type="human"),
        shortlisted_at=_first_event(org, to_status=Status.SHORTLISTED),
        hired_at=_first_event(org, to_status=Status.HIRED),
    )
    review: list[float] = []
    shortlist: list[float] = []
    hire: list[float] = []
    for r in rows.values("submitted_at", "reviewed_at", "shortlisted_at", "hired_at"):
        start = r["submitted_at"]
        for key, bucket in (
            ("reviewed_at", review),
            ("shortlisted_at", shortlist),
            ("hired_at", hire),
        ):
            if r[key] is not None and r[key] >= start:
                bucket.append((r[key] - start).total_seconds() / 3600)
    return {
        "time_to_review": _stats(review),
        "time_to_shortlist": _stats(shortlist),
        "time_to_hire": _stats(hire),
    }


def funnel(scope: Scope) -> dict[str, Any]:
    counts = submitted(scope).aggregate(
        submitted=Count("pk"),
        reviewed=Count("pk", filter=_reached(FUNNEL_REVIEWED)),
        shortlisted=Count("pk", filter=_reached(SHORTLIST_ONWARD)),
        interviewed=Count("pk", filter=_reached(INTERVIEW_ONWARD)),
        offered=Count("pk", filter=_reached(OFFER_ONWARD)),
        hired=Count("pk", filter=Q(status=Status.HIRED)),
        withdrawn=Count("pk", filter=Q(status=Status.WITHDRAWN)),
    )
    stages = []
    previous: int | None = None
    for name in ("submitted", "reviewed", "shortlisted", "interviewed", "offered", "hired"):
        n = counts[name]
        stages.append(
            {
                "stage": name,
                "count": n,
                "conversion": round(n / previous, 4) if previous else None,
            }
        )
        previous = n
    return {"stages": stages, "withdrawn": counts["withdrawn"]}


def sources(scope: Scope) -> list[dict[str, Any]]:
    rows = (
        submitted(scope)
        .annotate(src=KeyTextTransform("source", "source"))
        .values("src")
        .annotate(
            applications=Count("pk"),
            shortlisted=Count("pk", filter=_reached(SHORTLIST_ONWARD)),
        )
        .order_by("-applications", "src")
    )
    merged: dict[str, dict[str, int]] = {}
    for r in rows:
        name = (r["src"] or "direct").strip().lower()[:60] or "direct"
        slot = merged.setdefault(name, {"applications": 0, "shortlisted": 0})
        slot["applications"] += r["applications"]
        slot["shortlisted"] += r["shortlisted"]
    return [{"source": k, **v} for k, v in merged.items()]


def questionnaire(scope: Scope) -> dict[str, Any]:
    from apps.questionnaires.models import Question, QuestionResponse

    started = Application.objects.for_org(scope.organisation_id).filter(
        created_at__gte=scope.start, created_at__lte=scope.end
    )
    if scope.department_id:
        started = started.filter(job__department_id=scope.department_id)
    if scope.job_id:
        started = started.filter(job_id=scope.job_id)
    unfinished = started.filter(status__in=[Status.DRAFT, Status.ABANDONED])
    by_step = dict(
        unfinished.values_list("last_step").annotate(n=Count("pk")).values_list("last_step", "n")
    )
    steps = [{"step": STEPS[i - 1], "unfinished": by_step.get(i, 0)} for i in range(1, len(STEPS))]
    questions: list[dict[str, Any]] = []
    if scope.job_id:
        answering = started.filter(responses__isnull=False).distinct()
        reached = answering.count()
        answered = dict(
            QuestionResponse.objects.for_org(scope.organisation_id)
            .filter(application__in=answering.values("pk"), answered_at__isnull=False)
            .values_list("question_id")
            .annotate(n=Count("application", distinct=True))
            .values_list("question_id", "n")
        )
        ids = set(answered)
        for q in (
            Question.objects.for_org(scope.organisation_id)
            .filter(Q(pk__in=ids) | Q(questionnaire__job_version__job_id=scope.job_id))
            .order_by("order", "key")
            .distinct()
        ):
            n = answered.get(q.pk, 0)
            questions.append(
                {
                    "question_id": q.pk,
                    "key": q.key,
                    "prompt": q.prompt[:200],
                    "required": q.required,
                    "answered": n,
                    "started": reached,
                    "drop_off": round(1 - n / reached, 4) if reached else None,
                }
            )
    return {
        "started": started.count(),
        "submitted": started.exclude(submitted_at__isnull=True).count(),
        "unfinished": unfinished.count(),
        "unfinished_by_step": steps,
        "questions": questions,
    }


def processing(scope: Scope) -> dict[str, Any]:
    from apps.resumes.models import ExtractionRun, RunStatus
    from apps.screening.models import Evaluation

    apps = submitted(scope)
    runs = ExtractionRun.objects.for_org(scope.organisation_id).filter(
        application__in=apps.values("pk")
    )
    finished = runs.exclude(status__in=[RunStatus.PENDING, RunStatus.RUNNING])
    total = finished.count()
    failed = finished.filter(status=RunStatus.FAILED).count()
    partial = finished.filter(status=RunStatus.PARTIAL).count()
    ocr = finished.filter(timings_ms__has_key="ocr").count()
    durations = [
        (r["finished_at"] - r["started_at"]).total_seconds()
        for r in finished.filter(started_at__isnull=False, finished_at__isnull=False).values(
            "started_at", "finished_at"
        )
        if r["finished_at"] >= r["started_at"]
    ]
    first_eval = apps.annotate(
        evaluated_at=Subquery(
            Evaluation.objects.for_org(scope.organisation_id)
            .filter(application=OuterRef("pk"))
            .order_by("created_at")
            .values("created_at")[:1]
        )
    ).filter(evaluated_at__isnull=False)
    to_eval = [
        (r["evaluated_at"] - r["submitted_at"]).total_seconds() / 3600
        for r in first_eval.values("submitted_at", "evaluated_at")
        if r["evaluated_at"] >= r["submitted_at"]
    ]
    return {
        "extraction_runs": total,
        "parse_failure_rate": round(failed / total, 4) if total else None,
        "partial_rate": round(partial / total, 4) if total else None,
        "ocr_rate": round(ocr / total, 4) if total else None,
        "mean_extraction_seconds": round(statistics.fmean(durations), 2) if durations else None,
        "submission_to_evaluation": _stats(to_eval),
    }


def ai_agreement(scope: Scope) -> dict[str, Any]:
    from apps.screening.models import AIQualityReport
    from apps.screening.quality import rates
    from apps.shortlisting.selectors import decided_entries

    entries = decided_entries(scope.organisation_id, job_id=scope.job_id, since=scope.start).filter(
        shortlist__approved_at__lte=scope.end
    )
    if scope.department_id:
        entries = entries.filter(shortlist__job__department_id=scope.department_id)
    rows = list(entries.values("decision", "ai_band_at_decision", "override", "shortlist__job_id"))
    by_band: dict[str, dict[str, int]] = {}
    by_job: dict[str, dict[str, int]] = {}
    for r in rows:
        band = r["ai_band_at_decision"] or "not_evaluated"
        b = by_band.setdefault(band, {"decisions": 0, "overrides": 0})
        j = by_job.setdefault(str(r["shortlist__job_id"]), {"decisions": 0, "overrides": 0})
        for slot in (b, j):
            slot["decisions"] += 1
            slot["overrides"] += 1 if r["override"] else 0
    overrides = sum(1 for r in rows if r["override"])

    def with_rate(d: dict[str, int]) -> dict[str, Any]:
        rate = d["overrides"] / d["decisions"] if d["decisions"] else None
        return {**d, "override_rate": round(rate, 4) if rate is not None else None}

    reports = AIQualityReport.objects.filter(
        organisation_id=scope.organisation_id,
        period__gte=timezone.localdate(scope.start),
        period__lte=timezone.localdate(scope.end),
    )
    if scope.job_id:
        reports = reports.filter(job_id=scope.job_id)
    totals: dict[str, float] = {}
    for metrics in reports.values_list("metrics", flat=True):
        for k, v in (metrics or {}).items():
            if isinstance(v, (int, float)):
                totals[k] = totals.get(k, 0) + v
    derived = rates(totals)
    n = len(rows)
    return {
        "decisions": n,
        "overrides": overrides,
        "override_rate": round(overrides / n, 4) if n else None,
        "agreement_rate": round(1 - overrides / n, 4) if n else None,
        "by_band": [{"band": k, **with_rate(v)} for k, v in sorted(by_band.items())],
        "by_job": [{"job_id": k, **with_rate(v)} for k, v in sorted(by_job.items())],
        "claim_verification_override_rate": derived["verification_override_rate"],
        "evaluations": int(totals.get("evaluations", 0)),
    }


def clarifications(scope: Scope) -> dict[str, Any]:
    from apps.messaging.models import ClarificationRequest

    qs = ClarificationRequest.objects.for_org(scope.organisation_id).filter(
        application__in=submitted(scope).values("pk")
    )
    counts = qs.aggregate(
        total=Count("pk"),
        answered=Count("pk", filter=Q(status="answered")),
        expired=Count("pk", filter=Q(status="expired")),
        open=Count("pk", filter=Q(status="open")),
        cancelled=Count("pk", filter=Q(status="cancelled")),
    )
    closed = counts["answered"] + counts["expired"]
    hours = [
        (r["answered_at"] - r["created_at"]).total_seconds() / 3600
        for r in qs.filter(answered_at__isnull=False).values("created_at", "answered_at")
        if r["answered_at"] >= r["created_at"]
    ]
    return {
        **counts,
        "response_rate": round(counts["answered"] / closed, 4) if closed else None,
        "time_to_answer": _stats(hours),
    }


def report(scope: Scope) -> dict[str, Any]:
    return {
        "scope": scope.as_params(),
        "computed_at": now(),
        "timing": timing(scope),
        "funnel": funnel(scope),
        "sources": sources(scope),
        "questionnaire": questionnaire(scope),
        "processing": processing(scope),
        "ai_agreement": ai_agreement(scope),
        "clarifications": clarifications(scope),
        "applications": submitted(scope).count(),
    }
