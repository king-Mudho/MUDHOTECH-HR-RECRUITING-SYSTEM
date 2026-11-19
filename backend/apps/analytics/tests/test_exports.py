"""P13-T06: exports - permissioned, formula-injection safe (EC-PRV-08), blind option, 15-minute
links, 24-hour files, audited; never across organisations."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.analytics import exports
from apps.analytics.models import ExportJob
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import storage
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def world(s3: Any) -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    evil = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    Application.objects.unscoped().filter(pk=evil.pk).update(
        candidate_profile_snapshot={
            "first_name": '=HYPERLINK("http://evil.test","click")',
            "last_name": "+cmd",
            "email": "@sum(1+1)@example.test",
            "phone": "-2+3",
        },
        ai_band="recommended_for_review",
    )
    plain = make_application(job, UserFactory(), status=Status.SHORTLISTED)
    Application.objects.unscoped().filter(pk=plain.pk).update(
        candidate_profile_snapshot={"first_name": "Rudo", "last_name": "Moyo", "email": "r@x.test"}
    )
    return {"team": team, "job": job}


def request(world: dict[str, Any], **body: Any) -> dict[str, Any]:
    hr = staff(world["team"].hr_manager, world["team"].org)
    resp = hr.post("/api/v1/hr/exports/", body, format="json")
    assert resp.status_code == 202, resp.content
    return resp.json()


def built(export_id: str) -> ExportJob:
    job = exports.build(export_id)
    assert job is not None and job.status == ExportJob.Status.READY
    return job


def test_csv_neutralises_formulas_ec_prv_08(world: dict[str, Any]) -> None:
    body = request(world, kind="applicants", format="csv", job=str(world["job"].pk))
    assert OutboxEvent.objects.filter(event_type="export.requested").exists()
    job = built(body["id"])
    text = storage.get_bytes("exports", job.storage_key).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:4] == ["Reference", "Name", "Email", "Phone"]
    evil = next(r for r in rows[1:] if "HYPERLINK" in r[1])
    assert evil[1].startswith("'=") and evil[2].startswith("'@") and evil[3].startswith("'-")
    for r in rows:
        for value in r:
            assert not value.startswith(exports.csv_safe.DANGEROUS)
    assert "AI-assisted suggestion" in rows[0][6]
    assert job.row_count == 2


def test_blind_export_has_no_names_or_contacts(world: dict[str, Any]) -> None:
    body = request(world, kind="applicants", format="csv", job=str(world["job"].pk), blind=True)
    job = built(body["id"])
    text = storage.get_bytes("exports", job.storage_key).decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Reference,Vacancy,Status")
    assert "Rudo" not in text and "r@x.test" not in text and "HYPERLINK" not in text


def test_xlsx_and_pdf(world: dict[str, Any]) -> None:
    from openpyxl import load_workbook

    job = built(request(world, kind="applicants", format="xlsx", job=str(world["job"].pk))["id"])
    wb = load_workbook(io.BytesIO(storage.get_bytes("exports", job.storage_key)))
    values = [c.value for row in wb.active.iter_rows() for c in row if isinstance(c.value, str)]
    assert any(v.startswith("'=HYPERLINK") for v in values)
    assert not any(v.startswith("=") for v in values)  # no live formulas
    pdf = built(request(world, kind="report", format="pdf")["id"])
    assert storage.get_bytes("exports", pdf.storage_key).startswith(b"%PDF")
    report_csv = built(request(world, kind="report", format="csv")["id"])
    text = storage.get_bytes("exports", report_csv.storage_key).decode("utf-8-sig")
    assert "funnel" in text and "Section,Metric,Value" in text


def test_download_link_is_short_lived_audited_and_expires(world: dict[str, Any]) -> None:
    team = world["team"]
    hr = staff(team.hr_manager, team.org)
    body = request(world, kind="report", format="csv")
    early = hr.post(f"/api/v1/hr/exports/{body['id']}/download/")
    assert early.status_code == 409  # not built yet
    built(body["id"])
    link = hr.post(f"/api/v1/hr/exports/{body['id']}/download/")
    assert link.status_code == 200 and link.json()["expires_in"] == 900
    assert "X-Amz-Expires=900" in link.json()["url"]
    assert AuditEvent.objects.filter(action="exports.downloaded").count() == 1
    assert AuditEvent.objects.filter(action="exports.requested").exists()
    ExportJob.objects.unscoped().filter(pk=body["id"]).update(expires_at=now() - timedelta(1))
    assert exports.expire_old() == 1
    assert hr.post(f"/api/v1/hr/exports/{body['id']}/download/").status_code == 409
    listing = hr.get("/api/v1/hr/exports/").json()
    assert listing[0]["status"] == "expired"


def test_permissions_and_isolation(world: dict[str, Any]) -> None:
    team = world["team"]
    recruiter = staff(team.recruiter, team.org)
    assert (
        recruiter.post(
            "/api/v1/hr/exports/", {"kind": "report", "format": "csv"}, format="json"
        ).status_code
        == 403
    )
    hr = staff(team.hr_manager, team.org)
    missing = hr.post("/api/v1/hr/exports/", {"kind": "applicants", "format": "csv"}, format="json")
    assert missing.status_code == 400
    body = request(world, kind="report", format="csv")
    other = make_org_with_team()
    foreign = staff(other.hr_manager, other.org)
    assert foreign.get(f"/api/v1/hr/exports/{body['id']}/").status_code == 404
    assert foreign.post(f"/api/v1/hr/exports/{body['id']}/download/").status_code == 404
    stolen = foreign.post(
        "/api/v1/hr/exports/",
        {"kind": "applicants", "format": "csv", "job": str(world["job"].pk)},
        format="json",
    )
    assert stolen.status_code == 404
    assert exports.build(body["id"]) is not None
    assert exports.build(body["id"]) is None  # idempotent: built once
