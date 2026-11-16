"""Shortlist API (P08-T02): end-to-end flow, idempotent approval, error codes."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application
from apps.organisations.models import OrganisationPolicy

from .test_services import World, world  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


def client(w: World, user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(w.team.org.pk))
    return c


def test_full_flow_over_http(world: World) -> None:  # noqa: F811
    w = world
    rec, hr = client(w, w.team.recruiter), client(w, w.team.hr_manager)
    res = rec.post(f"/api/v1/hr/jobs/{w.job.pk}/shortlists/", {"desired_size": 1}, format="json")
    assert res.status_code == 201, res.json()
    body = res.json()
    sid = body["id"]
    assert body["summary"]["undecided"] == 4 and len(body["entries"]) == 4
    assert {e["decision"] for e in body["entries"]} == {"undecided"}

    bad = rec.patch(
        f"/api/v1/hr/shortlists/{sid}/entries/",
        {"decisions": [{"application_id": str(w.apps["lower"].pk), "decision": "not_selected"}]},
        format="json",
    )
    assert bad.status_code == 400
    assert str(w.apps["lower"].pk) in bad.json()["error"]["details"]["decisions"]

    ok = rec.patch(
        f"/api/v1/hr/shortlists/{sid}/entries/",
        {
            "decisions": [
                {"application_id": str(w.apps["top"].pk), "decision": "shortlist"},
                {
                    "application_id": str(w.apps["lower"].pk),
                    "decision": "not_selected",
                    "reason_code": "less_relevant_experience",
                },
            ],
            "lock_version": body["lock_version"],
        },
        format="json",
    )
    assert ok.status_code == 200 and ok.json()["summary"]["shortlist"] == 1
    stale = rec.patch(
        f"/api/v1/hr/shortlists/{sid}/entries/",
        {
            "decisions": [{"application_id": str(w.apps["top"].pk), "decision": "undecided"}],
            "lock_version": body["lock_version"],
        },
        format="json",
    )
    assert stale.status_code == 409

    assert rec.post(f"/api/v1/hr/shortlists/{sid}/submit/", {}, format="json").status_code == 200
    # recruiters cannot approve
    no = rec.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert no.status_code == 403
    # approval needs an Idempotency-Key
    assert hr.post(f"/api/v1/hr/shortlists/{sid}/approve/", {}, format="json").status_code == 400
    undecided = hr.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert undecided.status_code == 400
    assert undecided.json()["error"]["code"] == "undecided_remaining"
    key = str(uuid.uuid4())
    first = hr.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {"leave_undecided": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert first.status_code == 200 and first.json()["status"] == "approved"
    replay = hr.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {"leave_undecided": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert replay.status_code == 200 and replay["Idempotent-Replayed"] == "true"
    again = hr.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_processed"
    statuses = dict(Application.objects.for_org(w.team.org).values_list("pk", "status"))
    assert statuses[w.apps["top"].pk] == "shortlisted"
    assert statuses[w.apps["unsure"].pk] == "under_review"  # undecided: untouched

    undo = hr.post(
        f"/api/v1/hr/shortlists/{sid}/undo/", {"reason": "Approved too early"}, format="json"
    )
    assert undo.status_code == 200 and undo.json()["status"] == "undone"
    listed = rec.get(f"/api/v1/hr/jobs/{w.job.pk}/shortlists/").json()
    assert listed[0]["id"] == sid and listed[0]["status"] == "undone"


def test_self_approval_error_code(world: World) -> None:  # noqa: F811
    w = world
    OrganisationPolicy.objects.filter(organisation=w.team.org).update(shortlist_dual_control=True)
    hr = client(w, w.team.hr_manager)
    sid = hr.post(f"/api/v1/hr/jobs/{w.job.pk}/shortlists/", {}, format="json").json()["id"]
    hr.patch(
        f"/api/v1/hr/shortlists/{sid}/entries/",
        {"decisions": [{"application_id": str(w.apps["top"].pk), "decision": "shortlist"}]},
        format="json",
    )
    hr.post(f"/api/v1/hr/shortlists/{sid}/submit/", {}, format="json")
    res = hr.post(
        f"/api/v1/hr/shortlists/{sid}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "self_approval_forbidden"
    returned = client(w, w.team.admin).post(
        f"/api/v1/hr/shortlists/{sid}/reject/", {"reason": "Add the holds"}, format="json"
    )
    assert returned.status_code == 200 and returned.json()["status"] == "draft"
    assert returned.json()["return_reason"] == "Add the holds"
