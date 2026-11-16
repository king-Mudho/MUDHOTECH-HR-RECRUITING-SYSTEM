"""Phase 07 exit: 100 applications evaluated after extraction in <= 5 minutes (P07-T15).

Extraction runs once; its stored run and claims are copied to 99 more applications (extraction
throughput is the Phase 06 benchmark). Then each application goes through the full Django
screening path: build input, evaluate, explain, store versions/evidence, transition, outbox,
audit and quality counters. The time is printed for the benchmark report.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application
from apps.resumes.models import ExtractedClaim, ExtractionRun
from apps.screening import services
from apps.screening.models import Evaluation

pytestmark = [pytest.mark.django_db, pytest.mark.slow]
LIMIT_SECONDS = 300


def clone_evidence(source: Application, target: Application) -> None:
    for run in ExtractionRun.objects.for_org(source.organisation_id).filter(application=source):
        claims = list(ExtractedClaim.objects.for_org(source.organisation_id).filter(run=run))
        run.pk = None
        run.application = target
        run.save()
        for claim in claims:
            claim.pk = None
            claim.run = run
        ExtractedClaim.objects.bulk_create(claims)


def test_one_hundred_evaluations_within_five_minutes(read_app: Application, vacancy: Any) -> None:
    apps = [read_app]
    for _ in range(99):
        app = make_application(vacancy.job, UserFactory(), status=Status.PROCESSING)
        clone_evidence(read_app, app)
        apps.append(app)
    start = time.perf_counter()
    for app in apps:
        services.evaluate_application(app.pk)
    seconds = time.perf_counter() - start
    print(f"\n[P07 exit] 100 Django evaluations: {seconds:.1f} s")  # noqa: T201 - recorded in report
    assert Evaluation.objects.for_org(read_app.organisation_id).count() == 100
    assert (
        not Application.objects.for_org(read_app.organisation_id)
        .filter(status=Status.PROCESSING)
        .exists()
    )
    assert seconds <= LIMIT_SECONDS
