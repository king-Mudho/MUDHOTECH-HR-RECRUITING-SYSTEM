"""Rich-text sanitisation on save (P03-T09, EC-JOB-12): an XSS payload suite."""

from __future__ import annotations

import re

import pytest

from apps.jobs import services
from apps.jobs.tests.test_services import draft_job

pytestmark = pytest.mark.django_db

PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    '<a href="javascript:alert(1)">click</a>',
    '<a href="JaVaScRiPt:alert(1)">click</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">x</a>',
    '<a href="vbscript:msgbox(1)">x</a>',
    '<iframe src="https://evil.example"></iframe>',
    '<object data="x.swf"></object><embed src="x.swf">',
    '<p style="background:url(javascript:alert(1))">styled</p>',
    '<p onclick="alert(1)">click me</p>',
    "<style>body{display:none}</style>",
    '<form action="https://evil.example"><input name=password></form>',
    '<meta http-equiv="refresh" content="0;url=https://evil.example">',
    '<base href="https://evil.example/">',
    "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>",
    "<!--<script>alert(1)</script>-->",
    "<p>ok</p><scr<script>ipt>alert(1)</script>",
    "<details open ontoggle=alert(1)>",
    '<a href="https://example.com" target="_blank" onmouseover="alert(1)">link</a>',
]
DANGEROUS = re.compile(
    r"<\s*(script|img|svg|iframe|object|embed|style|form|input|meta|base|math|details)"
    r"|on[a-z]+\s*=|javascript:|vbscript:|data:text|style\s*=",
    re.IGNORECASE,
)


@pytest.mark.parametrize("payload", PAYLOADS)
@pytest.mark.parametrize("field", ["responsibilities_html", "requirements_html", "benefits_html"])
def test_payload_is_neutralised_on_save(team, field: str, payload: str) -> None:  # type: ignore[no-untyped-def]
    job = draft_job(team)
    services.update_job(job, actor=team.recruiter, data={field: payload}, lock_version=None)
    job.refresh_from_db()
    stored = getattr(job.current_version, field)
    assert not DANGEROUS.search(stored), stored


def test_allowed_markup_survives_and_links_get_rel(team) -> None:  # type: ignore[no-untyped-def]
    job = draft_job(team)
    html = (
        "<h2>About</h2><p><strong>Bold</strong> <em>it</em><br></p>"
        "<ul><li>a</li></ul><ol><li>b</li></ol><h3>x</h3><h4>y</h4>"
        '<a href="https://mudhotech.example/jobs">apply</a>'
    )
    services.update_job(job, actor=team.recruiter, data={"benefits_html": html}, lock_version=None)
    job.refresh_from_db()
    stored = job.current_version.benefits_html  # type: ignore[union-attr]
    for tag in ("<h2>", "<strong>", "<em>", "<br>", "<ul>", "<ol>", "<li>", "<h3>", "<h4>"):
        assert tag in stored
    assert 'rel="noopener nofollow ugc"' in stored
    assert 'href="https://mudhotech.example/jobs"' in stored


def test_h1_and_tables_are_stripped_but_text_kept(team) -> None:  # type: ignore[no-untyped-def]
    job = draft_job(team)
    services.update_job(
        job,
        actor=team.recruiter,
        data={"requirements_html": "<h1>Title</h1><table><tr><td>Cell</td></tr></table>"},
        lock_version=None,
    )
    job.refresh_from_db()
    stored = job.current_version.requirements_html  # type: ignore[union-attr]
    assert "<h1>" not in stored and "<table>" not in stored
    assert "Title" in stored and "Cell" in stored
