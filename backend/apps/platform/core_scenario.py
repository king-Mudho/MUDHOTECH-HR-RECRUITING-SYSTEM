"""Core-scenario seed for the end-to-end test (P08-T13; development/CI only).

After ``seed_demo``, submits N synthetic applications to the demo Software Developer vacancy through
the same services the candidate API uses (draft -> CV -> answers -> submit with consent). The
workers then extract and screen them via the outbox. CVs come from the synthetic corpus
(``fixtures/synthetic_cvs``) - no real people.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.accounts.models import User
from apps.core import storage
from apps.jobs.models import Job

CORPUS = Path(settings.BASE_DIR) / "fixtures" / "synthetic_cvs"
JOB_TITLE = "Software Developer"


@dataclass
class ScenarioResult:
    job_id: str = ""
    submitted: list[str] = field(default_factory=list)
    skipped: int = 0


def _cvs() -> list[tuple[str, bytes]]:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    usable = [
        c
        for c in labels
        if c["role"] == "software_developer"
        and c["parse_expected"] == "ok"
        and not c["needs_ocr"]
        and not c["injection"]
    ]
    return [(c["file"], (CORPUS / c["file"]).read_bytes()) for c in usable]


def _answer(question: dict[str, Any], i: int) -> Any:
    kind = question.get("type")
    options = [str(o) for o in question.get("options") or []]
    if kind == "yes_no":
        return "yes" if i % 9 else "no"
    if kind in ("number", "scale", "availability", "salary_expectation"):
        config = question.get("config") or {}
        low = int(config.get("min") or 0)
        high = int(config.get("max") or low + 10)
        return min(high, low + i % 8)
    if kind in ("single_choice", "dropdown") and options:
        return options[i % len(options)]
    if kind in ("multi_choice", "multiple_choice") and options:
        return options[:1]
    if kind == "date":
        return date.today().isoformat()
    if kind == "file":
        return None
    return "Built and maintained Django services with PostgreSQL for a payments team."


DAYTIME_ZONES = (
    "Africa/Harare",
    "Europe/London",
    "America/Sao_Paulo",
    "America/New_York",
    "America/Los_Angeles",
    "Pacific/Auckland",
    "Asia/Tokyo",
    "Asia/Kolkata",
)


def daytime_zone() -> str:
    """A zone where it is office hours now, so CI runs are not held by quiet hours (EC-NOT-09)."""
    import zoneinfo

    from apps.core.time import now

    for name in DAYTIME_ZONES:
        if 9 <= now().astimezone(zoneinfo.ZoneInfo(name)).hour < 18:
            return name
    return "Africa/Harare"


def _candidate(i: int, password: str, zone: str) -> User:
    from apps.platform.demo_seed import _user

    return _user(
        f"candidate{i:03d}@core-scenario.test",
        password,
        f"Candidate{i:03d}",
        "Synthetic",
        timezone=zone,
    )


def seed(count: int, password: str, *, delay_minutes: int | None = None) -> ScenarioResult:
    from apps.applications import services as applications
    from apps.documents.models import Document, Purpose, ScanStatus

    result = ScenarioResult()
    job = Job.objects.unscoped().filter(title=JOB_TITLE, status="published").first()
    if job is None:
        raise RuntimeError("Run seed_demo first (published Software Developer vacancy).")
    result.job_id = str(job.pk)
    if delay_minutes is not None:  # CI: short undo window so the run can check Mailpit
        from apps.organisations.models import OrganisationPolicy

        OrganisationPolicy.objects.filter(organisation_id=job.organisation_id).update(
            notification_delay_minutes=delay_minutes
        )
    zone = daytime_zone()
    corpus = _cvs()
    for i in range(1, count + 1):
        user = _candidate(i, password, zone)
        try:
            app, _ = applications.start_or_resume_draft(
                job, user, source={"channel": "core_scenario"}
            )
        except applications.DuplicateApplicationError:
            result.skipped += 1  # already submitted by an earlier run
            continue
        if app.status != "draft":
            result.skipped += 1
            continue
        name, data = corpus[i % len(corpus)]
        key = f"cv/core-scenario/{user.pk}/{name}"
        doc = Document.objects.create(
            owner_user=user,
            purpose=Purpose.CV,
            original_filename=name,
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
    return result
