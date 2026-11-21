"""Public job board response cache (P10-T05, EC-OPS-10 traffic spikes).

Served from cache, invalidated by any change.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.jobs import services
from apps.jobs.tests.test_services import published_job

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_on(settings: Any) -> Any:
    settings.PUBLIC_API_CACHE_SECONDS = 30
    cache.clear()
    yield
    cache.clear()


def count(client: APIClient, url: str) -> tuple[int, Any]:
    with CaptureQueriesContext(connection) as ctx:
        body = client.get(url).json()
    return len(ctx.captured_queries), body


def test_anonymous_list_and_detail_come_from_the_cache(team: Any) -> None:
    job = published_job(team)
    anon = APIClient()
    first, body = count(anon, "/api/v1/jobs/")
    again, cached = count(anon, "/api/v1/jobs/")
    assert body["count"] == 1 and cached == body
    assert first > 0 and again == 0  # no database work on a hit
    _, detail = count(anon, f"/api/v1/jobs/{job.slug}/")
    hit, detail_again = count(anon, f"/api/v1/jobs/{job.slug}/")
    assert hit == 0 and detail_again == detail
    # different filters are different entries
    assert anon.get("/api/v1/jobs/?q=nothing-matches").json()["count"] == 0


def test_closing_a_vacancy_shows_at_once(team: Any) -> None:
    job = published_job(team)
    anon = APIClient()
    assert anon.get("/api/v1/jobs/").json()["count"] == 1
    services.close(job, actor=team.hr_manager, reason="Filled the position")
    assert anon.get("/api/v1/jobs/").json()["count"] == 0  # generation bumped on save
    assert anon.get(f"/api/v1/jobs/{job.slug}/").status_code in (200, 410)


def test_signed_in_users_bypass_the_cache(team: Any) -> None:
    published_job(team)
    staff = APIClient()
    staff.force_login(team.hr_manager)
    staff.get("/api/v1/jobs/")
    queries, _ = count(staff, "/api/v1/jobs/")
    assert queries > 0
