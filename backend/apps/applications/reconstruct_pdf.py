"""PDF rendering of a reconstruction bundle (P08-T11) with PyMuPDF's Story (HTML subset).

Every value is HTML-escaped: names, reasons and snippets are untrusted text.
"""

from __future__ import annotations

import io
from html import escape
from typing import Any

import pymupdf

CSS = """
body { font-family: sans-serif; font-size: 9pt; }
h1 { font-size: 15pt; } h2 { font-size: 11pt; margin-top: 10pt; }
table { border-collapse: collapse; width: 100%; }
td, th { border: 0.5pt solid #999; padding: 2pt; text-align: left; vertical-align: top; }
.note { color: #555; }
"""


def _v(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return escape(str(value))


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return '<p class="note">None.</p>'
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_v(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def html(b: dict[str, Any]) -> str:
    a, job, rubric = b["application"], b["job"], b["rubric"]
    parts = [
        "<h1>Decision reconstruction</h1>",
        f'<p class="note">Generated for {_v(b["generated_for"])}. '
        "AI outputs are suggestions; every consequential decision below was made by a person."
        "</p>",
        "<h2>Application</h2>",
        _table(
            ["Reference", "Candidate", "Status", "Submitted", "Objected to automation"],
            [
                [
                    a["reference"],
                    a["candidate"],
                    a["status"],
                    a["submitted_at"],
                    "yes" if a["objects_to_automated_processing"] else "no",
                ]
            ],
        ),
        "<h2>Vacancy and rubric</h2>",
        f"<p>{_v(job['title'])} — version {_v(job['version'])}; rubric version "
        f"{_v(rubric['version'])} ({_v(rubric['status'])}).</p>",
        _table(
            ["Category", "Weight"],
            [[c.get("label") or c.get("key"), c.get("weight")] for c in rubric["categories"]],
        ),
        _table(
            ["Criterion", "Type", "Importance", "Category"],
            [[c["title"], c["type"], c["importance"], c["category"]] for c in rubric["criteria"]],
        ),
    ]
    for ev in b["evaluations"]:
        parts += [
            f"<h2>Evaluation version {_v(ev['version'])} ({_v(ev['status'])})</h2>",
            f"<p>Trigger {_v(ev['trigger'])}; band {_v(ev['band'])}; score "
            f"{_v(ev['total_score'])}; coverage {_v(ev['coverage'])}; engine "
            f"{_v(ev['engine_version'])}; thresholds {_v(ev['config_version'])}; models "
            f"{_v(', '.join(f'{k}: {v}' for k, v in (ev['model_ids'] or {}).items()))}; "
            f"input {_v(ev['input_hash'][:12])}.</p>",
            _table(
                ["Criterion", "Score", "Evidence", "Method", "Sources"],
                [
                    [
                        r["title"],
                        r["score"],
                        r["evidence_status"],
                        r["match_method"],
                        "; ".join(
                            f"p.{e['page']}" + (f" “{e['snippet']}”" if e["snippet"] else "")
                            for e in r["evidence"]
                        ),
                    ]
                    for r in ev["criteria"]
                ],
            ),
        ]
    parts += [
        "<h2>Status history</h2>",
        _table(
            ["When", "From", "To", "By", "Reason"],
            [
                [
                    e["at"],
                    e["from_status"],
                    e["to_status"],
                    e["actor"] or e["actor_type"],
                    e["reason_text"] or e["reason_code"],
                ]
                for e in b["status_events"]
            ],
        ),
        "<h2>Shortlist decisions</h2>",
        _table(
            ["Decision", "Reason", "AI band then", "Override", "Decided by", "Approved", "Applied"],
            [
                [
                    d["decision"],
                    d["reason_text"] or d["reason_code"],
                    d["ai_band_at_decision"],
                    "yes" if d["override"] else "no",
                    d["decided_by"],
                    d["approved_at"],
                    d["applied_at"] or d["apply_note"],
                ]
                for d in b["shortlist_decisions"]
            ],
        ),
        "<h2>Claim verifications</h2>",
        _table(
            ["Claim", "Decision", "By", "When"],
            [[v["claim_id"], v["decision"], v["verifier"], v["at"]] for v in b["verifications"]],
        ),
        "<h2>Access</h2>",
        _table(
            ["What", "By", "Reason", "When"],
            [[x["kind"], x["by"], x["reason"], x["at"]] for x in b["access"]],
        ),
        "<h2>Notifications</h2>",
        _table(
            ["Kind", "Channel", "Status", "Scheduled", "Sent"],
            [
                [n["key"], n["channel"], n["status"], n["scheduled_for"], n["sent_at"]]
                for n in b["notifications"]
            ],
        ),
    ]
    return "<body>" + "".join(parts) + "</body>"


def render(bundle: dict[str, Any]) -> bytes:
    story = pymupdf.Story(html=html(bundle), user_css=CSS)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page = pymupdf.paper_rect("a4")
    area = pymupdf.Rect(page.x0 + 36, page.y0 + 36, page.x1 - 36, page.y1 - 36)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()
