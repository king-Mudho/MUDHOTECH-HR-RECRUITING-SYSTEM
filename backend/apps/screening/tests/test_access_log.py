"""Access logging of candidate PII / CV views (P08-T12)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application
from apps.audit import services as audit
from apps.audit.models import AccessLog
from apps.organisations.models import Membership
from apps.screening import services as screening
from apps.shortlisting import services as shortlists

pytestmark = pytest.mark.django_db


def client(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def actions(user: Any) -> list[str]:
    return list(AccessLog.objects.filter(user=user).values_list("action", flat=True))


def test_every_pii_view_is_logged(read_app: Application, vacancy: Any) -> None:
    team = vacancy.team
    screening.evaluate_application(read_app.pk)
    c = client(team.hr_manager, team.org)
    base = f"/api/v1/hr/applications/{read_app.pk}"
    for path in (
        f"{base}/",
        f"{base}/extraction/",
        f"{base}/evidence-text/",
        f"{base}/evaluation/",
        f"{base}/evaluations/1/",
        f"{base}/reconstruct/",
        f"/api/v1/hr/jobs/{vacancy.job.pk}/applications/",
    ):
        assert c.get(path).status_code == 200, path
    m = Membership.objects.get(user=team.hr_manager, organisation=team.org)
    s = shortlists.create_proposal(m, team.hr_manager, vacancy.job.pk)
    assert c.get(f"/api/v1/hr/shortlists/{s.pk}/").status_code == 200
    logged = actions(team.hr_manager)
    for action in (
        "view",
        "extraction",
        "cv_text",
        "evaluation",
        "reconstruct",
        "list_applicants",
        "shortlist",
    ):
        assert action in logged, action
    assert all(
        a.request_id for a in AccessLog.objects.filter(user=team.hr_manager, action="cv_text")
    )
    # the reconstruction shows who looked
    body = c.get(f"{base}/reconstruct/").json()
    assert {"cv_text", "evaluation"} <= {v["action"] for v in body["views"]}


def test_list_sampling_never_applies_to_auditors_or_object_views(
    vacancy: Any, settings: Any
) -> None:
    settings.ACCESS_LOG_LIST_SAMPLE_RATE = 0.0
    team = vacancy.team
    recruiter = Membership.objects.get(user=team.recruiter, organisation=team.org)
    auditor = Membership.objects.get(user=team.auditor, organisation=team.org)
    assert audit.log_view(recruiter, ("job", vacancy.job.pk), listing=True) is None
    assert audit.log_view(auditor, ("job", vacancy.job.pk), listing=True) is not None
    assert audit.log_view(recruiter, ("application", "x"), action="view") is not None
