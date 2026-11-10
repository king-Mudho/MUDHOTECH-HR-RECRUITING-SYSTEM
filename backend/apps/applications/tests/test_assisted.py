"""Assisted applications (P04-T11, EC-APP-17/18)."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.audit.models import AuditEvent
from apps.core import crypto
from apps.core.email import EVENT as EMAIL_EVENT
from apps.core.models import OutboxEvent
from apps.documents.models import Document
from apps.documents.tests.test_scan_pipeline import make_pdf
from apps.jobs.models import JobAssignment
from apps.jobs.tests.test_services import published_job
from apps.organisations.models import Membership
from apps.privacy.models import ConsentRecord

pytestmark = pytest.mark.django_db


def body(**over: Any) -> dict[str, Any]:
    return {
        "email": "Rudo.Moyo@Example.TEST",
        "first_name": "Rudo",
        "last_name": "Moyo",
        "phone": "0772123456",
        "consent_confirmed": True,
        "consent_method": "in_person",
        "note": "Applied at the Kadoma community office",
        **over,
    }


def staff_client(team: Any, role: str = "recruiter") -> APIClient:
    c = APIClient()
    c.force_login(getattr(team, role))
    c.credentials(HTTP_X_ORG_ID=str(team.org.pk))
    return c


def post(client: APIClient, job: Any, data: dict[str, Any], fmt: str = "multipart") -> Any:
    return client.post(f"/api/v1/hr/jobs/{job.pk}/assisted-applications/", data, format=fmt)


def test_recruiter_submits_on_behalf_with_cv(team: Any, s3: Any) -> None:
    job = published_job(team)  # requires a CV
    cv = SimpleUploadedFile("Rudo CV.pdf", make_pdf(1), content_type="application/pdf")
    res = post(
        staff_client(team),
        job,
        {**body(), "cv": cv, "answers": '[{"key": "portfolio", "value": "yes"}]'},
    )
    assert res.status_code == 201, res.content
    app = Application.objects.unscoped().get(pk=res.json()["id"])
    candidate = User.objects.get(email="rudo.moyo@example.test")
    assert app.candidate_user == candidate and not candidate.has_usable_password()
    assert app.status == Status.SUBMITTED and app.is_assisted and app.assisted_by == team.recruiter
    assert app.channel == "assisted" and app.reference
    doc = Document.objects.get(owner_user=candidate)
    assert doc.organisation_id == team.org.pk
    event = ApplicationStatusEvent.objects.for_org(team.org).get(application=app)
    assert event.actor == team.recruiter and event.metadata["actor_kind"] == "staff"
    consent = ConsentRecord.objects.get(pk=app.consent_record_id)
    assert consent.context["assisted"]["method"] == "in_person"
    assert AuditEvent.objects.filter(
        action="application.assisted_created", target_id=str(app.pk)
    ).exists()
    invite = [
        e
        for e in OutboxEvent.objects.filter(event_type=EMAIL_EVENT)
        if e.payload["to"] == [candidate.email]
    ]
    texts = [crypto.decrypt(e.payload["text_enc"]) for e in invite]
    assert any("Set your password" in t and "/reset-password?key=" in t for t in texts)


def test_existing_account_is_reused_without_reset_link(team: Any) -> None:
    job = published_job(team)
    existing = UserFactory(email="known@example.test")
    from apps.jobs.models import JobVersion

    JobVersion.objects.for_org(team.org).filter(pk=job.published_version_id).update(
        required_documents=[]
    )
    res = post(
        staff_client(team),
        job,
        body(email="known@example.test", answers=[{"key": "portfolio", "value": "no"}]),
        fmt="json",
    )
    assert res.status_code == 201, res.content
    texts = [
        crypto.decrypt(e.payload["text_enc"])
        for e in OutboxEvent.objects.filter(event_type=EMAIL_EVENT)
        if e.payload["to"] == [existing.email]
    ]
    assert texts and all("reset-password" not in t for t in texts)


def test_consent_and_email_required(team: Any) -> None:
    job = published_job(team)
    c = staff_client(team)
    assert post(c, job, body(consent_confirmed=False), fmt="json").status_code == 400
    assert post(c, job, body(consent_method="sms"), fmt="json").status_code == 400
    assert post(c, job, body(email=""), fmt="json").status_code == 400  # EC-APP-18


def test_incomplete_assisted_application_is_not_submitted(team: Any) -> None:
    job = published_job(team)  # requires a CV, none given
    res = post(staff_client(team), job, body(), fmt="json")
    assert res.status_code == 422 and res.json()["error"]["code"] == "submit_blocked"
    assert not Application.objects.unscoped().filter(status=Status.SUBMITTED).exists()


def test_unassigned_recruiter_cannot_create(team: Any) -> None:
    job = published_job(team)
    JobAssignment.objects.for_org(team.org).filter(
        job=job, membership=Membership.objects.for_org(team.org).get(user=team.recruiter)
    ).delete()
    res = post(staff_client(team), job, body(), fmt="json")
    assert res.status_code in (403, 404)


def test_hiring_manager_cannot_create(team: Any) -> None:
    job = published_job(team)
    JobAssignment.objects.create(
        organisation=team.org,
        job=job,
        membership=Membership.objects.for_org(team.org).get(user=team.hiring_manager),
        role_on_job="hiring_manager",
    )
    res = post(staff_client(team, "hiring_manager"), job, body(), fmt="json")
    assert res.status_code == 403


def test_duplicate_application_for_same_candidate(team: Any) -> None:
    job = published_job(team)
    from apps.jobs.models import JobVersion

    JobVersion.objects.for_org(team.org).filter(pk=job.published_version_id).update(
        required_documents=[]
    )
    data = body(answers=[{"key": "portfolio", "value": "yes"}])
    c = staff_client(team)
    assert post(c, job, data, fmt="json").status_code == 201
    second = post(c, job, data, fmt="json")
    assert (
        second.status_code == 409
        and second.json()["error"]["code"] == "conflict.duplicate_application"
    )
