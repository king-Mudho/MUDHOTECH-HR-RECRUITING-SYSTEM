"""🌐 Public job board APIs (P03-T10): search, filters, visibility, closed/410, feeds."""

from __future__ import annotations

from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.core.time import now
from apps.jobs import services
from apps.jobs.models import Job, JobSlugRedirect, JobStatus
from apps.jobs.tests.test_services import QUESTIONS, published_job, team  # noqa: F401
from apps.organisations.models import Organisation

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _live(team, **header):  # type: ignore[no-untyped-def]  # noqa: F811
    job = published_job(team)
    if header:
        Job.objects.for_org(team.org).filter(pk=job.pk).update(**header)
        job.refresh_from_db()
        from apps.jobs.search import update_search_vector

        update_search_vector(job)
    return job


def test_list_search_filters_and_ordering(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dev = _live(team, title="Python Developer", workplace_type="remote")
    nurse = _live(team, title="Registered Nurse", employment_type="contract")
    res = client.get("/api/v1/jobs/")
    assert res.status_code == 200 and res.json()["count"] == 2
    item = res.json()["results"][0]
    assert {"slug", "organisation", "locations", "closes_at", "timezone", "summary"} <= set(item)
    assert "justification" not in str(item)
    assert [r["id"] for r in client.get("/api/v1/jobs/?q=nurse").json()["results"]] == [
        str(nurse.pk)
    ]
    assert client.get("/api/v1/jobs/?q=python developer").json()["results"][0]["id"] == str(dev.pk)
    remote = client.get("/api/v1/jobs/?workplace_type=remote,hybrid").json()["results"]
    assert [r["id"] for r in remote] == [str(dev.pk)]
    contract = client.get("/api/v1/jobs/?employment_type=contract").json()["results"]
    assert [r["id"] for r in contract] == [str(nurse.pk)]
    assert client.get(f"/api/v1/jobs/?org={team.org.slug}").json()["count"] == 2
    assert client.get("/api/v1/jobs/?org=nope").json()["count"] == 0
    city = dev.locations.first().city  # type: ignore[union-attr]
    assert client.get(f"/api/v1/jobs/?location={city}").json()["count"] == 2
    closing = client.get("/api/v1/jobs/?ordering=closing").json()["results"]
    assert len(closing) == 2
    assert client.get("/api/v1/jobs/?page_size=1").json()["next"] is not None


def test_list_hides_drafts_unlisted_paused_closed_and_suspended_orgs(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    from apps.jobs.tests.test_services import approved_job, draft_job

    draft_job(team)
    approved_job(team)
    unlisted = _live(team, visibility="unlisted")
    paused = _live(team)
    services.pause(paused, actor=team.hr_manager)
    closed = _live(team)
    services.close(closed, actor=team.hr_manager, reason="Position filled")
    visible = _live(team)
    ids = [r["id"] for r in client.get("/api/v1/jobs/").json()["results"]]
    assert ids == [str(visible.pk)]
    # unlisted is reachable by link
    assert client.get(f"/api/v1/jobs/{unlisted.slug}/").status_code == 200
    Organisation.objects.filter(pk=team.org.pk).update(status=Organisation.Status.SUSPENDED)
    assert client.get("/api/v1/jobs/").json()["count"] == 0
    assert client.get(f"/api/v1/jobs/{visible.slug}/").status_code == 404


def test_detail_by_slug_or_id_with_criteria_split(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = _live(team)
    by_slug = client.get(f"/api/v1/jobs/{job.slug}/")
    by_id = client.get(f"/api/v1/jobs/{job.pk}/")
    assert by_slug.status_code == by_id.status_code == 200
    body = by_slug.json()
    assert body["accepts_applications"] is True and body["is_closed"] is False
    assert [c["title"] for c in body["essential_criteria"]] == ["Python"]
    assert [c["title"] for c in body["preferred_criteria"]] == ["2 years web development"]
    assert "justification" not in str(body["essential_criteria"])
    assert body["required_documents"] == ["cv"] and body["version"] == 1
    assert client.get("/api/v1/jobs/does-not-exist/").status_code == 404


def test_draft_job_is_404(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    from apps.jobs.tests.test_services import draft_job

    job = draft_job(team)
    assert client.get(f"/api/v1/jobs/{job.slug}/").status_code == 404
    assert client.get(f"/api/v1/jobs/{job.slug}/questions/").status_code == 404


def test_closed_job_200_with_flag_then_410_after_90_days(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = _live(team)
    services.close(job, actor=team.hr_manager, reason="Position filled")
    res = client.get(f"/api/v1/jobs/{job.slug}/")
    assert res.status_code == 200
    assert res.json()["is_closed"] is True and res.json()["accepts_applications"] is False
    assert client.get(f"/api/v1/jobs/{job.slug}/questions/").status_code == 410
    Job.objects.for_org(team.org).filter(pk=job.pk).update(closed_at=now() - timedelta(days=91))
    res = client.get(f"/api/v1/jobs/{job.slug}/")
    assert res.status_code == 410 and res.json()["error"]["code"] == "gone"


def test_old_slug_redirects(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """EC-JOB-13."""
    job = _live(team)
    JobSlugRedirect.objects.create(old_slug="old-title-acme", job=job)
    res = client.get("/api/v1/jobs/old-title-acme/")
    assert res.status_code == 301 and res.json()["redirect"] == job.slug


def test_questions_hide_scoring_and_knockout(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    from apps.jobs.tests.test_services import draft_job

    job = draft_job(team)
    services.set_questionnaire(
        job,
        actor=team.recruiter,
        questions=[
            *QUESTIONS,
            {
                "key": "licence",
                "type": "yes_no",
                "prompt": "Do you hold a valid driver's licence?",
                "is_knockout": True,
                "knockout_expected": "yes",
            },
        ],
    )
    services.submit_for_approval(job, actor=team.recruiter)
    services.approve(job, actor=team.hr_manager)
    services.publish(job, actor=team.hr_manager)
    res = client.get(f"/api/v1/jobs/{job.slug}/questions/")
    assert res.status_code == 200
    body = res.json()
    assert [q["key"] for q in body] == ["portfolio", "licence"]
    text = str(body)
    assert "scoring" not in text and "knockout" not in text and "expected" not in text


def test_paused_job_detail_visible_but_not_accepting(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = _live(team)
    services.pause(job, actor=team.hr_manager)
    body = client.get(f"/api/v1/jobs/{job.slug}/").json()
    assert body["status"] == JobStatus.PAUSED and body["accepts_applications"] is False


def test_salary_only_when_disclosed(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    hidden = _live(team, salary_min=800, salary_max=1200)
    shown = _live(
        team, salary_min=800, salary_max=1200, salary_disclosed=True, salary_currency="ZWG"
    )
    assert client.get(f"/api/v1/jobs/{hidden.slug}/").json()["salary"] is None
    salary = client.get(f"/api/v1/jobs/{shown.slug}/").json()["salary"]
    assert salary["currency"] == "ZWG" and salary["min"] == "800.00"


def test_company_profile_lists_open_jobs(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = _live(team)
    closed = _live(team)
    services.close(closed, actor=team.hr_manager, reason="Position filled")
    body = client.get(f"/api/v1/companies/{team.org.slug}/").json()
    assert [j["id"] for j in body["open_jobs"]] == [str(job.pk)]


def test_sitemap_and_feeds(client, team) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    job = _live(team, title="Data <Analyst> & Co")
    sitemap = client.get("/api/v1/sitemap.xml")
    assert sitemap.status_code == 200 and sitemap["Content-Type"].startswith("application/xml")
    xml = sitemap.content.decode()
    assert f"/jobs/{job.slug}</loc>" in xml and f"/companies/{team.org.slug}</loc>" in xml
    rss = client.get("/api/v1/jobs/feed.rss")
    assert rss.status_code == 200 and "Data &lt;Analyst&gt; &amp; Co" in rss.content.decode()
    feed = client.get("/api/v1/jobs/feed.json").json()
    assert feed["version"].startswith("https://jsonfeed.org") and feed["items"][0]["id"] == str(
        job.pk
    )
