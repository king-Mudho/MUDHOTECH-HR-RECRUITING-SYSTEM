"""HR applicants list with 5,000 applications (P10-T05, NFR-PERF-01: P95 < 400 ms).

In-process timing (Django + PostgreSQL, no network or proxy): the server-side share of the
latency budget. The Locust run (`loadtests/`) measures the same endpoint end to end.
"""

from __future__ import annotations

import statistics
import time
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.applications.models import Application, Status
from apps.applications.services import active_key_for
from apps.applications.tests.factories import published_job
from apps.core.time import now
from apps.organisations.tests.factories import make_org_with_team

pytestmark = [pytest.mark.django_db, pytest.mark.slow]
COUNT = 5000
BUDGET_MS = 400


def seed(job: Any) -> None:
    stamp = int(time.time())
    users = User.objects.bulk_create(
        [
            User(email=f"scale{stamp}-{i}@example.test", first_name=f"Cand{i}", last_name="Scale")
            for i in range(COUNT)
        ],
        batch_size=1000,
    )
    bands = ["recommended_for_review", "review_needed", "lower_match", "eligibility_review"]
    apps = []
    for i, user in enumerate(users):
        app = Application(
            organisation_id=job.organisation_id,
            job=job,
            job_version_id=job.published_version_id,
            candidate_user=user,
            status=Status.UNDER_REVIEW,
            reference=f"SCALE-{stamp}-{i:05d}",
            submitted_at=now(),
            score=Decimal(i % 100),
            coverage=Decimal("0.80"),
            ai_band=bands[i % 4],
            essentials_met=3,
            essentials_unknown=i % 2,
            essentials_not_evidenced=0,
            tags=["python"] if i % 3 == 0 else [],
            candidate_profile_snapshot={"first_name": f"Cand{i}", "last_name": "Scale"},
        )
        app.active_key = active_key_for(app)
        apps.append(app)
    Application.objects.unscoped().bulk_create(apps, batch_size=1000)


def p95(times: list[float]) -> float:
    return statistics.quantiles(times, n=20)[-1] * 1000


def test_applicants_list_p95_with_5000_applications() -> None:
    team = make_org_with_team()
    job = published_job(organisation=team.org)
    seed(job)
    c = APIClient()
    c.force_login(team.hr_manager)
    c.credentials(HTTP_X_ORG_ID=str(team.org.pk))
    base = f"/api/v1/hr/jobs/{job.pk}/applications/"
    views = {
        "default (score desc)": "",
        "band filter": "?band=recommended_for_review",
        "essentials unknown + tag": "?essentials=unknown&tag=python",
        "oldest first": "?ordering=submitted_at",
        "search": "?search=Cand42",
    }
    results = {}
    for name, query in views.items():
        assert c.get(base + query).status_code == 200  # warm-up
        times = []
        for _ in range(30):
            start = time.perf_counter()
            res = c.get(base + query)
            times.append(time.perf_counter() - start)
            assert res.status_code == 200
        results[name] = p95(times)
    first = c.get(base).json()
    assert first["count"] == COUNT and len(first["results"]) == 50
    summary = ", ".join(f"{k}: {v:.0f} ms" for k, v in results.items())
    print(f"\n[P10-T05] applicants list, {COUNT} applications, P95 - {summary}")  # noqa: T201
    assert max(results.values()) < BUDGET_MS, results
