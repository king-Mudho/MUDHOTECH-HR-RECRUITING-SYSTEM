"""Phase 13 exit: consent boundaries, export safety and analytics reconciliation, end to end
through the HTTP API (P13-T08)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.analytics import exports
from apps.applications.models import ApplicationDocument, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.candidates.models import CandidateProfile, CandidateSkill
from apps.core import storage
from apps.documents.models import Document, ScanStatus
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy.erasure import erase

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def test_applying_to_one_employer_never_exposes_the_cv_to_another(s3: Any) -> None:
    a, b = make_org_with_team(), make_org_with_team()
    user = UserFactory(first_name="Chipo", last_name="Synthetic", email="chipo@example.test")
    profile = CandidateProfile.objects.create(user=user, headline="Python developer")
    CandidateSkill.objects.create(profile=profile, raw_name="Python")
    job_a = published_job(organisation=a.org)
    app = make_application(job_a, user, status=Status.UNDER_REVIEW)
    cv = Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename="chipo-cv.pdf",
        size_bytes=10,
        storage_key=f"cv/{uuid.uuid4().hex}.pdf",
        scan_status=ScanStatus.CLEAN,
    )
    ApplicationDocument.objects.create(
        organisation=a.org, application=app, document=cv, role="cv", required_doc_key="cv"
    )
    me = APIClient()
    me.force_login(user)
    # the candidate can only join employers they applied to
    assert (
        me.post(
            "/api/v1/candidate/talent-pools/", {"organisation_id": str(b.org.pk)}, format="json"
        ).status_code
        == 404
    )
    assert (
        me.post(
            "/api/v1/candidate/talent-pools/", {"organisation_id": str(a.org.pk)}, format="json"
        ).status_code
        == 200
    )
    hr_a, hr_b = staff(a.hr_manager, a.org), staff(b.hr_manager, b.org)
    found = hr_a.get("/api/v1/hr/talent-pool/", {"q": "python"}).json()["results"]
    assert [r["name"] for r in found] == ["Chipo Synthetic"]
    flat = str(found)
    assert str(cv.pk) not in flat and "chipo-cv" not in flat and "chipo@example.test" not in flat
    assert hr_b.get("/api/v1/hr/talent-pool/", {"q": "python"}).json()["results"] == []
    assert hr_b.get("/api/v1/hr/talent-pool/", {"q": "Chipo"}).json()["count"] == 0
    entry_id = found[0]["id"]
    assert hr_b.get(f"/api/v1/hr/talent-pool/{entry_id}/").status_code == 404
    assert hr_b.get(f"/api/v1/documents/{cv.pk}/download/").status_code in (403, 404)
    # withdrawal and erasure end the pool membership at once
    me.post(f"/api/v1/candidate/talent-pools/{a.org.pk}/leave/", {}, format="json")
    assert hr_a.get("/api/v1/hr/talent-pool/").json()["count"] == 0
    me.post("/api/v1/candidate/talent-pools/", {"organisation_id": str(a.org.pk)}, format="json")
    erase(user, a.org.pk)
    assert hr_a.get("/api/v1/hr/talent-pool/").json()["count"] == 0


def test_report_export_has_no_personal_data_and_funnel_matches_dashboard(s3: Any) -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    apps = [
        make_application(job, UserFactory(email=f"p{i}@example.test"), status=Status.UNDER_REVIEW)
        for i in range(4)
    ]
    transition(apps[0], Status.SHORTLISTED, actor=team.hr_manager, reason="Strong evidence")
    transition(apps[1], Status.NOT_SELECTED, actor=team.hr_manager, reason="Missing licence")
    hr = staff(team.hr_manager, team.org)
    report = hr.get("/api/v1/hr/reports/recruitment/", {"job": str(job.pk)}).json()
    dashboard = hr.get(f"/api/v1/hr/jobs/{job.pk}/funnel/").json()
    reported = {s["stage"]: s["count"] for s in report["funnel"]["stages"]}
    dash = {s["stage"]: s["count"] for s in dashboard["stages"]}
    for stage in ("submitted", "shortlisted", "interviewed", "offered", "hired"):
        assert reported[stage] == dash[stage], stage
    body = hr.post("/api/v1/hr/exports/", {"kind": "report", "format": "csv"}, format="json")
    job_row = exports.build(body.json()["id"])
    assert job_row is not None
    text = storage.get_bytes("exports", job_row.storage_key).decode("utf-8-sig")
    assert "@example.test" not in text and "Strong evidence" not in text
