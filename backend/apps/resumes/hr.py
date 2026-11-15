"""HR extraction panel and "Retry processing" (P06-T14).

Staff see what was read from each CV with the evidence (snippet + page), flags in plain words
and the candidate's corrections. Protected details are never shown - not even which kinds were
present - only how many items were set aside. Visibility follows the HR application rules
(``applications_visible_to``: role, job access, no drafts).
"""

from __future__ import annotations

import json
from typing import Any

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import ExtractedClaim
from apps.applications.models import Application, Status
from apps.core.exceptions import ConflictError

from .candidate import display
from .models import ExtractedClaim as ClaimRow
from .models import ExtractionRun, RunStatus


def _visible(membership: Any, application_id: Any) -> Application:
    from apps.applications.ats import _visible as visible

    return visible(membership, application_id)


def confidence_label(value: float) -> str:
    return "high" if value >= 0.8 else "medium" if value >= 0.55 else "low"


def hr_view(membership: Any, application_id: Any) -> dict[str, Any]:
    from .services import objected

    app = _visible(membership, application_id)
    runs = list(
        ExtractionRun.objects.for_org(app.organisation_id)
        .filter(application=app, engine_version=ENGINE_VERSION)
        .select_related("document")
        .order_by("created_at")
    )
    out = []
    for run in runs:
        rows = list(
            ClaimRow.objects.for_org(app.organisation_id)
            .filter(run=run)
            .prefetch_related("corrections")
            .order_by("ordinal")
        )
        claims, set_aside = [], 0
        for row in rows:
            if row.claim_type in ("contact", "protected") or row.excluded_reason:
                set_aside += 1
                continue
            claim = ExtractedClaim.model_validate_json(row.payload)
            shown = display(claim)
            claims.append(
                {
                    **shown,
                    "id": row.pk,
                    "index": row.ordinal,
                    "section": row.section,
                    "method": row.method,
                    "confidence": confidence_label(row.confidence),
                    "inferred": row.evidence == "inferred",
                    "corrections": [
                        {
                            "id": c.pk,
                            "status": c.status,
                            "created_at": c.created_at,
                            "values": json.loads(c.payload).get("fields", {}),
                            "remove": json.loads(c.payload).get("remove", False),
                            "note": c.note,
                        }
                        for c in row.corrections.all()
                    ],
                }
            )
        out.append(
            {
                "id": run.pk,
                "document_id": run.document_id,
                "filename": run.document.original_filename,
                "status": run.status,
                "error_code": run.error_code,
                "flags": run.flags,
                "language": run.language,
                "quality_score": run.quality_score,
                "page_count": run.page_count,
                "attempts": run.attempts,
                "finished_at": run.finished_at,
                "set_aside": set_aside,
                "claims": claims,
            }
        )
    return {
        "application_id": app.pk,
        "status": app.status,
        "flags": list(app.flags or []),
        "manual_review_requested": not runs and objected(app),
        "can_retry": can_retry(app, runs),
        "runs": out,
    }


def can_retry(app: Application, runs: list[ExtractionRun]) -> bool:
    if app.status == Status.PROCESSING_ERROR:
        return True
    return app.status == Status.PROCESSING and any(r.status == RunStatus.FAILED for r in runs)


def retry(membership: Any, actor: Any, application_id: Any) -> dict[str, Any]:
    from . import services

    app = _visible(membership, application_id)
    runs = list(
        ExtractionRun.objects.for_org(app.organisation_id).filter(
            application=app, engine_version=ENGINE_VERSION
        )
    )
    if not can_retry(app, runs):
        raise ConflictError(
            code="conflict.nothing_to_retry",
            message="This application is not waiting on a failed CV read.",
        )
    services.retry(app, actor=actor)
    return hr_view(membership, application_id)
