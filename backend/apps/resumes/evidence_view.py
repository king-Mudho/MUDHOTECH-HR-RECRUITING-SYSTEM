"""Evidence viewer data for the HR review page (P08-T06, docs/08 §3.3).

Returns each CV's extracted text page by page with the spans that support the criteria, so the
viewer can highlight evidence for PDFs and DOCX alike without rendering an untrusted file.

Masking keeps character offsets stable (every masked character becomes "•"), so highlight spans
stay valid:
* always: contact details, protected attributes and the personal/references sections (they are
  never evidence and reviewers do not need them);
* blind review (not revealed): the candidate's name wherever it appears; institution names too
  when the organisation masks them.
"""

from __future__ import annotations

import re
from typing import Any

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import EXCLUDED_SECTIONS, DocumentText, ExtractedClaim

from .models import ExtractedClaim as ClaimRow
from .models import ExtractionRun

MASK = "•"
PRIVATE_TYPES = ("contact", "protected")


def _mask(text: str, start: int, end: int) -> str:
    start, end = max(0, start), min(len(text), end)
    if end <= start:
        return text
    return text[:start] + MASK * (end - start) + text[end:]


def _mask_word(text: str, word: str) -> str:
    if len(word) < 2:
        return text
    return re.sub(re.escape(word), lambda m: MASK * len(m.group(0)), text, flags=re.IGNORECASE)


def _criteria_by_claim(app: Any) -> dict[str, list[str]]:
    from apps.screening.models import EvaluationEvidence

    if not app.current_evaluation_id or app.ai_band == "manual_review_requested":
        return {}
    out: dict[str, list[str]] = {}
    rows = EvaluationEvidence.objects.for_org(app.organisation_id).filter(
        criterion_result__evaluation_id=app.current_evaluation_id, claim__isnull=False
    )
    for claim_id, criterion_id in rows.values_list("claim_id", "criterion_result__criterion_id"):
        out.setdefault(str(claim_id), []).append(str(criterion_id))
    return out


def evidence_text(membership: Any, application_id: Any) -> dict[str, Any]:
    from apps.applications.ats import _visible
    from apps.applications.blind import BlindView

    app = _visible(membership, application_id)
    blind = BlindView(membership.user, app.organisation_id, [app.pk])
    hidden = blind.hidden(app.pk)
    mask_institutions = blind.masks_institutions(app.pk)
    snapshot = app.candidate_profile_snapshot or {}
    names = [str(snapshot.get(k) or "") for k in ("first_name", "last_name", "preferred_name")]
    criteria = _criteria_by_claim(app)
    runs = (
        ExtractionRun.objects.for_org(app.organisation_id)
        .filter(application=app, engine_version=ENGINE_VERSION, status__in=["succeeded", "partial"])
        .select_related("document", "text")
        .order_by("created_at")
    )
    documents = []
    for run in runs:
        text_row = getattr(run, "text", None)
        if text_row is None:
            continue
        doc = DocumentText.model_validate_json(text_row.payload)
        pages = {p.number: p.text for p in doc.pages}
        for section in text_row.sections or []:
            if section.get("kind") in {k.value for k in EXCLUDED_SECTIONS}:
                n = int(section.get("page") or 1)
                if n in pages:
                    pages[n] = _mask(pages[n], section["char_start"], section["char_end"])
        highlights = []
        institutions: set[str] = set()
        for row in (
            ClaimRow.objects.for_org(app.organisation_id).filter(run=run).order_by("ordinal")
        ):
            claim = ExtractedClaim.model_validate_json(row.payload)
            src = claim.source
            located = src.page in pages and src.char_start is not None and src.char_end is not None
            if row.claim_type in PRIVATE_TYPES or row.excluded_reason:
                if located:
                    pages[src.page] = _mask(pages[src.page], src.char_start, src.char_end)  # type: ignore[index, arg-type]
                continue
            if mask_institutions and claim.data.type == "education":
                institutions.add(getattr(claim.data, "institution", "") or "")
            if located:
                highlights.append(
                    {
                        "claim_id": str(row.pk),
                        "type": row.claim_type,
                        "page": src.page,
                        "start": src.char_start,
                        "end": src.char_end,
                        "criteria": criteria.get(str(row.pk), []),
                    }
                )
        if hidden:
            for n in pages:
                for word in names:
                    for part in word.split():
                        pages[n] = _mask_word(pages[n], part)
        for institution in institutions:
            for n in pages:
                pages[n] = _mask_word(pages[n], institution)
        documents.append(
            {
                "document_id": str(run.document_id),
                "filename": "CV" if hidden else run.document.original_filename,
                "mime": doc.mime,
                "original_available": (not hidden) and doc.mime == "application/pdf",
                "pages": [{"number": n, "text": pages[n]} for n in sorted(pages)],
                "highlights": highlights,
            }
        )
    return {
        "application_id": str(app.pk),
        "identity_hidden": hidden,
        "documents": documents,
    }
