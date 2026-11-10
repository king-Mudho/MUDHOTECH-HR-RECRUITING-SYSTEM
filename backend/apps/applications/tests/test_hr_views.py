"""Minimal HR application list/detail and staff document access (P04-T15)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import ApplicationDocument, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AccessLog
from apps.documents import services as documents
from apps.documents.models import Document, ScanStatus
from apps.jobs.models import JobAssignment
from apps.organisations.models import Membership
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def submitted(job: Any, first: str = "Rudo", last: str = "Moyo", **kw: Any) -> Any:
    user = UserFactory(first_name=first, last_name=last)
    app = make_application(job, user, status=kw.pop("status", Status.SUBMITTED))
    app.candidate_profile_snapshot = {
        "first_name": first,
        "last_name": last,
        "email": user.email,
        "headline": "Developer",
    }
    app.save(update_fields=["candidate_profile_snapshot"])
    return app


@pytest.fixture
def team() -> Any:
    return make_org_with_team()


@pytest.fixture
def job(team: Any) -> Any:
    return published_job(organisation=team.org)


def test_list_shows_submitted_only_with_filters(team: Any, job: Any) -> None:
    a = submitted(job, "Rudo", "Moyo")
    b = submitted(job, "Tendai", "Chari")
    make_application(job, UserFactory())  # a draft stays private to the candidate
    transition(b, Status.WITHDRAWN, actor=b.candidate_user, reason="Other job")
    c = staff(team.hr_manager, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/"
    rows = c.get(url).json()["results"]
    assert {r["id"] for r in rows} == {str(a.pk), str(b.pk)}
    assert {r["candidate_name"] for r in rows} == {"Rudo Moyo", "Tendai Chari"}
    only = c.get(url, {"status": "withdrawn"}).json()["results"]
    assert [r["id"] for r in only] == [str(b.pk)]
    found = c.get(url, {"search": "rudo"}).json()["results"]
    assert [r["id"] for r in found] == [str(a.pk)]
    assert c.get(url, {"search": a.reference}).json()["results"][0]["id"] == str(a.pk)


def test_assignment_and_role_rules(team: Any, job: Any) -> None:
    submitted(job)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/"
    assert staff(team.hiring_manager, team.org).get(url).status_code == 404  # not assigned
    hm = Membership.objects.for_org(team.org).get(user=team.hiring_manager)
    JobAssignment.objects.create(
        organisation=team.org, job=job, membership=hm, role_on_job="hiring_manager"
    )
    assert staff(team.hiring_manager, team.org).get(url).status_code == 200
    assert staff(team.panelist, team.org).get(url).status_code == 403
    assert staff(team.auditor, team.org).get(url).status_code == 403


def test_detail_has_documents_answers_timeline_and_logs_access(team: Any, job: Any) -> None:
    app = submitted(job)
    doc = Document.objects.create(
        owner_user=app.candidate_user,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key="k",
        scan_status=ScanStatus.CLEAN,
    )
    ApplicationDocument.objects.create(
        organisation=team.org, application=app, document=doc, role="cv", required_doc_key="cv"
    )
    transition(app, Status.PROCESSING, actor_type="system")
    c = staff(team.recruiter, team.org)
    JobAssignment.objects.get_or_create(
        organisation=team.org,
        job=job,
        membership=Membership.objects.for_org(team.org).get(user=team.recruiter),
        defaults={"role_on_job": "recruiter"},
    )
    body = c.get(f"/api/v1/hr/applications/{app.pk}/").json()
    assert body["reference"] == app.reference
    assert body["candidate"]["headline"] == "Developer"
    assert body["documents"][0]["filename"] == "cv.pdf" and body["documents"][0]["available"]
    assert [e["to_status"] for e in body["timeline"]][-1] == "processing"
    assert AccessLog.objects.filter(target_id=str(app.pk), user=team.recruiter).exists()


def test_detail_hides_drafts_and_foreign_orgs(team: Any, job: Any) -> None:
    draft = make_application(job, UserFactory())
    c = staff(team.hr_manager, team.org)
    assert c.get(f"/api/v1/hr/applications/{draft.pk}/").status_code == 404
    other = make_org_with_team()
    foreign = submitted(published_job(organisation=other.org))
    assert c.get(f"/api/v1/hr/applications/{foreign.pk}/").status_code == 404
    assert c.get(f"/api/v1/hr/jobs/{foreign.job_id}/applications/").status_code == 404


def test_staff_document_access_follows_application_visibility(team: Any, job: Any) -> None:
    app = submitted(job)
    doc = Document.objects.create(
        owner_user=app.candidate_user,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key="k",
        scan_status=ScanStatus.CLEAN,
    )
    ApplicationDocument.objects.create(
        organisation=team.org, application=app, document=doc, role="cv"
    )
    assert documents.can_access(team.hr_manager, doc)
    assert not documents.can_access(team.hiring_manager, doc)  # unassigned
    assert not documents.can_access(team.panelist, doc)
    assert not documents.can_access(make_org_with_team().hr_manager, doc)
    assert not documents.can_access(UserFactory(), doc)
    draft_doc = Document.objects.create(
        owner_user=app.candidate_user,
        purpose="cv",
        original_filename="draft.pdf",
        size_bytes=1,
        storage_key="k2",
    )
    draft = make_application(published_job(organisation=team.org), app.candidate_user)
    ApplicationDocument.objects.create(
        organisation=team.org, application=draft, document=draft_doc, role="cv"
    )
    assert not documents.can_access(team.hr_manager, draft_doc)  # drafts stay private
