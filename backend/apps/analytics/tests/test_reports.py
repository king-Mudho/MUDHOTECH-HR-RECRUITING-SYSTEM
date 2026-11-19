"""P13-T03: recruitment analytics reconcile with direct queries over the raw data; HR managers
only; another organisation's data never counts; snapshots for the default view."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.analytics import selectors, services
from apps.analytics.models import AnalyticsSnapshot
from apps.applications.models import Application, ApplicationStatusEvent, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application, published_job
from apps.core.time import now
from apps.documents.models import Document, ScanStatus
from apps.messaging.models import ClarificationRequest
from apps.organisations.tests.factories import make_org_with_team
from apps.resumes.models import ExtractionRun, RunStatus
from apps.shortlisting.models import Shortlist, ShortlistEntry

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def app(job: Any, status: str, *, hours_ago: float, source: str = "") -> Application:
    a = make_application(job, UserFactory(), status=status)
    Application.objects.unscoped().filter(pk=a.pk).update(
        submitted_at=now() - timedelta(hours=hours_ago),
        source={"source": source, "utm_source": source} if source else {},
    )
    a.refresh_from_db()
    return a


def run(a: Application, status: str, *, ocr: bool = False, seconds: int = 10) -> None:
    doc = Document.objects.create(
        owner_user=a.candidate_user,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key=f"cv/{uuid.uuid4().hex}.pdf",
        scan_status=ScanStatus.CLEAN,
    )
    started = now() - timedelta(minutes=5)
    ExtractionRun.objects.create(
        organisation_id=a.organisation_id,
        application=a,
        document=doc,
        engine_version="t",
        status=status,
        timings_ms={"ocr": 100.0} if ocr else {"parse": 5.0},
        started_at=started,
        finished_at=started + timedelta(seconds=seconds),
    )


@pytest.fixture
def world() -> dict[str, Any]:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    hm = team.hr_manager
    a = app(job, Status.UNDER_REVIEW, hours_ago=48, source="linkedin")
    b = app(job, Status.UNDER_REVIEW, hours_ago=30, source="linkedin")
    c = app(job, Status.UNDER_REVIEW, hours_ago=10)
    app(job, Status.PROCESSING, hours_ago=2, source="Facebook")
    transition(a, Status.SHORTLISTED, actor=hm, reason="Strong evidence")
    transition(a, Status.INTERVIEW, actor=hm, reason="Invite to interview")
    transition(a, Status.OFFER, actor=hm, reason="Make an offer")
    transition(a, Status.HIRED, actor=hm, reason="Hire confirmed")
    transition(b, Status.SHORTLISTED, actor=hm, reason="Good evidence")
    transition(b, Status.NOT_SELECTED, actor=hm, reason="Another candidate fitted better")
    transition(c, Status.NOT_SELECTED, actor=hm, reason="Missing the required licence")
    # abandoned drafts at different steps
    for step in (1, 3, 3):
        d = make_application(job, UserFactory(), status=Status.DRAFT)
        Application.objects.unscoped().filter(pk=d.pk).update(last_step=step)
    run(a, RunStatus.SUCCEEDED, seconds=10)
    run(b, RunStatus.SUCCEEDED, ocr=True, seconds=30)
    run(c, RunStatus.FAILED, seconds=20)
    for target, status, answered in ((a, "answered", True), (b, "expired", False)):
        ClarificationRequest.objects.create(
            organisation=team.org,
            application=target,
            questions=[{"id": "q1", "prompt": "Which year?"}],
            due_at=now() + timedelta(days=3),
            status=status,
            answered_at=now() if answered else None,
        )
    shortlist = Shortlist.objects.create(
        organisation=team.org,
        job=job,
        job_version=job.published_version,
        proposed_by=team.recruiter,
        status=Shortlist.Status.APPROVED,
        submitted_at=now(),
        approved_at=now(),
    )
    for target, decision, band, override in (
        (a, "shortlist", "recommended_for_review", False),
        (b, "shortlist", "lower_match", True),
        (c, "not_selected", "recommended_for_review", True),
    ):
        ShortlistEntry.objects.create(
            organisation=team.org,
            shortlist=shortlist,
            application=target,
            decision=decision,
            ai_band_at_decision=band,
            override=override,
            decided_by=hm,
            decided_at=now(),
            reason_code="other" if override else "",
            reason_text="Decided on the evidence" if override else "",
        )
    # another organisation's data must never count
    other = make_org_with_team()
    app(published_job(organisation=other.org), Status.UNDER_REVIEW, hours_ago=5, source="linkedin")
    return {"team": team, "job": job, "other": other, "a": a, "b": b, "c": c}


def scope(world: dict[str, Any], **params: Any) -> selectors.Scope:
    return selectors.scope_from(world["team"].org.pk, params)


def test_funnel_and_sources_reconcile(world: dict[str, Any]) -> None:
    s = scope(world)
    direct = Application.objects.for_org(world["team"].org).exclude(submitted_at__isnull=True)
    funnel = {r["stage"]: r for r in selectors.funnel(s)["stages"]}
    assert funnel["submitted"]["count"] == direct.count() == 4
    assert funnel["shortlisted"]["count"] == 2  # b was shortlisted, then not selected
    assert funnel["interviewed"]["count"] == funnel["offered"]["count"] == 1
    assert funnel["hired"]["count"] == direct.filter(status="hired").count() == 1
    assert funnel["shortlisted"]["conversion"] == round(2 / funnel["reviewed"]["count"], 4)
    sources = {r["source"]: r for r in selectors.sources(s)}
    assert sources["linkedin"] == {"source": "linkedin", "applications": 2, "shortlisted": 2}
    assert sources["facebook"]["applications"] == 1 and sources["direct"]["applications"] == 1
    assert sum(r["applications"] for r in sources.values()) == direct.count()


def test_timing_matches_status_history(world: dict[str, Any]) -> None:
    t = selectors.timing(scope(world))
    hired = ApplicationStatusEvent.objects.for_org(world["team"].org).get(to_status="hired")
    a = world["a"]
    expected = (hired.at - a.submitted_at).total_seconds() / 3600
    assert t["time_to_hire"]["count"] == 1
    assert t["time_to_hire"]["median_hours"] == pytest.approx(expected, abs=0.01)
    assert t["time_to_shortlist"]["count"] == 2
    assert t["time_to_review"]["count"] == 3  # a, b, c had a human action


def test_processing_questionnaire_clarifications_and_ai(world: dict[str, Any]) -> None:
    s = scope(world)
    p = selectors.processing(s)
    assert p["extraction_runs"] == 3
    assert p["parse_failure_rate"] == round(1 / 3, 4) and p["ocr_rate"] == round(1 / 3, 4)
    assert p["mean_extraction_seconds"] == pytest.approx(20.0)
    q = selectors.questionnaire(s)
    steps = {r["step"]: r["unfinished"] for r in q["unfinished_by_step"]}
    assert steps["contact"] == 1 and steps["documents"] == 2 and q["unfinished"] == 3
    cl = selectors.clarifications(s)
    assert cl["total"] == 2 and cl["response_rate"] == 0.5
    ai = selectors.ai_agreement(s)
    assert ai["decisions"] == 3 and ai["overrides"] == 2
    assert ai["override_rate"] == round(2 / 3, 4) and ai["agreement_rate"] == round(1 / 3, 4)
    bands = {r["band"]: r for r in ai["by_band"]}
    assert bands["recommended_for_review"]["override_rate"] == 0.5


def test_filters_and_date_window(world: dict[str, Any]) -> None:
    other_job = published_job(organisation=world["team"].org)
    app(other_job, Status.UNDER_REVIEW, hours_ago=1)
    assert selectors.report(scope(world, job=str(world["job"].pk)))["applications"] == 4
    assert selectors.report(scope(world))["applications"] == 5
    old = scope(world, **{"from": "2020-01-01", "to": "2020-01-31"})
    assert selectors.report(old)["applications"] == 0


def test_api_permissions_snapshot_and_isolation(world: dict[str, Any]) -> None:
    team, other = world["team"], world["other"]
    hr = staff(team.hr_manager, team.org)
    first = hr.get("/api/v1/hr/reports/recruitment/")
    assert first.status_code == 200 and first.json()["origin"] == "live"
    assert first.json()["applications"] == 4
    assert AnalyticsSnapshot.objects.for_org(team.org).count() == 1
    assert hr.get("/api/v1/hr/reports/recruitment/").json()["origin"] == "snapshot"
    refreshed = hr.post("/api/v1/hr/reports/recruitment/refresh/")
    assert refreshed.status_code == 200 and refreshed.json()["origin"] == "live"
    filtered = hr.get("/api/v1/hr/reports/recruitment/", {"job": str(world["job"].pk)})
    assert filtered.json()["origin"] == "live"
    assert staff(team.recruiter, team.org).get("/api/v1/hr/reports/recruitment/").status_code == 403
    foreign = staff(other.hr_manager, other.org)
    assert foreign.get("/api/v1/hr/reports/recruitment/").json()["applications"] == 1
    assert (
        foreign.get("/api/v1/hr/reports/recruitment/", {"job": str(world["job"].pk)}).status_code
        == 404
    )
    assert services.refresh_all() >= 0
