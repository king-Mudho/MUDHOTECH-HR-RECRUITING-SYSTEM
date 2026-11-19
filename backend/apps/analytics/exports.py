"""Exports (P13-T06, docs/04 POST /hr/exports, EC-PRV-08).

* Requested by an HR manager/admin; the request only records the job and emits
  ``export.requested`` through the outbox; the file is built on the ``reports`` queue.
* ``applicants`` - one vacancy's applications the requester can see (conflicts of interest
  excluded). ``blind=True`` leaves out names and contact details (reference only). AI bands are
  labelled as suggestions. ``report`` - the recruitment report for the chosen filters.
* Every text cell goes through ``csv_safe.cell`` (formula injection, also in XLSX). PDF values are
  HTML-escaped.
* Files live 24 hours in the private exports bucket; downloads use 15-minute presigned links and
  every link handed out is audited.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from html import escape
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import csv_safe, outbox, storage
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now
from apps.organisations.models import Membership

from .models import ExportJob

LINK_TTL = 15 * 60
KEEP_FOR = timedelta(hours=24)
MAX_ROWS = 10_000
CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
AI_LABEL = "AI band (AI-assisted suggestion - requires human review)"


# --- request ----------------------------------------------------------------------------------
def request_export(
    membership: Membership, *, kind: str, fmt: str, params: dict[str, Any], blind: bool = False
) -> ExportJob:
    from apps.jobs.assignments import jobs_visible_to

    clean = {k: str(v) for k, v in params.items() if v and k in ("from", "to", "department", "job")}
    if kind == ExportJob.Kind.APPLICANTS:
        if not clean.get("job"):
            raise DomainError(
                "validation_error", "Choose a vacancy.", details={"job": ["Required."]}
            )
        if not jobs_visible_to(membership).filter(pk=clean["job"]).exists():
            raise NotFoundError()
    elif clean.get("job") and not jobs_visible_to(membership).filter(pk=clean["job"]).exists():
        raise NotFoundError()
    with transaction.atomic():
        job = ExportJob.objects.create(
            organisation_id=membership.organisation_id,
            kind=kind,
            format=fmt,
            params=clean,
            blind=blind,
            requested_by=membership.user,
        )
        audit.record(
            actor=membership.user,
            action="exports.requested",
            target=job,
            organisation=membership.organisation_id,
            after={"kind": kind, "format": fmt, "blind": blind, "params": clean},
        )
        outbox.emit(
            "export.requested",
            job,
            {"export_id": str(job.pk)},
            dedupe_key=f"export.requested:{job.pk}",
            organisation_id=membership.organisation_id,
        )
    return job


# --- build ------------------------------------------------------------------------------------
def _applicant_rows(job: ExportJob) -> tuple[list[str], list[list[Any]]]:
    from apps.applications.hr import applications_visible_to

    membership = (
        Membership.objects.for_org(job.organisation_id)
        .filter(user_id=job.requested_by_id, status=Membership.Status.ACTIVE)
        .first()
    )
    if membership is None:  # the requester left: nothing is exported
        raise NotFoundError()
    apps = (
        applications_visible_to(membership)
        .filter(job_id=job.params["job"], submitted_at__isnull=False)
        .select_related("job")
        .order_by("submitted_at")[: MAX_ROWS + 1]
    )
    header = ["Reference", "Vacancy", "Status", AI_LABEL, "Submitted", "Source"]
    if not job.blind:
        header[1:1] = ["Name", "Email", "Phone"]
    rows: list[list[Any]] = []
    for app in apps:
        snap = app.candidate_profile_snapshot or {}
        row: list[Any] = [
            app.reference,
            app.job.title,
            app.get_status_display(),
            app.ai_band.replace("_", " "),
            app.submitted_at.isoformat() if app.submitted_at else "",
            (app.source or {}).get("source", "direct"),
        ]
        if not job.blind:
            name = " ".join(x for x in (snap.get("first_name"), snap.get("last_name")) if x)
            row[1:1] = [name, snap.get("email", ""), snap.get("phone", "")]
        rows.append(row)
    if len(rows) > MAX_ROWS:
        raise DomainError("export_too_large", f"More than {MAX_ROWS} rows - narrow the filters.")
    return header, rows


def _report_rows(job: ExportJob) -> tuple[list[str], list[list[Any]]]:
    from . import selectors

    data = selectors.report(selectors.scope_from(job.organisation_id, job.params))
    rows: list[list[Any]] = []

    def walk(section: str, value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(section, v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                label = (
                    item.get("stage") or item.get("source") or item.get("band") or item.get("step")
                    if isinstance(item, dict)
                    else None
                ) or str(i + 1)
                walk(section, item, f"{path}[{label}]")
        else:
            rows.append([section, path, "" if value is None else value])

    for section in (
        "timing",
        "funnel",
        "sources",
        "questionnaire",
        "processing",
        "ai_agreement",
        "clarifications",
    ):
        walk(section, data[section])
    scope = data["scope"]
    rows.insert(0, ["scope", "period", f"{scope['from']} to {scope['to']}"])
    rows.insert(1, ["scope", "applications", data["applications"]])
    return ["Section", "Metric", "Value"], rows


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(csv_safe.row(list(header)))
    for r in rows:
        writer.writerow(csv_safe.row(r))
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM: Excel opens UTF-8 correctly


def _xlsx(header: list[str], rows: list[list[Any]], title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(csv_safe.row(list(header)))
    for r in rows:
        # numbers stay numbers; every text value is neutralised (formula injection)
        ws.append([v if isinstance(v, (int, float)) else csv_safe.cell(v) for v in r])
    bold = Font(bold=True)
    for c in ws[1]:
        c.font = bold
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _pdf(header: list[str], rows: list[list[Any]], title: str) -> bytes:
    import pymupdf

    head = "".join(f"<th>{escape(str(h))}</th>" for h in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in r) + "</tr>" for r in rows
    )
    html = (
        f"<h1>{escape(title)}</h1>"
        f"<p class='muted'>Generated {escape(now().strftime('%d %B %Y %H:%M UTC'))}. "
        "Confidential.</p>"
        f"<table><tr>{head}</tr>{body}</table>"
    )
    css = (
        "body{font-family:sans-serif;font-size:8pt}h1{font-size:13pt}"
        ".muted{color:#555}table{border-collapse:collapse;width:100%}"
        "th,td{border:0.5pt solid #bbb;padding:2pt;text-align:left;vertical-align:top}"
        "th{font-weight:bold}"
    )
    story = pymupdf.Story(html=html, user_css=css)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page = pymupdf.paper_rect("a4-l")
    area = pymupdf.Rect(page.x0 + 36, page.y0 + 36, page.x1 - 36, page.y1 - 36)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()


def build(export_id: Any) -> ExportJob | None:
    """Idempotent: a job that is no longer queued is left alone."""
    job = ExportJob.objects.unscoped().filter(pk=export_id).first()  # system task
    if job is None or job.status != ExportJob.Status.QUEUED:
        return None
    title = "Applicants" if job.kind == ExportJob.Kind.APPLICANTS else "Recruitment report"
    try:
        header, rows = (
            _applicant_rows(job) if job.kind == ExportJob.Kind.APPLICANTS else _report_rows(job)
        )
        if job.format == ExportJob.Format.CSV:
            data = _csv(header, rows)
        elif job.format == ExportJob.Format.XLSX:
            data = _xlsx(header, rows, title)
        else:
            data = _pdf(header, rows, title)
    except (DomainError, NotFoundError) as exc:
        ExportJob.objects.unscoped().filter(pk=job.pk).update(
            status=ExportJob.Status.FAILED, error=str(exc)[:200], finished_at=now()
        )
        return None
    stamp = now()
    key = f"exports/{job.organisation_id}/{job.pk}.{job.format}"
    storage.put_bytes("exports", key, data, CONTENT_TYPES[job.format])
    filename = f"{job.kind}-{stamp:%Y%m%d-%H%M}.{job.format}"
    ExportJob.objects.unscoped().filter(pk=job.pk).update(
        status=ExportJob.Status.READY,
        storage_key=key,
        filename=filename,
        row_count=len(rows),
        finished_at=stamp,
        expires_at=stamp + KEEP_FOR,
    )
    job.refresh_from_db()
    return job


# --- download ----------------------------------------------------------------------------------
def visible(membership: Membership) -> Any:
    return ExportJob.objects.for_org(membership.organisation_id)


def download_url(membership: Membership, export_id: Any) -> tuple[ExportJob, str]:
    job = visible(membership).filter(pk=export_id).first()
    if job is None:
        raise NotFoundError()
    if job.status != ExportJob.Status.READY or (job.expires_at and job.expires_at <= now()):
        raise DomainError("export_not_ready", "This export is not available.", 409)
    url = storage.presign_get("exports", job.storage_key, ttl=LINK_TTL, filename=job.filename)
    audit.record(
        actor=membership.user,
        action="exports.downloaded",
        target=job,
        organisation=membership.organisation_id,
        after={"rows": job.row_count, "blind": job.blind},
    )
    return job, url


def expire_old() -> int:
    """Daily: delete files past their 24 hours."""
    due = ExportJob.objects.unscoped().filter(status=ExportJob.Status.READY, expires_at__lte=now())
    count = 0
    for job in due:
        if job.storage_key:
            storage.delete_object("exports", job.storage_key)
        ExportJob.objects.unscoped().filter(pk=job.pk).update(
            status=ExportJob.Status.EXPIRED, storage_key=""
        )
        count += 1
    return count
