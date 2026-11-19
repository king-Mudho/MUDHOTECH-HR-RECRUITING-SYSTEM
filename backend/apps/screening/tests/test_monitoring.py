"""P13-T07: AI quality monitoring - override alerts above 30 % per vacancy (advice only, once a
week), platform drift indicators (parse failure trend, score shift between engine versions)."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core.time import now
from apps.documents.models import Document, ScanStatus
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.resumes.models import ExtractionRun, RunStatus
from apps.screening import monitoring
from apps.screening.models import AIQualityReport, Evaluation
from apps.shortlisting.models import Shortlist, ShortlistEntry

pytestmark = pytest.mark.django_db


def decisions(team: Any, job: Any, *, total: int, overrides: int) -> None:
    shortlist = Shortlist.objects.create(
        organisation=team.org,
        job=job,
        job_version=job.published_version,
        proposed_by=team.recruiter,
        status=Shortlist.Status.APPROVED,
        submitted_at=now(),
        approved_at=now(),
    )
    for i in range(total):
        app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
        against = i < overrides
        ShortlistEntry.objects.create(
            organisation=team.org,
            shortlist=shortlist,
            application=app,
            decision="shortlist",
            ai_band_at_decision="lower_match" if against else "recommended_for_review",
            override=against,
            decided_by=team.hr_manager,
            decided_at=now(),
            reason_code="other" if against else "",
            reason_text="Decided on the evidence" if against else "",
        )


def test_override_alert_above_30_percent_once_a_week() -> None:
    team = make_org_with_team()
    hot = published_job(organisation=team.org, title="Data Engineer")
    calm = published_job(organisation=team.org, title="Accountant")
    small = published_job(organisation=team.org, title="Driver")
    decisions(team, hot, total=10, overrides=4)  # 40 %
    decisions(team, calm, total=10, overrides=3)  # 30 %: not above
    decisions(team, small, total=5, overrides=5)  # too few decisions
    assert monitoring.check_override_alerts() == 1
    alerts = Notification.objects.filter(key="ai_override_alert")
    assert {n.recipient_user_id for n in alerts} == {team.hr_manager.pk, team.admin.pk}
    assert all(n.payload.get("job_title") == "Data Engineer" for n in alerts if n.payload)
    assert AuditEvent.objects.filter(action="ai_quality.override_alert").count() == 1
    before = alerts.count()
    monitoring.check_override_alerts()  # same week: deduplicated
    assert Notification.objects.filter(key="ai_override_alert").count() == before
    # nothing about the applications or the rubric changed
    assert not Application.objects.for_org(team.org).exclude(status=Status.UNDER_REVIEW).exists()


def _evals(job: Any, version: str, scores: list[float], band: str) -> None:
    for score in scores:
        app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
        Evaluation.objects.create(
            organisation_id=app.organisation_id,
            application=app,
            job_version=app.job_version,
            version=1,
            total_score=score,
            coverage=0.8,
            band=band,
            input_hash=str(app.pk),
            engine_version=version,
        )


def test_drift_indicators_flag_a_score_shift_and_parse_trend() -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    _evals(job, "0.3.0", [60.0] * 20, "review_needed")
    Evaluation.objects.unscoped().filter(engine_version="0.3.0").update(
        created_at=now() - timedelta(days=10)
    )
    _evals(job, "0.3.1", [80.0] * 20, "recommended_for_review")
    app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    for status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
        doc = Document.objects.create(
            owner_user=app.candidate_user,
            purpose="cv",
            original_filename="cv.pdf",
            size_bytes=1,
            storage_key=f"cv/{uuid.uuid4().hex}",
            scan_status=ScanStatus.CLEAN,
        )
        ExtractionRun.objects.create(
            organisation=team.org,
            application=app,
            document=doc,
            engine_version=str(uuid.uuid4())[:8],
            status=status,
            finished_at=now(),
        )
    data = monitoring.drift_indicators()
    assert data["latest_shift"]["from"] == "0.3.0" and data["latest_shift"]["to"] == "0.3.1"
    assert "mean_score" in data["latest_shift"]["flags"]
    assert "band:recommended_for_review" in data["latest_shift"]["flags"]
    assert data["parse_failure_trend"][-1]["failure_rate"] == 0.5
    report = monitoring.store_platform_report()
    assert report.organisation_id is None and report.job_id is None
    assert AIQualityReport.objects.filter(organisation__isnull=True).count() == 1
    assert AuditEvent.objects.filter(action="ai_quality.drift_flagged").exists()
    out = io.StringIO()
    call_command("ai_quality_report", stdout=out)
    assert "latest_shift" in out.getvalue()


def test_platform_api_is_platform_staff_only() -> None:
    staff = UserFactory(platform_role=PlatformRole.PLATFORM_ADMIN)
    c = APIClient()
    c.force_login(staff)
    body = c.get("/api/v1/platform/ai/quality/")
    assert body.status_code == 200 and "engine_versions" in body.json()
    team = make_org_with_team()
    hr = APIClient()
    hr.force_login(team.hr_manager)
    assert hr.get("/api/v1/platform/ai/quality/").status_code == 403
