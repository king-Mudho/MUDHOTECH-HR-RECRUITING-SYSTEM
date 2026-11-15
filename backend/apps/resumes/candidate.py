"""Candidate-facing extraction features (P06-T13, EC-DOC-27).

* "What we extracted from your CV": a preview parse of the candidate's own CV, on request.
* Import to profile: copies chosen items into the profile only after explicit confirmation.
* Corrections: on a submitted application's claims; the original claim is kept, the correction is
  stored next to it and ``application.evidence_corrected`` asks screening to re-evaluate.
"""

from __future__ import annotations

import json
from datetime import date
from functools import partial
from typing import Any

from django.db import IntegrityError, transaction
from pydantic import TypeAdapter

from ai_engine import ENGINE_VERSION
from ai_engine.contracts import ClaimData, ExtractedClaim, PartialDate
from apps.audit import services as audit
from apps.core import outbox, storage
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now
from apps.documents.models import Document, ScanStatus

from . import engine
from .models import (
    ClaimCorrection,
    ExtractionRun,
    ResumeParse,
    RunStatus,
)
from .models import (
    ExtractedClaim as ClaimRow,
)

ACCEPTED = (ScanStatus.CLEAN, ScanStatus.SKIPPED)
CORRECTABLE = {"experience", "education", "certification", "skill", "language"}
CORRECTION_FIELDS = {
    "experience": {"title", "employer", "location", "start", "end", "is_current"},
    "education": {"qualification_text", "institution", "year", "grade"},
    "certification": {"name", "body", "issued"},
    "skill": {"name", "years"},
    "language": {"language", "level"},
}
PROTECTED_LABELS = {
    "date_of_birth": "date of birth",
    "age": "age",
    "national_id": "national ID number",
    "passport": "passport number",
    "gender": "gender",
    "marital_status": "marital status",
    "children": "number of children",
    "religion": "religion",
    "ethnicity": "tribe or ethnicity",
    "nationality": "nationality",
    "health": "health or disability information",
    "political": "political affiliation",
    "home_address": "home address",
}
_claims_adapter = TypeAdapter(list[ExtractedClaim])
_data_adapter: TypeAdapter[ClaimData] = TypeAdapter(ClaimData)


# --------------------------------------------------------------------------------- display
def _month(d: PartialDate | None) -> str:
    if d is None:
        return ""
    return f"{d.year}-{d.month:02d}" if d.month else str(d.year)


def display(claim: ExtractedClaim) -> dict[str, Any]:
    """A plain, candidate-safe summary of one claim (no scores, no internal confidence)."""
    data: Any = claim.data
    out: dict[str, Any] = {
        "type": data.type,
        "title": "",
        "subtitle": "",
        "dates": "",
        "detail": "",
        "snippet": claim.source.snippet,
        "page": claim.source.page,
        "excluded": claim.excluded_reason is not None,
        "excluded_reason": claim.excluded_reason.value if claim.excluded_reason else "",
    }
    if data.type == "experience":
        start, end = _month(data.dates.start), _month(data.dates.end)
        out |= {
            "title": data.title,
            "subtitle": data.employer,
            "dates": f"{start} - {'present' if data.dates.is_current else end}".strip(" -"),
            "detail": data.employment_kind.value.replace("_", " "),
        }
    elif data.type == "education":
        out |= {
            "title": data.qualification_text,
            "subtitle": data.institution,
            "dates": _month(data.dates.end) or _month(data.dates.start),
            "detail": data.grade,
        }
    elif data.type == "certification":
        out |= {"title": data.name, "subtitle": data.body, "dates": _month(data.issued)}
    elif data.type == "skill":
        out |= {
            "title": data.canonical or data.raw,
            "detail": f"{data.years:g} years" if data.years else "",
        }
    elif data.type == "language":
        out |= {"title": data.language, "detail": data.level}
    elif data.type == "project":
        out |= {"title": data.title, "detail": ", ".join(data.technologies)}
    elif data.type == "summary":
        out |= {"title": "Profile", "detail": data.text[:400]}
    elif data.type == "protected":
        out |= {"title": PROTECTED_LABELS.get(data.attribute, data.attribute), "snippet": ""}
    elif data.type == "contact":
        out |= {"title": "Contact details", "snippet": ""}
    return out


def _load(payload: str) -> list[ExtractedClaim]:
    return _claims_adapter.validate_json(payload) if payload else []


# ---------------------------------------------------------------------------------- preview
def own_cv(user: Any, document_id: Any) -> Document:
    doc = Document.objects.filter(
        pk=document_id, owner_user=user, purpose="cv", deleted_at__isnull=True
    ).first()
    if doc is None:
        raise NotFoundError()
    return doc


def preview(user: Any, document_id: Any) -> ResumeParse:
    """The candidate's parse of their CV; queued on first request (or after a failure)."""
    from .tasks import parse_resume_preview

    doc = own_cv(user, document_id)
    if doc.scan_status not in ACCEPTED:
        raise DomainError(
            "validation_error",
            "This file is still being checked or was not accepted.",
            status_code=409,
            details={"scan_status": doc.scan_status},
        )
    with transaction.atomic():
        try:
            with transaction.atomic():
                parse, created = ResumeParse.objects.get_or_create(
                    document=doc, engine_version=ENGINE_VERSION, defaults={"owner_user": user}
                )
        except IntegrityError:
            parse, created = (
                ResumeParse.objects.get(document=doc, engine_version=ENGINE_VERSION),
                False,
            )
        if created or parse.status == RunStatus.FAILED:
            if parse.status == RunStatus.FAILED:
                parse.status, parse.error_code = RunStatus.PENDING, ""
                parse.save(update_fields=["status", "error_code", "updated_at"])
            transaction.on_commit(partial(parse_resume_preview.delay, str(parse.pk)))
    return parse


def run_preview(parse_id: Any) -> str:
    with transaction.atomic():
        parse = ResumeParse.objects.select_for_update().filter(pk=parse_id).first()
        if parse is None or parse.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL):
            return parse.status if parse else "missing"
        parse.status = RunStatus.RUNNING
        parse.save(update_fields=["status", "updated_at"])
        doc = parse.document
    try:
        data = storage.get_bytes(doc.bucket, doc.storage_key)
    except Exception:
        ResumeParse.objects.filter(pk=parse_id).update(
            status=RunStatus.FAILED, error_code="storage_unavailable"
        )
        raise
    result, _ = engine.run(data, document_id=str(doc.pk), organisation_id=None, today=now().date())
    ResumeParse.objects.filter(pk=parse_id).update(
        status=result.status.value,
        error_code=result.error_code or "",
        flags=sorted(f.value for f in result.flags),
        claims=json.dumps([c.model_dump(mode="json") for c in result.claims]),
        updated_at=now(),
    )
    return result.status.value


def preview_view(parse: ResumeParse) -> dict[str, Any]:
    claims = _load(parse.claims) if parse.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL) else []
    return {
        "document_id": parse.document_id,
        "status": parse.status,
        "error_code": parse.error_code,
        "flags": parse.flags,
        "imported_at": parse.imported_at,
        "claims": [
            {"index": i, **display(c)} for i, c in enumerate(claims) if c.data.type != "contact"
        ],
    }


# --------------------------------------------------------------------------- import to profile
def _date(d: PartialDate | None, *, end: bool = False) -> date | None:
    if d is None:
        return None
    return date(d.year, d.month or (12 if end else 1), 1)


@transaction.atomic
def import_to_profile(user: Any, document_id: Any, indexes: list[int]) -> dict[str, int]:
    """Copy the chosen claims into the profile (source=cv_import). Duplicates are skipped."""
    from apps.candidates import models as cm
    from apps.candidates.services import get_or_create_profile, recompute_completeness
    from apps.taxonomy.models import Skill

    doc = own_cv(user, document_id)
    parse = (
        ResumeParse.objects.select_for_update()
        .filter(document=doc, engine_version=ENGINE_VERSION)
        .first()
    )
    if parse is None or parse.status not in (RunStatus.SUCCEEDED, RunStatus.PARTIAL):
        raise DomainError("conflict", "The CV has not been read yet.", status_code=409)
    claims = _load(parse.claims)
    chosen = sorted({i for i in indexes if 0 <= i < len(claims)})
    if not chosen:
        raise DomainError(
            "validation_error", "Choose at least one item.", details={"indexes": ["Required."]}
        )
    profile = get_or_create_profile(user)
    src = cm.Source.CV_IMPORT
    added = {"experiences": 0, "educations": 0, "certifications": 0, "skills": 0, "languages": 0}
    skipped = 0
    for i in chosen:
        claim = claims[i]
        data: Any = claim.data
        if not claim.evaluable:
            skipped += 1
            continue
        if data.type == "experience":
            start = _date(data.dates.start)
            if start is None or not data.title or not data.employer:
                skipped += 1  # a role needs a start date, title and employer in the profile
                continue
            if cm.Experience.objects.filter(
                profile=profile, employer__iexact=data.employer, title__iexact=data.title
            ).exists():
                skipped += 1
                continue
            cm.Experience.objects.create(
                profile=profile,
                source=src,
                employer=data.employer[:200],
                title=data.title[:200],
                location=data.location[:150],
                start_date=start,
                end_date=None if data.dates.is_current else _date(data.dates.end, end=True),
                is_current=data.dates.is_current,
                description="\n".join(data.responsibilities)[:4000],
            )
            added["experiences"] += 1
        elif data.type == "education":
            if cm.Education.objects.filter(
                profile=profile, qualification_text__iexact=data.qualification_text
            ).exists():
                skipped += 1
                continue
            cm.Education.objects.create(
                profile=profile,
                source=src,
                institution=(data.institution or "-")[:200],
                qualification_text=data.qualification_text[:200],
                field=data.field[:150],
                end_date=_date(data.dates.end, end=True),
                grade=data.grade[:60],
            )
            added["educations"] += 1
        elif data.type == "certification":
            if cm.Certification.objects.filter(profile=profile, name__iexact=data.name).exists():
                skipped += 1
                continue
            cm.Certification.objects.create(
                profile=profile, source=src, name=data.name[:200], issued_at=_date(data.issued)
            )
            added["certifications"] += 1
        elif data.type == "skill":
            name = (data.canonical or data.raw)[:150]
            skill = (
                Skill.objects.filter(pk=data.skill_id, organisation__isnull=True).first()
                if data.skill_id
                else None
            )
            exists = cm.CandidateSkill.objects.filter(profile=profile, raw_name__iexact=name)
            if skill is not None:
                exists = exists | cm.CandidateSkill.objects.filter(profile=profile, skill=skill)
            if exists.exists():
                skipped += 1
                continue
            cm.CandidateSkill.objects.create(
                profile=profile,
                source=src,
                skill=skill,
                raw_name=name,
                years=data.years,
            )
            added["skills"] += 1
        elif data.type == "language":
            if cm.Language.objects.filter(profile=profile, language__iexact=data.language).exists():
                skipped += 1
                continue
            level = {
                "native": "native",
                "mother tongue": "native",
                "first language": "native",
                "fluent": "fluent",
                "proficient": "fluent",
                "advanced": "fluent",
                "intermediate": "conversational",
                "conversational": "conversational",
            }.get(data.level, "basic")
            cm.Language.objects.create(
                profile=profile, source=src, language=data.language[:60], proficiency=level
            )
            added["languages"] += 1
        else:
            skipped += 1
    parse.imported_at = now()
    parse.save(update_fields=["imported_at", "updated_at"])
    recompute_completeness(profile)
    audit.record(
        actor=user,
        action="candidates.profile_imported_from_cv",
        target=profile,
        after={**added, "skipped": skipped},
    )
    return {**added, "skipped": skipped}


# ------------------------------------------------------------------- application extraction
def application_view(user: Any, application_id: Any) -> dict[str, Any]:
    from apps.applications.models import Application

    app = Application.objects.unscoped().filter(pk=application_id, candidate_user=user).first()
    if app is None:
        raise NotFoundError()
    runs = list(
        ExtractionRun.objects.for_org(app.organisation_id)
        .filter(application=app, engine_version=ENGINE_VERSION)
        .select_related("document")
    )
    out_runs = []
    for run in runs:
        rows = list(
            ClaimRow.objects.for_org(app.organisation_id)
            .filter(run=run)
            .exclude(claim_type="contact")
            .prefetch_related("corrections")
        )
        claims = []
        for row in rows:
            claim = ExtractedClaim.model_validate_json(row.payload)
            corrections = [
                {
                    "id": c.pk,
                    "status": c.status,
                    "created_at": c.created_at,
                    "values": json.loads(c.payload).get("fields", {}),
                    "remove": json.loads(c.payload).get("remove", False),
                }
                for c in row.corrections.all()
                if c.corrected_by_id == user.pk
            ]
            claims.append(
                {
                    "id": row.pk,
                    "index": row.ordinal,
                    "correctable": row.claim_type in CORRECTABLE and row.evaluable,
                    "corrections": corrections,
                    **display(claim),
                }
            )
        out_runs.append(
            {
                "document_id": run.document_id,
                "filename": run.document.original_filename,
                "status": run.status,
                "error_code": run.error_code,
                "flags": run.flags,
                "claims": claims,
            }
        )
    return {"application_id": app.pk, "objected": not runs and _objected(app), "runs": out_runs}


def _objected(app: Any) -> bool:
    from .services import objected

    return objected(app)


@transaction.atomic
def correct(
    user: Any, claim_id: Any, *, fields: dict[str, Any], remove: bool, note: str
) -> ClaimCorrection:
    """Store a candidate's correction (EC-DOC-27): original kept, re-evaluation requested."""
    row = (
        ClaimRow.objects.unscoped()
        .select_related("run__application")
        .filter(pk=claim_id, run__application__candidate_user=user)
        .first()
    )
    if row is None:
        raise NotFoundError()
    if row.claim_type not in CORRECTABLE or not row.evaluable:
        raise DomainError(
            "validation_error",
            "This item can't be corrected.",
            details={"claim": ["Not correctable."]},
        )
    allowed = CORRECTION_FIELDS[row.claim_type]
    unknown = set(fields) - allowed
    if unknown:
        raise DomainError(
            "validation_error",
            "Unknown fields for this item.",
            details={k: ["Not allowed."] for k in sorted(unknown)},
        )
    if not remove and not any(str(v).strip() for v in fields.values()):
        raise DomainError(
            "validation_error",
            "Tell us what is wrong or what it should say.",
            details={"values": ["Required."]},
        )
    clean = {k: str(v).strip()[:300] for k, v in fields.items()}
    correction = ClaimCorrection.objects.create(
        organisation_id=row.organisation_id,
        claim=row,
        corrected_by=user,
        payload=json.dumps({"type": row.claim_type, "fields": clean, "remove": remove}),
        note=note.strip()[:1000],
    )
    app = row.run.application
    outbox.emit(
        "application.evidence_corrected",
        app,
        {
            "application_id": str(app.pk),
            "claim_id": str(row.pk),
            "correction_id": str(correction.pk),
        },
        dedupe_key=f"application.evidence_corrected:{correction.pk}",
        organisation_id=app.organisation_id,
    )
    audit.record(
        actor=user,
        action="resumes.claim_corrected",
        target=correction,
        organisation=row.organisation_id,
        after={"claim_type": row.claim_type, "fields": sorted(clean), "remove": remove},
    )
    return correction
