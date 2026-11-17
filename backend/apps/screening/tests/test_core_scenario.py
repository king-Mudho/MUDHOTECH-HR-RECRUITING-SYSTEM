"""MVP core scenario, in process (P08-T13; Phase 08 exit criterion).

A published Software Developer vacancy receives 100 applications with synthetic CVs and screening
answers. Real CV extraction and screening run through the outbox consumers (eager in tests). HR
filters the applicants, verifies two claims, asks one applicant for clarification, proposes and
approves a shortlist of ten. After the notification delay exactly ten "shortlisted" emails go out;
nobody else is told anything they were not decided about. Every consequential status change has a
human actor and a reason.

The same journey runs in the browser against the Docker stack in the nightly job
(``frontend/e2e/core-scenario.spec.ts`` with ``manage.py seed_core_scenario``).
"""

from __future__ import annotations

import io
import json
import random
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationStatusEvent
from apps.core.time import now
from apps.jobs.models import JobAssignment
from apps.messaging.models import ClarificationRequest
from apps.notifications.models import Notification
from apps.organisations.models import Membership, OrganisationPolicy
from apps.questionnaires.models import QuestionResponse
from apps.resumes import services as resumes
from apps.resumes.tests.test_extraction_flow import attach, submitted_app

pytestmark = [pytest.mark.django_db, pytest.mark.slow]
CORPUS = Path(__file__).resolve().parents[3] / "fixtures" / "synthetic_cvs"
APPLICANTS = 100
SHORTLIST = 10


def cvs() -> list[tuple[str, bytes]]:
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))["cvs"]
    usable = [
        c
        for c in labels
        if c["role"] == "software_developer"
        and c["parse_expected"] == "ok"
        and not c["needs_ocr"]
        and not c["injection"]
    ]
    return [(c["file"], (CORPUS / c["file"]).read_bytes()) for c in usable]


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def test_core_scenario(vacancy: Any, act: Any, settings: Any, monkeypatch: Any) -> None:
    settings.SCREENING_AUTOSTART = True
    team, job = vacancy.team, vacancy.job
    OrganisationPolicy.objects.filter(organisation=team.org).update(
        blind_review_default=False, notification_delay_minutes=15
    )
    JobAssignment.objects.create(
        organisation=team.org,
        job=job,
        membership=Membership.objects.get(user=team.recruiter, organisation=team.org),
        role_on_job="recruiter",
    )

    # 1. 100 applications with CVs and answers; extraction + screening run via the outbox
    corpus = cvs()
    for i in range(APPLICANTS):
        app = submitted_app(org=team.org, user=UserFactory(verified=True))
        Application.objects.unscoped().filter(pk=app.pk).update(
            job=job, job_version=job.published_version
        )
        app.refresh_from_db()
        for question, value in (
            (vacancy.knockout, "yes" if i % 9 else "no"),
            (vacancy.years, i % 8),
        ):
            QuestionResponse.objects.create(
                organisation=team.org, application=app, question=question, value=value
            )
        name, data = corpus[i % len(corpus)]
        attach(app, data, filename=name)
        act(resumes.start, app.pk)
    apps = Application.objects.for_org(team.org).filter(job=job)
    assert apps.count() == APPLICANTS
    assert not apps.filter(status__in=["submitted", "processing"]).exists(), "processing done"
    assert apps.filter(current_evaluation_id__isnull=False).count() >= APPLICANTS - 5

    # 2. HR filters the applicants
    rec = staff(team.recruiter, team.org)
    url = f"/api/v1/hr/jobs/{job.pk}/applications/"
    recommended = rec.get(url, {"band": "recommended_for_review", "page_size": 200}).json()
    assert recommended["count"] >= SHORTLIST
    unsure = rec.get(url, {"band": "review_needed", "page_size": 5}).json()["results"]
    assert unsure, "some applicants need review"

    # 3. verify two claims (re-evaluated as new versions)
    hr = staff(team.hr_manager, team.org)
    verified = 0
    for row in recommended["results"]:
        ev = hr.get(f"/api/v1/hr/applications/{row['id']}/evaluation/").json()
        claim = next(
            (e["claim_id"] for c in ev["criteria"] for e in c["evidence"] if e["claim_id"]), None
        )
        if claim:
            res = act(
                hr.post,
                f"/api/v1/hr/claims/{claim}/verify/",
                {"decision": "confirmed", "reevaluate": True},
                format="json",
            )
            assert res.status_code == 201
            verified += 1
        if verified == 2:
            break
    assert verified == 2

    # 4. one clarification request
    res = act(
        rec.post,
        f"/api/v1/hr/applications/{unsure[0]['id']}/clarifications/",
        {
            "questions": [{"prompt": "Please describe a Django project you built."}],
            "due_at": (now() + timedelta(days=5)).isoformat(),
        },
        format="json",
    )
    assert res.status_code == 201, res.json()
    assert ClarificationRequest.objects.for_org(team.org).count() == 1

    # 5. propose, decide the top ten, submit; an HR manager approves
    proposal = rec.post(
        f"/api/v1/hr/jobs/{job.pk}/shortlists/", {"desired_size": SHORTLIST}, format="json"
    )
    assert proposal.status_code == 201, proposal.json()
    body = proposal.json()
    top = [
        e["application_id"] for e in body["entries"] if e["ai_band"] == "recommended_for_review"
    ][:SHORTLIST]
    assert len(top) == SHORTLIST
    res = rec.patch(
        f"/api/v1/hr/shortlists/{body['id']}/entries/",
        {"decisions": [{"application_id": a, "decision": "shortlist"} for a in top]},
        format="json",
    )
    assert res.status_code == 200 and res.json()["summary"]["shortlist"] == SHORTLIST
    assert (
        rec.post(f"/api/v1/hr/shortlists/{body['id']}/submit/", {}, format="json").status_code
        == 200
    )
    approved = act(
        hr.post,
        f"/api/v1/hr/shortlists/{body['id']}/approve/",
        {"leave_undecided": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert approved.status_code == 200, approved.json()
    assert apps.filter(status="shortlisted").count() == SHORTLIST

    # 6. nothing reaches candidates before the delay; afterwards exactly ten shortlisted emails
    from apps.notifications import delivery
    from apps.notifications.tasks import send_due

    outcome = Notification.objects.filter(key__in=["shortlisted", "not_selected"], channel="email")
    assert outcome.count() == SHORTLIST and not outcome.filter(status="sent").exists()
    mail.outbox.clear()
    notify_after = approved.json()["notify_after"]
    assert all(n.scheduled_for.isoformat() >= notify_after[:19] for n in outcome)  # not before
    # after the delay (and after quiet hours, when the run happens at night)
    later = max(n.scheduled_for for n in outcome) + timedelta(minutes=1)
    monkeypatch.setattr(delivery, "now", lambda: later)
    send_due()
    shortlisted = {
        a.candidate_user.email
        for a in apps.filter(status="shortlisted").select_related("candidate_user")
    }
    clarified = Application.objects.for_org(team.org).get(pk=unsure[0]["id"]).candidate_user.email
    recipients = [m.to[0] for m in mail.outbox]
    assert len(recipients) == SHORTLIST + 1  # ten outcomes + the clarification request
    assert set(recipients) == shortlisted | {clarified}  # nobody else hears anything
    assert outcome.filter(status="sent").count() == SHORTLIST
    assert not Notification.objects.filter(key="not_selected").exists()  # HR decided no one else

    # 7. accountability: every consequential change has a human actor and a reason
    consequential = ApplicationStatusEvent.objects.for_org(team.org).filter(
        to_status__in=["shortlisted", "not_selected", "offer", "hired"]
    )
    assert consequential.count() == SHORTLIST
    assert not consequential.filter(actor__isnull=True).exists()
    assert not consequential.exclude(actor_type="human").exists()
    assert not consequential.filter(reason_text="").exists()
    from django.core.management import call_command

    out = io.StringIO()
    call_command("check_human_decisions", stdout=out)  # exit criterion: audit query
    assert "0 consequential transitions without a human actor" in out.getvalue()

    # 8. reconstruction bundle is complete for a random sample of ten applications
    sample = random.Random(8).sample(list(apps.values_list("pk", flat=True)), 10)
    for app_id in sample:
        bundle = hr.get(f"/api/v1/hr/applications/{app_id}/reconstruct/").json()
        assert bundle["job"]["version"] and bundle["rubric"]["criteria"]
        assert bundle["status_events"], "status history"
        for ev in bundle["evaluations"]:
            assert ev["engine_version"] and ev["config_version"] and ev["input_hash"]
            assert ev["model_ids"] or ev["trigger"] in ("auto", "verification", "correction")
            assert all("evidence" in c for c in ev["criteria"])
        if bundle["application"]["status"] == "shortlisted":
            (decision,) = bundle["shortlist_decisions"]
            assert decision["decided_by"] and decision["approved_at"] and decision["applied_at"]
            assert {n["key"] for n in bundle["notifications"]} >= {"shortlisted"}
