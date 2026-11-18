"""Work lost with a killed worker is re-dispatched (P10-T07, EC-OPS-04)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from apps.applications.models import Application, Status
from apps.core.time import now
from apps.resumes import recovery, services
from apps.resumes.models import ExtractionRun, RunStatus
from apps.resumes.tests.test_extraction_flow import attach, submitted_app

pytestmark = pytest.mark.django_db


def test_a_run_left_running_by_a_dead_worker_is_finished_once(act: Any) -> None:
    app = submitted_app()
    attach(app)
    services.start(app.pk)  # extraction is queued on commit, but the worker "dies": it never runs
    run = ExtractionRun.objects.unscoped().get(application=app)
    ExtractionRun.objects.unscoped().filter(pk=run.pk).update(
        status=RunStatus.RUNNING, started_at=now() - timedelta(minutes=30)
    )
    assert act(recovery.recover) == {"extraction": 1}
    run.refresh_from_db()
    assert run.usable  # extracted by the recovery dispatch
    assert ExtractionRun.objects.unscoped().filter(application=app).count() == 1  # no duplicate
    assert "extraction" not in act(recovery.recover)  # nothing stuck any more


def test_a_retry_replaces_partial_output() -> None:
    """Defensive: leftovers of an unfinished run never collide with the retry."""
    from apps.resumes.models import DocumentText

    app = submitted_app()
    attach(app)
    services.start(app.pk)
    run = ExtractionRun.objects.unscoped().get(application=app)
    Application.objects.unscoped().filter(pk=app.pk).update(status=Status.PROCESSING)
    DocumentText.objects.create(
        organisation_id=run.organisation_id, run=run, payload="{}", sections=[], char_count=0
    )
    services.extract(run.document_id, app.pk)
    run.refresh_from_db()
    assert run.usable and DocumentText.objects.unscoped().filter(run=run).count() == 1


def test_recent_work_is_left_alone(act: Any) -> None:
    app = submitted_app()
    attach(app)
    act(services.start, app.pk)
    ExtractionRun.objects.unscoped().filter(application=app).update(
        status=RunStatus.RUNNING, started_at=now() - timedelta(minutes=2)
    )
    Application.objects.unscoped().filter(pk=app.pk).update(status=Status.PROCESSING)
    assert act(recovery.recover) == {}  # may still be running on a live worker


def test_finished_but_never_screened_is_screened(act: Any, settings: Any) -> None:
    settings.SCREENING_AUTOSTART = True
    app = submitted_app()
    attach(app)
    settings.SCREENING_AUTOSTART = False  # extraction finishes, screening task "lost"
    act(services.start, app.pk)
    settings.SCREENING_AUTOSTART = True
    app.refresh_from_db()
    assert app.status == Status.PROCESSING and app.current_evaluation_id is None
    Application.objects.unscoped().filter(pk=app.pk).update(
        updated_at=now() - timedelta(minutes=30)
    )
    counts = act(recovery.recover)
    assert counts.get("screening") == 1
