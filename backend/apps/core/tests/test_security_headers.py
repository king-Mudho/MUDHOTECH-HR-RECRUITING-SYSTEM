"""Security headers, CORS, admin gating and export safety (P09-T08, EC-PRV-08)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches

from apps.core.csv_safe import cell, row

pytestmark = pytest.mark.django_db
APPS = Path(__file__).resolve().parents[2]


def test_api_responses_carry_a_locked_down_csp() -> None:
    res = Client().get("/api/v1/jobs/")
    assert res["Content-Security-Policy"].startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in res["Content-Security-Policy"]
    assert res["X-Content-Type-Options"] == "nosniff"
    assert res["X-Frame-Options"] == "DENY"
    assert res["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=()" in res["Permissions-Policy"]


def test_cors_is_closed() -> None:
    """Same-origin only (ADR-004): no CORS headers for a foreign origin, preflight included."""
    res = Client().get("/api/v1/jobs/", HTTP_ORIGIN="https://evil.example")
    assert "Access-Control-Allow-Origin" not in res
    pre = Client().options(
        "/api/v1/auth/browser/v1/auth/login",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert "Access-Control-Allow-Origin" not in pre


@pytest.mark.parametrize(("enabled", "status"), [(False, 404), (True, 302)])
def test_django_admin_is_gated(enabled: bool, status: int) -> None:
    with override_settings(ENABLE_DJANGO_ADMIN=enabled):
        import importlib

        import config.urls

        clear_url_caches()
        importlib.reload(config.urls)
        try:
            assert Client().get("/django-admin/").status_code == status
        finally:
            clear_url_caches()
            importlib.reload(config.urls)


def test_formula_injection_is_neutralised() -> None:
    for payload in ("=HYPERLINK(1)", "+1+1", "-2", "@SUM(A1)", "\tx", "\rx"):
        assert cell(payload).startswith("'")
    assert cell("Rudo Moyo") == "Rudo Moyo" and cell(None) == ""
    assert row(["=1", 2]) == ["'=1", "2"]


def test_every_csv_writer_uses_the_safe_cell_helper() -> None:
    """EC-PRV-08 'used everywhere': a module that writes CSV must import ``csv_safe``."""
    offenders = []
    for path in APPS.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"csv\.(writer|DictWriter)\(", text) and "csv_safe" not in text:
            offenders.append(str(path.relative_to(APPS)))
    assert offenders == []
