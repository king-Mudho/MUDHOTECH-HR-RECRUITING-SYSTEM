"""P14-T01: platform admin console - overview, organisation detail, user search (minimal PII),
feature flags, dead letters, system health, taxonomy curation + publishing. Platform staff only;
support is read-only; every write audited."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import deadletters, flags
from apps.core.models import DeadLetter
from apps.organisations.tests.factories import make_org_with_team
from apps.taxonomy.models import QualificationLevel, Skill, TaxonomyVersion

pytestmark = pytest.mark.django_db


def client(role: str | None = None, user: Any = None) -> APIClient:
    c = APIClient()
    c.force_login(user or UserFactory(platform_role=role or PlatformRole.PLATFORM_ADMIN))
    return c


@pytest.fixture
def admin() -> APIClient:
    return client(PlatformRole.PLATFORM_ADMIN)


@pytest.fixture
def support() -> APIClient:
    return client(PlatformRole.PLATFORM_SUPPORT)


def test_overview_and_org_detail(admin: APIClient) -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    body = admin.get("/api/v1/platform/overview/").json()
    assert body["active_vacancies"] >= 1
    assert sum(d["count"] for d in body["applications_per_day"]) >= 1
    assert len(body["applications_per_day"]) == 14
    assert "dead_letters_open" in body["error_rates"]
    detail = admin.get(f"/api/v1/platform/organisations/{team.org.pk}/detail/").json()
    assert detail["usage"]["active_vacancies"] == 1
    assert detail["members_by_role"]["hr_manager"] == 1
    assert (
        admin.get(
            "/api/v1/platform/organisations/00000000-0000-0000-0000-000000000000/detail/"
        ).status_code
        == 404
    )


def test_users_search_minimal_pii(admin: APIClient) -> None:
    UserFactory(email="tendai.search@example.test", first_name="Tendai")
    assert admin.get("/api/v1/platform/users/", {"q": "te"}).json() == []  # 3 characters minimum
    rows = admin.get("/api/v1/platform/users/", {"q": "tendai.search"}).json()
    assert len(rows) == 1
    assert set(rows[0]) == {
        "id",
        "email",
        "name",
        "platform_role",
        "is_active",
        "memberships",
        "last_login",
    }


def test_flags(admin: APIClient, support: APIClient) -> None:
    team = make_org_with_team()
    listed = {f["key"]: f for f in admin.get("/api/v1/platform/flags/").json()}
    assert "ai.screening" in listed
    resp = admin.post(
        "/api/v1/platform/flags/",
        {"key": "jobs.ai_suggestions", "enabled": True, "organisation_id": str(team.org.pk)},
        format="json",
    )
    assert resp.status_code == 200
    assert flags.is_enabled("jobs.ai_suggestions", team.org) is True
    assert AuditEvent.objects.filter(action="platform.flag_set").exists()
    bad = admin.post("/api/v1/platform/flags/", {"key": "bad key!", "enabled": True}, format="json")
    assert bad.status_code == 400
    assert support.get("/api/v1/platform/flags/").status_code == 200
    denied = support.post("/api/v1/platform/flags/", {"key": "x.y", "enabled": True}, format="json")
    assert denied.status_code == 403


def test_dead_letters(admin: APIClient, support: APIClient, monkeypatch: Any) -> None:
    sent: list[Any] = []
    monkeypatch.setattr(deadletters, "_send", lambda n, a, k: sent.append(n))
    a = DeadLetter.objects.create(task_name="apps.core.tasks.ping", error="boom")
    b = DeadLetter.objects.create(task_name="apps.core.tasks.ping", error="bang")
    assert len(support.get("/api/v1/platform/dead-letters/").json()) == 2
    assert support.post(f"/api/v1/platform/dead-letters/{a.pk}/retry/").status_code == 403
    retried = admin.post(f"/api/v1/platform/dead-letters/{a.pk}/retry/")
    assert retried.status_code == 200 and retried.json()["resolved_at"]
    resolved = admin.post(
        f"/api/v1/platform/dead-letters/{b.pk}/resolve/",
        {"reason": "Object no longer exists"},
        format="json",
    )
    assert resolved.status_code == 200
    assert admin.get("/api/v1/platform/dead-letters/").json() == []
    assert len(admin.get("/api/v1/platform/dead-letters/", {"all": "true"}).json()) == 2


def test_system_health(admin: APIClient) -> None:
    body = admin.get("/api/v1/platform/system/").json()
    assert "database" in body["checks"] and "health" in body


def test_taxonomy_curation_and_publish(admin: APIClient, support: APIClient) -> None:
    TaxonomyVersion.objects.create(version="2026.11.0", checksum="x", published_at=None)
    created = admin.post(
        "/api/v1/platform/taxonomy/skills/",
        {"name": "Kotlin Multiplatform", "category": "software_it", "aliases": ["KMP"]},
        format="json",
    )
    assert created.status_code == 201, created.content
    skill_id = created.json()["id"]
    dup = admin.post(
        f"/api/v1/platform/taxonomy/skills/{skill_id}/aliases/", {"alias": "kmp"}, format="json"
    )
    assert dup.status_code == 409
    other = Skill.objects.create(
        canonical_name="Android", slug="android-test", category="software_it", organisation=None
    )
    rel = admin.post(
        "/api/v1/platform/taxonomy/relations/",
        {"from_skill": skill_id, "to_skill": str(other.pk), "relation": "related"},
        format="json",
    )
    assert rel.status_code == 201
    found = admin.get("/api/v1/platform/taxonomy/skills/", {"q": "kmp"}).json()
    assert found[0]["canonical_name"] == "Kotlin Multiplatform"
    assert found[0]["relations"][0]["to_skill_name"] == "Android"
    status = admin.get("/api/v1/platform/taxonomy/").json()
    assert status["unpublished_changes"] is True
    published = admin.post(
        "/api/v1/platform/taxonomy/", {"notes": "Add Kotlin Multiplatform"}, format="json"
    )
    assert published.status_code == 200
    body = published.json()
    assert body["unpublished_changes"] is False and body["current_version"].startswith("20")
    assert Skill.objects.get(pk=skill_id).taxonomy_version == body["current_version"]
    again = admin.post("/api/v1/platform/taxonomy/", {}, format="json")
    assert again.status_code == 409  # nothing changed since
    deactivated = admin.patch(
        f"/api/v1/platform/taxonomy/skills/{skill_id}/", {"is_active": False}, format="json"
    )
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert admin.get("/api/v1/platform/taxonomy/").json()["unpublished_changes"] is True
    level = QualificationLevel.objects.create(code="T-DIP", name="Diploma", rank=4, framework="ZW")
    q = admin.post(
        f"/api/v1/platform/taxonomy/qualifications/{level.pk}/aliases/",
        {"alias": "National Diploma (test)"},
        format="json",
    )
    assert q.status_code == 201
    assert (
        admin.delete(
            f"/api/v1/platform/taxonomy/qualification-aliases/{q.json()['id']}/"
        ).status_code
        == 204
    )
    assert (
        support.post(
            "/api/v1/platform/taxonomy/skills/",
            {"name": "X", "category": "software_it"},
            format="json",
        ).status_code
        == 403
    )
    assert AuditEvent.objects.filter(action="taxonomy.published").exists()


def test_org_staff_cannot_use_the_console() -> None:
    team = make_org_with_team()
    hr = client(user=team.admin)
    for url in (
        "/api/v1/platform/overview/",
        "/api/v1/platform/users/?q=abc",
        "/api/v1/platform/flags/",
        "/api/v1/platform/dead-letters/",
        "/api/v1/platform/system/",
        "/api/v1/platform/taxonomy/",
    ):
        assert hr.get(url).status_code == 403, url
