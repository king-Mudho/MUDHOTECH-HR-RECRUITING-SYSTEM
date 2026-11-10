"""Candidate profiles (P04-T01): no protected fields, CRUD, isolation, completeness."""

from __future__ import annotations

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.candidates.models import CandidateProfile

pytestmark = pytest.mark.django_db

# FR-M06-02 / principle 7: none of these may exist on any candidate model.
FORBIDDEN = {
    "date_of_birth",
    "dob",
    "birth_date",
    "age",
    "gender",
    "sex",
    "race",
    "ethnicity",
    "tribe",
    "totem",
    "religion",
    "marital_status",
    "pregnant",
    "pregnancy",
    "children",
    "disability",
    "health",
    "hiv_status",
    "political_party",
    "national_id",
    "id_number",
    "photo",
    "avatar",
    "picture",
}


def test_candidate_models_have_no_protected_fields() -> None:
    for model in django_apps.get_app_config("candidates").get_models():
        names = {f.name for f in model._meta.get_fields()}
        names |= {getattr(f, "attname", f.name) for f in model._meta.get_fields()}
        assert not names & FORBIDDEN, (model.__name__, names & FORBIDDEN)


@pytest.fixture
def user():  # type: ignore[no-untyped-def]
    return UserFactory()


@pytest.fixture
def client(user) -> APIClient:  # type: ignore[no-untyped-def]
    c = APIClient()
    c.force_login(user)
    return c


def test_profile_created_on_first_read_and_patched(client, user) -> None:  # type: ignore[no-untyped-def]
    res = client.get("/api/v1/candidate/profile/")
    assert res.status_code == 200
    body = res.json()
    assert body["profile_completeness"] == 0 and "headline" in body["missing"]
    res = client.patch(
        "/api/v1/candidate/profile/",
        {
            "headline": "Python developer",
            "city": "Harare",
            "phone_e164": "0772 123 456",
            "links": {"github": "https://github.com/example"},
            "lock_version": body["lock_version"],
        },
        format="json",
    )
    assert res.status_code == 200, res.content
    assert res.json()["phone_e164"] == "+263772123456"
    assert res.json()["profile_completeness"] == 25  # headline 10 + location 5 + phone 10
    assert CandidateProfile.objects.get(user=user).lock_version == 2


def test_profile_validation_and_lock(client) -> None:  # type: ignore[no-untyped-def]
    client.get("/api/v1/candidate/profile/")
    bad_phone = client.patch("/api/v1/candidate/profile/", {"phone_e164": "12"}, format="json")
    assert bad_phone.status_code == 400
    bad_link = client.patch(
        "/api/v1/candidate/profile/", {"links": {"github": "javascript:alert(1)"}}, format="json"
    )
    assert bad_link.status_code == 400
    unknown = client.patch("/api/v1/candidate/profile/", {"gender": "x"}, format="json")
    assert unknown.status_code == 400
    stale = client.patch(
        "/api/v1/candidate/profile/", {"headline": "x", "lock_version": 99}, format="json"
    )
    assert stale.status_code == 409


def test_sections_crud_and_completeness(client) -> None:  # type: ignore[no-untyped-def]
    base = "/api/v1/candidate/profile"
    exp = client.post(
        f"{base}/experiences/",
        {"employer": "Acme", "title": "Developer", "start_date": "2022-01-01", "is_current": True},
        format="json",
    )
    assert exp.status_code == 201, exp.content
    assert exp.json()["source"] == "manual" and exp.json()["end_date"] is None
    bad = client.post(
        f"{base}/experiences/",
        {"employer": "A", "title": "B", "start_date": "2022-05-01", "end_date": "2021-01-01"},
        format="json",
    )
    assert bad.status_code == 400
    assert (
        client.post(
            f"{base}/educations/",
            {"institution": "UZ", "qualification_text": "BSc Computer Science"},
            format="json",
        ).status_code
        == 201
    )
    for name in ("Python", "Django", "SQL"):
        assert client.post(f"{base}/skills/", {"raw_name": name}, format="json").status_code == 201
    dup = client.post(f"{base}/skills/", {"raw_name": "python"}, format="json")
    assert dup.status_code == 409
    assert (
        client.post(
            f"{base}/languages/", {"language": "Shona", "proficiency": "native"}, format="json"
        ).status_code
        == 201
    )
    profile = client.get(f"{base}/").json()
    assert (
        profile["profile_completeness"] == 55
    )  # experience 20 + education 15 + skills 15 + lang 5
    exp_id = exp.json()["id"]
    assert (
        client.patch(
            f"{base}/experiences/{exp_id}/", {"title": "Senior Developer"}, format="json"
        ).json()["title"]
        == "Senior Developer"
    )
    assert client.delete(f"{base}/experiences/{exp_id}/").status_code == 204
    assert client.get(f"{base}/").json()["profile_completeness"] == 35


def test_candidates_never_see_each_others_sections(client) -> None:  # type: ignore[no-untyped-def]
    exp = client.post(
        "/api/v1/candidate/profile/experiences/",
        {"employer": "Acme", "title": "Developer", "start_date": "2022-01-01"},
        format="json",
    ).json()
    other = APIClient()
    other.force_login(UserFactory())
    url = f"/api/v1/candidate/profile/experiences/{exp['id']}/"
    assert other.get(url).status_code == 404
    assert other.patch(url, {"title": "Hacked"}, format="json").status_code == 404
    assert other.delete(url).status_code == 404
    assert other.get("/api/v1/candidate/profile/experiences/").json() == []


def test_anonymous_is_rejected() -> None:
    res = APIClient().get("/api/v1/candidate/profile/")
    assert res.status_code in (401, 403)
