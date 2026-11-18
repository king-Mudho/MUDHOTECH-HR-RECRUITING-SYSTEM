"""Pilot benchmark (P10-T08; development/CI only).

``run_pilot_benchmark`` creates a fresh vacancy from the demo Software Developer spec, submits N
applications with CVs from the whole synthetic corpus (all five roles, including scanned,
corrupt, encrypted and prompt-injection CVs, as a real pilot would receive) through the candidate
services, waits until every application has left ``submitted``/``processing`` and writes an
accounting table: every submission accounted for, parse outcomes, bands, flags and timings.

``inline=True`` runs the outbox consumers in this process (no broker or workers needed); otherwise
the workers process the applications and this module only waits and counts.
"""

from __future__ import annotations

import json
import platform
import shutil
import statistics
import time as clock
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.test.utils import override_settings

from apps.applications.models import Application
from apps.core import storage
from apps.core.time import now
from apps.jobs.models import Job

CORPUS = Path(settings.BASE_DIR) / "fixtures" / "synthetic_cvs"
WAITING = ("submitted", "processing")


@dataclass
class PilotResult:
    job_id: str
    title: str
    submitted: list[str] = field(default_factory=list)
    corpus_files: dict[str, str] = field(default_factory=dict)  # application id -> CV file
    started: datetime = field(default_factory=now)
    seconds_to_submit: float = 0.0
    seconds_to_process: float = 0.0
    timed_out: bool = False


def corpus(count: int) -> list[dict[str, Any]]:
    """Deterministic mix of the labelled corpus (every role and every hard case)."""
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    labels.sort(key=lambda c: c["id"])
    # interleave roles so any prefix of the list is a fair mix
    by_role: dict[str, list[dict[str, Any]]] = {}
    for c in labels:
        by_role.setdefault(c["role"], []).append(c)
    mixed: list[dict[str, Any]] = []
    while len(mixed) < len(labels):
        for items in by_role.values():
            if items:
                mixed.append(items.pop(0))
    return [mixed[i % len(mixed)] for i in range(count)]


def _team(org: Any) -> dict[Any, Any]:
    from apps.organisations.models import Membership

    return {
        m.role: m.user
        for m in Membership.objects.for_org(org).select_related("user").order_by("created_at")
    }


def create_vacancy() -> Job:
    from apps.platform.demo_seed import JOBS, create_job_from_spec

    spec = next(j for j in JOBS if j.title == "Software Developer")
    template = Job.objects.unscoped().filter(title=spec.title, status="published").first()
    if template is None:
        raise RuntimeError("Run seed_demo first (demo organisation and vacancy).")
    title = f"Pilot Software Developer {now():%Y%m%d-%H%M%S}"
    return create_job_from_spec(
        template.organisation, _team(template.organisation), spec, title=title
    )


def submit(job: Job, count: int, password: str) -> PilotResult:
    from apps.applications import services as applications
    from apps.documents.models import Document, Purpose, ScanStatus
    from apps.platform.core_scenario import _answer, daytime_zone
    from apps.platform.demo_seed import _user

    result = PilotResult(job_id=str(job.pk), title=job.title)
    stamp = f"{now():%Y%m%d%H%M%S}"
    zone = daytime_zone()
    start = clock.perf_counter()
    for i, label in enumerate(corpus(count), start=1):
        # the account carries the synthetic person named on the CV, as a real applicant's would
        first, _, last = label["person"]["name"].partition(" ")
        user = _user(f"pilot{stamp}-{i:03d}@pilot.test", password, first, last, timezone=zone)
        app, _ = applications.start_or_resume_draft(job, user, source={"channel": "pilot"})
        data = (CORPUS / label["file"]).read_bytes()
        key = f"cv/pilot/{user.pk}/{label['file']}"
        doc = Document.objects.create(
            owner_user=user,
            purpose=Purpose.CV,
            original_filename=label["file"],
            size_bytes=len(data),
            storage_key=key,
            bucket="documents",
            scan_status=ScanStatus.CLEAN,  # synthetic corpus files, pre-cleared
        )
        storage.put_bytes("documents", key, data, "application/octet-stream")
        applications.set_documents(
            user, app.pk, [{"document_id": doc.pk, "role": "cv", "required_doc_key": "cv"}]
        )
        answers = [
            {"key": q["key"], "value": _answer(q, i)}
            for q in applications.question_defs(app)
            if _answer(q, i) is not None
        ]
        if answers:
            applications.upsert_answers(user, app.pk, answers)
        applications.submit(user, app.pk, accept_privacy=True)
        result.submitted.append(str(app.pk))
        result.corpus_files[str(app.pk)] = label["file"]
    result.seconds_to_submit = clock.perf_counter() - start
    return result


def _waiting(job_id: str) -> int:
    """Applications still in flight; a database restart (fault injection) counts as "still
    waiting" so the benchmark rides it out like a client would."""
    from django.db import OperationalError, connection

    try:
        return Application.objects.unscoped().filter(job_id=job_id, status__in=WAITING).count()
    except OperationalError:
        connection.close()
        return -1


def wait(result: PilotResult, *, inline: bool, timeout: float, poll: float = 5.0) -> None:
    from apps.core.outbox import relay_batch

    start = clock.perf_counter()
    while _waiting(result.job_id) != 0:
        if clock.perf_counter() - start > timeout:
            result.timed_out = True
            break
        if inline:
            if not relay_batch(100).published:
                clock.sleep(0.2)  # backoff of a failed event, or nothing due yet
        else:
            clock.sleep(poll)
    result.seconds_to_process = clock.perf_counter() - start


def accounting(result: PilotResult) -> dict[str, Any]:
    from apps.resumes.models import ExtractionRun
    from apps.screening.models import Evaluation

    apps = list(Application.objects.unscoped().filter(job_id=result.job_id))
    found = {str(a.pk) for a in apps}
    runs = ExtractionRun.objects.unscoped().filter(application__job_id=result.job_id)
    latest: dict[str, str] = {}
    for run in runs.order_by("created_at"):
        latest[str(run.application_id)] = run.status
    flags: Counter[str] = Counter()
    for a in apps:
        flags.update(a.flags or [])
    evaluations = Evaluation.objects.unscoped().filter(application__job_id=result.job_id)
    waits = [
        (e.created_at - a.submitted_at).total_seconds()
        for e in evaluations.select_related("application")
        for a in [e.application]
        if a.submitted_at
    ]
    labels = {
        c["file"]: c
        for c in json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    }
    by_role: dict[str, Counter[str]] = {}
    for a in apps:
        label = labels.get(result.corpus_files.get(str(a.pk), ""), {})
        role = label.get("role", "unknown")
        # gold suitability is labelled for the CV's own role, i.e. this vacancy for developers
        suitability = (
            label.get("hr_reference_suitability", "") if role == "software_developer" else ""
        )
        key = f"{role} ({suitability})" if suitability else role
        by_role.setdefault(key, Counter())[a.ai_band or "none"] += 1
    from django.db.models import Count

    from apps.applications.models import ApplicationStatusEvent

    # duplicates a redelivered or re-dispatched task could cause (runs and notifications are
    # already unique in the database): the same input evaluated twice, or a repeated status move
    duplicate_evaluations = (
        evaluations.values("application_id", "input_hash")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    duplicate_moves = (
        ApplicationStatusEvent.objects.unscoped()
        .filter(application__job_id=result.job_id, to_status="under_review")
        .values("application_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    return {
        "duplicate_evaluations": duplicate_evaluations,
        "duplicate_moves": duplicate_moves,
        "by_role": by_role,
        "submitted": len(result.submitted),
        "records": len(found),
        "missing": sorted(set(result.submitted) - found),
        "statuses": Counter(a.status for a in apps),
        "parse": Counter(latest.get(str(a.pk), "none") for a in apps),
        "bands": Counter(a.ai_band or "none" for a in apps),
        "flags": flags,
        "evaluations": evaluations.count(),
        "evaluated_apps": evaluations.values("application").distinct().count(),
        "median_s": statistics.median(waits) if waits else None,
        "max_s": max(waits) if waits else None,
    }


def _table(title: str, counts: Counter[str], total: int) -> list[str]:
    lines = [f"| {title} | Count | Share |", "|---|---|---|"]
    for key, n in counts.most_common():
        lines.append(f"| {key} | {n} | {n / total:.0%} |" if total else f"| {key} | {n} | - |")
    return lines


def _role_table(by_role: dict[str, Counter[str]]) -> list[str]:
    bands = sorted({b for c in by_role.values() for b in c})
    lines = ["| CV role | " + " | ".join(bands) + " |", "|---|" + "---|" * len(bands)]
    for role in sorted(by_role):
        lines.append(f"| {role} | " + " | ".join(str(by_role[role][b]) for b in bands) + " |")
    return lines


def _semantic_on() -> bool:
    from apps.screening.services import _semantic

    return _semantic() is not None


def report(result: PilotResult, acc: dict[str, Any], *, inline: bool) -> str:
    total = acc["records"]
    waiting = acc["statuses"].get("submitted", 0) + acc["statuses"].get("processing", 0)
    ok = (
        acc["records"] == acc["submitted"]
        and not acc["missing"]
        and not result.timed_out
        and not acc["duplicate_evaluations"]
        and not acc["duplicate_moves"]
    )
    lines = [
        f"# Pilot benchmark — {result.started:%Y-%m-%d}",
        "",
        "Generated by `python manage.py run_pilot_benchmark` (P10-T08). Synthetic corpus only "
        "(`backend/fixtures/synthetic_cvs`, all five roles including scanned, corrupt, "
        "encrypted and prompt-injection CVs) - no real people.",
        "",
        f"- Vacancy: **{result.title}** (`{result.job_id}`)",
        f"- Capabilities: semantic matching **{'on' if _semantic_on() else 'off'}**, "
        f"OCR **{'on' if shutil.which('tesseract') else 'off (scanned CVs cannot be read)'}**",
        f"- Mode: {'inline (consumers in one process)' if inline else 'workers'}; "
        f"{platform.system()} {platform.machine()} · Python {platform.python_version()}",
        f"- Submitting {acc['submitted']} applications"
        + (" (inline: includes extraction and screening)" if inline else "")
        + f": {result.seconds_to_submit:.1f} s; "
        f"processing until none waits: {result.seconds_to_process:.1f} s"
        + (" (**timed out**)" if result.timed_out else ""),
        "",
        "## Accounting",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Applications submitted | {acc['submitted']} |",
        f"| Application records found | {acc['records']} / {acc['submitted']} |",
        f"| Missing | {len(acc['missing'])} |",
        f"| Still waiting (submitted/processing) | {waiting} |",
        f"| Evaluations stored (applications evaluated) | {acc['evaluations']} "
        f"({acc['evaluated_apps']}) |",
        "| Submission to evaluation, median / max | "
        + (
            f"{acc['median_s']:.1f} s / {acc['max_s']:.1f} s |"
            if acc["median_s"] is not None
            else "- |"
        ),
        f"| Duplicate evaluations (same input twice) | {acc['duplicate_evaluations']} |",
        f"| Duplicate status moves to under review | {acc['duplicate_moves']} |",
        f"| **Every application accounted for** | **{'yes' if ok else 'NO'}** |",
        "",
        "## Status",
        "",
        *_table("Status", acc["statuses"], total),
        "",
        "## CV parsing (latest extraction run per application)",
        "",
        *_table("Outcome", acc["parse"], total),
        "",
        "## Bands (routing hints for people; there is no reject band)",
        "",
        *_table("Band", acc["bands"], total),
        "",
        "## Bands by CV role (developer CVs split by gold suitability)",
        "",
        *_role_table(acc["by_role"]),
        "",
        "## Flags",
        "",
        *(_table("Flag", acc["flags"], total) if acc["flags"] else ["No flags raised."]),
        "",
        "Applications whose CV could not be read wait in `processing_error` for HR (never lost); "
        "scanned CVs need Tesseract (worker image). Other-role CVs are expected to land in "
        "*review needed* or *lower match*.",
        "",
    ]
    return "\n".join(lines)


@contextmanager
def _inline(enabled: bool) -> Iterator[None]:
    """Run every task in this process: outbox consumers and the tasks they queue themselves.
    Celery reads its configuration once, so ``override_settings`` alone does not reach it."""
    if not enabled:
        yield
        return
    from config.celery import app

    previous = app.conf.task_always_eager
    app.conf.task_always_eager = True
    try:
        with override_settings(OUTBOX_EAGER_PUBLISH=True, CELERY_TASK_ALWAYS_EAGER=True):
            yield
    finally:
        app.conf.task_always_eager = previous


def run(
    count: int, password: str, *, inline: bool, timeout: float, out: Path | None
) -> tuple[PilotResult, dict[str, Any], str]:
    with _inline(inline):
        job = create_vacancy()
        result = submit(job, count, password)
        wait(result, inline=inline, timeout=timeout)
    acc = accounting(result)
    text = report(result, acc, inline=inline)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return result, acc, text
