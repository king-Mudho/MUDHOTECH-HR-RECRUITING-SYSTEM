"""Candidate extraction features (P06-T13): preview, import to profile, corrections (EC-DOC-27)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.candidates.models import CandidateSkill, Education, Experience, Language, Source
from apps.core.models import OutboxEvent
from apps.documents.models import Document, ScanStatus
from apps.organisations.tests.factories import make_org_with_team
from apps.resumes import services
from apps.resumes.models import ClaimCorrection, ExtractedClaim, ResumeParse

from .test_extraction_flow import attach, submitted_app

pytestmark = pytest.mark.django_db


def client_for(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def preview_url(doc: Document) -> str:
    return f"/api/v1/candidate/resumes/{doc.pk}/extraction/"


@pytest.fixture
def cv(act: Any) -> tuple[Any, Document]:
    app = submitted_app()
    doc = attach(app)
    return app, doc


def test_preview_is_read_on_request_and_owner_only(act: Any, cv: Any) -> None:
    app, doc = cv
    c = client_for(app.candidate_user)
    first = act(c.get, preview_url(doc))
    assert first.status_code == 202 and first.json()["status"] == "pending"
    done = c.get(preview_url(doc))
    assert done.status_code == 200 and done.json()["status"] == "succeeded"
    claims = done.json()["claims"]
    types = {x["type"] for x in claims}
    assert {"experience", "education", "skill", "language"} <= types
    assert "contact" not in types  # contact details are not listed back
    job = next(x for x in claims if x["type"] == "experience")
    assert job["title"] and job["subtitle"] and job["snippet"] and "confidence" not in job
    assert ResumeParse.objects.get(document=doc).owner_user == app.candidate_user

    assert client_for(UserFactory()).get(preview_url(doc)).status_code == 404
    assert APIClient().get(preview_url(doc)).status_code in (401, 403)
    Document.objects.filter(pk=doc.pk).update(scan_status=ScanStatus.PENDING)
    assert c.get(preview_url(doc)).status_code == 409


def test_import_to_profile_needs_confirmation_and_skips_duplicates(act: Any, cv: Any) -> None:
    app, doc = cv
    c = client_for(app.candidate_user)
    act(c.get, preview_url(doc))
    claims = c.get(preview_url(doc)).json()["claims"]
    wanted = [
        x["index"] for x in claims if x["type"] in ("experience", "education", "skill", "language")
    ]
    url = f"/api/v1/candidate/resumes/{doc.pk}/import-to-profile/"
    refused = c.post(url, {"confirm": False, "indexes": wanted}, format="json")
    assert refused.status_code == 400 and not Experience.objects.exists()
    done = c.post(url, {"confirm": True, "indexes": wanted}, format="json")
    assert done.status_code == 200, done.json()
    body = done.json()
    assert body["experiences"] == 2 and body["educations"] >= 2 and body["skills"] >= 5
    assert Experience.objects.filter(source=Source.CV_IMPORT, employer="Granite Labs").exists()
    assert Education.objects.filter(qualification_text__icontains="Computer Science").exists()
    assert CandidateSkill.objects.filter(raw_name="Python").exists()
    assert Language.objects.filter(language="English").exists()
    again = c.post(url, {"confirm": True, "indexes": wanted}, format="json").json()
    assert again["experiences"] == 0 and again["skipped"] == len(wanted)
    assert AuditEvent.objects.filter(action="candidates.profile_imported_from_cv").count() == 2
    other = client_for(UserFactory())
    assert other.post(url, {"confirm": True, "indexes": wanted}, format="json").status_code == 404


def test_application_extraction_and_corrections(act: Any, cv: Any) -> None:
    app, _ = cv
    act(services.start, app.pk)
    c = client_for(app.candidate_user)
    url = f"/api/v1/candidate/applications/{app.pk}/extraction/"
    view = c.get(url)
    assert view.status_code == 200
    (run,) = view.json()["runs"]
    job = next(x for x in run["claims"] if x["type"] == "experience")
    assert job["correctable"] and job["corrections"] == []
    claim_url = f"/api/v1/candidate/claims/{job['id']}/corrections/"
    made = c.post(
        claim_url,
        {"values": {"title": "Senior Software Developer"}, "note": "I was promoted in 2024"},
        format="json",
    )
    assert made.status_code == 201, made.json()
    correction = ClaimCorrection.objects.get()
    assert correction.status == ClaimCorrection.Status.PENDING
    assert ExtractedClaim.objects.unscoped().get(pk=job["id"]).payload  # original kept
    (event,) = OutboxEvent.objects.filter(event_type="application.evidence_corrected")
    assert event.payload["claim_id"] == job["id"]
    assert AuditEvent.objects.filter(action="resumes.claim_corrected").exists()
    again = c.get(url).json()["runs"][0]["claims"]
    shown = next(x for x in again if x["id"] == job["id"])
    assert shown["corrections"][0]["values"] == {"title": "Senior Software Developer"}

    assert c.post(claim_url, {"values": {"salary": "1"}}, format="json").status_code == 400
    assert c.post(claim_url, {"values": {}}, format="json").status_code == 400
    assert c.post(claim_url, {"remove": True}, format="json").status_code == 201
    stranger = client_for(UserFactory())
    assert stranger.get(url).status_code == 404
    assert stranger.post(claim_url, {"remove": True}, format="json").status_code == 404
    team = make_org_with_team()
    assert client_for(team.hr_manager).get(url).status_code == 404  # candidate endpoint only


def test_protected_and_contact_claims_cannot_be_corrected(act: Any) -> None:
    app = submitted_app()
    data = b"%PDF"  # replaced below with a CV that has personal details
    from pathlib import Path

    corpus = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_cvs"
    import json

    labels = json.loads((corpus / "labels.json").read_text(encoding="utf-8"))["cvs"]
    with_pii = next(
        x
        for x in labels
        if x["protected_data_present"] and x["parse_expected"] == "ok" and not x["needs_ocr"]
    )
    data = (corpus / with_pii["file"]).read_bytes()
    attach(app, data, filename=with_pii["file"])
    act(services.start, app.pk)
    c = client_for(app.candidate_user)
    claims = c.get(f"/api/v1/candidate/applications/{app.pk}/extraction/").json()["runs"][0][
        "claims"
    ]
    protected = [x for x in claims if x["type"] == "protected"]
    assert protected and all(x["excluded"] and not x["correctable"] for x in protected)
    assert all(x["snippet"] == "" for x in protected)  # never echo the value back
    resp = c.post(
        f"/api/v1/candidate/claims/{protected[0]['id']}/corrections/",
        {"remove": True},
        format="json",
    )
    assert resp.status_code == 400
