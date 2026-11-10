"""Consent and notice records on submit (P04-T10)."""

from __future__ import annotations

from typing import Any

import pytest

from apps.applications.tests.factories import published_job
from apps.applications.tests.test_submit import login, ready_draft, submit
from apps.organisations.models import OrganisationPolicy
from apps.privacy import services
from apps.privacy.models import ConsentRecord

pytestmark = pytest.mark.django_db


@pytest.fixture
def job() -> Any:
    job = published_job()
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(
        privacy_notice="We use your application only to assess you for this vacancy."
    )
    return job


def test_submit_records_processing_consent_and_ai_notice(job: Any) -> None:
    app = ready_draft(job)
    client = login(app.candidate_user)
    res = client.post(
        f"/api/v1/applications/{app.pk}/submit/",
        {"accept_privacy": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY="4b9d5c7e-1111-4222-8333-944455556666",
        REMOTE_ADDR="196.43.10.77",
    )
    assert res.status_code == 201, res.content
    app.refresh_from_db()
    records = {r.purpose: r for r in ConsentRecord.objects.filter(user=app.candidate_user)}
    processing = records["application_processing"]
    assert processing.granted and app.consent_record_id == processing.pk
    assert processing.notice_version == services.privacy_notice_version(job.organisation_id)[0]
    assert processing.ip_trunc == "196.43.10.0/24"  # never the full address
    assert processing.context["application_id"] == str(app.pk)
    ai = records["ai_assisted_screening"]
    assert ai.granted and ai.notice_version == services.ai_notice_version()
    assert app.objects_to_automated_processing is False


def test_objection_to_automated_processing_is_recorded(job: Any) -> None:
    app = ready_draft(job)
    assert (
        submit(login(app.candidate_user), app, objects_to_automated_processing=True).status_code
        == 201
    )
    app.refresh_from_db()
    assert app.objects_to_automated_processing is True
    ai = ConsentRecord.objects.get(user=app.candidate_user, purpose="ai_assisted_screening")
    assert ai.granted is False


def test_notice_version_changes_with_text(job: Any) -> None:
    before = services.privacy_notice_version(job.organisation_id)[0]
    OrganisationPolicy.objects.filter(organisation=job.organisation).update(
        privacy_notice="New wording."
    )
    assert services.privacy_notice_version(job.organisation_id)[0] != before


def test_application_exposes_notices_to_the_wizard(job: Any) -> None:
    app = ready_draft(job)
    body = login(app.candidate_user).get(f"/api/v1/applications/{app.pk}/").json()
    assert body["notices"]["privacy_notice"].startswith("We use your application")
    assert body["notices"]["ai_notice_url"] == "/how-we-use-ai"
    assert body["notices"]["ai_notice_version"] == services.ai_notice_version()


def test_unknown_purpose_rejected(job: Any) -> None:
    app = ready_draft(job)
    with pytest.raises(ValueError):
        services.record(app.candidate_user, "selling_data", granted=True, notice_version="x")
