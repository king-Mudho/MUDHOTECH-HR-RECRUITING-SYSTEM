"""Offer letter PDF (P12-T04).

Rendered with PyMuPDF's Story (the HTML subset already used for decision reconstructions,
``apps/applications/reconstruct_pdf.py``) instead of adding WeasyPrint; every value is HTML-escaped
(names and conditions are user text). The letter states the terms and how to answer; it never
mentions screening, scores or AI.
"""

from __future__ import annotations

import io
from decimal import Decimal
from html import escape
from typing import Any

import pymupdf

from apps.interviews.scheduling import format_when
from apps.jobs.models import EmploymentType, SalaryPeriod

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.4; }
h1 { font-size: 16pt; margin-bottom: 4pt; }
.org { font-size: 12pt; font-weight: bold; }
.muted { color: #555; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
td { border: 0.5pt solid #bbb; padding: 4pt; vertical-align: top; }
td.k { width: 32%; font-weight: bold; }
"""


def money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _lines(text: str) -> str:
    return "<br/>".join(escape(line) for line in text.strip().splitlines()) or "None."


def html(offer: Any) -> str:
    app = offer.application
    org = app.organisation
    snap = app.candidate_profile_snapshot or {}
    name = " ".join(x for x in (snap.get("first_name"), snap.get("last_name")) if x) or (
        app.candidate_user.full_name or "Candidate"
    )
    period = SalaryPeriod(offer.period).label
    rows = [
        ("Position", app.job.title),
        ("Contract", EmploymentType(offer.contract_type).label),
        ("Remuneration", f"{money(offer.salary_amount, offer.currency)} {period}"),
        ("Start date", offer.start_date.strftime("%d %B %Y")),
        ("Reference", app.reference),
    ]
    table = "".join(
        f'<tr><td class="k">{escape(k)}</td><td>{escape(str(v))}</td></tr>' for k, v in rows
    )
    deadline = format_when(offer.expires_at, org.default_timezone or "Africa/Harare")
    return (
        f'<p class="org">{escape(org.name)}</p>'
        f"<h1>Offer of employment</h1>"
        f"<p>Dear {escape(name)},</p>"
        f"<p>We are pleased to offer you the position of <b>{escape(app.job.title)}</b> with "
        f"{escape(org.name)} on the terms below.</p>"
        f"<table>{table}</table>"
        f"<p><b>Conditions</b><br/>{_lines(offer.conditions)}</p>"
        f"<p>This offer is open until <b>{escape(deadline)}</b>. To accept or decline it, "
        f"sign in to "
        f"your account and open the application; acceptance is recorded electronically with your "
        f"typed name and the time.</p>"
        f"<p>Yours sincerely,<br/>{escape(org.name)}</p>"
        '<p class="muted">Issued through MUDHOTECH HR RECRUITING SYSTEM. '
        "This letter is confidential "
        f"to the addressee.</p>"
    )


def render(offer: Any) -> bytes:
    story = pymupdf.Story(html=html(offer), user_css=CSS)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page = pymupdf.paper_rect("a4")
    area = pymupdf.Rect(page.x0 + 54, page.y0 + 54, page.x1 - 54, page.y1 - 54)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()
