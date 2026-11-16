"""Human verification of extracted claims (P07-T11).

HR confirms, corrects or rejects a claim. The original claim is never changed: the verdict is
stored as a ``HumanVerification`` and applied when the evaluation input is built (a confirmed or
corrected claim carries ``method=human`` so the criteria it supports become ``human_verified``;
a rejected one is no longer used). Re-evaluation is optional - HR may verify several claims and
re-evaluate once.
"""

from __future__ import annotations

import json
from functools import partial
from typing import Any

from django.db import transaction

from ai_engine.contracts import ExtractedClaim
from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now
from apps.resumes.models import ExtractedClaim as ClaimRow

from .models import HumanVerification, Trigger

LOCKED = {"type"}


def _claim(membership: Any, claim_id: Any) -> ClaimRow:
    from apps.applications.ats import _visible

    row = (
        ClaimRow.objects.for_org(membership.organisation_id)
        .select_related("run__application")
        .filter(pk=claim_id)
        .first()
    )
    if row is None:
        raise NotFoundError()
    _visible(membership, row.run.application_id)  # 404 when the member cannot see it
    if row.claim_type in ("contact", "protected") or row.excluded_reason:
        raise NotFoundError()  # set-aside claims are never shown nor verified
    return row


def _validated(row: ClaimRow, values: dict[str, Any]) -> str:
    if not values:
        raise DomainError(
            "validation_error", "Give the corrected values.", details={"values": ["Required."]}
        )
    claim = ExtractedClaim.model_validate_json(row.payload)
    data = claim.data.model_dump(mode="json")
    unknown = sorted(k for k in values if k not in data or k in LOCKED)
    if unknown:
        raise DomainError(
            "validation_error",
            "These fields cannot be corrected.",
            details={"values": [f"Unknown field: {k}" for k in unknown]},
        )
    try:
        type(claim.data).model_validate(data | values)
    except ValueError as exc:
        raise DomainError(
            "validation_error",
            "The corrected values are not valid.",
            details={"values": [str(exc)[:300]]},
        ) from exc
    return json.dumps(values, sort_keys=True)


def verify(
    membership: Any,
    actor: Any,
    claim_id: Any,
    *,
    decision: str,
    values: dict[str, Any] | None = None,
    note: str = "",
    reevaluate: bool = False,
    criterion_result_id: Any = None,
) -> HumanVerification:
    row = _claim(membership, claim_id)
    payload = ""
    if decision == HumanVerification.Decision.CORRECTED:
        payload = _validated(row, values or {})
    if decision == HumanVerification.Decision.REJECTED and len(note.strip()) < 3:
        raise DomainError(
            "validation_error",
            "Say why the claim is not supported.",
            details={"note": ["Required when rejecting a claim."]},
        )
    from .models import CriterionResult

    result = None
    if criterion_result_id is not None:
        result = (
            CriterionResult.objects.for_org(row.organisation_id)
            .filter(pk=criterion_result_id, evaluation__application_id=row.run.application_id)
            .first()
        )
    with transaction.atomic():
        verdict = HumanVerification.objects.create(
            organisation_id=row.organisation_id,
            application_id=row.run.application_id,
            claim=row,
            criterion_result=result,
            verifier=actor,
            decision=decision,
            corrected_payload=payload,
            note=note.strip()[:2000],
            at=now(),
        )
        audit.record(
            actor=actor,
            action="screening.claim_verified",
            target=verdict,
            organisation=row.organisation_id,
            after={"decision": decision, "claim_id": str(row.pk), "fields": sorted(values or {})},
        )
        from .quality import capture_verification

        capture_verification(verdict, job_id=row.run.application.job_id)
        if reevaluate:
            from .tasks import evaluate_application

            transaction.on_commit(
                partial(
                    evaluate_application.delay,
                    str(row.run.application_id),
                    Trigger.VERIFICATION,
                    None,
                    "Claim verified by HR",
                )
            )
    return verdict


def verifications_for(membership: Any, application_id: Any) -> list[HumanVerification]:
    from apps.applications.ats import _visible

    app = _visible(membership, application_id)
    return list(
        HumanVerification.objects.for_org(app.organisation_id)
        .filter(application=app)
        .select_related("verifier")
    )
