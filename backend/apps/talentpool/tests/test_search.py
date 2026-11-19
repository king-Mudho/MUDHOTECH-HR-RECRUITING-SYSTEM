"""P13-T02: HR talent search over consented profiles only, tags and invitations; no CV ever
crosses to another employer (M18 AC)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.applications.tests.factories import make_application, published_job
from apps.candidates.models import CandidateProfile, CandidateSkill, Education, Experience
from apps.jobs.models import Job, JobStatus
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.talentpool import services
from apps.talentpool.models import TalentPoolInvite

pytestmark = pytest.mark.django_db


def staff(user: Any, org: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def person(job: Job, *, name: str, headline: str, skills: list[str], title: str) -> Any:
    user = UserFactory(first_name=name, last_name="Synthetic")
    profile = CandidateProfile.objects.create(user=user, headline=headline, city="Harare")
    for i, skill in enumerate(skills):
        CandidateSkill.objects.create(profile=profile, raw_name=skill, order=i)
    Experience.objects.create(
        profile=profile, employer="Acme", title=title, start_date=date(2021, 1, 1), is_current=True
    )
    Education.objects.create(
        profile=profile, institution="UZ", qualification_text="BSc Computer Science"
    )
    make_application(job, user, status=Status.UNDER_REVIEW)
    return user


@pytest.fixture
def world() -> dict[str, Any]:
    team, other = make_org_with_team(), make_org_with_team()
    job = published_job(organisation=team.org)
    dev = person(
        job, name="Tatenda", headline="Python developer", skills=["Python", "Django"], title="Dev"
    )
    analyst = person(
        job, name="Nyasha", headline="Data analyst", skills=["SQL", "Excel"], title="Analyst"
    )
    never = person(job, name="Farai", headline="Python engineer", skills=["Python"], title="Eng")
    for user in (dev, analyst):
        services.join(user, team.org.pk)
    # the same developer also applied to and joined another employer's pool
    make_application(published_job(organisation=other.org), dev, status=Status.SUBMITTED)
    services.join(dev, other.org.pk)
    return {
        "team": team,
        "other": other,
        "job": job,
        "dev": dev,
        "analyst": analyst,
        "never": never,
    }


def names(resp: Any) -> list[str]:
    assert resp.status_code == 200, resp.content
    return sorted(r["name"] for r in resp.json()["results"])


def test_search_covers_consented_members_only(world: dict[str, Any]) -> None:
    hr = staff(world["team"].hr_manager, world["team"].org)
    assert names(hr.get("/api/v1/hr/talent-pool/")) == ["Nyasha Synthetic", "Tatenda Synthetic"]
    # FTS: Farai matches "python" but never opted in
    assert names(hr.get("/api/v1/hr/talent-pool/", {"q": "python"})) == ["Tatenda Synthetic"]
    assert names(hr.get("/api/v1/hr/talent-pool/", {"skill": "sql"})) == ["Nyasha Synthetic"]
    assert names(hr.get("/api/v1/hr/talent-pool/", {"skill": ["Python", "SQL"]})) == []
    services.leave(world["analyst"], world["team"].org.pk)
    assert names(hr.get("/api/v1/hr/talent-pool/")) == ["Tatenda Synthetic"]


def test_results_never_include_documents_or_other_employers(world: dict[str, Any]) -> None:
    other = staff(world["other"].hr_manager, world["other"].org)
    rows = other.get("/api/v1/hr/talent-pool/").json()["results"]
    assert [r["name"] for r in rows] == ["Tatenda Synthetic"]
    row = rows[0]
    assert set(row) == {
        "id",
        "name",
        "headline",
        "city",
        "skills",
        "qualifications",
        "latest_title",
        "tags",
        "joined_at",
        "expires_at",
        "latest_application",
        "invited_job_ids",
    }
    # the linked application is this employer's own, not the first employer's
    assert row["latest_application"]["job_title"] != world["job"].title
    mine = services.searchable(world["team"].org.pk).get(candidate_user=world["dev"])
    assert other.get(f"/api/v1/hr/talent-pool/{mine.pk}/").status_code == 404


def test_tags_and_invite(world: dict[str, Any]) -> None:
    team = world["team"]
    hr = staff(team.hr_manager, team.org)
    entry = services.searchable(team.org.pk).get(candidate_user=world["dev"])
    tagged = hr.patch(
        f"/api/v1/hr/talent-pool/{entry.pk}/", {"tags": ["Backend", " Backend ", ""]}, format="json"
    )
    assert tagged.status_code == 200 and tagged.json()["tags"] == ["Backend"]
    assert names(hr.get("/api/v1/hr/talent-pool/", {"tag": "Backend"})) == ["Tatenda Synthetic"]
    new_job = published_job(organisation=team.org)
    url = f"/api/v1/hr/talent-pool/{entry.pk}/invite/"
    sent = hr.post(url, {"job_id": str(new_job.pk)}, format="json")
    assert sent.status_code == 201
    assert Notification.objects.filter(
        recipient_user=world["dev"], key="talent_pool_invitation"
    ).exists()
    again = hr.post(url, {"job_id": str(new_job.pk)}, format="json")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_invited"
    applied = hr.post(url, {"job_id": str(world["job"].pk)}, format="json")
    assert applied.json()["error"]["code"] == "already_applied"
    Job.objects.for_org(team.org).filter(pk=new_job.pk).update(status=JobStatus.CLOSED)
    closed = published_job(organisation=team.org)
    Job.objects.for_org(team.org).filter(pk=closed.pk).update(status=JobStatus.CLOSED)
    assert hr.post(url, {"job_id": str(closed.pk)}, format="json").status_code == 409
    foreign_job = published_job(organisation=world["other"].org)
    assert hr.post(url, {"job_id": str(foreign_job.pk)}, format="json").status_code == 404
    assert TalentPoolInvite.objects.for_org(team.org).count() == 1


def test_withdrawn_member_cannot_be_invited_or_viewed(world: dict[str, Any]) -> None:
    team = world["team"]
    hr = staff(team.hr_manager, team.org)
    entry = services.searchable(team.org.pk).get(candidate_user=world["analyst"])
    services.leave(world["analyst"], team.org.pk)
    assert hr.get(f"/api/v1/hr/talent-pool/{entry.pk}/").status_code == 404
    job = published_job(organisation=team.org)
    resp = hr.post(
        f"/api/v1/hr/talent-pool/{entry.pk}/invite/", {"job_id": str(job.pk)}, format="json"
    )
    assert resp.status_code == 404
