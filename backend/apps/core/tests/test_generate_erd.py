"""P16-T04: the ER diagram is generated from the models (never hand-maintained)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from django.core.management import call_command


def test_generate_erd_covers_domain_apps(tmp_path: Path) -> None:
    out = tmp_path / "ERD.md"
    call_command("generate_erd", out=str(out), stdout=StringIO())
    text = out.read_text(encoding="utf-8")
    for entity in ("APPLICATIONS_APPLICATION", "BILLING_INVOICE", "INTEGRATIONS_WEBHOOKENDPOINT"):
        assert entity in text
    assert "erDiagram" in text and "CORE_TESTAPP" not in text
    assert '}o--||' in text  # relations are drawn
