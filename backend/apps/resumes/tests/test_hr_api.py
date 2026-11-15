"""HR extraction panel and retry (P06-T14)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application, Status
from apps.organisations.tests.factories import make_org_with_team
from apps.resumes import services
from apps.resumes.models import ClaimCorrection, ExtractionRun

from .test_extraction_flow import attach, submitted_app

pytestmark = pytest.mark.django_db
CORPUS = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_cvs"


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def pii_cv() -> tuple[str, bytes]:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    cv = next(
        x
        for x in labels
        if x["protected_data_present"] and x["parse_expected"] == "ok" and not x["needs_ocr"]
    )
    return cv["file"], (CORPUS / cv["file"]).read_bytes()


def test_panel_shows_evidence_hides_personal_details_and_shows_corrections(act: Any) -> None:
    team = make_org_with_team()
    app = submitted_app(org=team.org)
    name, data = pii_cv()
    attach(app, data, filename=name)
    act(services.start, app.pk)
    Application.objects.unscoped().filter(pk=app.pk).update(flags=["identity_mismatch_possible"])
    c = staff(team.hr_manager, team.org)
    url = f"/api/v1/hr/applications/{app.pk}/extraction/"
    body = c.get(url).json()
    assert body["flags"] == ["identity_mismatch_possible"] and body["can_retry"] is False
    (run,) = body["runs"]
    assert run["status"] == "succeeded" and run["set_aside"] >= 6  # 6 protected + contact
    types = {x["type"] for x in run["claims"]}
    assert "protected" not in types and "contact" not in types
    assert {"experience", "education", "skill"} <= types
    dumped = json.dumps(body)
    for word in ("date of birth", "religion", "gender", "national ID"):
        assert word not in dumped  # not even which kinds were present
    job = next(x for x in run["claims"] if x["type"] == "experience")
    assert job["snippet"] and job["page"] == 1 and job["confidence"] in ("high", "medium", "low")
    ClaimCorrection.objects.create(
        organisation_id=app.organisation_id,
        claim_id=job["id"],
        corrected_by=app.candidate_user,
        payload=json.dumps({"type": "experience", "fields": {"title": "Lead"}, "remove": False}),
        note="Promoted",
    )
    again = c.get(url).json()["runs"][0]["claims"]
    shown = next(x for x in again if x["id"] == job["id"])
    assert shown["corrections"][0]["values"] == {"title": "Lead"}
    assert shown["corrections"][0]["note"] == "Promoted"


def test_retry_after_failure_and_conflict_when_nothing_failed(act: Any) -> None:
    team = make_org_with_team()
    app = submitted_app(org=team.org)
    attach(app, b"%PDF-1.4 broken file", filename="broken.pdf")
    act(services.start, app.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR
    c = staff(team.hr_manager, team.org)
    panel = c.get(f"/api/v1/hr/applications/{app.pk}/extraction/").json()
    assert panel["can_retry"] and panel["runs"][0]["error_code"] == "corrupt"
    retried = act(c.post, f"/api/v1/hr/applications/{app.pk}/retry-processing/")
    assert retried.status_code == 200
    run = ExtractionRun.objects.for_org(app.organisation_id).get()
    assert run.attempts == 2  # a new attempt ran; the file is still unreadable
    app.refresh_from_db()
    assert app.status == Status.PROCESSING_ERROR

    good = submitted_app(org=team.org)
    attach(good)
    act(services.start, good.pk)
    Application.objects.unscoped().filter(pk=good.pk).update(status=Status.UNDER_REVIEW)
    conflict = c.post(f"/api/v1/hr/applications/{good.pk}/retry-processing/")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict.nothing_to_retry"
