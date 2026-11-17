"""Audit UI API and decision reconstruction (P08-T11, EC-PRV-06)."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application, IdentityReveal
from apps.audit.models import AuditEvent
from apps.core.time import now
from apps.organisations.models import Membership, OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.screening import services as screening
from apps.shortlisting import services as shortlists

pytestmark = pytest.mark.django_db
NAME = ("Takudzwa", "Chari")


def client(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


@pytest.fixture
def decided(read_app: Application, vacancy: Any) -> Application:
    """Evaluated, shortlisted through an approved shortlist."""
    team = vacancy.team
    Application.objects.unscoped().filter(pk=read_app.pk).update(
        candidate_profile_snapshot={"first_name": NAME[0], "last_name": NAME[1]}
    )
    screening.evaluate_application(read_app.pk)
    m = Membership.objects.get(user=team.hr_manager, organisation=team.org)
    s = shortlists.create_proposal(m, team.hr_manager, vacancy.job.pk)
    shortlists.set_decisions(
        m, team.hr_manager, s.pk, [{"application_id": read_app.pk, "decision": "shortlist"}]
    )
    shortlists.submit(m, team.hr_manager, s.pk)
    shortlists.approve(m, team.hr_manager, s.pk)
    read_app.refresh_from_db()
    return read_app


def test_reconstruction_bundle_is_complete(decided: Application, vacancy: Any) -> None:
    team = vacancy.team
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=False)
    body = (
        client(team.hr_manager, team.org)
        .get(f"/api/v1/hr/applications/{decided.pk}/reconstruct/")
        .json()
    )
    assert body["application"]["status"] == "shortlisted"
    assert body["job"]["version"] == decided.job_version.number
    assert body["rubric"]["criteria"] and body["rubric"]["categories"]
    (ev,) = body["evaluations"]
    assert ev["engine_version"] and ev["config_version"] and ev["input_hash"]
    assert any(c["evidence"] for c in ev["criteria"])
    assert any(
        e["to_status"] == "shortlisted" and e["actor_type"] == "human"
        for e in body["status_events"]
    )
    (decision,) = body["shortlist_decisions"]
    assert decision["decision"] == "shortlist" and decision["approved_at"]
    assert decision["ai_band_at_decision"] == ev["band"]
    assert {n["key"] for n in body["notifications"]} == {"shortlisted"}
    assert body["application"]["candidate"] == f"{NAME[0]} {NAME[1]}"
    assert AuditEvent.objects.filter(action="application.reconstructed").exists()


def test_auditor_sees_pii_redacted_until_revealed(decided: Application, vacancy: Any) -> None:
    team = vacancy.team
    OrganisationPolicy.objects.filter(organisation=team.org).update(blind_review_default=False)
    auditor = client(team.auditor, team.org)
    body = auditor.get(f"/api/v1/hr/applications/{decided.pk}/reconstruct/").json()
    assert body["identity_hidden"] is True  # EC-PRV-06: whatever the blind setting
    assert NAME[0] not in str(body) and NAME[1] not in str(body)
    assert all(
        e["snippet"] is None
        for ev in body["evaluations"]
        for c in ev["criteria"]
        for e in c["evidence"]
    )
    IdentityReveal.objects.create(
        organisation=team.org,
        application=decided,
        user=team.auditor,
        reason="Complaint review",
        at=now(),
    )
    body = auditor.get(f"/api/v1/hr/applications/{decided.pk}/reconstruct/").json()
    assert body["identity_hidden"] is False and NAME[0] in body["application"]["candidate"]


def test_reconstruction_pdf(decided: Application, vacancy: Any) -> None:
    team = vacancy.team
    res = client(team.hr_manager, team.org).get(
        f"/api/v1/hr/applications/{decided.pk}/reconstruct.pdf"
    )
    assert res.status_code == 200 and res["Content-Type"] == "application/pdf"
    assert res.content.startswith(b"%PDF") and len(res.content) > 1000


def test_recruiter_and_other_org_cannot_reconstruct(decided: Application, vacancy: Any) -> None:
    team = vacancy.team
    url = f"/api/v1/hr/applications/{decided.pk}/reconstruct/"
    assert client(team.recruiter, team.org).get(url).status_code == 403
    other = make_org_with_team()
    assert client(other.auditor, other.org).get(url).status_code == 404


def test_audit_events_filter_and_safe_export(decided: Application, vacancy: Any) -> None:
    team = vacancy.team
    from apps.audit import services as audit

    audit.record(
        actor=team.admin,
        action="note.test",
        target=("application", str(decided.pk)),
        organisation=team.org.pk,
        reason="=HYPERLINK(evil)",
    )
    c = client(team.auditor, team.org)
    body = c.get("/api/v1/hr/audit-events/", {"target_id": str(decided.pk)}).json()
    actions = {e["action"] for e in body["results"]}
    assert "application.status_changed" in actions and "note.test" in actions
    assert all(e["target_id"] == str(decided.pk) for e in body["results"])
    shortlisted = c.get("/api/v1/hr/audit-events/", {"action": "shortlist."}).json()
    assert {e["action"] for e in shortlisted["results"]} >= {"shortlist.approved"}
    export = c.get("/api/v1/hr/audit-events/export/", {"action": "note."})
    assert export.status_code == 200 and export["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(export.content.decode())))
    assert rows[0][4] == "action" and rows[1][7] == "'=HYPERLINK(evil)"  # neutralised
    assert AuditEvent.objects.filter(action="audit.exported").exists()
    assert client(team.recruiter, team.org).get("/api/v1/hr/audit-events/").status_code == 403
