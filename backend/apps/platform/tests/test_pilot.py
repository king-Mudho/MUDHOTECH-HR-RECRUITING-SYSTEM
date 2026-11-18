"""Pilot benchmark command (P10-T08): every submission is accounted for."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.applications.models import Application
from apps.platform import pilot
from apps.platform.demo_seed import seed as seed_demo

# real commits: the pipeline dispatches work from on_commit callbacks
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]
PASSWORD = "Synthetic-Demo-Seed-2026"  # pragma: allowlist secret - synthetic test password


def test_pilot_accounts_for_every_application(s3: Any, settings: Any, tmp_path: Path) -> None:
    settings.RESUMES_AUTOSTART = True
    settings.SCREENING_AUTOSTART = True
    seed_demo(PASSWORD)
    out = tmp_path / "PILOT.md"
    result, acc, text = pilot.run(6, PASSWORD, inline=True, timeout=300, out=out)
    assert acc["submitted"] == acc["records"] == 6 and acc["missing"] == []
    assert not result.timed_out
    waiting = Application.objects.unscoped().filter(job_id=result.job_id, status__in=pilot.WAITING)
    assert waiting.count() == 0  # each one is under review or waits in processing_error for HR
    assert sum(acc["statuses"].values()) == 6
    assert "**Every application accounted for** | **yes**" in text
    assert out.read_text(encoding="utf-8") == text
    # a fair mix: the first six CVs come from different roles
    assert len({c["role"] for c in pilot.corpus(5)}) == 5
