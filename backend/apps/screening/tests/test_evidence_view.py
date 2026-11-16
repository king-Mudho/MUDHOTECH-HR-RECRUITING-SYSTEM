"""Evidence viewer data (P08-T06): page text, highlights linked to criteria, masking."""

from __future__ import annotations

import json
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.applications.models import Application
from apps.organisations.models import OrganisationPolicy
from apps.screening import services

pytestmark = pytest.mark.django_db
NAME = ("Takudzwa", "Chari")  # the synthetic GOOD_CV's person


def client(vacancy: Any) -> APIClient:
    c = APIClient()
    c.force_login(vacancy.team.hr_manager)
    c.credentials(HTTP_X_ORG_ID=str(vacancy.team.org.pk))
    return c


def snapshot(app: Application) -> None:
    Application.objects.unscoped().filter(pk=app.pk).update(
        candidate_profile_snapshot={"first_name": NAME[0], "last_name": NAME[1]}
    )


def test_text_highlights_and_criteria_links(read_app: Application, vacancy: Any) -> None:
    OrganisationPolicy.objects.filter(organisation=vacancy.team.org).update(
        blind_review_default=False
    )
    services.evaluate_application(read_app.pk)
    body = client(vacancy).get(f"/api/v1/hr/applications/{read_app.pk}/evidence-text/").json()
    assert body["identity_hidden"] is False
    (doc,) = body["documents"]
    assert doc["pages"] and doc["pages"][0]["text"]
    pages = {p["number"]: p["text"] for p in doc["pages"]}
    python = str(vacancy.criteria["python"].pk)
    linked = [h for h in doc["highlights"] if python in h["criteria"]]
    assert linked, "the Python criterion cites at least one highlighted span"
    for h in doc["highlights"]:
        assert 0 <= h["start"] < h["end"] <= len(pages[h["page"]])
    text = " ".join(pages.values())
    assert "Python" in text
    # contact details are always masked (email/phone of the synthetic person)
    assert "@example.test" not in text and "+263" not in text
    assert doc["filename"].endswith(".docx") and doc["original_available"] is False  # DOCX


def test_blind_mode_masks_the_name(read_app: Application, vacancy: Any) -> None:
    snapshot(read_app)
    body = client(vacancy).get(f"/api/v1/hr/applications/{read_app.pk}/evidence-text/").json()
    assert body["identity_hidden"] is True
    dumped = json.dumps(body)
    assert NAME[0] not in dumped and NAME[1] not in dumped
    assert body["documents"][0]["filename"] == "CV"


def test_other_organisation_gets_404(read_app: Application) -> None:
    from apps.organisations.tests.factories import make_org_with_team

    other = make_org_with_team()
    c = APIClient()
    c.force_login(other.hr_manager)
    c.credentials(HTTP_X_ORG_ID=str(other.org.pk))
    assert c.get(f"/api/v1/hr/applications/{read_app.pk}/evidence-text/").status_code == 404
